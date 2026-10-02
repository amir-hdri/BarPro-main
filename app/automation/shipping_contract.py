"""Validation for UTCMS shipping payloads and business acknowledgements."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any


def utc_shipping_timestamp(value: str | datetime) -> str:
    """Convert an aware timestamp to the exact UTCMS wire format; never guess a zone."""
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


def shipping_acknowledged(response: dict[str, Any], *, start: bool = False) -> bool:
    code = response.get("resultCode")
    if type(code) is int and code in (0, 200):
        return True
    message = str(response.get("resultMessage") or "").replace("\u200c", "").replace("ي", "ی")
    if start and code == 4006:
        return "شروع حمل" in message and ("نمی توان" in message or "نمیتوان" in message)
    if not start and code == 4011:
        acknowledged = "تایید شد" in message or "تأیید شد" in message
        return "پایان حمل" in message and "خوداظهاری" in message and acknowledged and "نشده" not in message
    return False


def _distance(first: dict[str, Any], second: dict[str, Any]) -> float:
    a, b = math.radians(first["Latitude"]), math.radians(second["Latitude"])
    dlat = b - a
    dlon = math.radians(second["Longitude"] - first["Longitude"])
    h = math.sin(dlat / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(dlon / 2) ** 2
    return 12742.0 * math.asin(math.sqrt(min(1.0, max(0.0, h))))


def prepare_shipping_trace(gps_list: Any) -> list[dict[str, Any]]:
    """Validate a chronological trace and explicitly label any virtual detour.

    The detour is a synthetic route point, never an Android or physical GPS
    observation. Input objects are copied so preparation is deterministic.
    """
    if not isinstance(gps_list, list) or len(gps_list) < 2:
        raise ValueError("shipping trace requires an origin and destination")
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
    if distance >= 2.05:
        return formatted

    # Extend the last segment, retaining all earlier points and their chronology.
    pt_first, pt_last = formatted[-2:]
    segment = _distance(pt_first, pt_last)
    target_segment = 2.15 - (distance - segment)
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
