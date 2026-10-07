"""Tenant-scoped Redis key builders for the OTP forwarder flow.

Single source of truth for the key shapes written by
``app.api.routes.otp_forwarder.store_otp_in_redis`` and read by the RPA
automation. The unscoped global key (``rpa:otp:latest``) was retired because
concurrent OTPs from two tenants could be consumed cross-tenant; readers must
use :func:`otp_lookup_keys` (job-scoped, then phone-scoped) and NEVER fall
back to a global key.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

logger = logging.getLogger(__name__)

OTP_JOB_KEY_PREFIX = "rpa:otp:job:"
OTP_PHONE_KEY_PREFIX = "rpa:otp:phone:"
OTP_PENDING_PHONE_PREFIX = "rpa:otp:pending_by_phone:"
OTP_ISSUE_LOCK_PREFIX = "lock:otp:issue:"
OTP_ACTIVE_PENDING_JOBS_SET = "rpa:otp:active_pending_jobs"

_PERSIAN_TO_ENGLISH_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_phone_for_otp_key(raw_phone: str | None) -> str:
    """Normalize a phone number exactly the way the OTP webhook writer does.

    Kept identical to the writer's normalization so reader-side key lookups
    always hit the key the writer stored (Persian/Arabic digits, +98 prefix).
    """
    if not raw_phone:
        return ""
    digits = re.sub(r"[^\d]", "", str(raw_phone).translate(_PERSIAN_TO_ENGLISH_DIGITS))
    if digits.startswith("0098") and len(digits) == 14:
        digits = "0" + digits[4:]
    elif digits.startswith("98") and len(digits) == 12:
        digits = "0" + digits[2:]
    elif digits.startswith("9") and len(digits) == 10:
        digits = "0" + digits
    return digits


def otp_job_key(job_id: str) -> str:
    """Redis key holding the OTP targeted at one waybill job."""
    return f"{OTP_JOB_KEY_PREFIX}{job_id}"


def otp_phone_key(phone: str | None) -> str | None:
    """Redis key holding the OTP for one driver phone number, or None."""
    clean = normalize_phone_for_otp_key(phone)
    return f"{OTP_PHONE_KEY_PREFIX}{clean}" if clean else None


def otp_pending_phone_key(phone: str | None) -> str | None:
    """Redis key mapping a driver phone to their current pending waybill job."""
    clean = normalize_phone_for_otp_key(phone)
    return f"{OTP_PENDING_PHONE_PREFIX}{clean}" if clean else None


def otp_issue_lock_key(job_id: str) -> str:
    """Distributed lock key to prevent concurrent OTP submissions for the same job."""
    return f"{OTP_ISSUE_LOCK_PREFIX}{job_id}"


def otp_lookup_keys(job_id: str | None, driver_phone: str | None) -> list[str]:
    """Safe OTP lookup order for automation readers: job-scoped, then phone-scoped.

    The unscoped global key is deliberately absent: a reader with no
    job/phone context must fail closed (no OTP) rather than consume another
    tenant's code.
    """
    keys: list[str] = []
    if job_id:
        keys.append(otp_job_key(job_id))
    phone_key = otp_phone_key(driver_phone)
    if phone_key:
        keys.append(phone_key)
    return keys


async def reserve_otp_issue_lease(redis: Any, job_id: str, *, ttl_seconds: int = 30) -> str | None:
    """Acquire an owner-token lease; callers must retain its token for release."""
    if not redis or not job_id:
        return None
    token = secrets.token_hex(24)
    try:
        res = redis.set(otp_issue_lock_key(job_id), token, nx=True, ex=ttl_seconds)
        if inspect.isawaitable(res):
            res = await res
        return token if res else None
    except Exception as exc:
        logger.warning("reserve_otp_issue_lease_failed: %s", exc)
        return None


async def renew_otp_issue_lease(redis: Any, job_id: str, token: str, *, ttl_seconds: int = 30) -> bool:
    """Only the current owner may extend a lease; a lost lease fails closed."""
    result = await redis.eval(
        "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('EXPIRE', KEYS[1], ARGV[2]) end return 0",
        1,
        otp_issue_lock_key(job_id),
        token,
        ttl_seconds,
    )
    return bool(result)


async def release_otp_issue_lease(redis: Any, job_id: str, token: str) -> None:
    if not redis or not job_id or not token:
        return
    try:
        await redis.eval(
            "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end return 0",
            1,
            otp_issue_lock_key(job_id),
            token,
        )
    except Exception as exc:
        logger.warning("release_otp_issue_lease_failed: %s", exc)


@asynccontextmanager
async def maintained_otp_issue_lease(redis: Any, job_id: str) -> AsyncIterator[str]:
    """Keep ownership live during login/issuance; durable DB fences guard crash ambiguity."""
    from fastapi import HTTPException

    token = await reserve_otp_issue_lease(redis, job_id)
    if not token:
        raise HTTPException(status_code=503, detail="OTP issuance is busy or its lease store is unavailable")

    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(10)
            try:
                if not await renew_otp_issue_lease(redis, job_id, token):
                    return
            except Exception:
                logger.warning("otp_issue_lease_renewal_failed", exc_info=True)
                return

    task = asyncio.create_task(heartbeat())
    try:
        yield token
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await release_otp_issue_lease(redis, job_id, token)


async def consume_scoped_otp(
    redis: Any,
    *,
    job_id: str | None = None,
    driver_phone: str | None = None,
) -> int:
    """Atomically clear this job, without deleting another challenge's phone keys."""
    if not redis or not job_id:
        return 0
    script = """
local removed = redis.call('DEL', KEYS[1], KEYS[2])
redis.call('SREM', KEYS[3], ARGV[1])
if KEYS[4] ~= '' then
    local pending = redis.call('GET', KEYS[5])
    local raw = redis.call('GET', KEYS[4])
    if raw then
        local ok, value = pcall(cjson.decode, raw)
        if ok and (value.job_id == ARGV[1] or (not value.job_id and pending == ARGV[1])) then
            removed = removed + redis.call('DEL', KEYS[4])
        end
    end
    if pending == ARGV[1] then removed = removed + redis.call('DEL', KEYS[5]) end
end
return removed
"""
    try:
        return int(
            await redis.eval(
                script,
                5,
                otp_job_key(job_id),
                f"rpa:job:pending_doc:{job_id}",
                OTP_ACTIVE_PENDING_JOBS_SET,
                otp_phone_key(driver_phone) or "",
                otp_pending_phone_key(driver_phone) or "",
                job_id,
            )
        )
    except Exception:
        logger.warning("consume_scoped_otp_failed", exc_info=True)
        return 0
