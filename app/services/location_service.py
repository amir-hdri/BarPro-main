"""
سرویس متمرکز مدیریت مکان‌ها، تبدیل مختصات (Reverse Geocoding)، کَش درون‌حافظه‌ای و نرم‌سازی اسامی استان/شهر
"""

import logging
import math
import re
import time
from typing import Any

import aiohttp

from app.automation.proxy_rotator import get_proxy_rotator
from app.core.iran_locations import IRAN_PROVINCES_DATA, normalize_farsi_text

logger = logging.getLogger(__name__)


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """محاسبه دقیق فاصله بین دو نقطه بر حسب کیلومتر (فرمول هاورساین)"""
    r = 6371.0  # شعاع زمین به کیلومتر
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def clean_location_name(raw_name: str) -> str:
    """
    پاکسازی و نرم‌سازی اسامی مکان‌ها:
    - حذف پیشوندهای «استان»، «شهرستان»، «شهر»، «بخش»
    - تبدیل کاراکترهای عربی به فارسی و حذف نیم‌فاصله‌ها
    """
    if not raw_name:
        return ""
    text = normalize_farsi_text(raw_name)
    # حذف پیشوندهای رایج
    text = re.sub(r"^(استان|شهرستان|شهر|بخش)\s+", "", text).strip()
    return text


def match_location_to_known_dataset(raw_province: str, raw_city: str) -> tuple[str, str]:
    """
    تطبیق اسامی دریافتی از Nominatim با داده‌های رسمی استان‌ها و شهرهای ایران در IRAN_PROVINCES_DATA.
    در صورت عدم تطبیق دقیق، مقدار نرم‌سازی شده یا اصلی بازگردانده می‌شود.
    """
    clean_prov = clean_location_name(raw_province)
    clean_cit = clean_location_name(raw_city)

    matched_province = raw_province.strip()
    matched_city = raw_city.strip()

    # ۱. پیدا کردن استان مطبق
    found_prov_data = None
    for p in IRAN_PROVINCES_DATA:
        p_clean = clean_location_name(p["name"])
        if clean_prov and (clean_prov == p_clean or clean_prov in p_clean or p_clean in clean_prov):
            matched_province = p["name"]
            found_prov_data = p
            break

    # ۲. پیدا کردن شهر مطبق
    search_provinces = [found_prov_data] if found_prov_data else IRAN_PROVINCES_DATA
    for p in search_provinces:
        for c in p["cities"]:
            c_clean = clean_location_name(c["name"])
            if clean_cit and (clean_cit == c_clean or clean_cit in c_clean or c_clean in clean_cit):
                matched_city = c["name"]
                if not found_prov_data:
                    matched_province = p["name"]
                return matched_province, matched_city

    return matched_province, matched_city


