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
    _acquire_completion_claim,
    _escalated_trace_target_km,
    _release_completion_claim,
    extract_coordinates_from_payload,
    get_or_login_client,
    init_shipping,
    load_shipping_state,
    record_shipping_rejection,
    save_shipping_state,
    shipping_wait_reason,
)
from app.automation.shipping_contract import (
    prepare_shipping_trace,
    shipping_acknowledged,
    shipping_response,
    utc_shipping_timestamp,
)
from app.automation.worker_proxy import ProxyUnavailableError, get_worker_proxy_url
from app.core.config import utcms_config
from app.core.jalali import to_persian_digits
from app.core.security import require_sensitive_auth

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
        description="مسافت دستگاه (اختیاری)؛ در نبود آن از telemetry/مسیر محاسبه می‌شود",
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
            # get_current_user_or_admin guarantees "user" is a Client instance
            # (never None) when role == "client"; the assert only narrows the type.
            assert client is not None
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
            if driver is not None and driver.client_id != job.client_id:
                raise HTTPException(status_code=409, detail="مالکیت راننده با بارنامه مطابقت ندارد")
        return payload, driver


def _caller_client_id(user_context: dict[str, Any]) -> int | None:
    """Tenant id of the authenticated caller, or None for master_admin.

    master_admin has no tenant of its own; admin-triggered vault calls keep
    the legacy unscoped key path rather than guessing a tenant id.
    """
    if user_context.get("role") == "client":
        client = user_context.get("user")
        client_id = getattr(client, "id", None)
        return int(client_id) if client_id is not None else None
    return None


async def _login_driver_client(
    driver: Any,
    proxy_url: str | None,
    *,
    user_context: dict[str, Any],
    force_reauth: bool = False,
) -> Any:
    """Authenticate the driver's UTCMS mobile client via the session vault.

    Tenant-isolation (C3): the vault lookup is scoped to the authenticated
    caller's tenant, so two tenants sharing a driver national code never
    share a UTCMS session. master_admin callers have no tenant context and
    keep the legacy unscoped path (reported, not guessed).
    """
    from app.auth_multitenant import decrypt_driver_password

    pwd = decrypt_driver_password(driver.utcms_password_encrypted)
    return await get_or_login_client(
        national_code=driver.driver_national_code,
        password=pwd,
        proxy_url=proxy_url,
        force_reauth=force_reauth,
        client_id=getattr(driver, "client_id", None) or _caller_client_id(user_context),
    )


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


# Codes for which a UTCMS start response PROVES no new start was accepted, so
# the durable "starting" fence may safely roll back to the retryable "ready".
#
# Only 4006 qualifies: it is the documented pre-processing refusal
# ("برای بارنامه نمی‌توان شروع حمل ثبت کرد") — either a self-declared start
# already exists (handled as acknowledged by shipping_acknowledged(start=True))
# or UTCMS declined to record one. Either way THIS request created nothing.
#
# Everything else — HTTP 429 (which shipping_response() renders as a dict and
# which the gateway can emit AFTER the start landed), any code outside the
# known allowlist, and non-int renderings such as 200.0 — is ambiguous. Those
# fail closed to "unknown" so a silently-accepted start can never be retried
# into a duplicate RegisterStartOfShipping.
_START_PREPROCESSING_REJECTION_CODES = frozenset({"4006"})


def _start_rejection_is_preprocessing(result: dict[str, Any]) -> bool:
    """True only for codes that prove the start was refused before processing."""
    code = result.get("resultCode")
    if code is None or isinstance(code, bool):
        return False
    return str(code).strip() in _START_PREPROCESSING_REJECTION_CODES


def _persian_duration(total_seconds: float) -> str:
    """Render a wait as an operator-readable Persian duration."""
    seconds = max(0, int(total_seconds))
    minutes, hours = (seconds + 59) // 60, 0
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
    if hours and minutes:
        return f"{to_persian_digits(hours)} ساعت و {to_persian_digits(minutes)} دقیقه"
    if hours:
        return f"{to_persian_digits(hours)} ساعت"
    return f"{to_persian_digits(max(1, minutes))} دقیقه"


