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
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
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
}


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
    origin_meta = next((meta[key] for key in ("origin", "source") if isinstance(meta.get(key), dict)), {})
    dest_meta = next((meta[key] for key in ("destination", "dest") if isinstance(meta.get(key), dict)), {})

    # ── Origin coordinates ──
    origin_lat, origin_lng = _resolve_nested_coords(
        flat_lat=_float(_first(payload.get("originLat"), payload.get("sourceLatM"))),
        flat_lng=_float(_first(payload.get("originLng"), payload.get("sourceLngM"), payload.get("sourceLonM"))),
        meta_section=origin_meta,
        top_section=_safe_dict(payload.get("origin")),
    )

    # ── Destination coordinates ──
    dest_lat, dest_lng = _resolve_nested_coords(
        flat_lat=_float(_first(payload.get("destLat"), payload.get("destLatM"))),
        flat_lng=_float(_first(payload.get("destLng"), payload.get("destLngM"), payload.get("destLonM"))),
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


DRIVER_TOKEN_KEY = "utcms:driver:token:{national_code}"
DRIVER_REFRESH_KEY = "utcms:driver:refresh:{national_code}"
DRIVER_AUTH_LOCK_KEY = "utcms:driver:auth-lock:{national_code}"
SHIPPING_STATE_KEY = "utcms:shipping:job:{job_id}"
_LOCAL_AUTH_LOCKS: dict[str, asyncio.Lock] = {}


async def _get_redis():
    """Best-effort Redis accessor."""
    try:
        from app.core.redis import redis_manager

        return await redis_manager.get()
    except Exception:
        return None


async def get_cached_token(national_code: str) -> str | None:
    """Return cached UTCMS driver token from Redis, or None."""
    r = await _get_redis()
    if r is None:
        return None
    try:
        return await r.get(DRIVER_TOKEN_KEY.format(national_code=national_code))
    except Exception:
        return None


async def cache_token(national_code: str, token: str, ttl_seconds: int = 240) -> None:
    """Store driver UTCMS bearer token in Redis with TTL (default 240s < 5m expiry)."""
    if not token or not str(token).strip():
        return
    r = await _get_redis()
    if r is None:
        return
    try:
        await r.set(DRIVER_TOKEN_KEY.format(national_code=national_code), str(token).strip(), ex=ttl_seconds)
    except Exception as exc:
        logger.warning("cache_token_failed: %s", exc)


async def cache_refresh_token(national_code: str, refresh_token: str, ttl_seconds: int = 7000) -> None:
    """Store refresh token with TTL (default 7000s < 120m expiry)."""
    if not refresh_token or not str(refresh_token).strip():
        return
    r = await _get_redis()
    if r is None:
        return
    try:
        await r.set(DRIVER_REFRESH_KEY.format(national_code=national_code), str(refresh_token).strip(), ex=ttl_seconds)
    except Exception as exc:
        logger.warning("cache_refresh_token_failed: %s", exc)


async def get_cached_refresh_token(national_code: str) -> str | None:
    r = await _get_redis()
    if r is None:
        return None
    try:
        return await r.get(DRIVER_REFRESH_KEY.format(national_code=national_code))
    except Exception:
        return None


async def invalidate_cached_session(national_code: str) -> None:
    """Remove both cached credentials after UTCMS rejects authentication."""
    r = await _get_redis()
    if r is None:
        return
    try:
        await r.delete(
            DRIVER_TOKEN_KEY.format(national_code=national_code),
            DRIVER_REFRESH_KEY.format(national_code=national_code),
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
LOGIN_MAX_ATTEMPTS = 2
LOGIN_RETRY_DELAY_SECONDS = 2.0
_TRANSIENT_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


def _is_transient_login_error(exc: BaseException) -> bool:
    """True only for transport-level blips worth one retry.

    A set ``result_code`` is an authoritative portal verdict (e.g. code 1,
    bad credentials) — retrying burns budget and risks lockout. 401/403/444
    are explicit refusals, not blips.
    """
    from app.automation.utcms_mobile_client import UtcmsMobileApiError

    if not isinstance(exc, UtcmsMobileApiError):
        return False
    if exc.result_code is not None:
        return False
    if exc.status_code is not None:
        return exc.status_code in _TRANSIENT_HTTP_STATUSES
    message = str(exc).lower()
    return "transport failed" in message or "non-json response" in message


async def _solve_and_login_with_retry(client: Any, national_code: str, password: str) -> Any:
    """Solve the login CAPTCHA and log in, retrying transient blips once."""
    from app.automation.utcms_mobile_client import UtcmsMobileClient

    last_exc: Exception | None = None
    for attempt_no in range(1, LOGIN_MAX_ATTEMPTS + 1):
        try:
            solved = await client.auto_solve_captcha(form_id="login")
            cap_token = UtcmsMobileClient.cap_token_from_solution(solved)
            if not cap_token:
                raise RuntimeError("UTCMS mobile CAPTCHA could not be solved")
            return await client.login(national_code, password, cap_token=cap_token)
        except Exception as exc:
            last_exc = exc
            if attempt_no >= LOGIN_MAX_ATTEMPTS or not _is_transient_login_error(exc):
                raise
            logger.warning(
                "session_vault_login_retry national_code=%s attempt=%d",
                national_code,
                attempt_no,
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
) -> Any:
    """Get an authenticated UtcmsMobileClient, reusing cached token to avoid 429.

    1. Check Redis for cached token → use if valid.
    2. Check Redis for refresh token → call refresh if available.
    3. Only fall back to login() if nothing is cached.
    """
    from app.automation.utcms_mobile_client import UtcmsMobileClient

    local_lock = _LOCAL_AUTH_LOCKS.setdefault(national_code, asyncio.Lock())
    async with local_lock:
        redis = await _get_redis()
        lock_key = DRIVER_AUTH_LOCK_KEY.format(national_code=national_code)
        lock_token: str | None = None
        if redis is not None:
            lock_token = await _acquire_auth_lock(redis, lock_key)
        try:
            if force_reauth:
                await invalidate_cached_session(national_code)

            cached = await get_cached_token(national_code)
            if cached:
                logger.info("session_vault_hit national_code=%s", national_code)
                return UtcmsMobileClient(token=cached, proxy_url=proxy_url)

            refresh = await get_cached_refresh_token(national_code)
            if refresh and refresh.strip():
                client = UtcmsMobileClient(proxy_url=proxy_url)
                try:
                    auth = await client.refresh(refresh.strip())
                    await cache_token(national_code, auth.token)
                    if auth.refresh_token:
                        await cache_refresh_token(national_code, auth.refresh_token)
                    logger.info("session_vault_refreshed national_code=%s", national_code)
                    return client
                except Exception as exc:
                    logger.warning("session_vault_refresh_failed: %s, falling back to login", exc)
                    await invalidate_cached_session(national_code)

            if not password or password in ("dummy", "") or str(password).strip() in ("dummy", ""):
                raise ValueError(f"رمز عبور راننده برای کد ملی '{national_code}' معتبر نیست")

            client = UtcmsMobileClient(proxy_url=proxy_url)
            auth = await _solve_and_login_with_retry(client, national_code, password)
            await cache_token(national_code, auth.token)
            if auth.refresh_token:
                await cache_refresh_token(national_code, auth.refresh_token)
            logger.info("session_vault_login national_code=%s", national_code)
            return client
        finally:
            if redis is not None and lock_token is not None:
                await _release_auth_lock(redis, lock_key, lock_token)


# ──────────────────── Shipping State (Redis) ────────────────────


@dataclass
class ShippingState:
    job_id: str = ""
    doc_no: str = ""
    status: str = "ready"  # ready | in_transit | delivered | failed
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
    # Planned/display route; never treat these points as GPS evidence.
    waypoints: list[dict[str, Any]] = field(default_factory=list)
    # Explicit operator/device observations eligible for UTCMS submission.
    gps_list: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "doc_no": self.doc_no,
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
            "waypoints": self.waypoints,
            "gps_list": self.gps_list,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ShippingState:
        return cls(
            job_id=d.get("job_id", ""),
            doc_no=d.get("doc_no", ""),
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
            waypoints=d.get("waypoints", []),
            gps_list=d.get("gps_list", []),
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

    state = ShippingState(
        job_id=job_id,
        doc_no=doc_no,
        status="ready",
        origin_lat=olat,
        origin_lng=olng,
        origin_address=info["origin_address"],
        dest_lat=dlat,
        dest_lng=dlng,
        dest_address=info["dest_address"],
        distance_km=info["distance_km"],
        current_step=0,
        total_steps=len(waypoints) - 1,
        traveled_km=0.0,
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
    )
    if persist:
        await save_shipping_state(state)
    return state


__all__ = [
    "DEFAULT_CITY_COORDS",
    "GpsWaypoint",
    "ShippingState",
    "ShippingStatePersistenceError",
    "cache_refresh_token",
    "cache_token",
    "calculate_realistic_road_distance",
    "estimate_travel_duration_hours",
    "extract_coordinates_from_payload",
    "find_city_coordinates",
    "get_cached_refresh_token",
    "get_cached_token",
    "get_or_login_client",
    "haversine_km",
    "init_shipping",
    "interpolate_waypoints",
    "invalidate_cached_session",
    "is_mobile_authentication_error",
    "load_shipping_state",
    "normalize_city_name",
    "save_shipping_state",
]
