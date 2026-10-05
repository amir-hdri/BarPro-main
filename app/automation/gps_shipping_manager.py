"""Server-managed shipping lifecycle and GPS evidence state.

The operator registers the route; there is no driver-side Android agent. The
interpolated route is a planning/display artifact only. ``gps_list`` is the
separate evidence list and must contain only explicitly supplied anchors or
future live tracking observations.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import secrets
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0
TEHRAN_TZ = ZoneInfo("Asia/Tehran")

ROAD_DETOUR_FACTOR = 1.25  # ضریب پیچ‌وخم جاده نسبت به خط مستقیم هوایی (Haversine)
AVERAGE_TRUCK_SPEED_KMH = 65.0  # سرعت متوسط واقع‌گرایانه کامیون حمل بار در جاده‌های برون‌شهری (کیلومتر بر ساعت)

# --- Default city coordinates fallback when user did not provide lat/lng ---
DEFAULT_CITY_COORDS: dict[str, tuple[float, float]] = {
    # مراکز استان‌ها
    "تهران": (35.6892, 51.3890),
    "اصفهان": (32.6546, 51.6680),
    "مشهد": (36.2972, 59.6067),
    "شیراز": (29.5918, 52.5837),
    "تبریز": (38.0962, 46.2738),
    "اهواز": (31.3183, 48.6706),
    "کرج": (35.8327, 50.9915),
    "قم": (34.6401, 50.8764),
    "کرمانشاه": (34.3142, 47.0650),
    "ارومیه": (37.5528, 45.0761),
    "رشت": (37.2808, 49.5831),
    "زاهدان": (29.4963, 60.8629),
    "همدان": (34.7989, 48.5150),
    "کرمان": (30.2839, 57.0834),
    "یزد": (31.8974, 54.3569),
    "اردبیل": (38.2498, 48.2933),
    "بندرعباس": (27.1832, 56.2666),
    "بندر عباس": (27.1832, 56.2666),
    "اراک": (34.0954, 49.7013),
    "زنجان": (36.6736, 48.4787),
    "سنندج": (35.3219, 46.9862),
    "قزوین": (36.2797, 50.0049),
    "خرم‌آباد": (33.4878, 48.3558),
    "خرم آباد": (33.4878, 48.3558),
    "گرگان": (36.8427, 54.4439),
    "ساری": (36.5633, 53.0601),
    "بجنورد": (37.4747, 57.3290),
    "بوشهر": (28.9234, 50.8203),
    "بیرجند": (32.8663, 59.2211),
    "ایلام": (33.6374, 46.4227),
    "شهرکرد": (32.3256, 50.8644),
    "شهر کرد": (32.3256, 50.8644),
    "سمنان": (35.5769, 53.3970),
    "یاسوج": (30.6684, 51.5876),
    # بنادر، قطب‌های ترانزیتی و شهرهای بزرگ
    "کاشان": (33.9850, 51.4100),
    "ساوه": (35.0213, 50.3566),
    "دزفول": (32.3811, 48.4058),
    "آبادان": (30.3392, 48.3044),
    "خرمشهر": (30.4397, 48.1794),
    "ماهشهر": (30.5589, 49.1917),
    "بندر امام خمینی": (30.4333, 49.0833),
    "بندرامام": (30.4333, 49.0833),
    "چابهار": (25.2919, 60.6430),
    "عسلویه": (27.4761, 52.6078),
    "سیرجان": (29.4520, 55.6814),
    "رفسنجان": (30.4067, 55.9939),
    "نیشابور": (36.2133, 58.7958),
    "شاهرود": (36.4182, 54.9763),
    "سبزوار": (36.2126, 57.6750),
    "نجف آباد": (32.6342, 51.3668),
    "نجف‌آباد": (32.6342, 51.3668),
    "خمینی شهر": (32.7000, 51.5211),
    "شاهین شهر": (32.8642, 51.5478),
    "شهرضا": (31.9967, 51.8656),
    "مبارکه": (32.3486, 51.5042),
    "ورامین": (35.3242, 51.6472),
    "شهریار": (35.6597, 51.0592),
    "اسلامشهر": (35.5392, 51.2333),
    "ملارد": (35.6658, 50.9767),
    "پاکدشت": (35.5306, 51.6811),
    "دماوند": (35.7194, 52.0639),
    "فیروزکوه": (35.7569, 52.7708),
    "مرودشت": (29.8742, 52.8028),
    "جهرم": (28.5000, 53.5600),
    "فسا": (28.9383, 53.6483),
    "لار": (27.6833, 54.3333),
    "لامرد": (27.3339, 53.1789),
    "آمل": (36.4678, 52.3589),
    "بابل": (36.5514, 52.6789),
    "قائم شهر": (36.4642, 52.8597),
    "قائم‌شهر": (36.4642, 52.8597),
    "بهشهر": (36.6931, 53.5514),
    "تنکابن": (36.8164, 50.8739),
    "چالوس": (36.6550, 51.4206),
    "نوشهر": (36.6489, 51.4961),
    "رامسر": (36.9169, 50.6481),
    "لاهیجان": (37.2078, 50.0033),
    "بندرانزلی": (37.4747, 49.4608),
    "بندر انزلی": (37.4747, 49.4608),
    "لنگرود": (37.1972, 50.1536),
    "تالش": (37.8014, 48.9058),
    "آستارا": (38.4292, 48.8719),
    "مراغه": (37.3917, 46.2394),
    "مرند": (38.4331, 45.7750),
    "میانه": (37.4239, 47.7144),
    "شوشتر": (32.0456, 48.8567),
    "بهبهان": (30.5958, 50.2417),
    "مسجدسلیمان": (31.9364, 49.3039),
    "شوش": (32.1942, 48.2436),
    "ایذه": (31.8328, 49.8694),
    "امیدیه": (30.7597, 49.7050),
    "اندیمشک": (32.4600, 48.3561),
    "رامهرمز": (31.2800, 49.6047),
    "کنگان": (27.8339, 52.0628),
    "گناوه": (29.5792, 50.5178),
    "بندر گناوه": (29.5792, 50.5178),
    "دیر": (27.8533, 51.9378),
    "طبس": (33.5958, 56.9244),
    "قائن": (33.7278, 59.1844),
    "فردوس": (34.0186, 58.1722),
    "اردکان": (32.3100, 54.0175),
    "میبد": (32.2500, 54.0167),
    "بافق": (31.6036, 55.4056),
    "ملایر": (34.2969, 48.8236),
    "نهاوند": (34.1886, 48.3769),
    "بروجرد": (33.8973, 48.7516),
    "دورود": (33.4936, 49.0750),
    "الیگودرز": (33.4006, 49.6947),
    "گنبد کاووس": (37.2500, 55.1672),
    "گنبدکاووس": (37.2500, 55.1672),
    "سقز": (36.2497, 46.2733),
    "مریوان": (35.5269, 46.1761),
    "بانه": (35.9975, 45.8853),
    "قروه": (35.1664, 47.8044),
    "زابل": (31.0309, 61.4947),
    "ایرانشهر": (27.2025, 60.6847),
    "خوی": (38.5503, 44.9525),
    "بوکان": (36.5208, 46.2089),
    "مهاباد": (36.7631, 45.7222),
    "میاندوآب": (36.9678, 46.1039),
    "پارس آباد": (39.6483, 47.9172),
    "قشم": (26.9583, 56.2719),
    "کیش": (26.5578, 53.9790),
    "مهران": (33.1222, 46.1647),
    "شلمچه": (30.4900, 48.0600),
    "جلفا": (38.9372, 45.6294),
    "بازرگان": (39.3900, 44.3800),
    "سرخس": (36.5442, 61.1578),
    # شهرهای تکمیلی جهت تطبیق زمان‌بندی و بارنامه‌ها
    "کاشمر": (35.2383, 58.4656),
    "شوط": (39.2192, 45.0253),
    "دیزج": (39.2550, 45.0100),
    "مرگان": (39.1120, 45.0600),
    "طالقان": (36.1764, 50.7633),
    "میر": (36.1800, 50.7500),
    "کشرود": (36.1900, 50.7800),
    "ماکو": (39.2974, 44.5126),
    "پلدشت": (39.3497, 45.0689),
    "چالدران": (39.0633, 44.3892),
    "سیه چشمه": (39.0633, 44.3892),
    "چایپاره": (38.8500, 45.0833),
    "قره ضیاءالدین": (38.8500, 45.0833),
    "سلماس": (38.1969, 44.7644),
    "پیرانشهر": (36.6969, 45.1436),
    "نقده": (36.9553, 45.3881),
    "اشنویه": (37.0400, 45.0983),
    "سردشت": (36.1558, 45.4789),
    "تکاب": (36.4008, 47.1128),
    "شاهین دژ": (36.6789, 46.5683),
    "شاهین‌دژ": (36.6789, 46.5683),
}


def _mask_national_code(national_code: str | None) -> str:
    """Mask an Iranian national code for logs: show only the last 2 digits."""
    digits = re.sub(r"\D", "", str(national_code or ""))
    if len(digits) <= 2:
        return "***"
    return "*" * (len(digits) - 2) + digits[-2:]


def normalize_city_name(name: str | None) -> str:
    """نرمال‌سازی نام شهر برای جستجوی دقیق مختصات."""
    if not name or not isinstance(name, str):
        return ""

    cleaned = (
        name.strip()
        .replace("\u200c", "")
        .replace("\u200b", "")
        .replace("ي", "ی")
        .replace("ك", "ک")
        .replace("ة", "ه")
        .replace("آ", "ا")
    )
    return re.sub(r"^(شهر|شهرستان|استان)\s+", "", cleaned).strip()


def find_city_coordinates(city_name: str | None) -> tuple[float, float] | None:
    """یافتن مختصات جغرافیایی یک شهر بر اساس نام فارسی با جستجوی تطبیقی."""
    if not city_name:
        return None
    raw = city_name.strip()
    if raw in DEFAULT_CITY_COORDS:
        return DEFAULT_CITY_COORDS[raw]

    normalized = normalize_city_name(city_name)
    if not normalized:
        return None

    for key, coords in DEFAULT_CITY_COORDS.items():
        if normalize_city_name(key) == normalized:
            return coords

    for key, coords in DEFAULT_CITY_COORDS.items():
        norm_key = normalize_city_name(key)
        if norm_key in normalized or normalized in norm_key:
            return coords

    return None


# ──────────────────── Haversine & Interpolation ────────────────────


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance between two points in kilometres (as-the-crow-flies)."""
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def calculate_realistic_road_distance(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    detour_factor: float = ROAD_DETOUR_FACTOR,
) -> float:
    """محاسبه مسافت واقعی جاده‌ای بین دو نقطه با اعمال ضریب پیچ‌وخم جاده (Detour Factor).
    فاصله مستقیم هوایی (Haversine) ضرب در ضریب ۱.۲۵ می‌شود تا فاصله واقعی جاده‌ای به دست آید.
    در صورت یکسان بودن مبدأ و مقصد، حداقل فاصله ۱۰ کیلومتر شهری لحاظ می‌شود.
    """
    direct_km = haversine_km(lat1, lon1, lat2, lon2)
    if direct_km < 0.5:
        return 0.0
    return round(direct_km * detour_factor, 1)


