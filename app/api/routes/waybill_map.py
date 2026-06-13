"""مسیرهای API برای عملیات بارنامه مبتنی بر نقشه"""

import math

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.automation.reporting import report_service
from app.automation.traffic_control import waybill_traffic_controller
from app.core.config import utcms_config
from app.core.security import require_sensitive_auth
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
from app.services.waybill_service import waybill_service

router = APIRouter(prefix="/waybill", tags=["waybill-map"])


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
    return await queue_manager.enqueue_waybill(request, idempotency_key=effective_idempotency_key)


@router.get(
    "/tasks/{task_id}",
    response_model=WaybillTaskStatusResponse,
    dependencies=[Depends(require_sensitive_auth)],
)
async def get_waybill_task_status(task_id: str):
    """وضعیت اجرای تسک صف."""
    status = await queue_manager.get_task_status(task_id)
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


@router.post("/calculate-route")
async def calculate_route(origin: GeoCoordinateModel, destination: GeoCoordinateModel):
    """محاسبه مسیر بین دو مختصات جغرافیایی."""
    earth_radius_km = 6371

    lat1 = math.radians(origin.lat)
    lat2 = math.radians(destination.lat)
    dlat = math.radians(destination.lat - origin.lat)
    dlon = math.radians(destination.lng - origin.lng)

    a = (
        math.sin(dlat / 2) * math.sin(dlat / 2)
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) * math.sin(dlon / 2)
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = earth_radius_km * c

    duration_min = (distance / 60) * 60

    return {
        "distance_km": round(distance, 2),
        "duration_min": round(duration_min),
        "origin": origin.model_dump(),
        "destination": destination.model_dump(),
        "method": "haversine",
    }


@router.get("/reverse-geocode")
async def reverse_geocode(lat: float, lng: float):
    """تبدیل مختصات به آدرس (استان، شهر، منطقه)."""
    import aiohttp

    from app.automation.proxy_rotator import get_proxy_rotator

    url = "https://nominatim.openstreetmap.org/reverse"
    params = {
        "lat": lat,
        "lon": lng,
        "format": "json",
        "accept-language": "fa",
        "zoom": 10,
    }
    headers = {"User-Agent": "UTCMS-Automation/1.0"}

    data = None

    # 1. تلاش مستقیم
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
    except Exception:
        pass

    # 2. تلاش با پروکسی چرخشی در صورت شکست مستقیم
    if data is None:
        try:
            proxy_info = await get_proxy_rotator().get_next()
            if proxy_info and proxy_info.protocol in ("http", "https"):
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url,
                        params=params,
                        headers=headers,
                        proxy=proxy_info.full_url,
                        timeout=5
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
        except Exception:
            pass

    if data:
        address = data.get("address", {})
        return {
            "success": True,
            "province": (
                address.get("state") or
                address.get("province") or
                address.get("county") or
                ""
            ),
            "city": (
                address.get("city") or
                address.get("town") or
                address.get("village") or
                ""
            ),
            "district": (
                address.get("suburb") or
                address.get("district") or
                address.get("neighbourhood") or
                ""
            ),
            "display_name": data.get("display_name", ""),
        }

    return {
        "success": False,
        "error": "Failed to resolve geocode coordinates",
        "province": "",
        "city": "",
        "district": "",
    }


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
