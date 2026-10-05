"""Tenant-scoped Redis key builders for the OTP forwarder flow.

Single source of truth for the key shapes written by
``app.api.routes.otp_forwarder.store_otp_in_redis`` and read by the RPA
automation. The unscoped global key (``rpa:otp:latest``) was retired because
concurrent OTPs from two tenants could be consumed cross-tenant; readers must
use :func:`otp_lookup_keys` (job-scoped, then phone-scoped) and NEVER fall
back to a global key.
"""

from __future__ import annotations

import inspect
import logging
import re
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


async def reserve_otp_issue_lease(redis: Any, job_id: str, *, ttl_seconds: int = 30) -> bool:
    """Attempt to acquire a single-flight lease to submit OTP for a job.

    Prevents race conditions between polling workers, background event consumers,
    and manual operators. Returns True if lease acquired, False otherwise.
    """
    if not redis or not job_id:
        return False
    lock_key = otp_issue_lock_key(job_id)
    try:
        res = redis.set(lock_key, "1", nx=True, ex=ttl_seconds)
        if inspect.isawaitable(res):
            res = await res
        return bool(res)
    except Exception as exc:
        logger.warning("reserve_otp_issue_lease_failed: %s", exc)
        return False


async def release_otp_issue_lease(redis: Any, job_id: str) -> None:
    """Release the single-flight OTP issue lease for a job."""
    if not redis or not job_id:
        return
    lock_key = otp_issue_lock_key(job_id)
    try:
        res = redis.delete(lock_key)
        if inspect.isawaitable(res):
            await res
    except Exception as exc:
        logger.warning("release_otp_issue_lease_failed: %s", exc)


async def consume_scoped_otp(
    redis: Any,
    *,
    job_id: str | None = None,
    driver_phone: str | None = None,
) -> int:
    """Atomically consume and invalidate OTP keys and pending job pointers.

    Called immediately after successful waybill issuance so the OTP cannot be
    reused for subsequent jobs and stale pending pointers are cleaned up.
    Returns the number of deleted keys.
    """
    if not redis:
        return 0
    keys_to_del: list[str] = []
    if job_id:
        keys_to_del.append(otp_job_key(job_id))
        keys_to_del.append(f"rpa:job:pending_doc:{job_id}")
    if driver_phone:
        p_key = otp_phone_key(driver_phone)
        if p_key:
            keys_to_del.append(p_key)
        pending_p = otp_pending_phone_key(driver_phone)
        if pending_p:
            keys_to_del.append(pending_p)

    deleted_count = 0
    try:
        if job_id and hasattr(redis, "srem"):
            srem_res = redis.srem(OTP_ACTIVE_PENDING_JOBS_SET, job_id)
            if inspect.isawaitable(srem_res):
                await srem_res
        if keys_to_del and hasattr(redis, "delete"):
            del_res = redis.delete(*keys_to_del)
            if inspect.isawaitable(del_res):
                del_res = await del_res
            deleted_count = int(del_res or 0)
    except Exception as exc:
        logger.warning("consume_scoped_otp_failed: %s", exc)
    return deleted_count
