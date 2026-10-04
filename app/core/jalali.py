"""Self-contained Jalali (Persian/Shamsi) calendar utilities.

Used for operational period logic (e.g. 15-day driver registration periods
anchored at 9 Mehr). Implemented without third-party dependencies so unit
tests and offline environments never depend on ``jdatetime`` being installed.

The conversion algorithms below are the standard, widely-published
Gregorian <-> Jalali transforms (Kazemi/Birashk), verified against known
reference dates in ``tests/test_driver_tracking.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

# Tehran is UTC+3:30 year-round (DST abolished in Iran since 2022).
TEHRAN_UTC_OFFSET = timedelta(hours=3, minutes=30)

JALALI_MONTH_NAMES = [
    "فروردین",
    "اردیبهشت",
    "خرداد",
    "تیر",
    "مرداد",
    "شهریور",
    "مهر",
    "آبان",
    "آذر",
    "دی",
    "بهمن",
    "اسفند",
]

_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"


def to_persian_digits(value: int | str) -> str:
    """Render an integer (or digit string) with Persian digits."""
    return "".join(_PERSIAN_DIGITS[int(ch)] if ch.isdigit() else ch for ch in str(value))


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """Convert a Gregorian date to (jalali_year, jalali_month, jalali_day)."""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + g_d_m[gm - 1]
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    """Convert a Jalali date to (gregorian_year, gregorian_month, gregorian_day)."""
    jy += 1595
    days = -355668 + 365 * jy + jy // 33 * 8 + ((jy % 33) + 3) // 4 + jd
    if jm < 7:
        days += (jm - 1) * 31
    else:
        days += (jm - 7) * 30 + 186
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        gy += 100 * ((days - 1) // 36524)
        days = (days - 1) % 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = (gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0
    month_days = [0, 31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    while gm < 13 and gd > month_days[gm]:
        gd -= month_days[gm]
        gm += 1
    return gy, gm, gd


def jalali_add_days(jy: int, jm: int, jd: int, days: int) -> tuple[int, int, int]:
    """Add (or subtract) days to a Jalali date via Gregorian day arithmetic."""
    gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
    shifted = datetime(gy, gm, gd) + timedelta(days=days)
    return gregorian_to_jalali(shifted.year, shifted.month, shifted.day)


def tehran_today_jalali(now: datetime | None = None) -> tuple[int, int, int]:
    """Current date in Tehran as a Jalali (year, month, day) tuple."""
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    tehran = moment + TEHRAN_UTC_OFFSET
    return gregorian_to_jalali(tehran.year, tehran.month, tehran.day)


def jalali_day_bounds_utc(jy: int, jm: int, jd: int) -> tuple[datetime, datetime]:
    """Return naive-UTC [start, end) datetimes for a Jalali day in Tehran.

    ``WaybillJob.created_at`` is stored as naive UTC; comparing against these
    bounds selects jobs created during that Tehran calendar day.
    """
    gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
    start_utc = datetime(gy, gm, gd) - TEHRAN_UTC_OFFSET
    return start_utc, start_utc + timedelta(days=1)


def tehran_day_bounds_utc(gy: int, gm: int, gd: int) -> tuple[datetime, datetime]:
    """Return naive-UTC [start, end) datetimes for a Gregorian day in Tehran.

    The history-page date filters send Gregorian ``YYYY-MM-DD`` days picked in
    the user's (Tehran) timezone; ``created_at`` is stored as naive UTC, so the
    day must be shifted by the Tehran offset before comparing.

    ``TEHRAN_UTC_OFFSET`` is the fixed +03:30 offset. Iran abolished DST in
    2022, so this is exact for every current-era date. Days before September
    2022 that fell inside the old DST window are off by one hour; that is a
    deliberate trade for a dependency-free fixed offset, and it only affects
    historical reporting, never live filtering.
    """
    start_utc = datetime(gy, gm, gd) - TEHRAN_UTC_OFFSET
    return start_utc, start_utc + timedelta(days=1)


def _parse_calendar_day(day: str) -> datetime:
    """Parse a strict Gregorian ``YYYY-MM-DD`` filter value.

    Deliberately stricter than ``datetime.fromisoformat``, which also accepts
    ``20261002``, ``2026-W40-5``, full datetimes, and timezone-aware strings
    whose offset would then be silently discarded. Raises ``ValueError`` on
    anything else, so callers that already map ``ValueError`` to HTTP 422/400
    keep working unchanged.
    """
    return datetime.strptime(day.strip(), "%Y-%m-%d")


def tehran_day_start_utc(day: str) -> datetime:
    """Naive-UTC instant at which the given Tehran calendar day begins."""
    parsed = _parse_calendar_day(day)
    return tehran_day_bounds_utc(parsed.year, parsed.month, parsed.day)[0]


def tehran_day_end_utc(day: str) -> datetime:
    """Naive-UTC *exclusive* upper bound covering the whole Tehran day ``day``.

    Pair with :func:`tehran_day_start_utc` as ``start <= created_at < end`` so
    the selected end day is fully included.
    """
    parsed = _parse_calendar_day(day)
    return tehran_day_bounds_utc(parsed.year, parsed.month, parsed.day)[1]


# ---------------------------------------------------------------------------
# 15-day driver registration periods, anchored at 9 Mehr of the Jalali year.
#
# Phase 1:  9 Mehr  -> 23 Mehr   (days  0-14 of the cycle)
# Phase 2: 24 Mehr  ->  8 Aban   (days 15-29 of the cycle)
# Phase 3:  9 Aban  -> 23 Aban   ...
# The cycle continues year-round; totals are computed per period window, so
# the "کل ثبت" counter resets automatically when a period ends.
# ---------------------------------------------------------------------------

PERIOD_ANCHOR_MONTH = 7  # Mehr
PERIOD_ANCHOR_DAY = 9
PERIOD_LENGTH_DAYS = 15


def get_tracking_period(now: datetime | None = None) -> dict:
    """Describe the 15-day tracking period containing ``now`` (Tehran time).

    Returns a dict with:
      index: 0-based period index since the 9-Mehr anchor
      phase: 1-based human phase number (index + 1)
      start_jalali / end_jalali: (y, m, d) tuples; end is exclusive
      start_at / end_at: naive-UTC datetimes bounding the period
      label: Persian label, e.g. "دوره ۲ (۲۴ مهر تا ۸ آبان)"
    """
    jy, jm, jd = tehran_today_jalali(now)

    anchor_jy = jy
    if (jm, jd) < (PERIOD_ANCHOR_MONTH, PERIOD_ANCHOR_DAY):
        anchor_jy -= 1

    anchor_gy, anchor_gm, anchor_gd = jalali_to_gregorian(anchor_jy, PERIOD_ANCHOR_MONTH, PERIOD_ANCHOR_DAY)
    anchor_date = datetime(anchor_gy, anchor_gm, anchor_gd).date()

    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    today_tehran = (moment + TEHRAN_UTC_OFFSET).date()

    days_since_anchor = (today_tehran - anchor_date).days
    index = max(0, days_since_anchor // PERIOD_LENGTH_DAYS)

    start_j = jalali_add_days(anchor_jy, PERIOD_ANCHOR_MONTH, PERIOD_ANCHOR_DAY, index * PERIOD_LENGTH_DAYS)
    end_j = jalali_add_days(anchor_jy, PERIOD_ANCHOR_MONTH, PERIOD_ANCHOR_DAY, (index + 1) * PERIOD_LENGTH_DAYS)

    start_at, _ = jalali_day_bounds_utc(*start_j)
    end_at, _ = jalali_day_bounds_utc(*end_j)

    # Display uses the inclusive last day of the period (9 Mehr .. 23 Mehr),
    # while end_jalali/end_at remain the exclusive bound for queries.
    last_j = jalali_add_days(*end_j, -1)
    label = (
        f"دوره {to_persian_digits(index + 1)} "
        f"({to_persian_digits(start_j[2])} {JALALI_MONTH_NAMES[start_j[1] - 1]} "
        f"تا {to_persian_digits(last_j[2])} {JALALI_MONTH_NAMES[last_j[1] - 1]})"
    )

    return {
        "index": index,
        "phase": index + 1,
        "start_jalali": start_j,
        "end_jalali": end_j,
        "start_at": start_at,
        "end_at": end_at,
        "label": label,
    }
