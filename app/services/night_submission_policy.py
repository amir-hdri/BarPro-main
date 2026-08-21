"""Durable night retry policy for UTCMS waybill submissions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import utcms_config

TEHRAN_TZ = ZoneInfo("Asia/Tehran")


@dataclass(frozen=True)
class NightAttemptDecision:
    attempt_count: int
    window_key: str | None
    standby: bool
    retry_at: datetime | None


def tehran_now() -> datetime:
    return datetime.now(TEHRAN_TZ)


def is_in_night_window(now: datetime | None = None) -> bool:
    """Return True if the current or given Tehran datetime is within the 17:30-08:00 window."""
    current = (now or tehran_now()).astimezone(TEHRAN_TZ).time()
    start_time = time(
        hour=getattr(utcms_config, "PREDICTED_OTP_REQUIRED_START_HOUR", 17),
        minute=getattr(utcms_config, "PREDICTED_OTP_REQUIRED_START_MINUTE", 30),
    )
    end_time = time(
        hour=getattr(utcms_config, "PREDICTED_OTP_REQUIRED_END_HOUR", 8),
        minute=getattr(utcms_config, "PREDICTED_OTP_REQUIRED_END_MINUTE", 0),
    )
    if start_time > end_time:
        return current >= start_time or current < end_time
    return start_time <= current < end_time


def night_window_key(now: datetime | None = None) -> str | None:
    """Return the date on which the active 17:30-08:00 window started."""
    current = (now or tehran_now()).astimezone(TEHRAN_TZ)
    start_time = time(
        hour=getattr(utcms_config, "PREDICTED_OTP_REQUIRED_START_HOUR", 17),
        minute=getattr(utcms_config, "PREDICTED_OTP_REQUIRED_START_MINUTE", 30),
    )
    end_time = time(
        hour=getattr(utcms_config, "PREDICTED_OTP_REQUIRED_END_HOUR", 8),
        minute=getattr(utcms_config, "PREDICTED_OTP_REQUIRED_END_MINUTE", 0),
    )
    if current.time() >= start_time:
        return current.date().isoformat()
    if current.time() < end_time:
        return (current.date() - timedelta(days=1)).isoformat()
    return None


def next_reopen_at_utc_naive(now: datetime | None = None) -> datetime:
    """Return the next 08:00 Tehran boundary as a naive UTC DB timestamp."""
    current = (now or tehran_now()).astimezone(TEHRAN_TZ)
    start_time = time(
        hour=getattr(utcms_config, "PREDICTED_OTP_REQUIRED_START_HOUR", 17),
        minute=getattr(utcms_config, "PREDICTED_OTP_REQUIRED_START_MINUTE", 30),
    )
    end_time = time(
        hour=getattr(utcms_config, "PREDICTED_OTP_REQUIRED_END_HOUR", 8),
        minute=getattr(utcms_config, "PREDICTED_OTP_REQUIRED_END_MINUTE", 0),
    )
    reopen_date: date = current.date()
    if current.time() >= start_time:
        reopen_date += timedelta(days=1)
    reopen_local = datetime.combine(reopen_date, end_time, tzinfo=TEHRAN_TZ)
    return reopen_local.astimezone(UTC).replace(tzinfo=None)


def register_safe_night_failure(job, now: datetime | None = None) -> NightAttemptDecision:
    """Count a known-safe failed attempt and decide whether the job must stand by.

    This must never be called for a mutation whose dispatch result is ambiguous.
    """
    key = night_window_key(now)
    if key is None:
        job.night_attempt_count = 0
        job.night_attempt_window = None
        return NightAttemptDecision(0, None, False, None)

    if job.night_attempt_window != key:
        job.night_attempt_window = key
        job.night_attempt_count = 0

    job.night_attempt_count += 1
    limit = max(1, utcms_config.NIGHT_SUBMISSION_MAX_ATTEMPTS)
    standby = job.night_attempt_count >= limit
    return NightAttemptDecision(
        attempt_count=job.night_attempt_count,
        window_key=key,
        standby=standby,
        retry_at=next_reopen_at_utc_naive(now) if standby else None,
    )


def clear_expired_night_attempts(job, now: datetime | None = None) -> None:
    """Reset a prior night's allowance after the Tehran window rolls over."""
    current_key = night_window_key(now)
    if job.night_attempt_window and job.night_attempt_window != current_key:
        job.night_attempt_window = None
        job.night_attempt_count = 0