def estimate_travel_duration_hours(
    distance_km: float,
    avg_speed_kmh: float = AVERAGE_TRUCK_SPEED_KMH,
) -> float:
    """تخمین زمان سیر حمل بار به ساعت بر اساس سرعت متوسط کامیون."""
    return round(distance_km / max(avg_speed_kmh, 10.0), 2)


@dataclass(slots=True)
class GpsWaypoint:
    lat: float
    lon: float
    speed_kmh: float = 0.0
    cumulative_km: float = 0.0
    waypoint_type: int = 2  # 1=origin, 2=intermediate, 3=destination
    timestamp: str = ""
    address: str = ""


def interpolate_waypoints(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    num_steps: int = 8,
    avg_speed_kmh: float = AVERAGE_TRUCK_SPEED_KMH,
    origin_address: str = "",
    dest_address: str = "",
) -> list[GpsWaypoint]:
    """Generate *num_steps* intermediate waypoints between origin and destination.

    Returns a list of ``num_steps + 2`` points (origin + intermediates + destination).
    Each point has cumulative km (realistic road distance), realistic speed, and UTC timestamp.
    """
    total_km = calculate_realistic_road_distance(origin_lat, origin_lon, dest_lat, dest_lon)
    total_hours = total_km / max(avg_speed_kmh, 10.0)
    now = datetime.now(UTC)

    points: list[GpsWaypoint] = []

    # Origin
    points.append(
        GpsWaypoint(
            lat=origin_lat,
            lon=origin_lon,
            speed_kmh=0.0,
            cumulative_km=0.0,
            waypoint_type=1,
            timestamp=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            address=origin_address,
        )
    )

    # Intermediate points
    for i in range(1, num_steps + 1):
        frac = i / (num_steps + 1)
        lat = origin_lat + frac * (dest_lat - origin_lat)
        lon = origin_lon + frac * (dest_lon - origin_lon)
        cum_km = round(total_km * frac, 2)
        ts = now + timedelta(hours=total_hours * frac)
        speed = avg_speed_kmh * (0.85 + 0.3 * (i % 3) / 3)  # slight variation
        points.append(
            GpsWaypoint(
                lat=round(lat, 6),
                lon=round(lon, 6),
                speed_kmh=round(speed, 1),
                cumulative_km=cum_km,
                waypoint_type=2,
                timestamp=ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
        )

    # Destination
    ts_end = now + timedelta(hours=total_hours)
    points.append(
        GpsWaypoint(
            lat=dest_lat,
            lon=dest_lon,
            speed_kmh=0.0,
            cumulative_km=round(total_km, 2),
            waypoint_type=3,
            timestamp=ts_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            address=dest_address,
        )
    )
    return points


# ──────────────────── Payload Address Extraction ────────────────────


def extract_coordinates_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract origin and destination coordinates and addresses from a waybill
    ``payload_json``.  This preserves the **exact** address the user entered.

    Returns dict with keys:
        origin_lat, origin_lng, origin_address, origin_city,
        dest_lat, dest_lng, dest_address, dest_city, distance_km
    """

    def _float(v: Any) -> float | None:
        if not isinstance(v, (int, float, str)) or isinstance(v, bool):
            return None
        if isinstance(v, str):
            v = v.strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
            if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", v):
                return None
        try:
            value = float(v)
            return value if math.isfinite(value) else None
        except (TypeError, ValueError, OverflowError):
            return None

    def _safe_dict(raw: Any) -> dict[str, Any]:
        return raw if isinstance(raw, dict) else {}

    def _first(*values: Any) -> Any:
        return next((value for value in values if value is not None), None)

    def _resolve_nested_coords(
        flat_lat: float | None,
        flat_lng: float | None,
        meta_section: dict[str, Any],
        top_section: dict[str, Any],
    ) -> tuple[float | None, float | None]:
        """Select one complete valid pair; never mix coordinates across sources.

        Priority (matches the new waybill form which writes real pins into
        metadata_json.*.coordinates):
          1. meta_section.coordinates.{lat,lng}
          2. top_section.coordinates.{lat,lng}
          3. flat coordinates           (legacy)
          4. meta_section.{lat,lng}      (legacy)
          5. top_section.{lat,lng}       (legacy)
        """
        for raw in (
            meta_section.get("coordinates"),
            top_section.get("coordinates"),
            {"lat": flat_lat, "lng": flat_lng},
            meta_section,
            top_section,
        ):
            coords = _safe_dict(raw)
            lat = _float(_first(coords.get("lat"), coords.get("latitude")))
            lng = _float(_first(coords.get("lng"), coords.get("lon"), coords.get("longitude")))
            if lat is not None and lng is not None and -90 <= lat <= 90 and -180 <= lng <= 180 and (lat, lng) != (0, 0):
                return lat, lng
        return None, None

    # ── Parse metadata_json once ──
    meta = payload.get("metadata_json") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except (TypeError, json.JSONDecodeError):
            logger.debug("gps_payload_metadata_invalid_json")
            meta = {}
    meta = _safe_dict(meta)
    # A canonical object (even an empty one) takes precedence over its alias.
    origin_meta: dict[str, Any] = next(
        (meta[key] for key in ("origin", "source") if isinstance(meta.get(key), dict)), {}
    )
    dest_meta: dict[str, Any] = next(
        (meta[key] for key in ("destination", "dest") if isinstance(meta.get(key), dict)), {}
    )

    # ── Origin coordinates ──
    origin_lat, origin_lng = _resolve_nested_coords(
        flat_lat=_float(
            _first(
                payload.get("origin_lat"),
                payload.get("originLat"),
                payload.get("origin_latitude"),
                payload.get("sourceLatM"),
                payload.get("latitude") if not payload.get("dest_lat") else None,
            )
        ),
        flat_lng=_float(
            _first(
                payload.get("origin_lng"),
                payload.get("originLng"),
                payload.get("origin_longitude"),
                payload.get("sourceLngM"),
                payload.get("sourceLonM"),
                payload.get("longitude") if not payload.get("dest_lng") else None,
            )
        ),
        meta_section=origin_meta,
        top_section=_safe_dict(payload.get("origin")),
    )

    # ── Destination coordinates ──
    dest_lat, dest_lng = _resolve_nested_coords(
        flat_lat=_float(
            _first(
                payload.get("dest_lat"),
                payload.get("destLat"),
                payload.get("dest_latitude"),
                payload.get("destination_lat"),
                payload.get("destLatM"),
            )
        ),
        flat_lng=_float(
            _first(
                payload.get("dest_lng"),
                payload.get("destLng"),
                payload.get("dest_longitude"),
                payload.get("destination_lng"),
                payload.get("destLngM"),
                payload.get("destLonM"),
            )
        ),
        meta_section=dest_meta,
        top_section=_safe_dict(payload.get("destination")),
    )

    # ── Addresses — EXACT user input ──
    # Reuse meta sections for city/address fallback lookup.
    origin_city = str(
        payload.get("origin")
        or payload.get("citySourceMap")
        or payload.get("sourceCity")
        or payload.get("OriginCity")
        or origin_meta.get("city")
        or ""
    ).strip()
    origin_address = str(
        payload.get("origin_address")
        or payload.get("originAddress")
        or payload.get("AddressSource")
        or payload.get("addressSource")
        or payload.get("sourceAddress")
        or origin_meta.get("address")
        or origin_city
    ).strip()

    dest_city = str(
        payload.get("destination")
        or payload.get("CityDestMap")
        or payload.get("destCity")
        or payload.get("DestCity")
        or dest_meta.get("city")
        or ""
    ).strip()
    dest_address = str(
        payload.get("dest_address")
        or payload.get("destAddress")
        or payload.get("destinationAddress")
        or payload.get("AddressDest")
        or payload.get("addressDest")
        or dest_meta.get("address")
        or dest_city
    ).strip()

    if origin_lat is None or origin_lng is None:
        coords = find_city_coordinates(origin_city) or find_city_coordinates(origin_address)
        if coords:
            origin_lat, origin_lng = coords
    if dest_lat is None or dest_lng is None:
        coords = find_city_coordinates(dest_city) or find_city_coordinates(dest_address)
        if coords:
            dest_lat, dest_lng = coords

    distance_km = 0.0
    direct_distance_km = 0.0
    duration_hours = 0.0
    duration_minutes = 0
    if origin_lat is not None and origin_lng is not None and dest_lat is not None and dest_lng is not None:
        direct_distance_km = round(haversine_km(origin_lat, origin_lng, dest_lat, dest_lng), 2)
        distance_km = calculate_realistic_road_distance(origin_lat, origin_lng, dest_lat, dest_lng)
        duration_hours = estimate_travel_duration_hours(distance_km)
        duration_minutes = int(round(duration_hours * 60))

    return {
        "origin_lat": origin_lat,
        "origin_lng": origin_lng,
        "origin_address": origin_address,
        "origin_city": origin_city,
        "dest_lat": dest_lat,
        "dest_lng": dest_lng,
        "dest_address": dest_address,
        "dest_city": dest_city,
        "distance_km": distance_km,
        "direct_distance_km": direct_distance_km,
        "duration_hours": duration_hours,
        "duration_minutes": duration_minutes,
        "estimated_duration_text": (
            f"{int(duration_hours)} ساعت و {duration_minutes % 60} دقیقه"
            if duration_hours >= 1
            else f"{duration_minutes} دقیقه"
        ),
    }


# ──────────────────── Redis Session Vault ────────────────────

# Driver national codes are NOT tenant-unique: the same driver can work for
# several clients. Every vault key therefore carries the client (tenant) id
# (see _scoped_driver_key). The legacy unscoped key shape
# ("utcms:driver:token:{national_code}") is used ONLY when a caller cannot
# provide a tenant; scoped lookups NEVER fall back to it, so a tenant can
# never read another tenant's cached session.
SHIPPING_STATE_KEY = "utcms:shipping:job:{job_id}"
# Unified with the manual-mutation lock in shipping_gps._shipping_mutation_lock,
# so /start, /finish and the Beat auto-complete all contend for ONE key per trip.
COMPLETION_CLAIM_KEY = "lock:shipping:{job_id}"
# Rolling-deploy compatibility, added 2026-10-03: in Model B the Central node is
# updated while Workers 2/3 still run the previous image, which claims the OLD
# key. Acquiring BOTH keys means the two generations cannot both reach
# RegisterEndOfShipping for the same trip during the cutover.
# REMOVE this legacy key (and its acquire/release handling) in the release AFTER
# the whole fleet runs an image containing COMPLETION_CLAIM_KEY.
LEGACY_COMPLETION_CLAIM_KEY = "utcms:shipping:claim:{job_id}"
# Beat cadence is 120s; a 15-minute claim TTL bounds a claim left behind by a
# crashed worker while still covering the slowest UTCMS round-trips. The stuck
# fence reclaim (reclaim_stuck_shipping_fences) uses the same TTL as its
# "nobody is working on this any more" threshold.
COMPLETION_CLAIM_TTL_SECONDS = 900

# A terminal registration that keeps being refused must not retry forever: past
# this many attempts the trip is parked in a non-looping state for an operator.
MAX_COMPLETION_ATTEMPTS = 8

# UTCMS codes that mean "not yet, come back later" rather than "what you sent is
# wrong". They carry their own bounded schedules (rule 4013 -> 5 minutes, 429 ->
# 10/20/30 minutes capped at 1800s) and are therefore exempt from the attempt
# cap: a busy portal must not park a healthy trip in needs_review.
RETRY_LATER_CODES = (4013, 429)

# Shipping-state values that fence a trip while a worker owns its mutation.
# Neither is terminal: a worker killed mid-mutation leaves one behind, and
# without a reaper the trip is never completed and never surfaces as failed.
FENCE_STATUSES = ("finishing", "starting")

# Loop-aware per-driver auth locks, keyed (loop id, tenant scope, national code).
# asyncio.Lock binds to the loop that first awaits it; awaiting the same lock
# object from a second loop raises RuntimeError. get_shared_event_loop() gives
# every Celery thread its own loop, so locks are cached per running loop
# (mirroring traffic_control._get_loop_resources). The dict is bounded with
# FIFO eviction so it cannot grow without bound on national_code cardinality.
_AUTH_LOCKS_GUARD = threading.Lock()
_AUTH_LOCK_ENTRIES_MAX = 512
_LOCAL_AUTH_LOCKS: dict[tuple[int, str, str], tuple[asyncio.AbstractEventLoop, asyncio.Lock]] = {}


def _scoped_driver_key(kind: str, client_id: int | str | None, national_code: str) -> str:
    """Build the tenant-scoped Redis key for a driver session-vault entry.

    ``kind`` is one of "token" | "refresh" | "auth-lock". The client (tenant)
    id is part of the key because driver national codes are not tenant-unique:
    two tenants sharing a driver must never share UTCMS sessions. Callers
    without a tenant get the legacy unscoped key; scoped lookups NEVER fall
    back to it, so cross-tenant reads are impossible by construction.
    """
    scope = "" if client_id is None else f"{client_id}:"
    return f"utcms:driver:{kind}:{scope}{national_code}"


def _get_auth_lock(national_code: str, tenant_scope: str = "") -> asyncio.Lock:
    """Return the process-local auth lock for (running loop, tenant, driver).

    Loop-aware: each event loop gets its own lock object, so a lock awaited on
    the ASGI loop is never awaited from a Celery thread loop (RuntimeError).
    Guarded by a threading.Lock for setdefault-style init (init race is a
    thread-level concern, not an awaitable one). FIFO-evicts the oldest entry
    when the cache reaches _AUTH_LOCK_ENTRIES_MAX.
    """
    loop = asyncio.get_running_loop()
    key = (id(loop), tenant_scope, national_code)
    with _AUTH_LOCKS_GUARD:
        entry = _LOCAL_AUTH_LOCKS.get(key)
        if entry is not None:
            cached_loop, lock = entry
            if cached_loop is loop and not cached_loop.is_closed():
                return lock
            # Stale entry (loop replaced/closed): drop and recreate below.
            del _LOCAL_AUTH_LOCKS[key]
        while len(_LOCAL_AUTH_LOCKS) >= _AUTH_LOCK_ENTRIES_MAX:
            _LOCAL_AUTH_LOCKS.pop(next(iter(_LOCAL_AUTH_LOCKS)))
        lock = asyncio.Lock()
        _LOCAL_AUTH_LOCKS[key] = (loop, lock)
        return lock


async def _get_redis():
    """Best-effort Redis accessor."""
    try:
        from app.core.redis import redis_manager

        return await redis_manager.get()
    except Exception:
        return None


async def get_cached_token(national_code: str, *, client_id: int | str | None = None) -> str | None:
    """Return cached UTCMS driver token from Redis, or None.

    ``client_id`` scopes the key to the tenant; two tenants sharing a driver
    national code never share a session.
    """
    r = await _get_redis()
    if r is None:
        return None
    try:
        # cast is a runtime no-op: the redis client is untyped (Any); the
        # token is stored as a string or absent (None).
        return cast("str | None", await r.get(_scoped_driver_key("token", client_id, national_code)))
    except Exception:
        return None


async def cache_token(
    national_code: str, token: str, ttl_seconds: int = 240, *, client_id: int | str | None = None
) -> None:
    """Store driver UTCMS bearer token in Redis with TTL (default 240s < 5m expiry)."""
    if not token or not str(token).strip():
        return
    r = await _get_redis()
    if r is None:
        return
    try:
        await r.set(_scoped_driver_key("token", client_id, national_code), str(token).strip(), ex=ttl_seconds)
    except Exception as exc:
        logger.warning("cache_token_failed: %s", exc)


async def cache_refresh_token(
    national_code: str, refresh_token: str, ttl_seconds: int = 7000, *, client_id: int | str | None = None
) -> None:
    """Store refresh token with TTL (default 7000s < 120m expiry)."""
    if not refresh_token or not str(refresh_token).strip():
        return
    r = await _get_redis()
    if r is None:
        return
    try:
        await r.set(_scoped_driver_key("refresh", client_id, national_code), str(refresh_token).strip(), ex=ttl_seconds)
    except Exception as exc:
        logger.warning("cache_refresh_token_failed: %s", exc)


async def get_cached_refresh_token(national_code: str, *, client_id: int | str | None = None) -> str | None:
    r = await _get_redis()
    if r is None:
        return None
    try:
        # cast is a runtime no-op: the redis client is untyped (Any); the
        # refresh token is stored as a string or absent (None).
        return cast("str | None", await r.get(_scoped_driver_key("refresh", client_id, national_code)))
    except Exception:
        return None


async def invalidate_cached_session(national_code: str, *, client_id: int | str | None = None) -> None:
    """Remove both cached credentials after UTCMS rejects authentication."""
    r = await _get_redis()
    if r is None:
        return
    try:
        await r.delete(
            _scoped_driver_key("token", client_id, national_code),
            _scoped_driver_key("refresh", client_id, national_code),
        )
    except Exception as exc:
        logger.warning("invalidate_cached_session_failed: %s", exc)


async def _release_auth_lock(redis: Any, key: str, token: str) -> None:
    script = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
        return redis.call('del', KEYS[1])
    end
    return 0
    """
    try:
        await redis.eval(script, 1, key, token)
    except Exception as exc:
        logger.warning("utcms_auth_lock_release_failed: %s", exc)


async def _acquire_auth_lock(redis: Any, key: str, *, wait_seconds: float = 30.0) -> str | None:
    token = secrets.token_urlsafe(24)
    deadline = asyncio.get_running_loop().time() + wait_seconds
    while True:
        try:
            if await redis.set(key, token, ex=120, nx=True):
                return token
        except Exception as exc:
            logger.warning("utcms_auth_lock_unavailable; using process-local lock: %s", exc)
            return None
        if asyncio.get_running_loop().time() >= deadline:
            raise RuntimeError("UTCMS authentication is already in progress")
        await asyncio.sleep(0.25)


def is_mobile_authentication_error(exc: BaseException) -> bool:
    """Return true only for explicit authentication rejection responses."""
    return bool(getattr(exc, "status_code", None) in {401, 403} or getattr(exc, "result_code", None) in {3000, 3001})


# Login retry policy: the portal flaps (non-JSON blips, 5xx, 429) and a single
# transient failure must not kill the whole attempt — tonight driver 7 failed
# once then succeeded seconds later. Bounded to 2 attempts; authoritative
# portal verdicts (result_code set, 401/403/444) are NEVER retried.
LOGIN_MAX_ATTEMPTS = 3
LOGIN_RETRY_DELAY_SECONDS = 2.0
_TRANSIENT_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


def _is_transient_login_error(exc: BaseException) -> bool:
    """True only for transport-level blips or CAPTCHA rejection worth retrying.

    A set ``result_code`` is an authoritative portal verdict (e.g. code 1,
    bad credentials) — retrying burns budget and risks lockout. 401/403/444
    are explicit refusals, not blips.
    EXCEPTION: code 4003 ("کد امنیتی صحیح نمی باشد") is a transient CAPTCHA solver
    misread; retrying fetches a fresh CAPTCHA challenge and retries.
    """
    from app.automation.utcms_mobile_client import UtcmsMobileApiError

    if not isinstance(exc, UtcmsMobileApiError):
        return False
    if exc.result_code is not None:
        rc_str = str(exc.result_code).strip()
        if rc_str == "4003" or "کد امنیتی" in str(exc):
            return True
        return False
    if exc.status_code is not None:
        return exc.status_code in _TRANSIENT_HTTP_STATUSES
    message = str(exc).lower()
    return "transport failed" in message or "non-json response" in message


async def _solve_and_login_with_retry(client: Any, national_code: str, password: str) -> Any:
    """Solve the login CAPTCHA and log in, retrying transient blips up to LOGIN_MAX_ATTEMPTS."""

    last_exc: Exception | None = None
    for attempt_no in range(1, LOGIN_MAX_ATTEMPTS + 1):
        try:
            solved = await client.auto_solve_captcha(form_id="login")
            cap_token = client.cap_token_from_solution(solved)
            if not cap_token:
                raise RuntimeError("UTCMS mobile CAPTCHA could not be solved")
            return await client.login(national_code, password, cap_token=cap_token)
        except Exception as exc:
            last_exc = exc
            if attempt_no >= LOGIN_MAX_ATTEMPTS or not _is_transient_login_error(exc):
                raise
            logger.warning(
                "session_vault_login_retry national_code=%s attempt=%d/%d error=%s",
                _mask_national_code(national_code),
                attempt_no,
                LOGIN_MAX_ATTEMPTS,
                exc,
            )
            await asyncio.sleep(LOGIN_RETRY_DELAY_SECONDS)
    assert last_exc is not None  # loop always breaks (return) or raises
    raise last_exc


async def get_or_login_client(
    national_code: str,
    password: str,
    proxy_url: str | None = None,
    *,
    force_reauth: bool = False,
    client_id: int | str | None = None,
) -> Any:
    """Get an authenticated UtcmsMobileClient, reusing cached token to avoid 429.

    1. Check Redis for cached token → use if valid.
    2. Check Redis for refresh token → call refresh if available.
    3. Only fall back to login() if nothing is cached.

    ``client_id`` scopes every vault key (token, refresh, auth lock) to the
    tenant; two tenants sharing a driver national code never share a session.
    """
    from app.automation.utcms_mobile_client import UtcmsMobileClient

    tenant_scope = "" if client_id is None else str(client_id)
    local_lock = _get_auth_lock(national_code, tenant_scope)
    async with local_lock:
        redis = await _get_redis()
        lock_key = _scoped_driver_key("auth-lock", client_id, national_code)
        lock_token: str | None = None
        if redis is not None:
            lock_token = await _acquire_auth_lock(redis, lock_key)
        try:
            if force_reauth:
                await invalidate_cached_session(national_code, client_id=client_id)

            cached = await get_cached_token(national_code, client_id=client_id)
            if cached:
                logger.info("session_vault_hit national_code=%s", _mask_national_code(national_code))
                return UtcmsMobileClient(token=cached, proxy_url=proxy_url)

            refresh = await get_cached_refresh_token(national_code, client_id=client_id)
            if refresh and refresh.strip():
                client = UtcmsMobileClient(proxy_url=proxy_url)
                try:
                    auth = await client.refresh(refresh.strip())
                    await cache_token(national_code, auth.token, client_id=client_id)
                    if auth.refresh_token:
                        await cache_refresh_token(national_code, auth.refresh_token, client_id=client_id)
                    logger.info("session_vault_refreshed national_code=%s", _mask_national_code(national_code))
                    return client
                except Exception as exc:
                    logger.warning("session_vault_refresh_failed: %s, falling back to login", exc)
                    await invalidate_cached_session(national_code, client_id=client_id)

            if not password or password in ("dummy", "") or str(password).strip() in ("dummy", ""):
                raise ValueError(f"رمز عبور راننده برای کد ملی '{national_code}' معتبر نیست")

            from app.automation.login_attempt_ledger import (
                AccountCooldownError,
                check_login_allowed,
                record_login_failure,
                record_login_success,
            )

            # P0-1: refuse locally while the account cools down — a fresh login
            # attempt against a distressed account risks a UTCMS-side lockout.
            allowed, cooldown_reason = await check_login_allowed(national_code)
            if not allowed:
                raise AccountCooldownError(national_code, cooldown_reason or "cooldown active")

            client = UtcmsMobileClient(proxy_url=proxy_url)
            try:
                auth = await _solve_and_login_with_retry(client, national_code, password)
            except Exception as exc:
                # Only authoritative portal verdicts (a set result_code) burned an
                # attempt; transport/infra blips belong to the egress layer.
                if getattr(exc, "result_code", None) is not None:
                    await record_login_failure(national_code, kind="mobile")
                raise
            await record_login_success(national_code)
            await cache_token(national_code, auth.token, client_id=client_id)
            if auth.refresh_token:
                await cache_refresh_token(national_code, auth.refresh_token, client_id=client_id)
            logger.info("session_vault_login national_code=%s", _mask_national_code(national_code))
            return client
        finally:
            if redis is not None and lock_token is not None:
                await _release_auth_lock(redis, lock_key, lock_token)


# ──────────────────── UTCMS Document Status Codes (تاریخچه اسناد حمل) ────────────────────

UTCMS_STATUS_ISSUED = 0  # صادر شده
UTCMS_STATUS_IN_TRANSIT = 1  # در حال حمل
UTCMS_STATUS_DELIVERED = 2  # پایان حمل
UTCMS_STATUS_CANCELLED = 3  # باطل شده

UTCMS_STATUS_MAP: dict[int, str] = {
    UTCMS_STATUS_ISSUED: "issued",
    UTCMS_STATUS_IN_TRANSIT: "in_transit",
    UTCMS_STATUS_DELIVERED: "delivered",
    UTCMS_STATUS_CANCELLED: "cancelled",
}

UTCMS_STATUS_LABELS_FA: dict[int, str] = {
    UTCMS_STATUS_ISSUED: "صادر شده",
    UTCMS_STATUS_IN_TRANSIT: "در حال حمل",
    UTCMS_STATUS_DELIVERED: "پایان حمل",
    UTCMS_STATUS_CANCELLED: "باطل شده",
}

# ──────────────────── Shipping State (Redis) ────────────────────


@dataclass
class ShippingState:
    job_id: str = ""
    doc_no: str = ""
    doc_id: str = ""
    status: str = "ready"  # ready | in_transit | finishing | delivered | failed | unknown
    origin_lat: float = 0.0
    origin_lng: float = 0.0
    origin_address: str = ""
    dest_lat: float = 0.0
    dest_lng: float = 0.0
    dest_address: str = ""
    distance_km: float = 0.0
    current_step: int = 0
    total_steps: int = 0
    traveled_km: float = 0.0
    created_at: str = ""
    estimated_end_at: str = ""
    # Planned/display route; never treat these points as GPS evidence.
    waypoints: list[dict[str, Any]] = field(default_factory=list)
    # Explicit operator/device observations eligible for UTCMS submission.
    gps_list: list[dict[str, Any]] = field(default_factory=list)
    # ── Route Authority snapshot (Phase 5): frozen at init so a future
    # Neshan response can never rewrite history. ──
    route_snapshot: dict[str, Any] = field(default_factory=dict)
    route_source: str = ""
    route_distance_km: float = 0.0
    route_duration_s: float = 0.0
    anchor_hash: str = ""
    coordinate_source: str = "map_pin"
    # ── Travel execution (Phases 6/12/13): arrival-driven auto-complete. ──
    travel_status: str = ""
    travel_progress: float = 0.0
    measured_distance_km: float = 0.0
    gps_provider: str = "operator_anchor"
    provenance: str = "operator_confirmed"
    # ── Completion retry & backoff tracking ──
    completion_attempts: int = 0
    last_attempt_at: str = ""
    backoff_until: str = ""
    last_error_code: int | str | None = None
    last_error_message: str = ""
    # Cumulative trace length the NEXT terminal attempt must reach, learned from
    # the distance UTCMS reports in a rule-4012 rejection (0.0 = contract default).
    required_distance_km: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "doc_no": self.doc_no,
            "doc_id": self.doc_id,
            "status": self.status,
            "origin_lat": self.origin_lat,
            "origin_lng": self.origin_lng,
            "origin_address": self.origin_address,
            "dest_lat": self.dest_lat,
            "dest_lng": self.dest_lng,
            "dest_address": self.dest_address,
            "distance_km": self.distance_km,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "traveled_km": self.traveled_km,
            "created_at": self.created_at,
            "estimated_end_at": self.estimated_end_at,
            "waypoints": self.waypoints,
            "gps_list": self.gps_list,
            "route_snapshot": self.route_snapshot,
            "route_source": self.route_source,
            "route_distance_km": self.route_distance_km,
            "route_duration_s": self.route_duration_s,
            "anchor_hash": self.anchor_hash,
            "coordinate_source": self.coordinate_source,
            "travel_status": self.travel_status,
            "travel_progress": self.travel_progress,
            "measured_distance_km": self.measured_distance_km,
            "gps_provider": self.gps_provider,
            "provenance": self.provenance,
            "completion_attempts": self.completion_attempts,
            "last_attempt_at": self.last_attempt_at,
            "backoff_until": self.backoff_until,
            "last_error_code": self.last_error_code,
            "last_error_message": self.last_error_message,
            "required_distance_km": self.required_distance_km,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ShippingState:
        return cls(
            job_id=d.get("job_id", ""),
            doc_no=d.get("doc_no", ""),
            doc_id=str(d.get("doc_id") or ""),
            status=d.get("status", "ready"),
            origin_lat=d.get("origin_lat", 0.0),
            origin_lng=d.get("origin_lng", 0.0),
            origin_address=d.get("origin_address", ""),
            dest_lat=d.get("dest_lat", 0.0),
            dest_lng=d.get("dest_lng", 0.0),
            dest_address=d.get("dest_address", ""),
            distance_km=d.get("distance_km", 0.0),
            current_step=d.get("current_step", 0),
            total_steps=d.get("total_steps", 0),
            traveled_km=d.get("traveled_km", 0.0),
            created_at=str(d.get("created_at") or ""),
            estimated_end_at=str(d.get("estimated_end_at") or ""),
            waypoints=d.get("waypoints", []) if isinstance(d.get("waypoints"), list) else [],
            gps_list=d.get("gps_list", []) if isinstance(d.get("gps_list"), list) else [],
            route_snapshot=d.get("route_snapshot", {}) if isinstance(d.get("route_snapshot"), dict) else {},
            route_source=str(d.get("route_source") or ""),
            route_distance_km=float(d.get("route_distance_km") or 0.0),
            route_duration_s=float(d.get("route_duration_s") or 0.0),
            anchor_hash=str(d.get("anchor_hash") or ""),
            coordinate_source=str(d.get("coordinate_source") or "map_pin"),
            travel_status=str(d.get("travel_status") or ""),
            travel_progress=float(d.get("travel_progress") or 0.0),
            measured_distance_km=float(d.get("measured_distance_km") or 0.0),
            gps_provider=str(d.get("gps_provider") or "operator_anchor"),
            provenance=str(d.get("provenance") or "operator_confirmed"),
            completion_attempts=int(d.get("completion_attempts") or 0),
            last_attempt_at=str(d.get("last_attempt_at") or ""),
            backoff_until=str(d.get("backoff_until") or ""),
            last_error_code=d.get("last_error_code"),
            last_error_message=str(d.get("last_error_message") or ""),
            required_distance_km=float(d.get("required_distance_km") or 0.0),
        )


class ShippingStatePersistenceError(RuntimeError):
    """Raised when shipping state cannot be durably recorded."""


async def _persist_shipping_state_db(state: ShippingState) -> bool:
    """Mirror state into the Job result envelope for recovery after Redis loss."""
    try:
        from sqlmodel import select

        from app.core.database import async_session_factory
        from app.models_multitenant import WaybillJob

        async with async_session_factory() as session:
            job = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == state.job_id))).first()
            if job is None:
                return False
            result = dict(job.result_json or {})
            result["_shipping_state"] = state.to_dict()
            job.result_json = result
            job.updated_at = datetime.now(UTC).replace(tzinfo=None)
            session.add(job)
            await session.commit()
            return True
    except Exception as exc:
        logger.error("shipping_state_db_persist_failed", exc_info=True)
        raise ShippingStatePersistenceError("ذخیره پایدار وضعیت حمل ممکن نیست") from exc


