"""
تست‌های واحد برای سرویس مکان‌ها، پریفیکس API جدید، پاکسازی استعلام‌های معلق و گزینه‌های پویا
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.location_service import (
    clean_location_name,
    haversine_distance_km,
    location_service,
    match_location_to_known_dataset,
)


@pytest.mark.asyncio
async def test_location_name_cleaning():
    assert clean_location_name("استان اصفهان") == "اصفهان"
    assert clean_location_name("شهرستان خمینی‌شهر") == "خمینی شهر"
    assert clean_location_name("شهر تهران") == "تهران"


@pytest.mark.asyncio
async def test_match_location_to_known_dataset():
    prov, cit = match_location_to_known_dataset("استان اصفهان", "شهرستان خمینی‌شهر")
    assert prov == "اصفهان"
    assert cit == "خمینی‌شهر"


@pytest.mark.asyncio
async def test_haversine_distance():
    # تهران به اصفهان حدود ۳۴۰ کیلومتر
    dist = haversine_distance_km(35.6892, 51.3890, 32.6546, 51.6680)
    assert 300 < dist < 400


@pytest.mark.asyncio
async def test_location_service_offline_fallback():
    # نقطه دقیق میدان آزادی تهران
    res = await location_service.reverse_geocode(35.6997, 51.3380)
    assert res["success"] is True
    assert res["province"] == "تهران"
    assert res["city"] == "تهران"

    # نقطه دوردست خارج از حد آستانه (اقیانوس هند)
    out_res = await location_service.reverse_geocode(0.0, 0.0)
    assert out_res["success"] is False
    assert out_res["source"] == "out_of_bounds"


def test_api_v1_location_routes():
    client = TestClient(app)

    # تست استان‌ها با پریفیکس جدید /api/v1/locations/provinces
    resp = client.get("/api/v1/locations/provinces")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 31

    # تست شهرها با پریفیکس جدید
    resp_cities = client.get("/api/v1/locations/cities?province=تهران")
    assert resp_cities.status_code == 200
    cities_data = resp_cities.json()
    assert isinstance(cities_data, list)
    assert len(cities_data) > 0


def test_fuel_inquiry_options_route():
    client = TestClient(app)
    resp = client.get("/api/v1/fuel-inquiries/options")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["years"]) == 10
    assert len(data["months"]) == 12


def test_parse_address_route():
    client = TestClient(app)
    resp = client.post("/api/v1/locations/parse-address", json={"address_text": "اصفهان خمینی شهر خیابان دهم"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["province"] == "اصفهان"
    assert data["city"] == "خمینی‌شهر" or data["city"] == "اصفهان"


def test_location_favorite_model():
    from app.models.location_favorite import LocationFavorite

    fav = LocationFavorite(
        client_id=1,
        title="انبار مرکزی",
        province="تهران",
        city="تهران",
        district="منطقه ۱",
        address="خیابان آزادی پلاک ۱",
    )
    assert fav.client_id == 1
    assert fav.title == "انبار مرکزی"
    assert fav.is_origin is True
    assert fav.is_destination is True

