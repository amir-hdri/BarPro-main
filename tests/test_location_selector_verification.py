import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.automation.location_selector import LocationSelector

@pytest.mark.asyncio
async def test_try_map_selection_verification_failure():
    """تست اطمینان از اینکه اگر فرم بعد از کلیک نقشه پر نشود، متد نقشه خطا برمی‌گرداند"""
    mock_page = AsyncMock()
    # Mock evaluate to simulate `is_filled = False` (address/province not filled)
    mock_page.evaluate.return_value = False

    selector = LocationSelector(mock_page)
    # Mock MapController methods
    selector.map_controller.detect_map_type = AsyncMock(return_value="google_maps")
    selector.map_controller.select_on_map = AsyncMock(return_value=True)
    selector.map_controller.wait_for_map_idle = AsyncMock()

    location_data = {
        "coordinates": {"lat": 35.0, "lng": 51.0},
        "address": "test address"
    }

    result = await selector._try_map_selection(location_data, prefix="Origin")

    # Must be false because fields were not populated
    assert result["success"] is False
    assert result["method"] == "map"
    assert "پر نشدند" in result["error"]


@pytest.mark.asyncio
async def test_try_map_selection_verification_success():
    """تست اطمینان از اینکه اگر فرم بعد از کلیک نقشه پر شود، متد نقشه موفق است"""
    mock_page = AsyncMock()
    # Mock evaluate to simulate `is_filled = True`
    mock_page.evaluate.return_value = True

    selector = LocationSelector(mock_page)
    selector.map_controller.detect_map_type = AsyncMock(return_value="google_maps")
    selector.map_controller.select_on_map = AsyncMock(return_value=True)
    selector.map_controller.wait_for_map_idle = AsyncMock()

    location_data = {
        "coordinates": {"lat": 35.0, "lng": 51.0},
        "address": "test address"
    }

    result = await selector._try_map_selection(location_data, prefix="Origin")

    assert result["success"] is True
    assert result["method"] == "map"
    assert result["map_type"] == "google_maps"
