"""Durable, ordered OTP intake shared by the phone forwarder and its consumers."""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from typing import Any

from fastapi import HTTPException

from app.automation.otp_keys import normalize_phone_for_otp_key, otp_phone_key
from app.core.redis_client import redis_manager

OTP_TTL_SECONDS = 300
MAX_CLOCK_SKEW_SECONDS = 30

# A retry must neither refresh an OTP's lifetime nor resurrect a consumed code.
# Check deduplication and ordering in the same Redis operation as the durable write.
STORE_FORWARDED_OTP = """
if redis.call('EXISTS', KEYS[2]) == 1 then return 0 end
local previous = redis.call('GET', KEYS[1])
if previous then
    local ok, entry = pcall(cjson.decode, previous)
    if ok and tonumber(entry.received_at or 0) > tonumber(ARGV[3]) then return -1 end
end
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
redis.call('SET', KEYS[2], '1', 'EX', ARGV[4])
redis.call('PUBLISH', ARGV[5], ARGV[1])
pcall(redis.call, 'XADD', 'rpa:otp:stream', 'MAXLEN', '~', 1000, '*', 'payload', ARGV[1], 'phone', KEYS[1], 'message_id', KEYS[2])
return 1
"""


def recipient_phone(value: str) -> str:
    phone = normalize_phone_for_otp_key(value)
    if not re.fullmatch(r"09[0-9]{9}", phone):
        raise HTTPException(status_code=422, detail="A valid recipient driver_phone is required")
    return phone


def sms_received_at(value: Any, *, now: float) -> float:
    """Accept Unix seconds or Android milliseconds; never refresh stale messages."""
    if value is None:
        return now  # Compatibility for third-party forwarders without a timestamp.
    try:
        if isinstance(value, bool):
            raise ValueError
        timestamp = float(value)
        if timestamp > 100_000_000_000:
            timestamp /= 1000
        if not math.isfinite(timestamp) or timestamp <= 0:
            raise ValueError
    except (TypeError, ValueError, OverflowError) as exc:
        raise HTTPException(status_code=422, detail="Invalid SMS timestamp") from exc
    # Compensate for Iranian DST shift glitch (±1 hour / 3600s) on unpatched Android devices.
    # Iran permanently abolished DST in 1402, but some legacy phone kernels or outdated
    # time-zone databases still shift clocks by ±1 hour.
    if timestamp > now + MAX_CLOCK_SKEW_SECONDS:
        adjusted = timestamp - 3600.0
        if (now - adjusted) < OTP_TTL_SECONDS and adjusted <= now + MAX_CLOCK_SKEW_SECONDS:
            timestamp = adjusted
        else:
            raise HTTPException(status_code=422, detail="SMS timestamp is in the future; check device clock")
    elif now - timestamp >= OTP_TTL_SECONDS:
        adjusted = timestamp + 3600.0
        if (now - adjusted) < OTP_TTL_SECONDS and adjusted <= now + MAX_CLOCK_SKEW_SECONDS:
            timestamp = adjusted
        else:
            raise HTTPException(status_code=410, detail="SMS OTP has expired")

    return min(timestamp, now)


async def accept_forwarded_otp(
    *, code: str, sender: str, phone: str, text: str, timestamp: Any = None
) -> dict[str, Any]:
    now = time.time()
    phone = recipient_phone(phone)
    received_at = sms_received_at(timestamp, now=now)
    ttl = max(1, math.ceil(received_at + OTP_TTL_SECONDS - now))
    # Timestamp distinguishes a genuinely new SMS containing a repeated code.
    source_time = float(timestamp) if timestamp is not None else None
    if source_time is not None and source_time > 100_000_000_000:
        source_time /= 1000
    identity = f"{phone}\0{code}\0{round(source_time * 1000) if source_time is not None else 'legacy'}"
    message_id = hashlib.sha256(identity.encode()).hexdigest()
    payload = {
        "code": code,
        "sender": sender,
        "phone": phone,
        "received_at": received_at,
        "ingested_at": now,
        "expires_at": received_at + OTP_TTL_SECONDS,
        "message_id": message_id,
    }
    try:
        redis = await redis_manager.get()
        if redis is None:
            raise ConnectionError("Redis unavailable")
        result = int(
            await redis.eval(
                STORE_FORWARDED_OTP,
                2,
                otp_phone_key(phone),
                f"rpa:otp:seen:{message_id}",
                json.dumps(payload),
                ttl,
                received_at,
                OTP_TTL_SECONDS + MAX_CLOCK_SKEW_SECONDS,
                "rpa:otp:channel",
            )
        )
    except Exception as exc:
        # Do not acknowledge delivery until the durable write has succeeded.
        raise HTTPException(status_code=503, detail="OTP storage unavailable; retry delivery") from exc
    if result == -1:
        raise HTTPException(status_code=409, detail="A newer OTP has already been received")

    try:
        from app.services.otp_wakeup_consumer import trigger_job_completion_on_otp_received

        trigger_job_completion_on_otp_received(phone=phone, code=code)
    except Exception:
        pass

    return {
        "success": True,
        "status": "success",
        "otp_detected": True,
        "is_duplicate": result == 0,
        "received_at": received_at,
        "message": "OTP accepted",
    }
