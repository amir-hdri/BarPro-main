"""مسیرهای API برای وب‌سرویس‌های ITMB."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import utcms_config
from app.core.security import require_sensitive_auth
from app.schemas.itmb_ws import (
    WS01InsertBOLRequest,
    WS01InsertBOLResponse,
    WS03StartBOLRequest,
    WS03StartBOLResponse,
    WS04EndBOLRequest,
    WS04EndBOLResponse,
    WS06InsertBOLTrackRequest,
    WS06InsertBOLTrackResponse,
)
from app.services.itmb_baseinfo_service import itmb_baseinfo_service
from app.services.itmb_ws_service import itmb_ws_service

router = APIRouter(prefix="/waybill", tags=["itmb-ws"])


class BaseInfoRefreshRequest(BaseModel):
    CompanyCode: str | None = None
    ServicePassword: str | None = None


@router.post(
    "/ws01-insert-bol",
    response_model=WS01InsertBOLResponse,
    dependencies=[Depends(require_sensitive_auth)],
)
async def ws01_insert_bol(request: WS01InsertBOLRequest):
    """ثبت بارنامه در وب‌سرویس ITMB بر اساس WS01_InsertBOL."""
    return await itmb_ws_service.insert_bol(request)


@router.post(
    "/ws03-start-bol",
    response_model=WS03StartBOLResponse,
    dependencies=[Depends(require_sensitive_auth)],
)
async def ws03_start_bol(request: WS03StartBOLRequest):
    """آغاز سفر بارنامه در وب‌سرویس ITMB بر اساس WS03_StartBOL."""
    return await itmb_ws_service.start_bol(request)


@router.post(
    "/ws04-end-bol",
    response_model=WS04EndBOLResponse,
    dependencies=[Depends(require_sensitive_auth)],
)
async def ws04_end_bol(request: WS04EndBOLRequest):
    """پایان سفر بارنامه در وب‌سرویس ITMB بر اساس WS04_EndBOL."""
    return await itmb_ws_service.end_bol(request)


@router.post(
    "/ws06-insert-bol-track",
    response_model=WS06InsertBOLTrackResponse,
    dependencies=[Depends(require_sensitive_auth)],
)
async def ws06_insert_bol_track(request: WS06InsertBOLTrackRequest):
    """ثبت موقعیت و نقاط پیمایش بارنامه در وب‌سرویس ITMB بر اساس WS06_InsertBOLTrack."""
    return await itmb_ws_service.insert_bol_track(request)


@router.get("/baseinfo/status", dependencies=[Depends(require_sensitive_auth)])
async def baseinfo_status():
    """نمایش وضعیت کش BaseInfo."""
    return {
        "status": "ok",
        "meta": {
            "cache_ttl_seconds": utcms_config.ITMBOL_BASEINFO_CACHE_TTL_SECONDS,
            "validation_enabled": utcms_config.ITMBOL_VALIDATE_BASEINFO,
            "live_probe_enabled": utcms_config.ITMBOL_READYZ_LIVE_CHECK,
        },
        "items": itmb_baseinfo_service.status(),
    }


@router.post("/baseinfo/refresh", dependencies=[Depends(require_sensitive_auth)])
async def baseinfo_refresh(request: BaseInfoRefreshRequest):
    """بروزرسانی دستی کش BaseInfo."""
    return await itmb_baseinfo_service.refresh_all(
        company_code=request.CompanyCode,
        service_password=request.ServicePassword,
    )


__all__ = [
    "ws01_insert_bol",
    "ws03_start_bol",
    "ws04_end_bol",
    "ws06_insert_bol_track",
    "baseinfo_status",
    "baseinfo_refresh",
]