async def save_shipping_state(state: ShippingState) -> None:
    """Persist state in Redis and the Job envelope; never silently drop it."""
    serialized = json.dumps(state.to_dict(), ensure_ascii=False, allow_nan=False)
    r = await _get_redis()
    redis_saved = False
    if r is not None:
        try:
            key = SHIPPING_STATE_KEY.format(job_id=state.job_id)
            await r.set(key, serialized, ex=7 * 86400)
            redis_saved = True
        except Exception:
            logger.error("shipping_state_redis_persist_failed", exc_info=True)
    db_saved = await _persist_shipping_state_db(state)
    if not redis_saved and not db_saved:
        raise ShippingStatePersistenceError("ذخیره وضعیت حمل در Redis و پایگاه داده شکست خورد")


async def load_shipping_state(job_id: str) -> ShippingState | None:
    r = await _get_redis()
    if r is not None:
        try:
            raw = await r.get(SHIPPING_STATE_KEY.format(job_id=job_id))
            if raw is not None:
                return ShippingState.from_dict(json.loads(raw))
        except Exception:
            logger.error("shipping_state_redis_load_failed", exc_info=True)
    try:
        from sqlmodel import select

        from app.core.database import async_session_factory
        from app.models_multitenant import WaybillJob

        async with async_session_factory() as session:
            job = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == job_id))).first()
            if job is None:
                return None
            stored = (job.result_json or {}).get("_shipping_state")
            return ShippingState.from_dict(stored) if isinstance(stored, dict) else None
    except Exception as exc:
        logger.error("shipping_state_db_load_failed", exc_info=True)
        raise ShippingStatePersistenceError("خواندن پایدار وضعیت حمل ممکن نیست") from exc


