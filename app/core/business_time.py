"""Timezone-aware business date helpers for Tehran reset rules."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.core.config import utcms_config


def business_tz() -> ZoneInfo:
    return ZoneInfo(utcms_config.BUSINESS_TIMEZONE)


def now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def business_date_str(at: datetime | None = None) -> str:
    current = at or now_utc()
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(business_tz()).date().isoformat()
