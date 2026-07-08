from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.core.security import require_sensitive_auth
from app.schemas.management import (
    ManagedAccountUpsertRequest,
    ManagedCustomerUpsertRequest,
    ManagedQueueCreateRequest,
    ManagedQueueDispatchRequest,
    ManagedRouteUpsertRequest,
    ManagementBootstrapRequest,
    ManagementExcelImportOptions,
)
from app.services.management_service import management_service

router = APIRouter(prefix="/management", tags=["management"])


@router.get("/summary", response_model=dict, dependencies=[Depends(require_sensitive_auth)])
async def get_summary():
    return await management_service.summary()


@router.get("/diagnostics", response_model=dict, dependencies=[Depends(require_sensitive_auth)])
async def get_diagnostics():
    return await management_service.diagnostics()


@router.get("/operator/dashboard", response_model=dict, dependencies=[Depends(require_sensitive_auth)])
async def operator_dashboard():
    return await management_service.operator_dashboard()


@router.get("/operator/tasks", response_model=list, dependencies=[Depends(require_sensitive_auth)])
async def operator_tasks(limit: int = 50):
    return await management_service.operator_tasks(limit=limit)


@router.get("/operator/artifacts/{task_id}", response_model=dict, dependencies=[Depends(require_sensitive_auth)])
async def operator_artifacts(task_id: str):
    return await management_service.operator_artifacts(task_id)


@router.get("/operator/artifact-content", response_model=dict, dependencies=[Depends(require_sensitive_auth)])
async def operator_artifact_content(path: str):
    return await management_service.read_artifact_content(path)


@router.post("/bootstrap/local", response_model=dict, dependencies=[Depends(require_sensitive_auth)])
async def bootstrap_local(request: ManagementBootstrapRequest):
    return await management_service.bootstrap_local_scenario(request)


@router.get("/customers", response_model=list, dependencies=[Depends(require_sensitive_auth)])
async def list_customers():
    return await management_service.list_customers()


@router.post("/customers", response_model=dict, dependencies=[Depends(require_sensitive_auth)])
async def upsert_customer(request: ManagedCustomerUpsertRequest):
    return await management_service.upsert_customer(request)


@router.get("/routes", response_model=list, dependencies=[Depends(require_sensitive_auth)])
async def list_routes():
    return await management_service.list_routes()


@router.post("/routes", response_model=dict, dependencies=[Depends(require_sensitive_auth)])
async def upsert_route(request: ManagedRouteUpsertRequest):
    return await management_service.upsert_route(request)


@router.get("/accounts", response_model=list, dependencies=[Depends(require_sensitive_auth)])
async def list_accounts():
    return await management_service.list_accounts()


@router.post("/accounts", response_model=dict, dependencies=[Depends(require_sensitive_auth)])
async def upsert_account(request: ManagedAccountUpsertRequest):
    return await management_service.upsert_account(request)


@router.post(
    "/accounts/{account_external_name}/warm-session",
    response_model=dict,
    dependencies=[Depends(require_sensitive_auth)],
)
async def warm_account_session(account_external_name: str):
    return await management_service.warm_account_session(account_external_name)


@router.get("/queue", response_model=list, dependencies=[Depends(require_sensitive_auth)])
async def list_queue():
    return await management_service.list_queue()


@router.post("/queue", response_model=dict, dependencies=[Depends(require_sensitive_auth)])
async def create_queue_item(request: ManagedQueueCreateRequest):
    return await management_service.create_queue_item(request)


@router.post("/queue/{queue_item_id}/dispatch", response_model=dict, dependencies=[Depends(require_sensitive_auth)])
async def dispatch_queue_item(queue_item_id: str, request: ManagedQueueDispatchRequest):
    return await management_service.dispatch_queue_item(queue_item_id, request)


@router.get("/sync/logs", response_model=list, dependencies=[Depends(require_sensitive_auth)])
async def sync_logs():
    return await management_service.get_sync_logs()


@router.post("/import/excel", dependencies=[Depends(require_sensitive_auth)])
async def import_excel(
    file: UploadFile = File(...),
    source_system: str = Form("local"),
    customer_external_key: str = Form("excel-import"),
    customer_name: str = Form("Excel Import"),
    bot_owner: str | None = Form(None),
    wallet: str | None = Form(None),
    driver_limit: int | None = Form(None),
    platform: str = Form("Barname"),
    operation_mode: str = Form("safe"),
    login_url: str = Form("https://barname.utcms.ir/Barname/Account/Login"),
    include_auth: bool = Form(True),
    create_queue: bool = Form(True),
    reverse_geo_enabled: bool = Form(False),
    default_province: str = Form("تهران"),
    default_city: str = Form("تهران"),
    priority: int = Form(100),
    time_interval: int | None = Form(None),
):
    content = await file.read()
    options = ManagementExcelImportOptions(
        source_system=source_system,
        customer_external_key=customer_external_key,
        customer_name=customer_name,
        bot_owner=bot_owner,
        wallet=wallet,
        driver_limit=driver_limit,
        platform=platform,
        operation_mode=operation_mode,
        login_url=login_url,
        include_auth=include_auth,
        create_queue=create_queue,
        reverse_geo_enabled=reverse_geo_enabled,
        default_province=default_province,
        default_city=default_city,
        priority=priority,
        time_interval=time_interval,
    )
    return await management_service.import_excel_workbook(content, file.filename or "upload.xlsx", options)