async def init_shipping(
    job_id: str,
    doc_no: str,
    payload: dict[str, Any],
    num_steps: int = 8,
    persist: bool = True,
    doc_id: str = "",
) -> ShippingState:
    """Initialize shipping state from waybill payload with exact user addresses."""
    info = extract_coordinates_from_payload(payload)
    required = (info["origin_lat"], info["origin_lng"], info["dest_lat"], info["dest_lng"])
    if any(value is None for value in required):
        raise ValueError("مختصات واقعی مبدأ و مقصد برای فعال‌سازی GPS الزامی است")
    olat, olng, dlat, dlng = (float(value) for value in required)

    waypoints = interpolate_waypoints(
        olat,
        olng,
        dlat,
        dlng,
        num_steps=num_steps,
        origin_address=info["origin_address"],
        dest_address=info["dest_address"],
    )

    now_utc = datetime.now(UTC)
    distance_km = float(info.get("distance_km") or 0.0)
    duration_hours = estimate_travel_duration_hours(distance_km)
    min_minutes = 20.0
    duration_minutes = max(duration_hours * 60.0, min_minutes)
    estimated_end = now_utc + timedelta(minutes=duration_minutes)

    state = ShippingState(
        job_id=job_id,
        doc_no=doc_no,
        doc_id=str(doc_id or ""),
        status="ready",
        origin_lat=olat,
        origin_lng=olng,
        origin_address=info["origin_address"],
        dest_lat=dlat,
        dest_lng=dlng,
        dest_address=info["dest_address"],
        distance_km=distance_km,
        current_step=0,
        total_steps=len(waypoints) - 1,
        traveled_km=0.0,
        created_at=now_utc.isoformat(),
        estimated_end_at=estimated_end.isoformat(),
        waypoints=[
            {
                "lat": wp.lat,
                "lon": wp.lon,
                "speed": wp.speed_kmh,
                "cum_km": wp.cumulative_km,
                "type": wp.waypoint_type,
                "ts": wp.timestamp,
                "address": wp.address,
            }
            for wp in waypoints
        ],
        gps_list=[],
        coordinate_source="map_pin",
    )
    # Freeze the canonical route snapshot (best-effort: never block init).
    try:
        from app.services.route_authority import resolve_route

        snapshot = await resolve_route(olat, olng, dlat, dlng)
        state.route_snapshot = snapshot
        state.route_source = str(snapshot.get("source") or "")
        state.route_distance_km = float(snapshot.get("distance_km") or 0.0)
        state.route_duration_s = float(snapshot.get("duration_s") or 0.0)
        state.anchor_hash = str(snapshot.get("anchor_hash") or "")
        if not state.distance_km and state.route_distance_km:
            state.distance_km = state.route_distance_km
            duration_hours = estimate_travel_duration_hours(state.distance_km)
            duration_minutes = max(duration_hours * 60.0, min_minutes)
            state.estimated_end_at = (now_utc + timedelta(minutes=duration_minutes)).isoformat()
    except Exception:
        logger.warning("init_shipping_route_snapshot_failed job=%s", job_id, exc_info=True)
    if persist:
        await save_shipping_state(state)
    return state


