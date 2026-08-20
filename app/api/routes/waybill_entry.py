"""API routes for manual waybill entry and Excel file upload."""

import io
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.auth_multitenant import _decode_jwt
from app.core.config import utcms_config
from app.core.security import _extract_bearer_token, _is_api_key_valid, require_sensitive_auth
from app.schemas.waybill import OperationMode, WaybillMapRequest
from app.services.excel_template_service import ExcelTemplateService
from app.services.waybill_entry_service import excel_waybill_service, manual_waybill_service

router = APIRouter(prefix="/waybill", tags=["waybill-entry"])
logger = logging.getLogger(__name__)


def _extract_client_id_from_request(request: Request) -> int | None:
    api_key = request.headers.get(utcms_config.API_KEY_HEADER)
    if api_key and _is_api_key_valid(api_key):
        return 1
    token = _extract_bearer_token(request.headers.get("Authorization")) or request.cookies.get("utcms_auth_token")
    if token:
        try:
            payload = _decode_jwt(token)
            if payload.get("role") == "client":
                raw_id = payload.get("sub")
                if raw_id is not None:
                    return int(str(raw_id))
            elif payload.get("role") == "master_admin":
                return 1
        except Exception:
            pass
    return None


@router.post(
    "/validate-manual-entry",
    dependencies=[Depends(require_sensitive_auth)],
)
async def validate_manual_entry(request: WaybillMapRequest):
    """اعتبارسنجی ورودی دستی بارنامه قبل از ارسال."""
    validation = manual_waybill_service.validate_manual_entry(request)
    return {
        "valid": validation["valid"],
        "errors": validation["errors"],
        "warnings": validation["warnings"],
        "field_count": validation["field_count"],
        "completed_fields": validation["completed_fields"],
        "completion_percent": (
            round(validation["completed_fields"] / validation["field_count"] * 100, 1)
            if validation["field_count"] > 0
            else 0
        ),
    }


@router.post(
    "/submit-manual-waybill",
    dependencies=[Depends(require_sensitive_auth)],
)
async def submit_manual_waybill(request: WaybillMapRequest, raw_request: Request):
    """ارسال دستی بارنامه با اعتبارسنجی اولیه و قرارگیری در صف برای اجرا."""
    from app.queue.queue_manager import queue_manager

    # Validate first
    validation = manual_waybill_service.validate_manual_entry(request)
    if not validation["valid"]:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "VALIDATION_FAILED",
                "message": "اطلاعات وارد شده نامعتبر است",
                "errors": validation["errors"],
                "warnings": validation["warnings"],
            },
        )

    # Enqueue via queue manager
    try:
        client_id = _extract_client_id_from_request(raw_request)
        task = await queue_manager.enqueue_waybill(request, client_id=client_id)
        return {
            "success": True,
            "message": "بارنامه با موفقیت در صف ثبت قرار گرفت",
            "result": task.model_dump(),
        }
    except HTTPException as exc:
        raise exc
    except Exception as exc:
        logger.exception("manual_waybill_submit_failed")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "SUBMISSION_FAILED",
                "message": "خطا در قرارگیری بارنامه در صف",
                "detail": str(exc),
            },
        ) from exc


@router.post(
    "/parse-excel",
    dependencies=[Depends(require_sensitive_auth)],
)
async def parse_excel_file(
    file: UploadFile = File(..., description="فایل اکسل حاوی اطلاعات بارنامه"),
    operation_mode: OperationMode = Form(default=OperationMode.SAFE),
):
    """پردازش فایل اکسل و نمایش اطلاعات بارنامه‌ها."""
    # Validate file type
    if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_FILE_TYPE",
                "message": "فایل باید با فرمت اکسل (xlsx/xls) باشد",
            },
        )

    # Validate file size (max 10MB)
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "FILE_TOO_LARGE",
                "message": "حجم فایل نباید بیشتر از 10 مگابایت باشد",
            },
        )

    # Reset file pointer
    await file.seek(0)

    # Parse Excel
    result = await excel_waybill_service.parse_excel_file(file, operation_mode)

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "EXCEL_PARSE_FAILED",
                "message": result.get("error", "خطا در پردازش فایل اکسل"),
            },
        )

    return {
        "success": True,
        "file_name": result["file_name"],
        "total_rows": result["total_rows"],
        "valid_waybills": result["valid_waybills"],
        "errors": result["errors"],
        "waybills_preview": [
            {
                "row": item["row"],
                "sender": item["waybill"].sender.name,
                "receiver": item["waybill"].receiver.name,
                "origin": f"{item['waybill'].origin.city}, {item['waybill'].origin.province}",
                "destination": f"{item['waybill'].destination.city}, {item['waybill'].destination.province}",
                "cargo_weight": item["waybill"].cargo.weight,
                "validation": item["validation"],
            }
            for item in result["waybills"][:10]  # Show first 10 as preview
        ],
        "error_details": result.get("error_details", [])[:10],
    }