def _wait_detail(wait: dict[str, Any]) -> str:
    """Persian sentence for an ETA/backoff gate.

    ``shipping_wait_reason`` returns a structured dict; handing that dict to
    HTTPException made ``main.py``'s ``str(exc.detail)`` render a Python repr
    (``{'status': 'waiting_eta', ...}``) in an RTL Persian UI and leaked the
    internal field names. The structured payload is logged instead.
    """
    remaining = _persian_duration(wait.get("remaining_seconds") or 0)
    if wait.get("status") == "backoff":
        return f"ثبت پایان حمل در حال انتظار است؛ لطفاً {remaining} دیگر دوباره تلاش کنید"
    return f"زمان لازم برای پایان حمل هنوز سپری نشده است؛ لطفاً {remaining} دیگر دوباره تلاش کنید"


# Operator-facing Persian text for UTCMS finish rejections. Keyed by the
# category record_shipping_rejection() derives, so the raw upstream envelope
# never has to reach the client to explain the outcome.
_REJECTION_MESSAGES_FA: dict[str, str] = {
    "needs_review": "UTCMS پایان حمل خوداظهاری را تأیید نکرد؛ این بارنامه نیازمند بررسی دستی است",
    "waiting_distance_requirement": (
        "برای ثبت پایان حمل باید حداقل ۲ کیلومتر مسیر طی شده باشد؛ پس از پایان زمان انتظار دوباره تلاش کنید"
    ),
    "waiting_elapsed_time": ("زمان لازم برای پایان حمل هنوز سپری نشده است؛ پس از پایان زمان انتظار دوباره تلاش کنید"),
    "rate_limited": ("تعداد درخواست‌ها به UTCMS بیش از حد مجاز است؛ پس از پایان زمان انتظار دوباره تلاش کنید"),
    "rejected": "UTCMS ثبت پایان حمل را نپذیرفت؛ پس از پایان زمان انتظار دوباره تلاش کنید",
}


def _rejection_detail(job_id: str, rejection: dict[str, Any]) -> dict[str, Any]:
    """Project a UTCMS finish rejection down to an allowlisted client payload.

    ``record_shipping_rejection`` returns ``{"status", "result", "backoff_until"}``
    where ``result`` is the verbatim decoded UTCMS body. Passing that straight
    into HTTPException leaked the whole upstream envelope to the API client
    (``main.py`` renders a non-str detail with ``str(exc.detail)``), which
    contradicts UtcmsMobileApiError's own "response bodies are never logged"
    contract. Only the category, the result code, a mapped Persian message and
    the cooldown cross the boundary; the raw body stays server-side.
    """
    raw_result = rejection.get("result")
    raw: dict[str, Any] = raw_result if isinstance(raw_result, dict) else {}
    status = str(rejection.get("status") or "rejected")
    logger.error(
        "utcms_finish_rejected job=%s status=%s result=%r backoff_until=%s",
        job_id,
        status,
        raw,
        rejection.get("backoff_until"),
    )
    code = raw.get("resultCode")
    return {
        "status": status,
        "resultCode": code,
        "message": _REJECTION_MESSAGES_FA.get(status, _REJECTION_MESSAGES_FA["rejected"]),
        "backoff_until": rejection.get("backoff_until") or "",
    }


def _origin_witness_backfill(state: Any, fallback_stamp: str) -> dict[str, Any] | None:
    """Recreate the origin Type-2 witness for a trip that never recorded one.

    Mirrors the Beat task's backfill (``gps_shipping_manager.auto_complete_shipping``):
    the issuance auto-start path (``waybill_bot_multitenant._finalize_shipping_start``)
    persists ``status="in_transit"`` from ``init_shipping(gps_list=[])`` without
    ever appending an origin point, so a manually finished waybill reached
    ``prepare_shipping_trace`` with a single point and 500'd.

    Returns ``None`` when a non-destination witness already exists. The origin
    coordinates are required: a (0, 0) anchor must never be submitted to UTCMS.
    """
    if any(point.get("Type") != 3 for point in state.gps_list):
        return None
    if not state.origin_lat or not state.origin_lng:
        raise HTTPException(status_code=422, detail="مختصات مبدأ برای ثبت پایان حمل در بارنامه ثبت نشده است")
    # Recover the start time from the recorded trip start, never backdate it;
    # a corrupt created_at falls back to "now" rather than bricking the finish.
    try:
        stamp = utc_shipping_timestamp(state.created_at) if state.created_at else fallback_stamp
    except (TypeError, ValueError):
        logger.warning("shipping_origin_backfill_bad_created_at job=%s value=%r", state.job_id, state.created_at)
        stamp = fallback_stamp
    return {
        "Type": 2,
        "Latitude": state.origin_lat,
        "Longitude": state.origin_lng,
        "Altitude": 1000,
        "Speed": 0,
        "Date": stamp,
        "DateTime": stamp,
        "ObservedAt": stamp,
        "Provider": "operator_anchor",
        "Provenance": "route_anchor",
    }