class LocationService:
    """سرویس متمرکز تبدیل مختصات و مدیریت مکان‌ها با کش درون‌حافظه‌ای"""

    def __init__(self):
        # کش درون‌حافظه‌ای با ساختار: (lat_round, lng_round) -> (timestamp, data_dict)
        self._cache: dict[tuple[float, float], tuple[float, dict[str, Any]]] = {}
        self._cache_ttl_seconds = 86400  # اعتبار کش: ۲۴ ساعت

    def _get_from_cache(self, lat: float, lng: float) -> dict[str, Any] | None:
        key = (round(lat, 3), round(lng, 3))
        entry = self._cache.get(key)
        if entry:
            ts, data = entry
            if time.time() - ts < self._cache_ttl_seconds:
                cached_data = dict(data)
                cached_data["source"] = "cache"
                return cached_data
            else:
                del self._cache[key]
        return None

    def _set_cache(self, lat: float, lng: float, data: dict[str, Any]) -> None:
        key = (round(lat, 3), round(lng, 3))
        # محدودسازی اندازه کش جهت جلوگیری از نشت حافظه (حداکثر ۲۰۰۰ آیتم)
        if len(self._cache) > 2000:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][0])
            del self._cache[oldest_key]
        self._cache[key] = (time.time(), data)

    async def reverse_geocode(self, lat: float, lng: float) -> dict[str, Any]:
        """
        تبدیل مختصات جغرافیایی به آدرس فارسی:
        ۱. بررسی کش درون‌حافظه‌ای
        ۲. تلاش مستقیم آنلاین با Nominatim
        ۳. تلاش ثانویه با پروکسی
        ۴. فال‌بک آفلاین به نزدیک‌ترین شهر ایران (با شرط حداکثر فاصله ۵۰ کیلومتر)
        """
        # ۱. چک کردن کش
        cached = self._get_from_cache(lat, lng)
        if cached:
            return cached

        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            "lat": lat,
            "lon": lng,
            "format": "json",
            "accept-language": "fa",
            "zoom": 12,
        }
        headers = {"User-Agent": "BarPro-Automation/2.0"}
        raw_data = None

        # ۲. تلاش مستقیم
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=2.5)
                ) as resp:
                    if resp.status == 200:
                        raw_data = await resp.json()
        except Exception:
            logger.debug("reverse_geocode_direct_failed")

        # ۳. تلاش با پروکسی چرخشی
        if raw_data is None:
            try:
                proxy_info = await get_proxy_rotator().get_next()
                if proxy_info and proxy_info.protocol in ("http", "https"):
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            url,
                            params=params,
                            headers=headers,
                            proxy=proxy_info.full_url,
                            timeout=aiohttp.ClientTimeout(total=3.5),
                        ) as resp:
                            if resp.status == 200:
                                raw_data = await resp.json()
            except Exception:
                logger.debug("reverse_geocode_proxy_failed")

        # اگر پاسخ از آنلاین دریافت شد
        if raw_data and isinstance(raw_data, dict):
            addr = raw_data.get("address", {})
            raw_prov = addr.get("state") or addr.get("province") or addr.get("county") or ""
            raw_cit = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("county") or ""
            dist = addr.get("suburb") or addr.get("district") or addr.get("neighbourhood") or ""
            disp = raw_data.get("display_name", "")

            prov, cit = match_location_to_known_dataset(raw_prov, raw_cit)

            if prov or cit:
                result = {
                    "success": True,
                    "province": prov,
                    "city": cit,
                    "district": dist,
                    "address": disp,
                    "display_name": disp,
                    "source": "online_geocode",
                    "is_approximate": False,
                }
                self._set_cache(lat, lng, result)
                return result

        # ۴. فال‌بک آفلاین: محاسبه نزدیک‌ترین شهر دیتابیس با حد آستانه فاصله (max 50km)
        best_match = None
        min_dist_km = float("inf")

        for p in IRAN_PROVINCES_DATA:
            for c in p["cities"]:
                dist_km = haversine_distance_km(lat, lng, c["lat"], c["lng"])
                if dist_km < min_dist_km:
                    min_dist_km = dist_km
                    best_match = {
                        "province": p["name"],
                        "city": c["name"],
                        "district": "",
                        "lat": c["lat"],
                        "lng": c["lng"],
                    }

        max_allowed_distance_km = 50.0

        if best_match and min_dist_km <= max_allowed_distance_km:
            result = {
                "success": True,
                "province": best_match["province"],
                "city": best_match["city"],
                "district": "",
                "address": f"محدوده {best_match['city']}، {best_match['province']}",
                "display_name": f"محدوده {best_match['city']}، {best_match['province']}",
                "source": "offline_dataset",
                "is_approximate": True,
                "distance_km": round(min_dist_km, 1),
            }
            self._set_cache(lat, lng, result)
            return result

        return {
            "success": False,
            "error": "مکان مورد نظر یافت نشد یا خارج از محدوده شهرهای ایران است",
            "province": "",
            "city": "",
            "district": "",
            "address": "",
            "display_name": "",
            "source": "out_of_bounds",
            "is_approximate": False,
        }


# Singleton instance
location_service = LocationService()
