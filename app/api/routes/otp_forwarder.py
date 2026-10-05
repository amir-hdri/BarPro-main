"""Webhook and API endpoints for SMS OTP Forwarders (SecureSMS Forwarder / SMS Forwarder apps)."""

from __future__ import annotations

import hmac
import json
import logging
import re
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import select

from app.auth_multitenant import get_current_admin, get_current_user_or_admin
from app.automation.otp_keys import (
    normalize_phone_for_otp_key,
    otp_job_key,
    otp_phone_key,
)
from app.core.config import utcms_config
from app.core.database import async_session_factory
from app.core.redis_client import redis_manager
from app.models_multitenant import WaybillJob
from app.services.otp_delivery import accept_forwarded_otp, recipient_phone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/otp", tags=["OTP Forwarder"])

# RETIRED (tenant-isolation C1): the unscoped global key ``rpa:otp:latest`` is
# no longer written — concurrent OTPs from two tenants could be consumed
# cross-tenant. The constant stays only so the admin-only /latest endpoint can
# read (and report the absence of) legacy keys. All automation readers use the
# job-scoped / phone-scoped keys from app.automation.otp_keys.
REDIS_OTP_LATEST_KEY = "rpa:otp:latest"
REDIS_OTP_CHANNEL = "rpa:otp:channel"
DEFAULT_OTP_TTL = 300  # 5 minutes

# Header carrying the shared webhook token. The SMS forwarder Android apps
# cannot compute HMAC signatures, but they can send a static custom header,
# so a shared bearer token (over TLS) is the deployable authentication here.
WEBHOOK_TOKEN_HEADER = "X-OTP-Webhook-Token"


def _require_webhook_auth(request: Request) -> None:
    """Authenticate SMS-forwarder webhook calls with the shared webhook token.

    Fail-closed: if ``OTP_WEBHOOK_SECRET`` is not configured the endpoint
    refuses every request instead of accepting unauthenticated OTP injections.
    """
    secret = (getattr(utcms_config, "OTP_WEBHOOK_SECRET", "") or "").strip()
    if not secret:
        logger.error("otp_webhook_rejected: OTP_WEBHOOK_SECRET is not configured")
        raise HTTPException(status_code=503, detail="OTP webhook is not configured")
    token = request.headers.get(WEBHOOK_TOKEN_HEADER, "")
    if not token or not hmac.compare_digest(token.encode(), secret.encode()):
        logger.warning("otp_webhook_rejected: invalid or missing webhook token")
        raise HTTPException(status_code=401, detail="Invalid webhook token")


# ── Digit normalization ────────────────────────────────────────────────────────
_PERSIAN_TO_ENGLISH_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_to_english_digits(text: str) -> str:
    """Convert Persian and Arabic digits to standard ASCII English digits."""
    if not text:
        return ""
    return str(text).translate(_PERSIAN_TO_ENGLISH_DIGITS)


def extract_otp_code(text: str) -> str | None:
    """Extract a bounded OTP, never a prefix of a phone/tracking number."""
    clean = normalize_to_english_digits(text).replace("\u200c", " ").replace("\u200f", "")
    if not clean:
        return None
    if any(phrase in clean for phrase in ("رمز دوم", "کد تخفیف", "برداشت از حساب", "خرید اینترنتی")):
        return None
    keyword = (
        r"کد\s*(?:تایید|تأیید|ورود|فعالسازی|فعال\s*سازی|احراز|اعتبار|یک\s*بار\s*مصرف|یکبار\s*مصرف|امنیتی|مجوز|صدور)"
        r"|رمز\s*(?:یک\s*بار\s*مصرف|یکبار\s*مصرف|ورود|موقت|اعتبار|تایید|تأیید)"
        r"|(?:verification|security|login|auth)\s*(?:otp\s*)?code|otp(?:\s*code)?"
    )
    for pattern in (
        rf"(?:{keyword})[^0-9]{{0,60}}(?<![0-9])([0-9]{{4,8}})(?![0-9])",
        rf"(?<![0-9])([0-9]{{4,8}})(?![0-9])[^0-9]{{0,25}}(?:{keyword})",
    ):
        match = re.search(pattern, clean, re.IGNORECASE)
        if match:
            return match.group(1)
    if any(word in clean for word in ("رهگیری", "ردیابی", "شماره بارنامه", "ثبت شد", "صادر شد", "ثبت گردید")):
        return None
    # Short templates sent by older forwarders: "کد: 12345" or just the code.
    match = re.search(r"کد\s*[:=]\s*([0-9]{4,8})(?![0-9])", clean)
    if match:
        return match.group(1)
    if re.fullmatch(r"\s*[0-9]{4,8}\s*", clean):
        return clean.strip()
    return None