def shipping_wait_reason(state: ShippingState, now: datetime | None = None) -> dict[str, Any] | None:
    """Enforce persisted cooldown and physical ETA on every entry point.

    A MISSING ETA is "not yet due", never "due now". The arrival gate that used
    to sit in front of the terminal POST is gone, so the ETA is the only
    client-side trigger left; treating a blank one as satisfied made such an
    envelope due immediately with nothing left to stop it. Fail closed instead
    and let an operator force completion explicitly (``force=True``).

    A CORRUPT value is still logged with context and treated as "no wait" — the
    fail-closed mutation gates and UTCMS rule 4013 are the real backstops, and
    a typo must not permanently dead-end a real trip. The cooldown is evaluated
    before the ETA so a corrupt-cooldown diagnostic is never skipped.
    """
    stamp = now or datetime.now(UTC)
    for field_name, status in (("backoff_until", "backoff"), ("estimated_end_at", "waiting_eta")):
        raw = getattr(state, field_name)
        if not raw:
            if field_name == "estimated_end_at":
                return {"status": "waiting_eta", "reason": "missing_estimated_end_at", "estimated_end_at": ""}
            continue  # an empty cooldown simply means "no cooldown"
        try:
            deadline = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=UTC)  # legacy persisted times were UTC
        except (TypeError, ValueError):
            event = "shipping_backoff_parse_failed" if field_name == "backoff_until" else "shipping_eta_parse_failed"
            logger.warning("%s job=%s field=%s value=%r", event, state.job_id, field_name, raw)
            continue
        if stamp < deadline:
            return {
                "status": status,
                "remaining_seconds": math.ceil((deadline - stamp).total_seconds()),
                field_name: raw,
            }
    return None


def _fence_is_abandoned(state: ShippingState, now: datetime) -> bool:
    """True when a "finishing"/"starting" fence is older than the claim TTL.

    The fence is written immediately before the terminal POST; the claim that
    goes with it expires after COMPLETION_CLAIM_TTL_SECONDS. A fence still
    standing after that window therefore belongs to a worker that died, not to
    one that is working.
    """
    if state.status not in FENCE_STATUSES:
        return False
    raw = state.last_attempt_at or state.created_at
    if not raw:
        return True  # no attempt timestamp at all: nothing can be waiting on it
    try:
        stamped = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        logger.warning("shipping_fence_timestamp_parse_failed job=%s value=%r", state.job_id, raw)
        return True
    if stamped.tzinfo is None:
        stamped = stamped.replace(tzinfo=UTC)  # legacy persisted times were UTC
    return (now - stamped).total_seconds() > COMPLETION_CLAIM_TTL_SECONDS


async def reclaim_stuck_shipping_fences(states: list[ShippingState], now: datetime) -> list[ShippingState]:
    """Return abandoned fences to "in_transit" so they are swept again.

    Without this, a worker OOM-killed between the durable fence and the
    response leaves Redis on "finishing" for the key's 7-day TTL: the claim
    expires but nothing resets the status, so the trip is never completed and
    never surfaces as failed. Only reclaimed when NO claim of either
    generation is held, so a live mutation is never stolen.
    """
    reclaimed: list[ShippingState] = []
    for state in states:
        if not _fence_is_abandoned(state, now):
            continue
        if await _completion_claim_is_held(state.job_id):
            continue
        previous = state.status
        logger.warning(
            "shipping_fence_reclaimed job=%s from=%s last_attempt_at=%r",
            state.job_id,
            previous,
            state.last_attempt_at,
        )
        state.status = "in_transit"
        state.last_error_message = f"reclaimed abandoned {previous} fence"[:200]
        try:
            await save_shipping_state(state)
        except Exception:
            logger.error("shipping_fence_reclaim_persist_failed job=%s", state.job_id, exc_info=True)
            continue
        reclaimed.append(state)
    return reclaimed


# The DB fallback scan is bounded so a backlog cannot load every envelope into
# the worker at once; Redis remains the primary, authoritative source.
DUE_SCAN_DB_LIMIT = 50


