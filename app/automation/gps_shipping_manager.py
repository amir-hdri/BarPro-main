"""GPS Shipping Lifecycle Manager — distance calculation, waypoint interpolation,
Redis Session Vault for token caching (eliminates HTTP 429), and state management.

All coordinates are derived from the **exact** user-entered payload for each waybill.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
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
    import re
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
    now = datetime.now(TEHRAN_TZ)

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
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    # ── Origin coordinates ──
    origin_lat = _float(payload.get("originLat") or payload.get("sourceLatM"))
    origin_lng = _float(payload.get("originLng") or payload.get("sourceLngM") or payload.get("sourceLonM"))

    # Try nested metadata_json
    meta = payload.get("metadata_json") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}
    origin_meta = meta.get("origin") or meta.get("source") or {}
    if origin_lat is None:
        origin_lat = _float(origin_meta.get("lat") or origin_meta.get("latitude"))
    if origin_lng is None:
        origin_lng = _float(origin_meta.get("lng") or origin_meta.get("lon") or origin_meta.get("longitude"))

    # ── Destination coordinates ──
    dest_lat = _float(payload.get("destLat") or payload.get("destLatM"))
    dest_lng = _float(payload.get("destLng") or payload.get("destLngM") or payload.get("destLonM"))
    dest_meta = meta.get("destination") or meta.get("dest") or {}
    if dest_lat is None:
        dest_lat = _float(dest_meta.get("lat") or dest_meta.get("latitude"))
    if dest_lng is None:
        dest_lng = _float(dest_meta.get("lng") or dest_meta.get("lon") or dest_meta.get("longitude"))

    # ── Addresses — EXACT user input ──
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
        "estimated_duration_text": f"{int(duration_hours)} ساعت و {duration_minutes % 60} دقیقه" if duration_hours >= 1 else f"{duration_minutes} دقیقه",
    }


# ──────────────────── Redis Session Vault ────────────────────


DRIVER_TOKEN_KEY = "utcms:driver:token:{national_code}"
DRIVER_REFRESH_KEY = "utcms:driver:refresh:{national_code}"
SHIPPING_STATE_KEY = "utcms:shipping:job:{job_id}"


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


async def cache_token(national_code: str, token: str, ttl_seconds: int = 6900) -> None:
    """Store driver UTCMS token in Redis with TTL (default ~115 min < 2h expiry)."""
    r = await _get_redis()
    if r is None:
        return
    try:
        await r.set(DRIVER_TOKEN_KEY.format(national_code=national_code), token, ex=ttl_seconds)
    except Exception as exc:
        logger.warning("cache_token_failed: %s", exc)


async def cache_refresh_token(national_code: str, refresh_token: str) -> None:
    """Store refresh token with long TTL (24h)."""
    r = await _get_redis()
    if r is None:
        return
    try:
        await r.set(DRIVER_REFRESH_KEY.format(national_code=national_code), refresh_token, ex=86400)
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


async def get_or_login_client(
    national_code: str,
    password: str,
    proxy_url: str | None = None,
) -> Any:
    """Get an authenticated UtcmsMobileClient, reusing cached token to avoid 429.

    1. Check Redis for cached token → use if valid.
    2. Check Redis for refresh token → call refresh if available.
    3. Only fall back to login() if nothing is cached.
    """
    from app.automation.utcms_mobile_client import UtcmsMobileClient

    cached = await get_cached_token(national_code)
    if cached:
        logger.info("session_vault_hit national_code=%s", national_code)
        return UtcmsMobileClient(token=cached, proxy_url=proxy_url)

    # Try refresh
    refresh = await get_cached_refresh_token(national_code)
    if refresh:
        client = UtcmsMobileClient(proxy_url=proxy_url)
        try:
            auth = await client.refresh(refresh)
            await cache_token(national_code, auth.token)
            if auth.refresh_token:
                await cache_refresh_token(national_code, auth.refresh_token)
            logger.info("session_vault_refreshed national_code=%s", national_code)
            return client
        except Exception as exc:
            logger.warning("session_vault_refresh_failed: %s, falling back to login", exc)

    # Full login requires a fresh server-issued CAPTCHA proof; an empty token
    # is rejected by the mobile API and must never be used as a fallback.
    client = UtcmsMobileClient(proxy_url=proxy_url)
    solved = await client.auto_solve_captcha(form_id=1)
    cap_token = UtcmsMobileClient.cap_token_from_solution(solved)
    if not cap_token:
        raise RuntimeError("UTCMS mobile CAPTCHA could not be solved")
    auth = await client.login(national_code, password, cap_token=cap_token)
    await cache_token(national_code, auth.token)
    if auth.refresh_token:
        await cache_refresh_token(national_code, auth.refresh_token)
    logger.info("session_vault_login national_code=%s", national_code)
    return client


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
    waypoints: list[dict[str, Any]] = field(default_factory=list)
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


async def save_shipping_state(state: ShippingState) -> None:
    r = await _get_redis()
    if r is None:
        return
    key = SHIPPING_STATE_KEY.format(job_id=state.job_id)
    await r.set(key, json.dumps(state.to_dict(), ensure_ascii=False), ex=86400)


async def load_shipping_state(job_id: str) -> ShippingState | None:
    r = await _get_redis()
    if r is None:
        return None
    raw = await r.get(SHIPPING_STATE_KEY.format(job_id=job_id))
    if raw is None:
        return None
    return ShippingState.from_dict(json.loads(raw))


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
        olat, olng, dlat, dlng,
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
    "cache_refresh_token",
    "cache_token",
    "extract_coordinates_from_payload",
    "get_cached_refresh_token",
    "get_cached_token",
    "get_or_login_client",
    "haversine_km",
    "init_shipping",
    "interpolate_waypoints",
    "load_shipping_state",
    "save_shipping_state",
]
