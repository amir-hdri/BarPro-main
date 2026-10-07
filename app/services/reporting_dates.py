"""Validated, inclusive calendar-day filters shared by reporting services."""

import re
from datetime import UTC, datetime

from fastapi import HTTPException

from app.core.jalali import tehran_day_end_utc, tehran_day_start_utc


def utc_report_timestamp(value: datetime | None) -> str | None:
    """Expose the database's UTC convention explicitly to all API clients."""
    if value is None:
        return None
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat().replace("+00:00", "Z")


def parse_report_date_bounds(date_from: str | None, date_to: str | None) -> tuple[datetime | None, datetime | None]:
    """Convert Tehran dates into naive UTC [start, end) query bounds."""
    bounds: list[datetime | None] = []
    for name, raw, parser in (
        ("date_from", date_from, tehran_day_start_utc),
        ("date_to", date_to, tehran_day_end_utc),
    ):
        if raw is None:
            bounds.append(None)
            continue
        try:
            if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw) is None:
                raise ValueError("expected YYYY-MM-DD")
            bounds.append(parser(raw))
        except (ValueError, OverflowError):
            raise HTTPException(status_code=422, detail=f"Invalid {name} format: '{raw}'. Use YYYY-MM-DD.") from None
    start, end = bounds
    if start is not None and end is not None and start >= end:
        raise HTTPException(status_code=400, detail="date_from must not be after date_to")
    return start, end