async def get_due_in_transit_jobs(now_dt: datetime | None = None) -> list[ShippingState]:
    """Find due envelopes, with Redis decisions taking precedence over stale DB mirrors.

    ``seen`` is populated BEFORE the dueness filter on purpose: Redis is the
    authoritative store and the DB envelope is only a fallback for Redis loss,
    so a Redis decision ("delivered", the fail-closed "unknown", a live
    "finishing" fence) must never be overridden by a stale DB mirror that still
    says "in_transit". Abandoned fences are fixed at the source instead, by
    reclaim_stuck_shipping_fences.
    """
    now = now_dt or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    due: list[ShippingState] = []
    fenced: list[ShippingState] = []
    seen: set[str] = set()

    def consider(raw: Any) -> None:
        state = ShippingState.from_dict(raw)
        if not state.job_id or state.job_id in seen:
            return
        seen.add(state.job_id)
        if state.status in FENCE_STATUSES:
            fenced.append(state)
        elif state.status == "in_transit" and shipping_wait_reason(state, now) is None:
            due.append(state)

    redis = await _get_redis()
    if redis is not None:
        try:
            cursor = 0
            while True:
                cursor, keys = await redis.scan(cursor=cursor, match="utcms:shipping:job:*", count=100)
                for key in keys:
                    try:
                        raw = await redis.get(key)
                        if raw:
                            consider(json.loads(raw))
                    except (ValueError, TypeError, AttributeError):
                        logger.warning("shipping_state_decode_failed key=%s", key, exc_info=True)
                if int(cursor) == 0:
                    break
        except Exception:
            logger.warning("shipping_due_redis_scan_failed", exc_info=True)
    try:
        from sqlalchemy import cast
        from sqlalchemy.dialects.postgresql import JSONB
        from sqlmodel import select

        from app.core.database import async_session_factory
        from app.models_multitenant import WaybillJob

        async with async_session_factory() as session:
            # Issuance can already be SUCCESS while its shipping envelope is in transit.
            #
            # INDEX NOTE: this is an UNINDEXED JSONB path predicate that runs on
            # every Beat tick (120s) on a 4 vCPU box shared with Worker 1, so it
            # is a full sequential scan of waybill_jobs. ``result_json`` is a
            # JSON column, so the cast below is real and an expression index
            # must match it exactly:
            #
            #   CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_wj_shipping_state_status
            #     ON waybill_jobs ((CAST(result_json AS jsonb) -> '_shipping_state' ->> 'status'))
            #     WHERE (CAST(result_json AS jsonb) -> '_shipping_state' ->> 'status')
            #           IN ('in_transit', 'finishing', 'starting');
            #
            # Deliberately NOT created here: an index belongs in a reviewed
            # Alembic revision, not in a runtime import path. Until it exists,
            # DUE_SCAN_DB_LIMIT bounds the damage.
            status_expr = cast(WaybillJob.result_json, JSONB)["_shipping_state"]["status"].astext
            query = select(WaybillJob).where(status_expr.in_(("in_transit", *FENCE_STATUSES))).limit(DUE_SCAN_DB_LIMIT)
            jobs = (await session.exec(query)).all()
            for job in jobs:
                if job.job_id in seen:
                    continue
                try:
                    stored = (job.result_json or {}).get("_shipping_state")
                    if isinstance(stored, dict) and stored.get("job_id") == job.job_id:
                        consider(stored)
                except (ValueError, TypeError, AttributeError):
                    logger.warning("shipping_state_decode_failed job=%s", job.job_id, exc_info=True)
    except Exception:
        logger.warning("shipping_due_db_scan_failed", exc_info=True)
    for state in await reclaim_stuck_shipping_fences(fenced, now):
        if shipping_wait_reason(state, now) is None:
            due.append(state)
    return due


_UTCM_RULE_CODE_RE = re.compile(r"\(code:\s*(\d{3,5})\)")


def _extract_utcms_rule_code(exc: BaseException) -> str | None:
    """Extract the UTCMS business-rule code from an exception — structurally.

    Never substring-match free exception text: a doc/tracking number or a
    prose message can contain "4011" without being business rule 4011.
    Prefers the structured ``result_code`` field on UtcmsMobileApiError;
    falls back to the strict "(code: NNNN)" pattern that
    require_successful_mutation() emits. Returns None when no code is found.
    """
    code = getattr(exc, "result_code", None)
    if code is not None:
        code_str = str(code).strip()
        if code_str:
            return code_str
    match = _UTCM_RULE_CODE_RE.search(str(exc))
    return match.group(1) if match else None


async def _route_shipping_job_to_reconciliation(
    job_id: str,
    *,
    reason: str,
    error: str,
) -> str:
    """Route a shipping job whose completion outcome is UNKNOWN through the
    JobStateMachine into reconciling — never success (fail-closed).

    The shipping layer's "in_transit" is not a JobStateMachine node, so the
    first hop is chosen from the edges the machine actually allows from the
    job's current status (unknown→reconciling directly; success→needs_review→
    reconciling). Every hop goes through JobStateMachine.transition, so
    transition validation always applies.

    Deliberately does NOT set reconciled_at or mutation_status="confirmed":
    those are written only when reconciliation actually completes with all
    three witnesses (see reconciliation_service / waybill_job_service).
    Fabricating them here would let a later success transition pass the
    machine's SUCCESS gate without real verification. The existing
    mutation_status (issuance truth) is preserved.
    """
    from sqlmodel import select

    from app.core.database import async_session_factory
    from app.models_multitenant import WaybillJob
    from app.orchestrator.state_machine import JobStateMachine, JobStatus, StateTransitionError

    now = datetime.now(UTC)
    async with async_session_factory() as session:
        job = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == job_id))).first()
        if job is None:
            logger.warning("shipping_reconciliation_job_missing job=%s reason=%s", job_id, reason)
            return "job_missing"

        res_json = dict(job.result_json or {})
        res_json["shipping_completion"] = {
            "status": "unknown",
            "reason": reason,
            "error": error[:200],
            "at": now.isoformat(),
        }
        fields: dict[str, Any] = {
            "result_json": res_json,
            "updated_at": now.replace(tzinfo=None),
            "last_error": f"shipping completion unknown: {reason}",
        }

        current = job.status
        if current == JobStatus.RECONCILING.value:
            targets: list[str] = []
        elif current == JobStatus.UNKNOWN.value:
            targets = [JobStatus.RECONCILING.value]
        else:
            # First hop must be an edge the machine allows from `current`.
            targets = []
            for first in (JobStatus.UNKNOWN.value, JobStatus.NEEDS_REVIEW.value):
                try:
                    JobStateMachine.assert_allowed(current, first)
                except StateTransitionError:
                    continue
                targets = [first, JobStatus.RECONCILING.value]
                break

        if not targets:
            # No fail-closed edge exists in the graph from this status.
            # Record the evidence on the job and change nothing about its
            # status: inventing an edge here would bypass the machine this
            # fix exists to enforce.
            logger.error(
                "shipping_reconciliation_no_allowed_edge job=%s status=%s reason=%s",
                job_id,
                current,
                reason,
            )
            job.result_json = res_json
            job.updated_at = fields["updated_at"]
            job.last_error = fields["last_error"]
            session.add(job)
            await session.commit()
            return "no_allowed_edge"

        try:
            for target in targets:
                JobStateMachine.transition(session, job, target, **fields)
            await session.commit()
        except StateTransitionError as exc:
            await session.rollback()
            logger.error(
                "shipping_reconciliation_transition_rejected job=%s status=%s targets=%s err=%s",
                job_id,
                current,
                targets,
                exc,
            )
            raise
        logger.info(
            "shipping_completion_routed_to_reconciliation job=%s from=%s to=%s reason=%s",
            job_id,
            current,
            targets[-1],
            reason,
        )
        return targets[-1]


async def _acquire_completion_claim(job_id: str) -> str | None:
    """Acquire the same distributed lock used by manual start/finish; fail closed.

    Both the current and the legacy key are claimed (see
    LEGACY_COMPLETION_CLAIM_KEY) so a mid-rollout fleet running two image
    generations still serialises on one trip. Partial acquisition is rolled
    back, so neither generation can be starved by an orphaned half-claim.
    """
    r = await _get_redis()
    if not r:
        raise ShippingStatePersistenceError("shipping mutation lock unavailable")
    token = secrets.token_urlsafe(16)
    held: list[str] = []
    try:
        for template in (COMPLETION_CLAIM_KEY, LEGACY_COMPLETION_CLAIM_KEY):
            key = template.format(job_id=job_id)
            if not await r.set(key, token, ex=COMPLETION_CLAIM_TTL_SECONDS, nx=True):
                for acquired_key in held:
                    await _release_claim_key(r, acquired_key, token)
                logger.info("completion_claim_held job=%s key=%s; skipping duplicate attempt", job_id, key)
                return None
            held.append(key)
    except ShippingStatePersistenceError:
        raise
    except Exception as exc:
        for acquired_key in held:
            await _release_claim_key(r, acquired_key, token)
        raise ShippingStatePersistenceError("shipping mutation lock unavailable") from exc
    return token


async def _release_claim_key(redis: Any, key: str, token: str) -> None:
    """Compare-and-delete one claim key; never raise over a release failure."""
    try:
        await redis.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end return 0",
            1,
            key,
            token,
        )
    except Exception as exc:
        logger.warning("completion_claim_release_failed key=%s err=%s", key, exc)


async def _release_completion_claim(job_id: str, token: str) -> None:
    """Release a completion claim previously acquired by this caller."""
    if not token:
        return
    r = await _get_redis()
    if r is None:
        return
    for template in (COMPLETION_CLAIM_KEY, LEGACY_COMPLETION_CLAIM_KEY):
        await _release_claim_key(r, template.format(job_id=job_id), token)


async def _completion_claim_is_held(job_id: str) -> bool:
    """True when either claim generation still owns this trip's mutation."""
    r = await _get_redis()
    if r is None:
        return True  # fail closed: without Redis we cannot prove nobody holds it
    for template in (COMPLETION_CLAIM_KEY, LEGACY_COMPLETION_CLAIM_KEY):
        try:
            if await r.get(template.format(job_id=job_id)) is not None:
                return True
        except Exception:
            logger.warning("completion_claim_probe_failed job=%s", job_id, exc_info=True)
            return True
    return False


