"""Timezone-aware business date helpers for Tehran reset rules."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.core.config import utcms_config


def business_tz() -> ZoneInfo:
    return ZoneInfo(utcms_config.BUSINESS_TIMEZONE)


def now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def now_in_business_tz() -> datetime:
    return now_utc().astimezone(business_tz())


def business_date_str(at: datetime | None = None) -> str:
    current = at or now_utc()
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(business_tz()).date().isoformat()


def business_midnight_utc(at: datetime | None = None) -> datetime:
    current = at or now_utc()
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    localized = current.astimezone(business_tz())
    midnight = localized.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(UTC)