def _shipping_mutation_lock(handler):
    @wraps(handler)
    async def wrapped(req, user_context):
        if not utcms_config.ALLOW_LIVE_SUBMIT:
            raise HTTPException(status_code=409, detail="ثبت زنده GPS غیرفعال است")
        # Tenant-isolation (C4): ownership is verified BEFORE the mutation
        # lock is acquired. A caller that cannot see the job (unknown id or
        # another tenant's job) gets 404 here and never holds
        # lock:shipping:{job_id}, so it cannot squat the lock and block the
        # owning tenant's mutation for the TTL.
        await _get_job_and_driver(req.job_id, user_context)
        try:
            acquired = await _acquire_completion_claim(req.job_id)
        except Exception as exc:
            logger.error("shipping_mutation_lock_unavailable", exc_info=True)
            raise HTTPException(status_code=503, detail="قفل ثبت GPS در دسترس نیست") from exc
        if not acquired:
            raise HTTPException(status_code=409, detail="ثبت GPS دیگری برای همین بارنامه در حال اجراست")
        try:
            return await handler(req, user_context)
        finally:
            await _release_completion_claim(req.job_id, acquired)

    return wrapped


# ──────────────────── Endpoints ────────────────────


@router.post("/coordinates", response_model=CoordinateInfoResponse, dependencies=[Depends(require_sensitive_auth)])
async def get_job_coordinates(
    req: ShippingInfoRequest, user_context: dict[str, Any] = Depends(get_current_user_or_admin)  # noqa: B008
):
    """استخراج مختصات و آدرس‌های دقیق از payload بارنامه — دقیقاً آدرسی که کاربر وارد کرده."""
    payload, _ = await _get_job_and_driver(req.job_id, user_context)
    info = extract_coordinates_from_payload(payload)
    return CoordinateInfoResponse(**info)