def _is_missing_start_rejection(result: dict[str, Any]) -> bool:
    """Rule 4011 variant where the self-declared start was never registered upstream."""
    if result.get("resultCode") != 4011:
        return False
    # ZWNJ («ثبت‌نشده») must fold to the same spaced form as the documented
    # marker, otherwise the no-start variant slips past and is never recovered.
    message = str(result.get("resultMessage") or "").replace("‌", " ").replace("ي", "ی").replace("ك", "ک")
    message = " ".join(message.split())
    return "شروع حمل" in message and "ثبت نشده" in message


def _assume_utc_timestamp(value: Any, *, fallback: datetime) -> str:
    """Normalise a persisted timestamp to the strict UTCMS wire format.

    ``utc_shipping_timestamp`` deliberately hard-raises on a naive value so a
    Tehran-local time can never be wired as UTC (rule 4013). Legacy envelopes,
    however, persisted naive strings that WERE UTC — the rest of this module
    already assumes that (``shipping_wait_reason``, and
    ``advance_travel_execution`` in shipping_travel_service). Without this
    helper a single legacy ``created_at`` escapes auto_complete_shipping as a
    ValueError with NO state saved, so no backoff is recorded and the Beat tick
    repeats it every 2 minutes forever, burning a Session-Vault login (and a
    CAPTCHA solve when cold) on each pass.
    """
    from app.automation.shipping_contract import utc_shipping_timestamp

    raw = str(value or "").strip()
    if not raw:
        return utc_shipping_timestamp(fallback)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        logger.warning("shipping_timestamp_parse_failed value=%r; using fallback", raw)
        return utc_shipping_timestamp(fallback)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=UTC)  # legacy persisted times were UTC
    return utc_shipping_timestamp(parsed)


def _escalated_trace_target_km(state: ShippingState) -> float:
    """Cumulative trace length the next terminal attempt should aim for.

    Rule 4012 is evaluated by UTCMS on ROAD distance, which is shorter than the
    haversine length of our trace, so re-sending the same 2.15 km trace is
    rejected identically forever. ``required_distance_km`` carries the target
    learned from the distance UTCMS reported last time; the contract clamps it
    up to the documented default, so this can only ever escalate.
    """
    from app.automation.shipping_contract import DEFAULT_TRACE_TARGET_KM

    required = float(state.required_distance_km or 0.0)
    if not math.isfinite(required) or required <= DEFAULT_TRACE_TARGET_KM:
        return DEFAULT_TRACE_TARGET_KM
    return min(required, 500.0)  # sanity ceiling: a trace is evidence, not fiction


def _is_transient_completion_failure(cause: Any) -> bool:
    """True for transport blips worth retrying, false for anything ambiguous.

    ``shipping_response`` returns None for 503/502/504/500/408 because none of
    them is a UTCMS business code — they must not be dressed up as one. They
    are nevertheless the COMMON failure (see _TRANSIENT_HTTP_STATUSES), so the
    completion path classifies them here instead and keeps the trip retryable.
    """
    if cause is None:
        return False
    status = getattr(cause, "status_code", None)
    if status is not None:
        return status in _TRANSIENT_HTTP_STATUSES
    if getattr(cause, "result_code", None) is not None:
        return False  # an authoritative portal verdict, not a blip
    from app.core.network import is_retryable_network_error

    return is_retryable_network_error(cause)


def _completion_backoff_seconds(attempts: int) -> int:
    """Bounded exponential cooldown: 5, 10, 20, 40, 60 minutes (capped)."""
    return int(min(3600, 300 * 2 ** min(max(0, attempts - 1), 4)))


async def _record_unconfirmed_completion(
    state: ShippingState,
    cause: Any,
    *,
    now: datetime,
    reason: str = "completion_unconfirmed",
) -> dict[str, Any]:
    """Persist an UNKNOWN terminal outcome: the POST may already have landed.

    Two outcomes, deliberately distinguished:

    * transient (5xx/timeout/reset) — the trip stays RETRYABLE: status remains
      "in_transit" behind a bounded cooldown so the Beat sweeper picks it up
      again, which is what the pre-refactor path achieved by re-raising for
      Celery. Re-POSTing is safe at the business level: UTCMS answers 4011/4012
      /4013 for an end already registered, all of which are handled.
    * anything else — fails CLOSED to "unknown" and is never retried
      automatically.

    Both persist state (so a Beat tick cannot hot-loop) and route the job
    through JobStateMachine into reconciling, exactly as the 4011-recovery
    branch does, so the ambiguity is visible rather than silently orphaned.
    """
    state.completion_attempts = max(state.completion_attempts, 1)
    state.last_attempt_at = now.isoformat()
    state.last_error_message = str(cause)[:200]
    retryable = _is_transient_completion_failure(cause)
    exhausted = state.completion_attempts >= MAX_COMPLETION_ATTEMPTS
    if retryable and not exhausted:
        state.status = "in_transit"
    else:
        state.status = "unknown"
    state.backoff_until = (now + timedelta(seconds=_completion_backoff_seconds(state.completion_attempts))).isoformat()
    routed = "not_routed"
    try:
        routed = await _route_shipping_job_to_reconciliation(state.job_id, reason=reason, error=str(cause))
    except Exception:
        logger.error("shipping_unconfirmed_routing_failed job=%s", state.job_id, exc_info=True)
    await save_shipping_state(state)
    logger.error(
        "shipping_completion_unconfirmed job=%s retryable=%s attempts=%s backoff_until=%s routed=%s",
        state.job_id,
        retryable and not exhausted,
        state.completion_attempts,
        state.backoff_until,
        routed,
    )
    return {
        "status": "unknown",
        "reason": "completion_attempts_exhausted" if exhausted else reason,
        "retryable": retryable and not exhausted,
        "backoff_until": state.backoff_until,
        "routed_to": routed,
    }


async def auto_complete_shipping(job_id: str, force: bool = False) -> dict[str, Any]:
    """ETA-triggered terminal registration, with UTCMS rule 4013 as the backstop.

    The trigger is the persisted physical ETA (``estimated_end_at``), not a
    client-side arrival calculation: the travel engine's ARRIVED signal is
    best-effort and only exists for trips whose Neshan snapshot resolved, while
    UTCMS evaluates its own clock and refuses an early end with rule 4013. A
    blank ETA is treated as "not yet due" (see ``shipping_wait_reason``).

    The per-trip completion claim (SET NX) guarantees that two overlapping
    Beat runs (2-minute cadence) cannot double-call RegisterEndOfShipping for
    the same trip: the second claimant skips.
    """
    state = await load_shipping_state(job_id)
    if not state or state.status != "in_transit":
        return {"status": "skipped", "reason": "not_in_transit"}

    claim_token = await _acquire_completion_claim(job_id)
    if claim_token is None:
        return {"status": "skipped", "reason": "completion_claim_held", "job_id": job_id}
    try:
        return await _auto_complete_shipping_inner(job_id, force=force)
    finally:
        await _release_completion_claim(job_id, claim_token or "")


