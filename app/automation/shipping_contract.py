"""Validation for UTCMS shipping payloads and business acknowledgements."""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from typing import Any

# UTCMS business rules that acknowledge a mutation the portal had already
# self-declared (AGENTS.md -> "Automated Shipping Lifecycle & GPS Completion
# Contract"): 4006 on the start side, 4011 on the end side.
SELF_DECLARED_START_RULE = 4006
SELF_DECLARED_END_RULE = 4011

# Minimum cumulative trace distance UTCMS accepts for a terminal registration
# (rule 4012) and the default target the detour aims for.
DEFAULT_TRACE_TARGET_KM = 2.15
TRACE_TARGET_MARGIN_KM = 0.10

# A rule code alone cannot always decide acknowledgement: UTCMS reuses 4011 for
# BOTH "end confirmed by self-declaration" and at least one refusal variant
# ("... شروع حمل ثبت نشده است"). The positive decision is therefore made on the
# numeric code (so a reworded acknowledgement can never dead-end a trip), and
# only an EXPLICIT negation can veto it. Fail-closed by design: a false veto
# retries after a cooldown, while a false acknowledgement would record a
# rejection as a delivery, which is unrecoverable.
_REJECTION_MARKERS = ("نشده", "نمی باشد", "مجاز نیست", "ناموفق")

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
# "... مسیر طی شده فعلی : 1.552 کیلومتر" — the distance UTCMS itself measured.
_REPORTED_DISTANCE_RE = re.compile(r"فعلی\s*[:：]?\s*(\d+(?:\.\d+)?)")


def normalize_shipping_message(value: Any) -> str:
    """Fold the Persian spelling variants UTCMS mixes into one comparable form."""
    text = str(value or "")
    # ZWNJ becomes a SPACE, not deletion: Word-joining it away merges the two
    # sides ("نمی‌باشد"→"نمیباشد"), which then evades the space-bearing
    # rejection markers ("نمی باشد", "مجاز نیست") and can flip a refused
    # 4006/4011 into a false acknowledgement.
    for source, target in (("‌", " "), ("ي", "ی"), ("ى", "ی"), ("ك", "ک"), ("أ", "ا"), ("إ", "ا")):
        text = text.replace(source, target)
    return " ".join(text.split())


def shipping_result_code(response: Any) -> int | None:
    """Return the numeric UTCMS result code, or None when there is none."""
    code = response.get("resultCode") if isinstance(response, dict) else None
    if code is None or isinstance(code, bool):
        return None
    try:
        return int(str(code).strip())
    except (TypeError, ValueError):
        return None


def utc_shipping_timestamp(value: str | datetime) -> str:
    """Convert an aware timestamp to the exact UTCMS wire format; never guess a zone.

    Deliberately strict: a naive value submitted as UTC when it was really
    Tehran local time shifts ``estimatedTimeOfEndShipment`` by 3.5 hours and
    trips rule 4013. Callers holding a legacy naive value must normalise it
    explicitly (see ``gps_shipping_manager._assume_utc_timestamp``).
    """
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("shipping timestamp must include a timezone")
    return parsed.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def shipping_number(value: Any, low: float, high: float, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"invalid shipping {name}")
    number = float(value)
    if not math.isfinite(number) or not low <= number <= high:
        raise ValueError(f"invalid shipping {name}")
    return number


def shipping_response(value: Any) -> dict[str, Any] | None:
    """Preserve structured rejection messages without inventing a successful result."""
    if isinstance(value, dict):
        result = dict(value)
    else:
        code = getattr(value, "result_code", None)
        if code is None and getattr(value, "status_code", None) == 429:
            code = 429
        if code is None:
            return None
        result = {"resultCode": code, "resultMessage": getattr(value, "result_message", None) or str(value)}
    code = result.get("resultCode")
    if isinstance(code, bool) or str(code).strip() not in {"0", "200", "4006", "4011", "4012", "4013", "429"}:
        return result
    result["resultCode"] = int(str(code).strip())
    return result


