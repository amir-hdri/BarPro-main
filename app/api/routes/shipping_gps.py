"""API routes for GPS Shipping lifecycle — start, step, finish, simulate, status.

All operations use the **exact** addresses and coordinates the user entered
for each waybill, extracted from ``WaybillJob.payload_json``.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth_multitenant import get_current_user_or_admin
from app.automation.gps_shipping_manager import (
    extract_coordinates_from_payload,
    init_shipping,
    load_shipping_state,
    save_shipping_state,
)
from app.core.config import utcms_config
from app.core.security import require_sensitive_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shipping", tags=["shipping-gps"])


# ──────────────────── Request / Response Models ────────────────────


class ShippingStartRequest(BaseModel):
    job_id: str = Field(..., description="شناسه Job بارنامه")
    doc_no: str = Field(..., description="شماره سند بارنامه در UTCMS")
    latitude: float = Field(..., ge=-90, le=90, description="عرض جغرافیایی واقعی دستگاه")
    longitude: float = Field(..., ge=-180, le=180, description="طول جغرافیایی واقعی دستگاه")
    altitude: float = Field(default=0, ge=-500, le=10000)
    speed: float = Field(default=0, ge=0, le=400)


class ShippingStepRequest(BaseModel):
    job_id: str = Field(..., description="شناسه Job بارنامه")


class ShippingFinishRequest(BaseModel):
    job_id: str = Field(..., description="شناسه Job بارنامه")
    latitude: float = Field(..., ge=-90, le=90, description="عرض جغرافیایی واقعی دستگاه")
    longitude: float = Field(..., ge=-180, le=180, description="طول جغرافیایی واقعی دستگاه")
    altitude: float = Field(default=0, ge=-500, le=10000)
    speed: float = Field(default=0, ge=0, le=400)


class ShippingInfoRequest(BaseModel):
    job_id: str = Field(..., description="شناسه Job بارنامه")


class CoordinateInfoResponse(BaseModel):
    origin_lat: float | None = None
    origin_lng: float | None = None
    origin_address: str = ""
    origin_city: str = ""
    dest_lat: float | None = None
    dest_lng: float | None = None
    dest_address: str = ""
    dest_city: str = ""
    distance_km: float = 0.0
    direct_distance_km: float = 0.0
    duration_hours: float = 0.0
    duration_minutes: int = 0
    estimated_duration_text: str = ""


# ──────────────────── Helper ────────────────────


async def _get_job_and_driver(job_id: str, user_context: dict[str, Any]) -> tuple[dict[str, Any], Any | None]:
    """Load job payload and driver from the database."""
    from sqlmodel import select

    from app.core.database import async_session_factory
    from app.models_multitenant import Driver, WaybillJob

    async with async_session_factory() as session:
        query = select(WaybillJob).where(WaybillJob.job_id == job_id)
        if user_context.get("role") == "client":
            client = user_context.get("user")
            query = query.where(WaybillJob.client_id == int(client.id))
        result = await session.exec(query)
        job = result.first()
        if job is None:
            raise HTTPException(status_code=404, detail=f"بارنامه با شناسه {job_id} یافت نشد")
        driver = None
        if job.driver_id:
            driver = (await session.exec(select(Driver).where(Driver.id == job.driver_id))).first()
        return dict(job.payload_json or {}), driver


# ──────────────────── Endpoints ────────────────────


@router.post("/coordinates", response_model=CoordinateInfoResponse, dependencies=[Depends(require_sensitive_auth)])
async def get_job_coordinates(req: ShippingInfoRequest, user_context: dict[str, Any] = Depends(get_current_user_or_admin)):
    """استخراج مختصات و آدرس‌های دقیق از payload بارنامه — دقیقاً آدرسی که کاربر وارد کرده."""
    payload, _ = await _get_job_and_driver(req.job_id, user_context)
    info = extract_coordinates_from_payload(payload)
    return CoordinateInfoResponse(**info)


@router.post("/start", dependencies=[Depends(require_sensitive_auth)])
async def start_shipping(req: ShippingStartRequest, user_context: dict[str, Any] = Depends(get_current_user_or_admin)):
    """شروع حمل با GPS — ثبت مختصات مبدأ (آدرس دقیق کاربر) در سامانه UTCMS و ذخیره در سیستم."""
    if not utcms_config.ALLOW_LIVE_SUBMIT:
        raise HTTPException(status_code=409, detail="ثبت زنده GPS غیرفعال است")
    payload, driver = await _get_job_and_driver(req.job_id, user_context)
    existing = await load_shipping_state(req.job_id)
    if existing and existing.status in {"in_transit", "delivered"}:
        raise HTTPException(status_code=409, detail=f"حمل قبلاً در وضعیت {existing.status} ثبت شده است")
    try:
        state = await init_shipping(req.job_id, req.doc_no, payload, persist=False)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # Build the origin witness, but persist local state only after UTCMS confirms.
    wp = state.waypoints[0]
    state.gps_list.append({
        "Type": 1,
        "Longitude": req.longitude,
        "Latitude": req.latitude,
        "Altitude": req.altitude,
        "Speed": req.speed,
        "Date": wp["ts"],
    })
    if not driver or not driver.utcms_password_encrypted:
        raise HTTPException(status_code=409, detail="اعتبارنامه راننده برای GPS موجود نیست")
    utcms_result = None
    try:
        from app.auth_multitenant import decrypt_driver_password
        from app.automation.utcms_mobile_client import UtcmsMobileClient
        from app.automation.worker_proxy import get_worker_proxy_url
        pwd = decrypt_driver_password(driver.utcms_password_encrypted)
        client = UtcmsMobileClient(proxy_url=get_worker_proxy_url())
        auth = await client.auto_solve_captcha(form_id=1)
        cap_token = UtcmsMobileClient.cap_token_from_solution(auth)
        await client.login(driver.driver_national_code, pwd, cap_token=cap_token)
        utcms_result = await client.start_shipping_with_gps(
            doc_no=req.doc_no,
            lat=req.latitude, lon=req.longitude, alt=req.altitude, speed=req.speed,
            allow_live_submit=utcms_config.ALLOW_LIVE_SUBMIT,
        )
        if not isinstance(utcms_result, dict):
            raise RuntimeError("پاسخ شروع GPS نامعتبر است")
    except Exception as exc:
        logger.error("utcms_live_start_shipping_failed", exc_info=True)
        raise HTTPException(status_code=502, detail="UTCMS شروع حمل را تأیید نکرد") from exc

    state.status = "in_transit"
    state.current_step = 0
    await save_shipping_state(state)
    return {
        "status": "started",
        "message": f"حمل شروع شد از: {state.origin_address}",
        "origin": {"lat": state.origin_lat, "lng": state.origin_lng, "address": state.origin_address},
        "destination": {"lat": state.dest_lat, "lng": state.dest_lng, "address": state.dest_address},
        "distance_km": state.distance_km,
        "total_steps": state.total_steps,
        "waypoints": state.waypoints,
        "utcms_result": utcms_result,
    }


@router.post("/step", dependencies=[Depends(require_sensitive_auth)])
async def step_shipping(req: ShippingStepRequest, user_context: dict[str, Any] = Depends(get_current_user_or_admin)):
    """Intermediate GPS is intentionally disabled until a live UTCMS ping contract is proven."""
    await _get_job_and_driver(req.job_id, user_context)
    raise HTTPException(status_code=410, detail="ثبت نقطه میانی بدون GPS واقعی UTCMS مجاز نیست")


@router.post("/finish", dependencies=[Depends(require_sensitive_auth)])
async def finish_shipping(req: ShippingFinishRequest, user_context: dict[str, Any] = Depends(get_current_user_or_admin)):
    """پایان حمل با GPS — ثبت مختصات مقصد (آدرس دقیق کاربر) در سامانه UTCMS."""
    if not utcms_config.ALLOW_LIVE_SUBMIT:
        raise HTTPException(status_code=409, detail="ثبت زنده GPS غیرفعال است")
    state = await load_shipping_state(req.job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="ابتدا حمل را شروع کنید")
    if state.status in {"delivered", "finishing", "failed"}:
        raise HTTPException(status_code=409, detail=f"پایان حمل قابل تکرار نیست؛ وضعیت فعلی {state.status} است")

    # Add the operator's real destination point; no interpolated telemetry is
    # ever submitted to UTCMS.
    dest_wp = state.waypoints[-1]
    if not state.gps_list or state.gps_list[-1].get("Type") != 3:
        state.gps_list.append({
            "Type": 3,
            "Longitude": req.longitude,
            "Latitude": req.latitude,
            "Altitude": req.altitude,
            "Speed": req.speed,
            "Date": dest_wp["ts"],
        })

    # Fence the two UTCMS mutations.  A timeout after the first mutation must
    # never be retried as a fresh finish request.
    state.status = "finishing"
    await save_shipping_state(state)

    _, driver = await _get_job_and_driver(req.job_id, user_context)
    if not driver or not driver.utcms_password_encrypted:
        raise HTTPException(status_code=409, detail="اعتبارنامه راننده برای GPS موجود نیست")
    try:
        from app.auth_multitenant import decrypt_driver_password
        from app.automation.utcms_mobile_client import UtcmsMobileClient
        from app.automation.worker_proxy import get_worker_proxy_url
        pwd = decrypt_driver_password(driver.utcms_password_encrypted)
        client = UtcmsMobileClient(proxy_url=get_worker_proxy_url())
        solved = await client.auto_solve_captcha(form_id=1)
        cap_token = UtcmsMobileClient.cap_token_from_solution(solved)
        await client.login(driver.driver_national_code, pwd, cap_token=cap_token)
        finish_result = await client.finish_shipping_with_gps(
            doc_no=state.doc_no,
            lat=req.latitude,
            lon=req.longitude,
            alt=req.altitude,
            speed=req.speed,
            total_distance_km=state.distance_km,
            allow_live_submit=utcms_config.ALLOW_LIVE_SUBMIT,
        )
        history_result = await client.register_end_of_shipping(
            document_id=state.doc_no,
            gps_list=state.gps_list,
            allow_live_submit=utcms_config.ALLOW_LIVE_SUBMIT,
        )
        utcms_result = {"finish": finish_result, "history": history_result}
    except Exception as exc:
        logger.error("utcms_live_end_shipping_failed", exc_info=True)
        state.status = "failed"
        await save_shipping_state(state)
        raise HTTPException(status_code=502, detail="UTCMS پایان حمل را تأیید نکرد") from exc

    state.status = "delivered"
    state.current_step = len(state.waypoints) - 1
    state.traveled_km = state.distance_km
    await save_shipping_state(state)

    return {
        "status": "delivered",
        "message": f"حمل با موفقیت در مقصد تحویل شد: {state.dest_address}",
        "distance_km": state.distance_km,
        "gps_list": state.gps_list,
        "total_points": len(state.gps_list),
        "utcms_result": utcms_result,
    }


@router.get("/status/{job_id}", dependencies=[Depends(require_sensitive_auth)])
async def get_shipping_status(job_id: str, user_context: dict[str, Any] = Depends(get_current_user_or_admin)):
    """وضعیت فعلی حمل و نقاط GPS ثبت‌شده."""
    state = await load_shipping_state(job_id)
    if state is None:
        # Try to extract coordinate info from the job for pre-start display
        try:
            payload, _ = await _get_job_and_driver(job_id, user_context)
            info = extract_coordinates_from_payload(payload)
            duration_hours = round(info["distance_km"] / 65.0, 2)
            duration_minutes = int(round(duration_hours * 60))
            duration_text = f"{int(duration_hours)} ساعت و {duration_minutes % 60} دقیقه" if duration_hours >= 1 else f"{duration_minutes} دقیقه"
            return {
                "status": "not_started",
                "origin": {"lat": info["origin_lat"], "lng": info["origin_lng"], "address": info["origin_address"], "city": info["origin_city"]},
                "destination": {"lat": info["dest_lat"], "lng": info["dest_lng"], "address": info["dest_address"], "city": info["dest_city"]},
                "distance_km": info["distance_km"],
                "direct_distance_km": info.get("direct_distance_km", 0.0),
                "duration_hours": duration_hours,
                "duration_minutes": duration_minutes,
                "estimated_duration_text": duration_text,
                "waypoints": [],
                "gps_list": [],
                "current_step": 0,
                "total_steps": 0,
                "traveled_km": 0,
                "progress_pct": 0,
            }
        except Exception as exc:
            raise HTTPException(status_code=404, detail="اطلاعات حمل یافت نشد") from exc

    progress = round((state.traveled_km / max(state.distance_km, 0.01)) * 100, 1) if state.distance_km > 0 else 0
    duration_hours = round(state.distance_km / 65.0, 2)
    duration_minutes = int(round(duration_hours * 60))
    duration_text = f"{int(duration_hours)} ساعت و {duration_minutes % 60} دقیقه" if duration_hours >= 1 else f"{duration_minutes} دقیقه"
    remaining_km = round(state.distance_km - state.traveled_km, 2)
    remaining_hours = round(remaining_km / 65.0, 2)
    remaining_minutes = int(round(remaining_hours * 60))
    remaining_text = f"{int(remaining_hours)} ساعت و {remaining_minutes % 60} دقیقه" if remaining_hours >= 1 else f"{remaining_minutes} دقیقه"

    return {
        "status": state.status,
        "doc_no": state.doc_no,
        "origin": {"lat": state.origin_lat, "lng": state.origin_lng, "address": state.origin_address},
        "destination": {"lat": state.dest_lat, "lng": state.dest_lng, "address": state.dest_address},
        "distance_km": state.distance_km,
        "duration_hours": duration_hours,
        "duration_minutes": duration_minutes,
        "estimated_duration_text": duration_text,
        "traveled_km": state.traveled_km,
        "remaining_km": remaining_km,
        "remaining_duration_text": remaining_text,
        "progress_pct": progress,
        "current_step": state.current_step,
        "total_steps": state.total_steps,
        "waypoints": state.waypoints,
        "gps_list": state.gps_list,
    }
