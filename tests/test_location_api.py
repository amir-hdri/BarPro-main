"""
تست‌های خودکار APIهای سرویس مکان، پارسر هوشمند آدرس و استان‌ها/شهرها
"""

from app.core.iran_locations import (
    find_nearest_city_coords,
    get_all_provinces,
    get_cities_by_province,
    parse_smart_address,
)


def test_iran_locations_dataset():
    provinces = get_all_provinces()
    assert len(provinces) >= 30
    province_names = [p["name"] for p in provinces]
    assert "تهران" in province_names
    assert "اصفهان" in province_names

    tehran_cities = get_cities_by_province("تهران")
    assert len(tehran_cities) > 0
    city_names = [c["name"] for c in tehran_cities]
    assert "اسلامشهر" in city_names or "تهران" in city_names


def test_parse_smart_address():
    res = parse_smart_address("اصفهان، خمینی‌شهر، شهرک صنعتی جی، خیابان دهم پلاک ۱۲")
    assert res["province"] == "اصفهان"
    assert res["city"] == "خمینی‌شهر" or res["city"] == "اصفهان"
    assert res["address"] != ""
    assert res["coordinates"] is not None


def test_offline_reverse_geocode_fallback():
    # Tehrans lat/lng
    match = find_nearest_city_coords(35.6892, 51.3890)
    assert match is not None
    assert match["province"] == "تهران"
    assert match["city"] == "تهران"