def shipping_explicitly_rejected(response: dict[str, Any]) -> bool:
    """True when the message carries an explicit negation of the mutation.

    A NEGATION-only guard, never a positive acknowledgement test: UTCMS answers
    both the accepted and the refused self-declared-end outcomes under the SAME
    rule code 4011, so the numeric code on its own cannot tell them apart. See
    ``shipping_acknowledged`` for why the veto is the fail-closed side.
    """
    message = normalize_shipping_message(response.get("resultMessage"))
    if not message:
        return False
    return any(marker in message for marker in _REJECTION_MARKERS)


def shipping_acknowledged(response: dict[str, Any], *, start: bool = False) -> bool:
    """Decide acknowledgement from the numeric rule code, vetoed only by a negation.

    * 0 / 200 - plain success.
    * 4006 (start) / 4011 (end) - the documented self-declared rules. The code
      alone decides the POSITIVE case, so UTCMS rewording an acknowledgement can
      no longer flip a successful self-declared start into a false rejection
      (which dead-ended the trip: ``/start`` reset to "ready", every retry
      4006'd again, and ``/finish`` refused because status was not in_transit).
    * Anything else - not acknowledged.

    The message is consulted ONLY to veto, because rule 4011 is overloaded
    upstream: an explicit refusal must never be recorded as a delivery. A false
    veto merely retries after a cooldown; a false acknowledgement is
    unrecoverable. ``resultMessage`` stays on the response for diagnostics.
    """
    code = shipping_result_code(response)
    if code in (0, 200):
        return True
    if code == (SELF_DECLARED_START_RULE if start else SELF_DECLARED_END_RULE):
        return not shipping_explicitly_rejected(response)
    return False


def shipping_reported_distance_km(response: dict[str, Any]) -> float | None:
    """Extract the distance UTCMS measured for itself from a rule-4012 message.

    UTCMS computes ROAD distance along ``gpsList`` and reports its own figure
    (for example a trailing "1.552" before the kilometre unit). Ignoring that
    number is what made detour injection non-escalating: a trace rebuilt to the
    same 2.15 km target is rejected identically forever.
    """
    message = normalize_shipping_message(response.get("resultMessage")).translate(_PERSIAN_DIGITS)
    match = _REPORTED_DISTANCE_RE.search(message.replace("\u066b", ".").replace("\u060c", "."))
    if match is None:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    return value if math.isfinite(value) and 0.0 <= value < 100_000.0 else None