@router.post("/start", dependencies=[Depends(require_sensitive_auth)])
@_shipping_mutation_lock
async def start_shipping(
    req: ShippingStartRequest, user_context: dict[str, Any] = Depends(get_current_user_or_admin)
):  # noqa: B008
    """شروع حمل توسط اپراتور — ثبت anchor مبدأ بارنامه در UTCMS."""
    if not utcms_config.ALLOW_LIVE_SUBMIT:
        raise HTTPException(status_code=409, detail="ثبت زنده GPS غیرفعال است")
    payload, driver = await _get_job_and_driver(req.job_id, user_context, expected_doc_no=req.doc_no)
    existing = await _load_state_or_503(req.job_id)
    # "starting" is the durable fence written immediately before the first
    # RegisterStartOfShipping POST. A state still sitting at "starting" when a
    # NEW request arrives means the previous request already finished without
    # persisting an outcome (process died mid-POST, or its rollback save also
    # failed) — otherwise the Redis SET-NX completion claim held by that
    # in-flight request would have 409'd this one in _shipping_mutation_lock
    # before the handler body ran. Treating it as terminal bricked a paid
    # waybill forever: /start 409'd here and /finish 409'd on "not in_transit",
    # with no reset path. Re-entry stays safe because (a) the mutation lock,
    # not this check, is what prevents two concurrent POSTs, (b) every status
    # that records an ACKNOWLEDGED start (in_transit / finishing / delivered)
    # is still refused, (c) the ambiguous "unknown" outcome is still refused
    # and must go through reconciliation, and (d) a start that silently landed
    # upstream answers the retry with business rule 4006, which
    # shipping_acknowledged(start=True) resolves to in_transit rather than
    # creating a second start.
    if existing and existing.status not in {"ready", "starting"}:
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
    # ── Route Authority snapshot (Phase 5): frozen at start, best-effort ──
    try:
        from app.services.shipping_travel_service import ensure_route_snapshot

        await ensure_route_snapshot(state)
    except Exception:
        logger.warning("route_snapshot_best_effort_failed job=%s", req.job_id, exc_info=True)
    # ── Android readback gate (Phase 8): fail-closed only when bridge enabled ──
    # Bridge disabled (default) → legacy operator_anchor path is preserved.
    # Bridge enabled → Start is blocked unless Android reports the same origin.
    android_verified = False
    try:
        from app.android_bridge.client import BridgeConfig

        bridge_enabled = BridgeConfig.from_env().enabled
    except Exception as exc:
        raise HTTPException(status_code=503, detail="تنظیمات GPS اندروید معتبر نیست") from exc
    if bridge_enabled:
        # Phase 11: apply the waybill's own origin coordinates via FakeTraveler
        # BEFORE readback — the mock location must be exactly what the user
        # pinned on the map for this waybill (state.origin_lat/lng come from
        # the stored payload). apply_location is fail-closed and verifies the
        # mock provider registered before returning.
        from app.android_bridge.controller import AndroidShippingController

        try:
            controller = AndroidShippingController()
            await controller.apply_location(state.origin_lat, state.origin_lng)
            logger.info(
                "shipping_start_faketraveler_applied job=%s lat=%.6f lng=%.6f",
                req.job_id,
                state.origin_lat,
                state.origin_lng,
            )
        except Exception as exc:
            # B1: a transient FakeTraveler/ADB hiccup must NOT brick the
            # waybill. Persisting status="failed" here would make every later
            # /start 409 (existing.status != "ready") with no reset endpoint,
            # bricking a paid waybill. Nothing has been mutated in UTCMS yet
            # and the mock-location write is idempotent on retry, so the
            # persisted state is left retryable ("ready" or absent) while the
            # request still fails closed with 503.
            logger.error("shipping_start_apply_transient job=%s", req.job_id, exc_info=True)
            raise HTTPException(
                status_code=503,
                detail=f"اعمال موقعیت مبدأ در FakeTraveler ناموفق بود: {exc}",
            ) from exc

        from app.services.shipping_travel_service import verify_android_anchor

        # B2: readback must verify what was actually applied to the device
        # (the waybill's stored origin), not the operator's request anchor.
        # The request anchor already passed the 0.0002° (~22 m) route gate
        # above, while readback uses a 5 m tolerance — comparing the request
        # anchor would deterministically fail readback for any legitimately
        # gated 5–22 m offset. Comparing the stored origin aligns the gates.
        check = await verify_android_anchor(expected_lat=state.origin_lat, expected_lng=state.origin_lng)
        if not check.get("verified"):
            # Same B1 reasoning as the apply branch: readback runs before any
            # UTCMS mutation, so a transient failure stays retryable (503)
            # instead of persisting a terminal "failed".
            logger.error("shipping_start_readback_transient job=%s", req.job_id, exc_info=True)
            raise HTTPException(
                status_code=503,
                detail=f"تأیید GPS اندروید برای مبدأ ناموفق بود: {check.get('reason', 'readback_unavailable')}",
            )
        android_verified = True
    # Build the origin witness, but persist local state only after UTCMS confirms.
    # The witness records state.origin_lat/lng — the SAME coordinates the wire
    # payload below sends. Storing req.latitude/longitude here let the recorded
    # evidence drift up to ~22 m (the _assert_route_anchor tolerance) from what
    # UTCMS actually received, and that drift then fed the Rule-4012 distance
    # math at finish time.
    observed_at = utc_shipping_timestamp(datetime.now(UTC))
    state.gps_list.append(
        {
            "Type": 2,
            "Longitude": state.origin_lng,
            "Latitude": state.origin_lat,
            "Altitude": req.altitude,
            "Speed": req.speed,
            "Date": observed_at,
            "DateTime": observed_at,
            "ObservedAt": observed_at,
            "Provider": "android_faketraveler_applied" if android_verified else "operator_anchor",
            "Provenance": "android_verified" if android_verified else "operator_confirmed",
        }
    )
    state.gps_provider = "android_faketraveler_applied" if android_verified else "operator_anchor"
    state.provenance = "android_verified" if android_verified else "operator_confirmed"
    if not driver or not driver.utcms_password_encrypted:
        raise HTTPException(status_code=409, detail="اعتبارنامه راننده برای GPS موجود نیست")
    utcms_result = None
    mutation_attempted = False
    try:
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
        client = await _login_driver_client(driver, proxy_url, user_context=user_context)
        start_date_iso = utc_shipping_timestamp(datetime.now(UTC))
        target_doc_id = state.doc_id or state.doc_no
        state.status = "starting"
        await save_shipping_state(state)  # durable fence before the first POST
        mutation_attempted = True
        try:
            utcms_result = await client.register_start_of_shipping(
                document_id=target_doc_id,
                speed=req.speed,
                altitude=req.altitude,
                longitude=state.origin_lng,
                latitude=state.origin_lat,
                start_date=start_date_iso,
                allow_live_submit=utcms_config.ALLOW_LIVE_SUBMIT,
            )
        except Exception as exc:
            utcms_result = shipping_response(exc)
            if utcms_result is None:
                raise
        utcms_result = shipping_response(utcms_result)
        if utcms_result is None or not shipping_acknowledged(utcms_result, start=True):
            # Roll the durable fence back to the retryable "ready" ONLY for a
            # code that proves the start was refused before processing. Any
            # other code (429, an unrecognized code, a non-int 200.0) might
            # have been returned AFTER UTCMS accepted the start, so it fails
            # closed to "unknown" instead of inviting a duplicate start.
            if utcms_result is not None and _start_rejection_is_preprocessing(utcms_result):
                mutation_attempted = False  # documented pre-processing rejection
            raise RuntimeError("shipping start was not acknowledged")

    except ProxyUnavailableError as exc:
        logger.error("utcms_live_start_shipping_proxy_unavailable", exc_info=True)
        raise HTTPException(status_code=503, detail="پراکسی UTCMS در دسترس نیست — IP سرور محافظت شد") from exc
    except Exception as exc:
        logger.error("utcms_live_start_shipping_failed", exc_info=True)
        state.status = "unknown" if mutation_attempted else "ready"
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
        "route_source": state.route_source,
        "is_real_route": state.route_source == "neshan",
        "anchor_hash": state.anchor_hash,
        "gps_provider": state.gps_provider,
        "provenance": state.provenance,
        "utcms_result": utcms_result,
    }


