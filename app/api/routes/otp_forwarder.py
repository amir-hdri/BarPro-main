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

from app.auth_multitenant import get_current_user_or_admin
from app.core.config import utcms_config
from app.core.redis_client import redis_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/otp", tags=["OTP Forwarder"])

REDIS_OTP_LATEST_KEY = "rpa:otp:latest"
REDIS_OTP_PHONE_PREFIX = "rpa:otp:phone:"
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
    if not token or not hmac.compare_digest(token, secret):
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
    """
    Extract 4-8 digit OTP code from SMS message text.
    Prioritizes 5 or 6 digit codes commonly sent by UTCMS / Iranian government portals.
    """
    if not text:
        return None

    clean_text = normalize_to_english_digits(text)

    # 1. Look for patterns near keywords: کد, تایید, تأیید, رمز, بارنامه, شهرداری
    keyword_patterns = [
        r"(?:کد\s*(?:تایید|تأیید|فعالسازی|ورود)?|رمز\s*یکبار\s*مصرف|بارنامه|شهرداری)[^\d]{0,25}[:\-=\s]?\s*(\d{4,8})",
        r"(\d{4,8})[^\d]{0,25}(?:کد\s*(?:تایید|تأیید)|رمز)",
    ]
    for pattern in keyword_patterns:
        match = re.search(pattern, clean_text, re.IGNORECASE)
        if match:
            code = match.group(1).strip()
            if 4 <= len(code) <= 8:
                return code

    # 2. Look for standalone 5 or 6 digit numbers (UTCMS standard)
    matches_5_6 = re.findall(r"\b(\d{5,6})\b", clean_text)
    if matches_5_6:
        # Ignore common Iranian year representations like 1403, 1404, 1405
        filtered = [m for m in matches_5_6 if not m.startswith("140")]
        if filtered:
            return filtered[0]
        return matches_5_6[0]

    # 3. Look for standalone 4 to 8 digit numbers
    matches_any = re.findall(r"\b(\d{4,8})\b", clean_text)
    if matches_any:
        filtered = [m for m in matches_any if not (len(m) == 4 and m.startswith("140"))]
        if filtered:
            return filtered[0]
        return matches_any[0]

    return None


def clean_phone_number(raw_phone: str) -> str:
    """Normalize phone number to standard format (e.g. 0912xxxxxxx or 20007777)."""
    if not raw_phone:
        return ""
    digits = re.sub(r"[^\d]", "", normalize_to_english_digits(raw_phone))
    if digits.startswith("98") and len(digits) > 10:
        digits = "0" + digits[2:]
    return digits


async def store_otp_in_redis(code: str, sender: str, text: str, phone: str = "") -> dict[str, Any]:
    """Store the extracted OTP in Redis and publish to the pub/sub channel."""
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

    r = await redis_manager.get()
    if r:
        try:
            await r.set(REDIS_OTP_LATEST_KEY, payload_json, ex=DEFAULT_OTP_TTL)
            if phone:
                clean_p = clean_phone_number(phone)
                if clean_p:
                    await r.set(f"{REDIS_OTP_PHONE_PREFIX}{clean_p}", payload_json, ex=DEFAULT_OTP_TTL)
            if sender:
                clean_s = clean_phone_number(sender)
                if clean_s:
                    await r.set(f"{REDIS_OTP_PHONE_PREFIX}{clean_s}", payload_json, ex=DEFAULT_OTP_TTL)
            # Publish event for listening subscribers
            await r.publish(REDIS_OTP_CHANNEL, payload_json)
        except Exception as exc:
            logger.error("Failed to store OTP in Redis: %s", exc)

    return payload


class ManualOtpRequest(BaseModel):
    code: str = Field(..., description="The OTP verification code (e.g. 12345)")
    phone: str | None = Field(default=None, description="Optional associated phone number")
    job_id: str | None = Field(default=None, description="Optional associated waybill job ID")


