"""Tenant-scoped Redis key builders for the OTP forwarder flow.

Single source of truth for the key shapes written by
``app.api.routes.otp_forwarder.store_otp_in_redis`` and read by the RPA
automation. The unscoped global key (``rpa:otp:latest``) was retired because
concurrent OTPs from two tenants could be consumed cross-tenant; readers must
use :func:`otp_lookup_keys` (job-scoped, then phone-scoped) and NEVER fall
back to a global key.
"""

from __future__ import annotations

import re

OTP_JOB_KEY_PREFIX = "rpa:otp:job:"
OTP_PHONE_KEY_PREFIX = "rpa:otp:phone:"

_PERSIAN_TO_ENGLISH_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_phone_for_otp_key(raw_phone: str | None) -> str:
    """Normalize a phone number exactly the way the OTP webhook writer does.

    Kept identical to the writer's normalization so reader-side key lookups
    always hit the key the writer stored (Persian/Arabic digits, +98 prefix).
    """
    if not raw_phone:
        return ""
    digits = re.sub(r"[^\d]", "", str(raw_phone).translate(_PERSIAN_TO_ENGLISH_DIGITS))
    if digits.startswith("98") and len(digits) > 10:
        digits = "0" + digits[2:]
    return digits


def otp_job_key(job_id: str) -> str:
    """Redis key holding the OTP targeted at one waybill job."""
    return f"{OTP_JOB_KEY_PREFIX}{job_id}"


def otp_phone_key(phone: str | None) -> str | None:
    """Redis key holding the OTP for one driver phone number, or None."""
    clean = normalize_phone_for_otp_key(phone)
    return f"{OTP_PHONE_KEY_PREFIX}{clean}" if clean else None


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