async def _auto_complete_shipping_inner(job_id: str, force: bool = False) -> dict[str, Any]:
    """Complete one trip while holding its distributed mutation lease."""
    from app.automation.shipping_contract import prepare_shipping_trace, shipping_acknowledged, shipping_response
    from app.automation.worker_proxy import get_worker_proxy_url
    from app.core.config import utcms_config

    if not utcms_config.ALLOW_LIVE_SUBMIT:
        return {"status": "skipped", "reason": "live_submit_disabled"}
    state = await load_shipping_state(job_id)
    if not state or state.status != "in_transit":
        return {"status": "skipped", "reason": "not_in_transit"}
    if not force:
        # force is an explicit operator override (manual/script completion): it
        # bypasses only the ETA/backoff wait, never the fail-closed mutation gates.
        wait = shipping_wait_reason(state)
        if wait:
            return wait
    # Fail-closed integrity guards before the terminal POST (held under the claim):
    # never submit a trip with no document id, or a (0,0) destination that must
    # never reach UTCMS.
    if not (state.doc_id or state.doc_no):
        return {"status": "skipped", "reason": "missing_doc_id"}
    if not state.dest_lat or not state.dest_lng:
        return {"status": "skipped", "reason": "missing_dest_coordinates"}

    from sqlmodel import select

    from app.auth_multitenant import decrypt_driver_password
    from app.core.database import async_session_factory
    from app.models_multitenant import Driver, WaybillJob

    async with async_session_factory() as session:
        job = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == job_id))).first()
        if not job or not job.driver_id:
            return {"status": "skipped", "reason": "job_or_driver_not_found"}
        driver = await session.get(Driver, job.driver_id)
        tenant_id = getattr(job, "client_id", None)
        if not driver or getattr(driver, "client_id", None) != tenant_id:
            return {"status": "needs_review", "reason": "driver_ownership_mismatch"}
        from app.api.routes.shipping_gps import _document_ids

        document_ids = _document_ids(job, dict(getattr(job, "payload_json", None) or {}))
        target_doc_id = state.doc_id or state.doc_no
        if not target_doc_id or target_doc_id not in document_ids:
            return {"status": "needs_review", "reason": "document_ownership_mismatch"}
    if not driver.utcms_password_encrypted:
        return {"status": "skipped", "reason": "driver_credentials_missing"}

    from app.android_bridge.client import BridgeConfig
    from app.services.shipping_travel_service import advance_travel_execution, verify_android_anchor

    bridge = BridgeConfig.from_env()  # invalid enabled config must never downgrade to direct transport
    if bridge.enabled:
        from app.android_bridge.controller import AndroidShippingController

        await AndroidShippingController(bridge).apply_location(state.dest_lat, state.dest_lng)
        check = await verify_android_anchor(expected_lat=state.dest_lat, expected_lng=state.dest_lng)
        if not check.get("verified"):
            return {"status": "waiting_readback", "reason": check.get("reason", "readback_unavailable")}
    # Travel sampling is advisory (progress/telemetry), never a gate on the only
    # terminal path: build_engine_for_state is guarded internally but start()/
    # sample()/compute_measured_distance_km are not, and an engine error must
    # not abort completion and leave the state un-persisted. shipping_gps.py
    # treats the identical call as best effort.
    try:
        advance_travel_execution(state)
    except Exception:
        logger.warning("auto_complete_travel_advance_failed job=%s", job_id, exc_info=True)
    proxy_url = get_worker_proxy_url()  # propagate fail-closed egress failures
    client = await get_or_login_client(
        national_code=driver.driver_national_code,
        password=decrypt_driver_password(driver.utcms_password_encrypted),
        proxy_url=proxy_url,
        client_id=tenant_id,
    )
    now = datetime.now(UTC)
    from app.automation.shipping_contract import utc_shipping_timestamp

    # Recover a legacy origin only from its recorded start time, never backdate
    # it. A legacy envelope may carry a NAIVE created_at, which the strict wire
    # formatter refuses; assume UTC for it rather than hot-looping the sweep.
    origin_stamp = _assume_utc_timestamp(state.created_at, fallback=now)
    evidence = [dict(point) for point in state.gps_list if point.get("Type") != 3]
    if not evidence:
        evidence.append(
            {
                "Latitude": state.origin_lat,
                "Longitude": state.origin_lng,
                "Type": 2,
                "Date": origin_stamp,
                "Provider": "operator_anchor",
                "Provenance": "route_anchor",
            }
        )
    evidence.append(
        {
            "Latitude": state.dest_lat,
            "Longitude": state.dest_lng,
            "Type": 3,
            "Date": utc_shipping_timestamp(now),
            "Speed": 0,
            "Altitude": 1000,
            "Provider": "android_faketraveler_applied" if bridge.enabled else "operator_anchor",
            "Provenance": "virtual_observation" if bridge.enabled else "route_anchor",
        }
    )
    try:
        evidence = prepare_shipping_trace(evidence, target_km=_escalated_trace_target_km(state))
    except ValueError as exc:
        # A malformed trace fails identically on every retry, so park the trip
        # behind a cooldown WITH state persisted instead of letting the error
        # escape un-recorded and repeat on the next tick. Nothing was POSTed,
        # so there is no ambiguous mutation to reconcile.
        logger.error("shipping_trace_invalid job=%s err=%s", job_id, exc)
        state.status = "unknown"
        state.last_error_message = str(exc)[:200]
        state.backoff_until = (now + timedelta(seconds=_completion_backoff_seconds(1))).isoformat()
        await save_shipping_state(state)
        return {"status": "needs_review", "reason": "invalid_shipping_trace", "error": str(exc)[:200]}
    state.gps_list = evidence
    state.completion_attempts += 1
    state.last_attempt_at = now.isoformat()
    state.status = "finishing"
    await save_shipping_state(state)  # durable fence before the only terminal POST
    try:
        result = await client.register_end_of_shipping(
            document_id=target_doc_id, gps_list=evidence, allow_live_submit=utcms_config.ALLOW_LIVE_SUBMIT
        )
    except Exception as exc:
        # Classify STRUCTURALLY (never by free-text substring): a genuine
        # business-rule 4011 is the self-declared-end outcome handled below; any
        # other terminal-POST exception is ambiguous -> unknown, but a transient
        # transport blip stays retryable (see _record_unconfirmed_completion).
        if _extract_utcms_rule_code(exc) == "4011":
            result = {"resultCode": 4011, "resultMessage": str(exc)}
        else:
            parsed = shipping_response(exc)
            if parsed is None:
                return await _record_unconfirmed_completion(state, exc, now=now)
            result = parsed
    result = shipping_response(result)
    if result is None or result.get("resultCode") is None:
        return await _record_unconfirmed_completion(state, result, now=now, reason="completion_response_unparseable")
    if _is_missing_start_rejection(result):
        # Rule 4011 "شروع حمل ثبت نشده": the self-declared start was never
        # recorded upstream. Register start once from the origin witness, then
        # retry the single terminal POST. If recovery does not settle (start
        # fails, or the retry is unconfirmed / still no-start), route the job
        # through JobStateMachine into reconciling — never success (fail-closed).
        recovery_error: str | None = None
        retry: dict[str, Any] | None = None
        try:
            await client.register_start_of_shipping(
                target_doc_id,
                longitude=state.origin_lng,
                latitude=state.origin_lat,
                start_date=origin_stamp,
                allow_live_submit=utcms_config.ALLOW_LIVE_SUBMIT,
            )
            retry = shipping_response(
                await client.register_end_of_shipping(
                    document_id=target_doc_id, gps_list=evidence, allow_live_submit=utcms_config.ALLOW_LIVE_SUBMIT
                )
            )
        except Exception as exc:
            recovery_error = str(exc)
        if (
            recovery_error is not None
            or retry is None
            or retry.get("resultCode") is None
            or _is_missing_start_rejection(retry)
        ):
            routed = await _route_shipping_job_to_reconciliation(
                job_id, reason="completion_recovery_failed", error=recovery_error or f"recovery did not settle: {retry}"
            )
            state.status = "unknown"
            state.last_error_message = (recovery_error or "recovery did not settle")[:200]
            state.backoff_until = (now + timedelta(seconds=300)).isoformat()
            await save_shipping_state(state)
            return {"status": "unknown", "reason": "completion_recovery_failed", "routed_to": routed}
        result = retry
    # Acknowledgement is evaluated for EVERY code, 4011 included. The previous
    # `resultCode != 4011 and ...` short-circuit meant shipping_acknowledged was
    # never asked about the one outcome it exists to validate, so an explicit
    # refusal ("... تایید نشده است", which UTCMS also returns under 4011) was
    # recorded as a delivery. /shipping/finish has always called it
    # unconditionally; the two paths now agree on the same response.
    if not shipping_acknowledged(result):
        return await record_shipping_rejection(state, result, now=now)
    if result.get("resultCode") == 4011:
        result["mode"] = "self_declared_auto_complete"
    state.status = "delivered"
    state.backoff_until = ""
    state.current_step = max(1, len(state.waypoints) - 1)
    state.traveled_km = state.distance_km
    await save_shipping_state(state)
    async with async_session_factory() as session:
        job = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == job_id))).first()
        if job:
            res_json = dict(job.result_json or {})
            res_json.update(end_shipping=result, completed_at=now.isoformat())
            job.result_json = res_json
            # Shipping evidence does not promote or invalidate issuance witnesses.
            job.updated_at = now.replace(tzinfo=None)
            session.add(job)
            await session.commit()
    return {"status": "delivered", "result": result}


async def record_shipping_rejection(
    state: ShippingState, result: dict[str, Any], *, now: datetime | None = None
) -> dict[str, Any]:
    """Known rejections are retryable after cooldown; a missing-start result needs review."""
    from app.automation.shipping_contract import DEFAULT_TRACE_TARGET_KM, shipping_reported_distance_km

    stamp = now or datetime.now(UTC)
    code = result.get("resultCode")
    state.last_error_code = code
    state.last_error_message = str(result.get("resultMessage") or "")[:200]
    state.status = "in_transit"
    route_reason: str | None = None
    if code == 4011:
        # Rule 4011 that is neither acknowledged nor the no-start variant: the
        # end was refused outright. Route it like any other unknown outcome so
        # it reaches reconciliation instead of waiting for someone to notice.
        state.status = "unknown"
        status, seconds = "needs_review", 0
        route_reason = "shipping_end_rejected_4011"
    elif code == 4012:
        # Escalate: UTCMS measures ROAD distance and tells us its own figure, so
        # aim for that figure plus a full contract margin. Re-sending the same
        # 2.15 km trace is rejected identically forever (288 calls/day/trip,
        # which then trips the 429 breaker).
        reported = shipping_reported_distance_km(result)
        base = reported if reported is not None else DEFAULT_TRACE_TARGET_KM * max(1, state.completion_attempts)
        state.required_distance_km = max(state.required_distance_km, base + DEFAULT_TRACE_TARGET_KM)
        status = "waiting_distance_requirement"
        seconds = min(1800, 300 * max(1, state.completion_attempts))
        logger.warning(
            "shipping_distance_requirement_escalated job=%s reported_km=%s next_target_km=%.3f attempts=%s",
            state.job_id,
            reported,
            state.required_distance_km,
            state.completion_attempts,
        )
    elif code == 4013:
        status, seconds = "waiting_elapsed_time", 300
    elif code == 429:
        status, seconds = "rate_limited", min(1800, 600 * max(1, state.completion_attempts))
    else:
        status, seconds = "rejected", _completion_backoff_seconds(state.completion_attempts)
    if code not in RETRY_LATER_CODES and state.completion_attempts >= MAX_COMPLETION_ATTEMPTS:
        # A capped trip must stop looping: "unknown" is not swept, so it parks
        # for an operator instead of burning a login + POST every cooldown.
        # 4013/429 are exempt because they are UTCMS telling us "not yet" with
        # its own bounded schedule, not a defect in what we sent.
        state.status = "unknown"
        status, seconds = "needs_review", 0
        route_reason = "completion_attempts_exhausted"
    state.backoff_until = (stamp + timedelta(seconds=seconds)).isoformat() if seconds else ""
    routed: str | None = None
    if route_reason is not None:
        try:
            routed = await _route_shipping_job_to_reconciliation(
                state.job_id, reason=route_reason, error=state.last_error_message
            )
        except Exception:
            logger.error("shipping_rejection_routing_failed job=%s", state.job_id, exc_info=True)
            routed = "not_routed"
    await save_shipping_state(state)
    response: dict[str, Any] = {"status": status, "result": result, "backoff_until": state.backoff_until}
    if routed is not None:
        response["routed_to"] = routed
    return response


__all__ = [
    "DEFAULT_CITY_COORDS",
    "FENCE_STATUSES",
    "MAX_COMPLETION_ATTEMPTS",
    "GpsWaypoint",
    "ShippingState",
    "ShippingStatePersistenceError",
    "auto_complete_shipping",
    "cache_refresh_token",
    "cache_token",
    "calculate_realistic_road_distance",
    "estimate_travel_duration_hours",
    "extract_coordinates_from_payload",
    "find_city_coordinates",
    "get_cached_refresh_token",
    "get_cached_token",
    "get_due_in_transit_jobs",
    "get_or_login_client",
    "haversine_km",
    "init_shipping",
    "interpolate_waypoints",
    "invalidate_cached_session",
    "is_mobile_authentication_error",
    "load_shipping_state",
    "normalize_city_name",
    "reclaim_stuck_shipping_fences",
    "record_shipping_rejection",
    "save_shipping_state",
    "shipping_wait_reason",
]