@router.post("/step", dependencies=[Depends(require_sensitive_auth)])
async def step_shipping(
    req: ShippingStepRequest, user_context: dict[str, Any] = Depends(get_current_user_or_admin)
):  # noqa: B008
    """Intermediate GPS is intentionally disabled until a live UTCMS ping contract is proven."""
    await _get_job_and_driver(req.job_id, user_context)
    raise HTTPException(status_code=410, detail="ثبت نقطه میانی بدون GPS واقعی UTCMS مجاز نیست")


@router.post("/finish", dependencies=[Depends(require_sensitive_auth)])
@_shipping_mutation_lock
async def finish_shipping(
    req: ShippingFinishRequest, user_context: dict[str, Any] = Depends(get_current_user_or_admin)  # noqa: B008
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
    _assert_route_anchor(
        latitude=req.latitude,
        longitude=req.longitude,
        expected_lat=state.dest_lat,
        expected_lng=state.dest_lng,
        label="مقصد",
    )
    wait = shipping_wait_reason(state)
    if wait:
        # The structured reason stays server-side; the client gets a sentence.
        logger.info("shipping_finish_waiting job=%s reason=%r", req.job_id, wait)
        raise HTTPException(status_code=409, detail=_wait_detail(wait))
    # ── Route snapshot recovery (Phase 5): old jobs may predate snapshots ──
    try:
        from app.services.shipping_travel_service import ensure_route_snapshot

        await ensure_route_snapshot(state)
    except Exception:
        logger.warning("route_snapshot_best_effort_failed job=%s", req.job_id, exc_info=True)
    # ── Destination Android gate (Phase 10): fail-closed when bridge enabled ──
    android_verified = False
    try:
        from app.android_bridge.client import BridgeConfig

        bridge_enabled = BridgeConfig.from_env().enabled
    except Exception as exc:
        raise HTTPException(status_code=503, detail="تنظیمات GPS اندروید معتبر نیست") from exc
    if bridge_enabled:
        # Apply the waybill's own destination coordinates via FakeTraveler
        # BEFORE readback — the mock location must be exactly what the user
        # pinned on the map for this waybill.
        from app.android_bridge.controller import AndroidShippingController

        try:
            controller = AndroidShippingController()
            await controller.apply_location(state.dest_lat, state.dest_lng)
            logger.info(
                "shipping_finish_faketraveler_applied job=%s lat=%.6f lng=%.6f",
                req.job_id,
                state.dest_lat,
                state.dest_lng,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"اعمال موقعیت مقصد در FakeTraveler ناموفق بود: {exc}",
            ) from exc

        from app.services.shipping_travel_service import verify_android_anchor

        # B2: same alignment as /start — verify what was applied to the device
        # (the waybill's stored destination), not the operator's request
        # anchor, so a legitimately-gated 5–22 m offset can never fail
        # the 5 m readback deterministically.
        check = await verify_android_anchor(expected_lat=state.dest_lat, expected_lng=state.dest_lng)
        if not check.get("verified"):
            raise HTTPException(
                status_code=503,
                detail=f"تأیید GPS اندروید برای مقصد ناموفق بود: {check.get('reason', 'readback_unavailable')}",
            )
        android_verified = True
    # ── measured_distance (Phase 11): derived, never operator-supplied alone ──
    # Legacy clients still send it; when present and sane it is kept for
    # compatibility, otherwise it is computed from telemetry/route.
    from app.services.shipping_travel_service import advance_travel_execution, compute_measured_distance_km

    try:
        advance_travel_execution(state)
    except Exception:
        logger.warning("travel_advance_best_effort_failed job=%s", req.job_id, exc_info=True)
    auto_km = compute_measured_distance_km(state)
    measured_km = req.measured_distance_km
    if measured_km is None or not (0 < measured_km <= 1_000_000):
        measured_km = auto_km if auto_km > 0 else (state.route_distance_km or state.distance_km or 0.0)
    if not measured_km or measured_km <= 0:
        raise HTTPException(status_code=422, detail="مسافت قابل محاسبه برای پایان حمل یافت نشد")

    # Add the confirmed route destination anchor; no interpolated
    # telemetry is ever submitted to UTCMS.
    observed_at = utc_shipping_timestamp(datetime.now(UTC))
    # Legacy/auto-started trips reach here with gps_list == [] because the
    # issuance auto-start persisted status="in_transit" without an origin
    # witness. Recreate it (same approach as the Beat auto-complete task)
    # BEFORE the Type-3 destination so the trace stays chronological and
    # prepare_shipping_trace() gets the two points it requires.
    origin_witness = _origin_witness_backfill(state, observed_at)
    if origin_witness is not None:
        logger.info("shipping_finish_origin_backfilled job=%s", req.job_id)
        state.gps_list.insert(0, origin_witness)
    if not state.gps_list or state.gps_list[-1].get("Type") != 3:
        state.gps_list.append(
            {
                "Type": 3,
                # Submit the waybill's frozen destination anchor, not the
                # request's (up to ~22 m away under _assert_route_anchor), so
                # the stored evidence matches both the wire payload and the
                # coordinates the Android gate applied above.
                "Longitude": state.dest_lng,
                "Latitude": state.dest_lat,
                "Altitude": req.altitude,
                "Speed": req.speed,
                "Date": observed_at,
                "DateTime": observed_at,
                "ObservedAt": observed_at,
                "Provider": "android_faketraveler_applied" if android_verified else "operator_anchor",
                "Provenance": "android_verified" if android_verified else "operator_confirmed",
            }
        )

    if not driver or not driver.utcms_password_encrypted:
        raise HTTPException(status_code=409, detail="اعتبارنامه راننده برای GPS موجود نیست")
    try:
        # Escalate the Rule-4012 distance target exactly as the Beat auto-complete
        # path does (_escalated_trace_target_km). A short / intra-city route whose
        # first finish was rejected for <2 km must retry with a longer injected
        # detour; rebuilding at the default ~2.15 km target re-sends an identical
        # trace and loops on 4012 until the attempt cap parks it in needs_review.
        state.gps_list = prepare_shipping_trace(state.gps_list, target_km=_escalated_trace_target_km(state))
    except ValueError as exc:
        # A genuine contract violation (bad point type, non-chronological
        # stamps, out-of-range values) is a 422 with the validation message —
        # this call sits outside every try block below, so it used to escape
        # into general_exception_handler as a bare 500.
        logger.error("shipping_finish_trace_invalid job=%s err=%s", req.job_id, exc)
        raise HTTPException(status_code=422, detail=f"مسیر GPS پایان حمل معتبر نیست: {exc}") from exc
    mutation_attempted = False
    try:
        proxy_url = get_worker_proxy_url()
        if proxy_url is None and (
            (os.environ.get("ENVIRONMENT") or "").lower() == "production"
            or os.environ.get("PROXY_FAIL_CLOSED", "").lower() == "true"
        ):
            raise ProxyUnavailableError("ارتباط مستقیم با UTCMS بدون پراکسی در پروداکشن مجاز نیست")
        client = await _login_driver_client(driver, proxy_url, user_context=user_context)
        state.status = "finishing"
        state.completion_attempts += 1
        state.last_attempt_at = datetime.now(UTC).isoformat()
        await save_shipping_state(state)
        mutation_attempted = True
        try:
            history_result = await client.register_end_of_shipping(
                document_id=state.doc_id or state.doc_no,
                gps_list=state.gps_list,
                allow_live_submit=utcms_config.ALLOW_LIVE_SUBMIT,
            )
        except Exception as exc:
            history_result = shipping_response(exc)
            if history_result is None:
                raise
        history_result = shipping_response(history_result)
        if history_result is None or history_result.get("resultCode") is None:
            raise RuntimeError("shipping completion was not acknowledged")
        if not shipping_acknowledged(history_result):
            rejection = await record_shipping_rejection(state, history_result)
            raise HTTPException(status_code=409, detail=_rejection_detail(req.job_id, rejection))
        if history_result.get("resultCode") == 4011:
            history_result["mode"] = "self_declared_auto_complete"
        utcms_result = {"history": history_result}
    except HTTPException:
        raise
    except ProxyUnavailableError as exc:
        raise HTTPException(status_code=503, detail="پراکسی UTCMS در دسترس نیست — IP سرور محافظت شد") from exc
    except Exception as exc:
        logger.error("utcms_live_end_shipping_failed", exc_info=True)
        state.status = "unknown" if mutation_attempted else "in_transit"
        # save_shipping_state raises ShippingStatePersistenceError whenever the
        # DB mirror fails, even if Redis succeeded. Unprotected (unlike the
        # identical handler in start_shipping) it escaped this block, so the
        # 502 below never ran and the operator got a bare 500 that masked the
        # real UTCMS cause. The 502 must always surface.
        try:
            await save_shipping_state(state)
        except Exception:
            logger.error("shipping_finish_failure_state_persist_failed", exc_info=True)
        raise HTTPException(status_code=502, detail="UTCMS پایان حمل را تأیید نکرد") from exc

    state.status = "delivered"
    state.backoff_until = ""
    state.current_step = len(state.waypoints) - 1
    state.traveled_km = measured_km
    state.measured_distance_km = measured_km
    try:
        await save_shipping_state(state)
    except ShippingStatePersistenceError as exc:
        raise HTTPException(status_code=503, detail="وضعیت تحویل پایدار نشد") from exc

    return {
        "status": "delivered",
        "message": f"حمل با موفقیت در مقصد تحویل شد: {state.dest_address}",
        "distance_km": state.distance_km,
        "measured_distance_km": measured_km,
        "measured_source": "operator_supplied" if req.measured_distance_km else "route_derived",
        "route_source": state.route_source,
        "is_real_route": state.route_source == "neshan",
        "travel_status": state.travel_status,
        "gps_list": state.gps_list,
        "total_points": len(state.gps_list),
        "utcms_result": utcms_result,
    }


@router.get("/status/{job_id}", dependencies=[Depends(require_sensitive_auth)])
async def get_shipping_status(
    job_id: str, user_context: dict[str, Any] = Depends(get_current_user_or_admin)
):  # noqa: B008
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
        "route_source": state.route_source,
        "is_real_route": state.route_source == "neshan",
        "route_distance_km": state.route_distance_km or state.distance_km,
        "anchor_hash": state.anchor_hash,
        "travel_status": state.travel_status,
        "travel_progress": state.travel_progress,
        "measured_distance_km": state.measured_distance_km or state.distance_km,
        "gps_provider": state.gps_provider,
        "provenance": state.provenance,
    }
