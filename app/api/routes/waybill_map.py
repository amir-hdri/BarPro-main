"""مسیرهای API برای عملیات بارنامه مبتنی بر نقشه"""

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.auth_multitenant import _decode_jwt, get_current_user_or_admin
from app.automation.reporting import report_service
from app.automation.traffic_control import waybill_traffic_controller
from app.core.config import utcms_config
from app.core.security import _extract_bearer_token, _is_api_key_valid, require_sensitive_auth
from app.queue.queue_manager import queue_manager
from app.schemas.task import EnqueueWaybillResponse, QueueSnapshotResponse, WaybillTaskStatusResponse
from app.schemas.waybill import (
    CargoModel,
    FinancialModel,
    GeoCoordinateModel,
    LocationModel,
    OperationMode,
    ReceiverModel,
    SenderModel,
    ShippingOptionsModel,
    UTCMSLoginModel,
    VehicleModel,
    WaybillMapRequest,
)
from app.services.task_service import task_service
from app.services.waybill_service import waybill_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/waybill", tags=["waybill-map"])


def _extract_client_id_from_request(request: Request) -> int | None:
    # NOTE: The global API_KEY is an infrastructure credential (workers, health
    # probes). It must never silently attribute jobs to tenant 1. Callers that
    # only present the API_KEY get client_id=None here; queue_manager then
    # rejects the request in production (400) and falls back to tenant 1 in dev.
    api_key = request.headers.get(utcms_config.API_KEY_HEADER)
    if api_key and _is_api_key_valid(api_key):
        logger.warning("legacy_waybill_api_key_has_no_tenant_context")
        return None
    token = _extract_bearer_token(request.headers.get("Authorization")) or request.cookies.get(
        utcms_config.AUTH_COOKIE_NAME
    )
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


@router.post("/create-with-map", dependencies=[Depends(require_sensitive_auth)])
async def create_waybill_with_map(request: WaybillMapRequest):
    """ایجاد بارنامه با حالت safe/full."""
    return await waybill_service.create_waybill_with_map(request)


@router.post(
    "/queue/create-with-map",
    response_model=EnqueueWaybillResponse,
    dependencies=[Depends(require_sensitive_auth)],
)
async def enqueue_create_waybill_with_map(
    request: WaybillMapRequest,
    raw_request: Request,
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
):
    """ایجاد تسک صف برای ثبت بارنامه با idempotency."""
    dynamic_header_value = raw_request.headers.get(utcms_config.QUEUE_IDEMPOTENCY_HEADER)
    if dynamic_header_value is not None:
        dynamic_header_value = dynamic_header_value.strip() or None
    if idempotency_key is not None:
        idempotency_key = idempotency_key.strip() or None
    effective_idempotency_key = dynamic_header_value or idempotency_key
    client_id = _extract_client_id_from_request(raw_request)
    return await queue_manager.enqueue_waybill(
        request,
        client_id=client_id,
        idempotency_key=effective_idempotency_key,
    )


@router.get(
    "/tasks/{task_id}",
    response_model=WaybillTaskStatusResponse,
)
async def get_waybill_task_status(
    task_id: str,
    user_context: dict = Depends(get_current_user_or_admin),  # noqa: B008
):
    """وضعیت اجرای تسک صف.

    Tenant-isolation (GAP-3): clients may only read their own jobs
    (`job_*` IDs scoped by client_id); legacy queue task IDs are
    admin-only. Previously this endpoint used `require_sensitive_auth`
    alone, which carries no tenant identity.
    """
    role = user_context.get("role")
    if role == "master_admin":
        status = await queue_manager.get_task_status(task_id)
    else:
        client = user_context.get("user")
        client_id = getattr(client, "id", None)
        if client_id is None or not task_id.startswith("job_"):
            raise HTTPException(status_code=404, detail="task_id یافت نشد")
        status = await task_service.get_task_status(task_id, client_id=int(client_id))
    if not status:
        raise HTTPException(status_code=404, detail="task_id یافت نشد")
    return status


@router.get(
    "/queue/snapshot",
    response_model=QueueSnapshotResponse,
    dependencies=[Depends(require_sensitive_auth)],
)
async def get_queue_snapshot():
    """اسنپ‌شات صف توزیع‌شده."""
    return await queue_manager.snapshot()


@router.post("/detect-map", dependencies=[Depends(require_sensitive_auth)])
async def detect_map(session_id: str | None = None):
    """تشخیص وجود نقشه و نوع آن در صفحه."""
    return await waybill_service.detect_map(session_id=session_id)


@router.get("/traffic-status", dependencies=[Depends(require_sensitive_auth)])
async def get_traffic_status():
    """نمایش وضعیت صف و محدودسازی بار برای پایش عملیاتی."""
    snapshot = waybill_traffic_controller.snapshot()
    mode_counters = report_service.get_mode_counters()

    return {
        "active_requests": snapshot.active_requests,
        "queued_requests": snapshot.queued_requests,
        "next_allowed_in_seconds": round(snapshot.next_allowed_in_seconds, 2),
        "blocked_for_seconds": round(snapshot.blocked_for_seconds, 2),
        "max_concurrent": utcms_config.WAYBILL_MAX_CONCURRENT,
        "min_gap_seconds": utcms_config.WAYBILL_MIN_GAP_SECONDS,
        "active_by_mode": {
            "safe": snapshot.active_safe,
            "full": snapshot.active_full,
        },
        "queued_by_mode": {
            "safe": snapshot.queued_safe,
            "full": snapshot.queued_full,
        },
        "mode_counters": mode_counters,
    }


@router.post("/calculate-route", dependencies=[Depends(require_sensitive_auth)])
async def calculate_route(origin: GeoCoordinateModel, destination: GeoCoordinateModel):
    """محاسبه مسیر بین دو مختصات — از Route Authority واحد (Neshan یا fallback صریح)."""
    from app.services.route_authority import resolve_route

    snapshot = await resolve_route(origin.lat, origin.lng, destination.lat, destination.lng)
    return {
        "distance_km": snapshot["distance_km"],
        "duration_min": round(snapshot["duration_min"]),
        "duration_s": snapshot["duration_s"],
        "origin": origin.model_dump(),
        "destination": destination.model_dump(),
        "method": snapshot["source"],
        "source": snapshot["source"],
        "is_real_route": snapshot["is_real_route"],
        "polyline": snapshot["polyline"],
        "anchor_hash": snapshot["anchor_hash"],
    }


@router.get("/reverse-geocode", dependencies=[Depends(require_sensitive_auth)])
async def reverse_geocode(lat: float, lng: float):
    """تبدیل مختصات به آدرس (استان، شهر، منطقه)."""
    from app.services.location_service import location_service

    return await location_service.reverse_geocode(lat, lng)


__all__ = [
    "GeoCoordinateModel",
    "LocationModel",
    "SenderModel",
    "ReceiverModel",
    "UTCMSLoginModel",
    "CargoModel",
    "VehicleModel",
    "FinancialModel",
    "OperationMode",
    "ShippingOptionsModel",
    "WaybillMapRequest",
    "create_waybill_with_map",
    "enqueue_create_waybill_with_map",
    "get_waybill_task_status",
    "get_queue_snapshot",
    "detect_map",
    "get_traffic_status",
    "calculate_route",
]