def _distance(first: dict[str, Any], second: dict[str, Any]) -> float:
    a, b = math.radians(first["Latitude"]), math.radians(second["Latitude"])
    dlat = b - a
    dlon = math.radians(second["Longitude"] - first["Longitude"])
    h = math.sin(dlat / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(dlon / 2) ** 2
    return 12742.0 * math.asin(math.sqrt(min(1.0, max(0.0, h))))


def prepare_shipping_trace(gps_list: Any, *, target_km: float = DEFAULT_TRACE_TARGET_KM) -> list[dict[str, Any]]:
    """Validate a chronological trace and explicitly label any virtual detour.

    The detour is a synthetic route point, never an Android or physical GPS
    observation. Input objects are copied so preparation is deterministic.

    ``target_km`` is the cumulative length the detour aims for when the trace
    is too short for UTCMS rule 4012. It is clamped UP to the documented
    default, so a caller can only ever escalate (see
    ``gps_shipping_manager._escalated_trace_target_km``), never weaken the
    2.0 km floor. Escalation matters because UTCMS measures ROAD distance and
    rejects an identical re-send forever.
    """
    if not isinstance(gps_list, list) or len(gps_list) < 2:
        raise ValueError("shipping trace requires an origin and destination")
    target = max(DEFAULT_TRACE_TARGET_KM, float(target_km))
    if not math.isfinite(target):
        raise ValueError("invalid shipping trace target")
    formatted: list[dict[str, Any]] = []
    for index, point in enumerate(gps_list):
        if not isinstance(point, dict):
            raise ValueError("invalid shipping trace point")

        def _get_field(*names: str, default: Any = None, _point: dict[str, Any] = point) -> Any:
            return next((_point[name] for name in names if _point.get(name) is not None), default)

        lat = shipping_number(_get_field("Latitude", "latitude", "lat"), -90, 90, "latitude")
        lon = shipping_number(_get_field("Longitude", "longitude", "lon", "lng"), -180, 180, "longitude")
        speed = shipping_number(_get_field("Speed", "speed", default=0), 0, 400, "speed")
        altitude = shipping_number(_get_field("Altitude", "altitude", "alt", default=1000), -500, 10000, "altitude")
        stamp = utc_shipping_timestamp(_get_field("Date", "date", "DateTime", "ts"))
        raw_type = _get_field("Type", "type", "waypoint_type", default=3 if index == len(gps_list) - 1 else 2)
        if isinstance(raw_type, bool) or str(raw_type) not in {"1", "2", "3"}:
            raise ValueError("invalid shipping point type")
        point_type = 2 if str(raw_type) == "1" else int(raw_type)
        if point_type != (3 if index == len(gps_list) - 1 else 2):
            raise ValueError("only the final shipping point may be the destination")
        if formatted and stamp < formatted[-1]["Date"]:
            raise ValueError("shipping trace timestamps must be chronological")
        item = {
            key: point[key]
            for key in ("Provider", "Provenance", "ObservedAt", "SampledAt", "DeviceSerial")
            if key in point
        }
        item.update(
            Latitude=lat,
            Longitude=lon,
            latitude=lat,
            longitude=lon,
            Speed=speed,
            speed=speed,
            Altitude=altitude,
            altitude=altitude,
            Date=stamp,
            date=stamp,
            DateTime=stamp,
            Type=point_type,
            type=point_type,
        )
        formatted.append(item)

    distance = sum(_distance(a, b) for a, b in zip(formatted, formatted[1:], strict=False))
    if distance >= target - TRACE_TARGET_MARGIN_KM:
        return formatted

    # Extend the last segment, retaining all earlier points and their chronology.
    pt_first, pt_last = formatted[-2:]
    segment = _distance(pt_first, pt_last)
    target_segment = target - (distance - segment)
    lat1, lon1 = math.radians(pt_first["Latitude"]), math.radians(pt_first["Longitude"])
    lat2, lon2 = math.radians(pt_last["Latitude"]), math.radians(pt_last["Longitude"])
    bearing = math.atan2(
        math.sin(lon2 - lon1) * math.cos(lat2),
        math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1),
    )

    def point_at(distance_km: float, heading: float) -> dict[str, Any]:
        angular = distance_km / 6371.0
        lat = math.asin(math.sin(lat1) * math.cos(angular) + math.cos(lat1) * math.sin(angular) * math.cos(heading))
        lon = lon1 + math.atan2(
            math.sin(heading) * math.sin(angular) * math.cos(lat1), math.cos(angular) - math.sin(lat1) * math.sin(lat)
        )
        return {"Latitude": math.degrees(lat), "Longitude": (math.degrees(lon) + 180) % 360 - 180}

    # A perpendicular excursion from the segment's first point is monotonic
    # in length at these distances, including identical anchors and the poles.
    lo, hi = 0.0, target_segment
    for _ in range(48):
        mid = (lo + hi) / 2
        candidate = point_at(mid, bearing + math.pi / 2)
        if _distance(pt_first, candidate) + _distance(candidate, pt_last) < target_segment:
            lo = mid
        else:
            hi = mid
    detour = point_at(hi, bearing + math.pi / 2)
    start = datetime.fromisoformat(pt_first["Date"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(pt_last["Date"].replace("Z", "+00:00"))
    stamp = utc_shipping_timestamp(start + (end - start) / 2)
    detour.update(
        latitude=detour["Latitude"],
        longitude=detour["Longitude"],
        Speed=35.0,
        speed=35.0,
        Altitude=1000.0,
        altitude=1000.0,
        Date=stamp,
        date=stamp,
        DateTime=stamp,
        Type=2,
        type=2,
        Provider="virtual_route",
        Provenance="simulated_detour",
    )
    formatted.insert(-1, detour)
    return formatted