def clean_phone_number(raw_phone: str) -> str:
    """Normalize phone number to standard format (e.g. 0912xxxxxxx or 20007777).

    Canonical implementation lives in :mod:`app.automation.otp_keys` so the
    writer and the automation readers always derive identical Redis keys.
    """
    return normalize_phone_for_otp_key(raw_phone)


async def store_otp_in_redis(code: str, sender: str, text: str, phone: str = "") -> dict[str, Any]:
    """Store the extracted OTP in Redis and publish to the pub/sub channel.

    Tenant-isolation (C1): only tenant-scoped keys are written — the
    phone-scoped key here and the job-scoped key written by
    ``submit_manual_otp``. The unscoped global key ``rpa:otp:latest`` is
    retired and never written, so one tenant's OTP can never be consumed by
    another tenant's job.
    """
    now = time.time()
    payload = {
        "code": code,
        "sender": sender,
        "phone": phone,
        "raw_text": text,
        "received_at": now,
        "expires_at": now + DEFAULT_OTP_TTL,
    }
    payload_json = json.dumps(payload, ensure_ascii=False)

    try:
        r = await redis_manager.get()
        if r is None:
            raise ConnectionError("Redis unavailable")
        if r:
            phone_key = otp_phone_key(phone)
            if phone_key:
                await r.set(phone_key, payload_json, ex=DEFAULT_OTP_TTL)
            # Publish event for listening subscribers
            await r.publish(REDIS_OTP_CHANNEL, payload_json)
    except Exception as exc:
        logger.error("Failed to store OTP in Redis (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="OTP storage unavailable") from exc

    return payload


class ManualOtpRequest(BaseModel):
    code: str = Field(..., description="The OTP verification code (e.g. 12345)")
    phone: str | None = Field(default=None, description="Optional associated phone number")
    job_id: str | None = Field(default=None, description="Optional associated waybill job ID")


@router.post("/sms-gateway", summary="Authenticated inbound GSM relay for offline OTP delivery")
async def receive_sms_gateway(request: Request) -> dict[str, Any]:
    _require_webhook_auth(request)
    raw_body = await request.body()
    if len(raw_body) > 2048:
        raise HTTPException(status_code=413, detail="Gateway payload is too large")
    try:
        data = await request.json()
        origin = recipient_phone(str(data["from"]))
        text = data["text"]
        if not isinstance(text, str):
            raise ValueError("Invalid envelope")
        parts = text.strip().split("#")
        if len(parts) != 5 or parts[0] != "BP1":
            raise ValueError("Invalid envelope")
        _, phone, timestamp, code, signature = parts
        if phone != origin or not re.fullmatch(r"[0-9]{4,8}", code):
            raise ValueError("Sender mismatch or invalid code")
        secret = utcms_config.OTP_WEBHOOK_SECRET.strip()
        expected = hmac.new(secret.encode(), "#".join(parts[:4]).encode("ascii"), "sha256").hexdigest()[:32]
        if not hmac.compare_digest(signature.encode(), expected.encode()):
            raise HTTPException(status_code=401, detail="Invalid SMS signature")
    except HTTPException:
        raise
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid signed SMS envelope") from exc
    return await accept_forwarded_otp(code=code, phone=phone, sender=origin, text="", timestamp=timestamp)


@router.post("/sms-forwarder", summary="Webhook for SecureSMS Forwarder / SMS Forwarder Android Apps")
@router.post("/sms-forwarder/{path_driver_phone}", summary="Webhook with path-based driver phone")
@router.post("/webhook", summary="Alias webhook for SMS Forwarders")
@router.post("/webhook/{path_driver_phone}", summary="Alias webhook with path-based driver phone")
async def receive_sms_forwarder_webhook(request: Request, path_driver_phone: str | None = None) -> dict[str, Any]:
    """
    Accepts incoming SMS from SecureSMS Forwarder or any SMS forwarding Android app.
    Supports JSON payloads, form-encoded data, query parameters, headers, or raw text.

    Requires the ``X-OTP-Webhook-Token`` header matching ``OTP_WEBHOOK_SECRET``.
    """
    _require_webhook_auth(request)

    sender = ""
    content = ""
    phone = ""
    timestamp = None

    if path_driver_phone:
        norm_p = normalize_phone_for_otp_key(path_driver_phone)
        if re.fullmatch(r"09[0-9]{9}", norm_p):
            phone = norm_p

    body = await request.body()
    if len(body) > 16_384:
        raise HTTPException(status_code=413, detail="SMS payload is too large")

    # 1. Try parsing JSON
    try:
        json_data = await request.json()
        if isinstance(json_data, dict):
            event = json_data.get("event", "SMS_RECEIVED")
            if event == "HEALTH_CHECK":
                try:
                    redis = await redis_manager.get()
                    if redis is None or not await redis.ping():
                        raise ConnectionError("Redis unavailable")
                except Exception as exc:
                    raise HTTPException(status_code=503, detail="OTP storage unavailable") from exc
                return {"success": True, "status": "ready", "protocol": "barpro-otp-v1"}
            if event != "SMS_RECEIVED" or json_data.get("encrypted") is True:
                raise HTTPException(status_code=422, detail="Unsupported OTP event or encrypted envelope")
            timestamp = json_data.get("timestamp")
            # Check various possible field names used by forwarders
            for key in ("content", "text", "msg", "message", "body", "sms", "data"):
                if key in json_data and isinstance(json_data[key], str):
                    content = json_data[key]
                    break
            for key in ("from", "sender", "phone", "mobile", "origin", "address"):
                if key in json_data and isinstance(json_data[key], (str, int)):
                    sender = str(json_data[key])
                    break
            for key in (
                "driver_phone",
                "driver_mobile",
                "target",
                "target_phone",
                "recipient",
                "recipient_phone",
                "sim_number",
            ):
                if key in json_data and isinstance(json_data[key], (str, int)):
                    phone = str(json_data[key])
                    break
            if not phone:
                for key in ("phone", "phone_number", "mobile"):
                    if key in json_data and isinstance(json_data[key], (str, int)):
                        val = str(json_data[key])
                        clean_val = normalize_phone_for_otp_key(val)
                        if re.fullmatch(r"09[0-9]{9}", clean_val) and val != sender:
                            phone = val
                            break
    except HTTPException:
        raise
    except Exception as exc:
        # Never log the body: it may contain the OTP code itself.
        logger.debug("otp_webhook_json_parse_failed", extra={"extra_fields": {"error": str(exc)}})

    # 2. Try form data if not found in JSON
    if not content:
        try:
            form_data = await request.form()
            for key in ("content", "text", "msg", "message", "body", "sms"):
                if key in form_data:
                    content = str(form_data[key])
                    break
            for key in ("from", "sender", "phone", "mobile", "origin"):
                if key in form_data:
                    sender = str(form_data[key])
                    break
            if not phone:
                phone = str(
                    form_data.get("driver_phone")
                    or form_data.get("driver_mobile")
                    or form_data.get("target")
                    or form_data.get("target_phone")
                    or ""
                )
                if not phone:
                    form_phone = str(form_data.get("phone") or form_data.get("mobile") or "")
                    if re.fullmatch(r"09[0-9]{9}", normalize_phone_for_otp_key(form_phone)) and form_phone != sender:
                        phone = form_phone
            timestamp = form_data.get("timestamp")
        except Exception as exc:
            logger.debug("otp_webhook_form_parse_failed", extra={"extra_fields": {"error": str(exc)}})

    # 3. Check query parameters
    if not content and request.query_params:
        for key in ("content", "text", "msg", "message", "body"):
            if key in request.query_params:
                content = request.query_params[key]
                break
        for key in ("from", "sender", "phone"):
            if key in request.query_params:
                sender = request.query_params[key]
                break
        if not phone:
            phone = (
                request.query_params.get("driver_phone")
                or request.query_params.get("driver_mobile")
                or request.query_params.get("target")
                or request.query_params.get("target_phone")
                or ""
            )
            if not phone:
                q_phone = request.query_params.get("phone") or request.query_params.get("mobile") or ""
                if re.fullmatch(r"09[0-9]{9}", normalize_phone_for_otp_key(q_phone)) and q_phone != sender:
                    phone = q_phone
        timestamp = request.query_params.get("timestamp")

    # 4. Fallback to raw body text
    if not content and request.headers.get("content-type", "").split(";")[0] == "text/plain":
        try:
            raw_body = await request.body()
            content = raw_body.decode("utf-8", errors="ignore").strip()
        except Exception as exc:
            # Never log the body: it may contain the OTP code itself.
            logger.debug("otp_webhook_raw_body_read_failed", extra={"extra_fields": {"error": str(exc)}})

    if not content:
        logger.warning("SMS webhook received with empty content")
        raise HTTPException(status_code=400, detail="No content or text provided in SMS payload")

    otp_code = extract_otp_code(content)
    if not otp_code:
        # Never log message content: it may contain the OTP code itself.
        logger.warning("Could not extract OTP code from SMS content (content_len=%d)", len(content))
        return {
            "success": False,
            "status": "ignored",
            "otp_detected": False,
            "message": "No valid OTP code found in SMS text",
            "sender": sender,
            "content_length": len(content),
        }

    if not phone and request.query_params:
        for key in ("driver_phone", "driver_mobile", "phone", "mobile", "target", "target_phone", "recipient"):
            val = request.query_params.get(key)
            if val:
                clean_val = normalize_phone_for_otp_key(val)
                if re.fullmatch(r"09[0-9]{9}", clean_val) and clean_val != sender:
                    phone = clean_val
                    break

    if not phone:
        for key in ("X-Driver-Phone", "X-Driver-Mobile", "X-Target-Phone", "X-Phone"):
            val = request.headers.get(key)
            if val:
                clean_val = normalize_phone_for_otp_key(val)
                if re.fullmatch(r"09[0-9]{9}", clean_val) and clean_val != sender:
                    phone = clean_val
                    break

    if not phone:
        # Fallback: if exactly one pending waybill job is awaiting OTP in the system, attribute to it.
        try:
            from app.services.otp_wakeup_consumer import resolve_single_flight_pending_phone

            single_phone = await resolve_single_flight_pending_phone()
            if single_phone == "AMBIGUOUS":
                raise HTTPException(
                    status_code=422,
                    detail="AMBIGUOUS_OTP: Multiple pending waybills awaiting OTP; driver_phone is required to disambiguate",
                )
            if single_phone:
                phone = single_phone
        except HTTPException:
            raise
        except Exception as fallback_exc:
            logger.debug("single_flight_attribution_attempt_failed: %s", fallback_exc)

    try:
        stored = await accept_forwarded_otp(
            code=otp_code,
            sender=sender,
            text=content,
            phone=phone,
            timestamp=timestamp,
        )
    except HTTPException as exc:
        if exc.detail == "SMS timestamp is in the future; check device clock":
            logger.warning(
                "sms_forwarder_timestamp_skew_fallback_to_now",
                extra={"extra_fields": {"phone": phone, "raw_timestamp": str(timestamp), "reason": exc.detail}},
            )
            stored = await accept_forwarded_otp(
                code=otp_code,
                sender=sender,
                text=content,
                phone=phone,
                timestamp=None,
            )
        else:
            raise

    # Log metadata only — never the code itself.
    logger.info(
        "sms_forwarder_otp_received",
        extra={"extra_fields": {"code_len": len(otp_code), "sender": sender, "phone": phone}},
    )

    return stored


@router.post("/submit-manual", summary="Manually submit OTP code via API/Admin")
async def submit_manual_otp(
    req: ManualOtpRequest,
    user_context: dict[str, Any] = Depends(get_current_user_or_admin),  # noqa: B008
) -> dict[str, Any]:
    """Allows an operator or admin to manually submit an OTP code (auth required).

    Tenant-isolation (GAP-2): a client may only target a job they own; a
    client submission without a job_id is rejected. Admin submissions without
    a job_id write only the phone-scoped key (the unscoped global OTP key is
    retired — see C1).
    """
    code = normalize_to_english_digits(req.code.strip())
    if not re.fullmatch(r"[0-9]{4,8}", code):
        raise HTTPException(status_code=400, detail="Invalid OTP code format (must be 4 to 8 digits)")

    role = user_context.get("role")
    if role != "master_admin":
        client = user_context.get("user")
        client_id = getattr(client, "id", None)
        if client_id is None:
            raise HTTPException(status_code=403, detail="Forbidden")
        if not req.job_id:
            raise HTTPException(
                status_code=403,
                detail="job_id is required for client OTP submissions",
            )
        # Verify the caller owns the target job before writing its OTP key.
        async with async_session_factory() as session:
            statement = select(WaybillJob).where(
                (WaybillJob.client_id == client_id) & (WaybillJob.job_id == req.job_id)
            )
            result = await session.exec(statement)
            if not result.first():
                raise HTTPException(status_code=404, detail="Job not found")

    stored = await store_otp_in_redis(
        code=code,
        sender="manual_operator",
        text=f"Manual OTP submission: {code}",
        # A job submission must never also target a caller-supplied phone belonging to another tenant.
        phone=(req.phone or "") if not req.job_id else "",
    )

    if req.job_id:
        r = await redis_manager.get()
        if r:
            payload_json = json.dumps(stored, ensure_ascii=False)
            await r.set(otp_job_key(req.job_id), payload_json, ex=DEFAULT_OTP_TTL)

    logger.info(
        "manual_otp_submitted",
        extra={"extra_fields": {"code_len": len(code), "phone": req.phone, "job_id": req.job_id}},
    )

    return {
        "status": "success",
        "message": "Manual OTP received and stored in Redis",
        "job_id": req.job_id,
        "received_at": stored.get("received_at"),
    }


@router.get("/latest", summary="Get the latest received OTP code (admin only)")
async def get_latest_otp(
    _admin: dict[str, Any] = Depends(get_current_admin),  # noqa: B008
) -> dict[str, Any]:
    """Check the legacy global OTP key (admin only).

    The unscoped global key is retired (C1) and no longer written, so this
    normally reports ``none``; it exists only to observe stray legacy keys.
    Admin-only: OTP codes belong to tenant drivers and must never be exposed
    to tenant clients (tenant-isolation GAP-1).
    """
    r = await redis_manager.get()
    if not r:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    raw = await r.get(REDIS_OTP_LATEST_KEY)
    if not raw:
        return {"status": "none", "message": "No active OTP in cache"}

    try:
        data = json.loads(raw)
        now = time.time()
        age_seconds = round(now - data.get("received_at", now), 1)
        return {
            "status": "active",
            "code": data.get("code"),
            "sender": data.get("sender"),
            "received_at": data.get("received_at"),
            "age_seconds": age_seconds,
            "expires_in_seconds": max(0, round(data.get("expires_at", now) - now, 1)),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to decode OTP data: {exc}") from exc


@router.get("/securesms-config", summary="Configuration guide for SecureSMS Forwarder on Android")
async def get_securesms_forwarder_config() -> dict[str, Any]:
    """
    Returns step-by-step configuration parameters for the SecureSMS Forwarder Android app.
    Webhook URLs are built from the PUBLIC_BASE_URL setting; when it is not
    configured the guide tells the operator to set it instead of embedding a
    hard-coded address.
    """
    base = utcms_config.PUBLIC_BASE_URL
    if base:
        webhook_url = f"{base}/api/v1/otp/sms-forwarder"
        alt_url = f"{base}/api/v1/otp/webhook"
        url_step = f"۳. آدرس Webhook را برابر {webhook_url} قرار دهید.\n"
    else:
        webhook_url = "<PUBLIC_BASE_URL from server .env>/api/v1/otp/sms-forwarder"
        alt_url = "<PUBLIC_BASE_URL from server .env>/api/v1/otp/webhook"
        url_step = (
            "۳. ابتدا در فایل .env سرور مقدار PUBLIC_BASE_URL را (با https) تنظیم کنید،\n"
            "   سپس آدرس Webhook را برابر <PUBLIC_BASE_URL>/api/v1/otp/sms-forwarder قرار دهید.\n"
        )
    return {
        "app_name": "SecureSMS Forwarder (or SMS Forwarder / SmsForwarder)",
        "server_webhook_url": webhook_url,
        "alternative_url": alt_url,
        "http_method": "POST",
        "headers": {
            "Content-Type": "application/json",
            "X-OTP-Webhook-Token": "<OTP_WEBHOOK_SECRET from server .env>",
        },
        "payload_template": {
            "sender": "[from]",
            "text": "[content]",
            "timestamp": "[timestamp]",
            "driver_phone": "<recipient driver mobile in 09xxxxxxxxx format>",
        },
        "recommended_rules": [
            {
                "rule_name": "UTCMS OTP Rule",
                "filter_sender": "20007777, 30001923, *",
                "filter_keyword": "کد, تایید, بارنامه, شهرداری",
                "action": "Send Webhook to server_webhook_url",
            }
        ],
        "instructions_fa": (
            "۱. برنامه SecureSMS Forwarder یا SMS Forwarder را روی گوشی راننده یا گوشی گیرنده پیامک نصب کنید.\n"
            "۲. یک Webhook جدید (یا Forward Rule) با متد POST ایجاد کنید.\n"
            + url_step
            + "۴. فرمت بدنه (Body) را به صورت JSON تنظیم کنید و مقادیر from و content را به قالب ارسال اضافه نمایید.\n"
            "۵. فیلتر فرستنده را روی سرشماره‌های ۲۰۰۰۷۷۷۷ یا ۳۰۰۰۱۹۲۳ (یا کلمه کلیدی 'بارنامه' و 'کد') تنظیم نمایید.\n"
            "۶. تست ارسال (Test Send) را در اپلیکیشن بزنید تا پیامک آزمایشی ثبت شود.\n"
            "۷. امنیت: در تنظیمات هدر اپلیکیشن، هدر X-OTP-Webhook-Token را با مقدار\n"
            "   OTP_WEBHOOK_SECRET سرور (فایل .env) اضافه کنید؛ بدون این هدر، وب‌هوک با خطای 401 رد می‌شود."
        ),
    }