@router.post(
    "/submit-excel-waybills",
    dependencies=[Depends(require_sensitive_auth)],
)
async def submit_excel_waybills(
    file: UploadFile = File(..., description="فایل اکسل حاوی اطلاعات بارنامه"),
    operation_mode: OperationMode = Form(default=OperationMode.SAFE),
    skip_invalid: bool = Form(default=True, description="رد کردن موارد نامعتبر"),
):
    """پردازش و ارسال گروهی بارنامه‌ها از فایل اکسل."""
    # Validate file type
    if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_FILE_TYPE",
                "message": "فایل باید با فرمت اکسل (xlsx/xls) باشد",
            },
        )

    # Process Excel file
    result = await excel_waybill_service.process_excel_waybills(file, operation_mode, skip_invalid)

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "EXCEL_PROCESS_FAILED",
                "message": result.get("error", "خطا در پردازش فایل اکسل"),
            },
        )

    return {
        "success": True,
        "message": f"پردازش {result['total_processed']} بارنامه انجام شد",
        "file_name": result["file_name"],
        "total_processed": result["total_processed"],
        "success_count": result["success_count"],
        "error_count": result["error_count"],
        "results": result["results"],
    }


@router.post(
    "/queue-excel-waybills",
    dependencies=[Depends(require_sensitive_auth)],
)
async def queue_excel_waybills(
    raw_request: Request,
    file: UploadFile = File(..., description="فایل اکسل حاوی اطلاعات بارنامه"),
    operation_mode: OperationMode = Form(default=OperationMode.SAFE),
    skip_invalid: bool = Form(default=True, description="رد کردن موارد نامعتبر"),
):
    """پردازش و افزودن گروهی بارنامه‌ها به صف."""
    from app.queue.queue_manager import queue_manager

    # Validate file type
    if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_FILE_TYPE",
                "message": "فایل باید با فرمت اکسل (xlsx/xls) باشد",
            },
        )

    # Parse Excel first
    parse_result = await excel_waybill_service.parse_excel_file(file, operation_mode)

    if not parse_result["success"]:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "EXCEL_PARSE_FAILED",
                "message": parse_result.get("error", "خطا در پردازش فایل اکسل"),
            },
        )

    # Queue each valid waybill
    queued = []
    errors = []
    client_id = _extract_client_id_from_request(raw_request)

    for item in parse_result["waybills"]:
        try:
            waybill = item["waybill"]

            # Enqueue
            task = await queue_manager.enqueue_waybill(waybill, client_id=client_id)
            queued.append(
                {
                    "row": item["row"],
                    "task_id": task.task_id,
                    "status": "queued",
                }
            )
        except Exception as exc:
            errors.append(
                {
                    "row": item["row"],
                    "error": str(exc),
                }
            )

    return {
        "success": True,
        "message": f"{len(queued)} بارنامه به صف اضافه شد",
        "file_name": parse_result["file_name"],
        "total_parsed": parse_result["total_rows"],
        "queued_count": len(queued),
        "error_count": len(errors),
        "queued_tasks": queued,
        "errors": errors,
    }


@router.get("/excel-template", tags=["templates"], dependencies=[Depends(require_sensitive_auth)])
async def download_excel_template():
    """دانلود قالب اکسل برای ورود اطلاعات بارنامه."""
    content = ExcelTemplateService.generate_waybill_template()
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=waybill_template.xlsx"},
    )
