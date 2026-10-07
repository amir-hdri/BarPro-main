"""Street-level geocoding: never reuse a neighboring pin's address or invent one."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.auth_multitenant import get_current_user_or_admin
from app.main import app
from app.services.location_service import LocationService, match_location_to_known_dataset


def test_nearby_pins_have_independent_street_addresses():
    service = LocationService()
    service._set_cache(35.68921, 51.38901, {"address": "street A", "is_approximate": False})
    assert service._get_from_cache(35.68921, 51.38901)["address"] == "street A"
    assert service._get_from_cache(35.68949, 51.38949) is None


def test_similar_city_names_are_not_replaced_by_substring():
    assert match_location_to_known_dataset("استان کرمانشاه", "کرمانشاه")[0] == "کرمانشاه"
    assert match_location_to_known_dataset("تهران", "تهرانپارس")[1] == "تهرانپارس"


@pytest.mark.asyncio
async def test_offline_city_hint_does_not_fill_exact_address(monkeypatch):
    monkeypatch.setattr("app.services.location_service.aiohttp.ClientSession", MagicMock(side_effect=RuntimeError()))
    monkeypatch.setattr(
        "app.services.location_service.get_proxy_rotator",
        lambda: MagicMock(get_next=AsyncMock(return_value=None)),
    )
    result = await LocationService().reverse_geocode(35.6892, 51.389)
    assert result["success"] is True
    assert result["is_approximate"] is True
    assert result["city"] == "تهران"
    assert result["address"] == ""


@pytest.mark.asyncio
async def test_online_query_requests_street_detail(monkeypatch):
    response = MagicMock(status=200)
    response.json = AsyncMock(
        return_value={
            "address": {"state": "تهران", "city": "تهران", "road": "آزادی", "country_code": "ir"},
            "display_name": "تهران، خیابان آزادی",
        }
    )
    request = MagicMock()
    request.__aenter__ = AsyncMock(return_value=response)
    client = MagicMock()
    client.get.return_value = request
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    monkeypatch.setattr("app.services.location_service.aiohttp.ClientSession", lambda: context)
    result = await LocationService().reverse_geocode(35.6892, 51.389)
    assert result["address"] == "تهران، خیابان آزادی"
    assert result["is_approximate"] is False
    assert client.get.call_args.kwargs["params"]["zoom"] == 18


@pytest.mark.parametrize("lat,lng", [(91, 50), (35, 181), ("NaN", 50), (35, "inf")])
def test_invalid_coordinates_rejected_before_geocoding(lat, lng, monkeypatch):
    geocode = AsyncMock()
    monkeypatch.setattr("app.services.location_service.location_service.reverse_geocode", geocode)
    app.dependency_overrides[get_current_user_or_admin] = lambda: {"role": "master_admin"}
    try:
        response = TestClient(app).get("/api/v1/locations/reverse-geocode", params={"lat": lat, "lng": lng})
        assert response.status_code == 422
        geocode.assert_not_awaited()
    finally:
        app.dependency_overrides.pop(get_current_user_or_admin, None)
