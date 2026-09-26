"""Server-managed shipping lifecycle and GPS evidence routes.

The operator registers the waybill and route in BarPro; no driver Android
agent is required. Planned waypoints are display-only. Only route-anchor
coordinates explicitly supplied by the operator are eligible for UTCMS.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from functools import wraps
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth_multitenant import get_current_user_or_admin
from app.automation.gps_shipping_manager import (
    ShippingStatePersistenceError,
    extract_coordinates_from_payload,
    get_or_login_client,
    init_shipping,
    is_mobile_authentication_error,
    load_shipping_state,
    save_shipping_state,
)
from app.automation.utcms_mobile_client import require_successful_mutation
from app.automation.worker_proxy import ProxyUnavailableError, get_worker_proxy_url
from app.core.config import utcms_config
from app.core.security import require_sensitive_auth
from app.services.rpa_runtime_service import rpa_runtime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shipping", tags=["shipping-gps"])


# ──────────────────── Request / Response Models ────────────────────


class ShippingStartRequest(BaseModel):
    job_id: str = Field(..., description="شناسه Job بارنامه")
    doc_no: str = Field(..., description="شماره سند بارنامه در UTCMS")
    latitude: float = Field(..., ge=-90, le=90, description="عرض جغرافیایی مبدأ ثبت‌شده در بارنامه")
    longitude: float = Field(..., ge=-180, le=180, description="طول جغرافیایی مبدأ ثبت‌شده در بارنامه")
    altitude: float = Field(default=0, ge=-500, le=10000, description="ارتفاع ثبت‌شده؛ در نبود دستگاه صفر است")
    speed: float = Field(default=0, ge=0, le=400, description="سرعت ثبت‌شده؛ در نبود دستگاه صفر است")


class ShippingStepRequest(BaseModel):
    job_id: str = Field(..., description="شناسه Job بارنامه")


class ShippingFinishRequest(BaseModel):
    job_id: str = Field(..., description="شناسه Job بارنامه")
    latitude: float = Field(..., ge=-90, le=90, description="عرض جغرافیایی مقصد ثبت‌شده در بارنامه")
    longitude: float = Field(..., ge=-180, le=180, description="طول جغرافیایی مقصد ثبت‌شده در بارنامه")
    altitude: float = Field(default=0, ge=-500, le=10000, description="ارتفاع ثبت‌شده؛ در نبود دستگاه صفر است")
    speed: float = Field(default=0, ge=0, le=400, description="سرعت ثبت‌شده؛ در نبود دستگاه صفر است")
    measured_distance_km: float | None = Field(
        default=None,
        gt=0,
        le=1_000_000,
        description="مسافت اندازه‌گیری‌شده توسط دستگاه/اپ؛ مقدار تخمینی مسیر مجاز نیست",
    )


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


def _document_ids(job: Any, payload: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for value in (getattr(job, "document_id", None),):
        if value is not None and str(value).strip():
            ids.add(str(value).strip())
    for source in (getattr(job, "result_json", None), payload):
        stack = [source] if isinstance(source, dict) else []
        while stack:
            item = stack.pop()
            for key, value in item.items():
                if key.lower() in {"document_id", "documentid", "docid", "doc_no", "docno"}:
                    if value is not None and str(value).strip():
                        ids.add(str(value).strip())
                elif isinstance(value, dict):
                    stack.append(value)
                elif isinstance(value, list):
                    stack.extend(entry for entry in value if isinstance(entry, dict))
    return ids


async def _get_job_and_driver(
    job_id: str,
    user_context: dict[str, Any],
    *,
    expected_doc_no: str | None = None,
) -> tuple[dict[str, Any], Any | None]:
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
        payload = dict(job.payload_json or {})
        if expected_doc_no is not None:
            document_ids = _document_ids(job, payload)
            expected = str(expected_doc_no).strip()
            if len(document_ids) != 1 or expected not in document_ids:
                raise HTTPException(
                    status_code=409,
                    detail="شماره سند GPS با سند ثبت‌شده بارنامه تطبیق ندارد",
                )
        driver = None
        if job.driver_id:
            driver = (await session.exec(select(Driver).where(Driver.id == job.driver_id))).first()
        return payload, driver


async def _load_state_or_503(job_id: str):
    try:
        return await load_shipping_state(job_id)
    except ShippingStatePersistenceError as exc:
        logger.error("shipping_state_load_unavailable", exc_info=True)
        raise HTTPException(status_code=503, detail="ذخیره‌ساز وضعیت حمل در دسترس نیست") from exc


def _assert_route_anchor(
    *, latitude: float, longitude: float, expected_lat: float | None, expected_lng: float | None, label: str
) -> None:
    """Ensure an operator-submitted anchor belongs to the waybill route."""
    if expected_lat is None or expected_lng is None:
        raise HTTPException(status_code=422, detail=f"مختصات {label} در بارنامه ثبت نشده است")
    # Coordinates are serialized as decimals in several clients; allow only
    # harmless rounding while rejecting arbitrary locations.
    tolerance = 0.0002
    if abs(latitude - expected_lat) > tolerance or abs(longitude - expected_lng) > tolerance:
        raise HTTPException(status_code=422, detail=f"مختصات ارسالی با {label} بارنامه تطبیق ندارد")


def _shipping_mutation_lock(handler):
    @wraps(handler)
    async def wrapped(req, user_context):
        if not utcms_config.ALLOW_LIVE_SUBMIT:
            raise HTTPException(status_code=409, detail="ثبت زنده GPS غیرفعال است")
        key = f"lock:shipping:{req.job_id}"
        try:
            acquired = await rpa_runtime.acquire_lock(key, max(int(utcms_config.RPA_LOCK_TTL_SECONDS), 900))
        except Exception as exc:
            logger.error("shipping_mutation_lock_unavailable", exc_info=True)
            raise HTTPException(status_code=503, detail="قفل ثبت GPS در دسترس نیست") from exc
        if not acquired:
            raise HTTPException(status_code=409, detail="ثبت GPS دیگری برای همین بارنامه در حال اجراست")
        try:
            return await handler(req, user_context)
        finally:
            await rpa_runtime.release_lock(key)

    return wrapped


# ──────────────────── Endpoints ────────────────────


@router.post("/coordinates", response_model=CoordinateInfoResponse, dependencies=[Depends(require_sensitive_auth)])
async def get_job_coordinates(
    req: ShippingInfoRequest, user_context: dict[str, Any] = Depends(get_current_user_or_admin)
):
    """استخراج مختصات و آدرس‌های دقیق از payload بارنامه — دقیقاً آدرسی که کاربر وارد کرده."""
    payload, _ = await _get_job_and_driver(req.job_id, user_context)
    info = extract_coordinates_from_payload(payload)
    return CoordinateInfoResponse(**info)


@router.post("/start", dependencies=[Depends(require_sensitive_auth)])
@_shipping_mutation_lock
async def start_shipping(req: ShippingStartRequest, user_context: dict[str, Any] = Depends(get_current_user_or_admin)):
    """شروع حمل توسط اپراتور — ثبت anchor مبدأ بارنامه در UTCMS."""
    if not utcms_config.ALLOW_LIVE_SUBMIT:
        raise HTTPException(status_code=409, detail="ثبت زنده GPS غیرفعال است")
    payload, driver = await _get_job_and_driver(req.job_id, user_context, expected_doc_no=req.doc_no)
    existing = await _load_state_or_503(req.job_id)
    if existing and existing.status != "ready":
        raise HTTPException(status_code=409, detail=f"حمل قبلاً در وضعیت {existing.status} ثبت شده است")
    try:
        state = await init_shipping(req.job_id, req.doc_no, payload, persist=False)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _assert_route_anchor(
        latitude=req.latitude,
        longitude=req.longitude,
        expected_lat=state.origin_lat,
        expected_lng=state.origin_lng,
        label="مبدأ",
    )
    # Build the origin witness, but persist local state only after UTCMS confirms.
    observed_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    state.gps_list.append(
        {
            "Type": 1,
            "Longitude": req.longitude,
            "Latitude": req.latitude,
            "Altitude": req.altitude,
            "Speed": req.speed,
            "Date": observed_at,
            "ObservedAt": observed_at,
            "Provider": "operator_anchor",
            "Provenance": "operator_confirmed",
        }
    )
    if not driver or not driver.utcms_password_encrypted:
        raise HTTPException(status_code=409, detail="اعتبارنامه راننده برای GPS موجود نیست")
    utcms_result = None
    mutation_attempted = False
    try:
        from app.auth_multitenant import decrypt_driver_password

        pwd = decrypt_driver_password(driver.utcms_password_encrypted)
        # ── Session Vault: reuse cached token → refresh → login only as last resort ──
        # Previous code solved CAPTCHA and logged in on EVERY request, causing
        # auth spam and 429 risk.  get_or_login_client() caches the driver bearer
        # token in Redis with a short TTL (default 240s) and the refresh token
        # with TTL 7000s, trying refresh before a full login to reduce UTCMS
        # auth traffic (it does not eliminate 429).
        proxy_url = get_worker_proxy_url()
        if proxy_url is None and (
            (os.environ.get("ENVIRONMENT") or "").lower() == "production"
            or os.environ.get("PROXY_FAIL_CLOSED", "").lower() == "true"
        ):
            raise ProxyUnavailableError("ارتباط مستقیم با UTCMS بدون پراکسی در پروداکشن مجاز نیست")
        client = await get_or_login_client(
            national_code=driver.driver_national_code,
            password=pwd,
            proxy_url=proxy_url,
        )
        # ── StartShippingWithGps is the V2 GPS-aware endpoint that supersedes
        # the legacy RegisterStartOfShipping.  Unlike the finish flow (which
        # calls BOTH FinishShippingWithGps + RegisterEndOfShipping to submit
        # the full GPS history list), start has no history to submit — so
        # StartShippingWithGps alone is correct and symmetric.
        # RegisterStartOfShipping is the verified mobile API endpoint
        start_date_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        target_doc_id = state.doc_id or state.doc_no
        try:
            mutation_attempted = True
            utcms_result = await client.register_start_of_shipping(
                document_id=target_doc_id,
                speed=req.speed,
                altitude=req.altitude,
                longitude=req.longitude,
                latitude=req.latitude,
                start_date=start_date_iso,
                allow_live_submit=utcms_config.ALLOW_LIVE_SUBMIT,
            )
        except Exception as exc:
            if not is_mobile_authentication_error(exc):
                raise
            client = await get_or_login_client(
                national_code=driver.driver_national_code,
                password=pwd,
                proxy_url=proxy_url,
                force_reauth=True,
            )
            utcms_result = await client.register_start_of_shipping(
                document_id=target_doc_id,
                speed=req.speed,
                altitude=req.altitude,
                longitude=req.longitude,
                latitude=req.latitude,
                start_date=start_date_iso,
                allow_live_submit=utcms_config.ALLOW_LIVE_SUBMIT,
            )
        utcms_result = require_successful_mutation(utcms_result, "شروع GPS")
    except ProxyUnavailableError as exc:
        logger.error("utcms_live_start_shipping_proxy_unavailable", exc_info=True)
        raise HTTPException(status_code=503, detail="پراکسی UTCMS در دسترس نیست — IP سرور محافظت شد") from exc
    except Exception as exc:
        logger.error("utcms_live_start_shipping_failed", exc_info=True)
        state.status = "unknown" if mutation_attempted else "failed"
        try:
            await save_shipping_state(state)
        except Exception:
            logger.error("shipping_start_failure_state_persist_failed", exc_info=True)
        raise HTTPException(status_code=502, detail="UTCMS شروع حمل را تأیید نکرد") from exc

    state.status = "in_transit"
    state.current_step = 0
    try:
        await save_shipping_state(state)
    except ShippingStatePersistenceError as exc:
        logger.error("shipping_start_state_persist_failed", exc_info=True)
        raise HTTPException(status_code=503, detail="وضعیت ثبت GPS پایدار نشد") from exc
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
@_shipping_mutation_lock
async def finish_shipping(
    req: ShippingFinishRequest, user_context: dict[str, Any] = Depends(get_current_user_or_admin)
):
    """پایان حمل توسط اپراتور — ثبت anchor مقصد بارنامه در UTCMS."""
    if not utcms_config.ALLOW_LIVE_SUBMIT:
        raise HTTPException(status_code=409, detail="ثبت زنده GPS غیرفعال است")
    _, driver = await _get_job_and_driver(req.job_id, user_context)
    state = await _load_state_or_503(req.job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="ابتدا حمل را شروع کنید")
    if state.status != "in_transit":
        raise HTTPException(status_code=409, detail=f"پایان حمل قابل تکرار نیست؛ وضعیت فعلی {state.status} است")
    await _get_job_and_driver(req.job_id, user_context, expected_doc_no=state.doc_no)
    if req.measured_distance_km is None:
        raise HTTPException(status_code=422, detail="مسافت اندازه‌گیری‌شده دستگاه برای پایان حمل الزامی است")

    _assert_route_anchor(
        latitude=req.latitude,
        longitude=req.longitude,
        expected_lat=state.dest_lat,
        expected_lng=state.dest_lng,
        label="مقصد",
    )

    # Add the operator-confirmed route destination anchor; no interpolated
    # telemetry is ever submitted to UTCMS.
    observed_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    if not state.gps_list or state.gps_list[-1].get("Type") != 3:
        state.gps_list.append(
            {
                "Type": 3,
                "Longitude": req.longitude,
                "Latitude": req.latitude,
                "Altitude": req.altitude,
                "Speed": req.speed,
                "Date": observed_at,
                "ObservedAt": observed_at,
                "Provider": "operator_anchor",
                "Provenance": "operator_confirmed",
            }
        )

    # Fence the two UTCMS mutations.  A timeout after the first mutation must
    # never be retried as a fresh finish request.
    state.status = "finishing"
    try:
        await save_shipping_state(state)
    except ShippingStatePersistenceError as exc:
        raise HTTPException(status_code=503, detail="وضعیت پایان حمل پایدار نشد") from exc
    if not driver or not driver.utcms_password_encrypted:
        state.status = "failed"
        await save_shipping_state(state)
        raise HTTPException(status_code=409, detail="اعتبارنامه راننده برای GPS موجود نیست")
    mutation_attempted = False
    try:
        from app.auth_multitenant import decrypt_driver_password

        pwd = decrypt_driver_password(driver.utcms_password_encrypted)
        # ── Session Vault: reuse cached token (same rationale as /start) ──
        proxy_url = get_worker_proxy_url()
        if proxy_url is None and (
            (os.environ.get("ENVIRONMENT") or "").lower() == "production"
            or os.environ.get("PROXY_FAIL_CLOSED", "").lower() == "true"
        ):
            raise ProxyUnavailableError("ارتباط مستقیم با UTCMS بدون پراکسی در پروداکشن مجاز نیست")
        client = await get_or_login_client(
            national_code=driver.driver_national_code,
            password=pwd,
            proxy_url=proxy_url,
        )
        # ── Dual-endpoint finish is intentional and NOT a bug ──
        # 1. FinishShippingWithGps → records the terminal GPS point + distance
        # 2. RegisterEndOfShipping → submits the full gps_list history
        # The start flow only calls StartShippingWithGps because there is no
        finish_result: dict[str, Any] = {}
        try:
            finish_result = await client.finish_shipping_with_gps(
                doc_no=state.doc_no,
                lat=req.latitude,
                lon=req.longitude,
                alt=req.altitude,
                speed=req.speed,
                total_distance_km=req.measured_distance_km,
                allow_live_submit=utcms_config.ALLOW_LIVE_SUBMIT,
            )
            finish_result = require_successful_mutation(finish_result, "پایان GPS")
        except Exception as exc:
            logger.warning("finish_shipping_with_gps non_critical_blip: %s", exc)
        target_doc_id = state.doc_id or state.doc_no
        try:
            mutation_attempted = True
            history_result = await client.register_end_of_shipping(
                document_id=target_doc_id,
                gps_list=state.gps_list,
                allow_live_submit=utcms_config.ALLOW_LIVE_SUBMIT,
            )
        except Exception as exc:
            if not is_mobile_authentication_error(exc):
                raise
            client = await get_or_login_client(
                national_code=driver.driver_national_code,
                password=pwd,
                proxy_url=proxy_url,
                force_reauth=True,
            )
            history_result = await client.register_end_of_shipping(
                document_id=target_doc_id,
                gps_list=state.gps_list,
                allow_live_submit=utcms_config.ALLOW_LIVE_SUBMIT,
            )
        history_result = require_successful_mutation(history_result, "ثبت تاریخچه GPS")
        utcms_result = {"finish": finish_result, "history": history_result}
    except ProxyUnavailableError as exc:
        logger.error("utcms_live_end_shipping_proxy_unavailable", exc_info=True)
        state.status = "unknown" if mutation_attempted else "failed"
        await save_shipping_state(state)
        raise HTTPException(status_code=503, detail="پراکسی UTCMS در دسترس نیست — IP سرور محافظت شد") from exc
    except Exception as exc:
        logger.error("utcms_live_end_shipping_failed", exc_info=True)
        state.status = "unknown" if mutation_attempted else "failed"
        await save_shipping_state(state)
        raise HTTPException(status_code=502, detail="UTCMS پایان حمل را تأیید نکرد") from exc

    state.status = "delivered"
    state.current_step = len(state.waypoints) - 1
    state.traveled_km = req.measured_distance_km
    try:
        await save_shipping_state(state)
    except ShippingStatePersistenceError as exc:
        raise HTTPException(status_code=503, detail="وضعیت تحویل پایدار نشد") from exc

    return {
        "status": "delivered",
        "message": f"حمل با موفقیت در مقصد تحویل شد: {state.dest_address}",
        "distance_km": state.distance_km,
        "measured_distance_km": req.measured_distance_km,
        "gps_list": state.gps_list,
        "total_points": len(state.gps_list),
        "utcms_result": utcms_result,
    }


@router.get("/status/{job_id}", dependencies=[Depends(require_sensitive_auth)])
async def get_shipping_status(job_id: str, user_context: dict[str, Any] = Depends(get_current_user_or_admin)):
    """وضعیت فعلی حمل و نقاط GPS ثبت‌شده."""
    payload, _ = await _get_job_and_driver(job_id, user_context)
    state = await _load_state_or_503(job_id)
    if state is None:
        # Try to extract coordinate info from the job for pre-start display
        try:
            info = extract_coordinates_from_payload(payload)
            duration_hours = round(info["distance_km"] / 65.0, 2)
            duration_minutes = int(round(duration_hours * 60))
            duration_text = (
                f"{int(duration_hours)} ساعت و {duration_minutes % 60} دقیقه"
                if duration_hours >= 1
                else f"{duration_minutes} دقیقه"
            )
            return {
                "status": "not_started",
                "origin": {
                    "lat": info["origin_lat"],
                    "lng": info["origin_lng"],
                    "address": info["origin_address"],
                    "city": info["origin_city"],
                },
                "destination": {
                    "lat": info["dest_lat"],
                    "lng": info["dest_lng"],
                    "address": info["dest_address"],
                    "city": info["dest_city"],
                },
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
    duration_text = (
        f"{int(duration_hours)} ساعت و {duration_minutes % 60} دقیقه"
        if duration_hours >= 1
        else f"{duration_minutes} دقیقه"
    )
    remaining_km = round(state.distance_km - state.traveled_km, 2)
    remaining_hours = round(remaining_km / 65.0, 2)
    remaining_minutes = int(round(remaining_hours * 60))
    remaining_text = (
        f"{int(remaining_hours)} ساعت و {remaining_minutes % 60} دقیقه"
        if remaining_hours >= 1
        else f"{remaining_minutes} دقیقه"
    )

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