@router.post("/sms-forwarder", summary="Webhook for SecureSMS Forwarder / SMS Forwarder Android Apps")
@router.post("/webhook", summary="Alias webhook for SMS Forwarders")
async def receive_sms_forwarder_webhook(request: Request) -> dict[str, Any]:
    """
    Accepts incoming SMS from SecureSMS Forwarder or any SMS forwarding Android app.
    Supports JSON payloads, form-encoded data, query parameters, or raw text.

    Requires the ``X-OTP-Webhook-Token`` header matching ``OTP_WEBHOOK_SECRET``.
    """
    _require_webhook_auth(request)

    sender = ""
    content = ""
    phone = ""

    # 1. Try parsing JSON
    try:
        json_data = await request.json()
        if isinstance(json_data, dict):
            # Check various possible field names used by forwarders
            for key in ("content", "text", "msg", "message", "body", "sms", "data"):
                if key in json_data and isinstance(json_data[key], str):
                    content = json_data[key]
                    break
            for key in ("from", "sender", "phone", "mobile", "origin", "address"):
                if key in json_data and isinstance(json_data[key], (str, int)):
                    sender = str(json_data[key])
                    break
            for key in ("target", "phone_number", "driver_phone"):
                if key in json_data and isinstance(json_data[key], (str, int)):
                    phone = str(json_data[key])
                    break
    except Exception:
        pass

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
        except Exception:
            pass

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

    # 4. Fallback to raw body text
    if not content:
        try:
            raw_body = await request.body()
            content = raw_body.decode("utf-8", errors="ignore").strip()
        except Exception:
            pass

    if not content:
        logger.warning("SMS webhook received with empty content")
        raise HTTPException(status_code=400, detail="No content or text provided in SMS payload")

    otp_code = extract_otp_code(content)
    if not otp_code:
        # Never log message content: it may contain the OTP code itself.
        logger.warning("Could not extract OTP code from SMS content (content_len=%d)", len(content))
        return {
            "status": "ignored",
            "message": "No valid OTP code found in SMS text",
            "sender": sender,
            "content_length": len(content),
        }

    stored = await store_otp_in_redis(
        code=otp_code,
        sender=sender,
        text=content,
        phone=phone or sender,
    )

    # Log metadata only — never the code itself.
    logger.info(
        "sms_forwarder_otp_received",
        extra={"extra_fields": {"code_len": len(otp_code), "sender": sender, "phone": phone}},
    )

    return {
        "status": "success",
        "message": "OTP code extracted and queued for waybill verification",
        "sender": sender,
        "received_at": stored.get("received_at"),
    }


@router.post("/submit-manual", summary="Manually submit OTP code via API/Admin")
async def submit_manual_otp(
    req: ManualOtpRequest,
    user_context: dict[str, Any] = Depends(get_current_user_or_admin),  # noqa: B008
) -> dict[str, Any]:
    """Allows an operator or admin to manually submit an OTP code (auth required)."""
    code = normalize_to_english_digits(req.code.strip())
    if not code or not (4 <= len(code) <= 8):
        raise HTTPException(status_code=400, detail="Invalid OTP code format (must be 4 to 8 digits)")

    stored = await store_otp_in_redis(
        code=code,
        sender="manual_operator",
        text=f"Manual OTP submission: {code}",
        phone=req.phone or "",
    )

    if req.job_id:
        r = await redis_manager.get()
        if r:
            payload_json = json.dumps(stored, ensure_ascii=False)
            await r.set(f"rpa:otp:job:{req.job_id}", payload_json, ex=DEFAULT_OTP_TTL)

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


@router.get("/latest", summary="Get the latest received OTP code")
async def get_latest_otp(
    user_context: dict[str, Any] = Depends(get_current_user_or_admin),  # noqa: B008
) -> dict[str, Any]:
    """Check the latest OTP received in the last 5 minutes (auth required)."""
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
        "payload_template": {"from": "[from]", "content": "[content]", "timestamp": "[timestamp]"},
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
