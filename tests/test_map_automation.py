import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

# Add app to path
sys.path.append(os.getcwd())

from app.automation.location_selector import LocationSelector
from app.automation.map_controller import GeoCoordinate, MapController
from app.core.exceptions import LocationSelectionError


class TestMapAutomation(unittest.IsolatedAsyncioTestCase):
    def _create_mock_page(self):
        from unittest.mock import MagicMock
        page = AsyncMock()
        page.locator = MagicMock()
        mock_loc = MagicMock()
        mock_loc.input_value = AsyncMock(return_value="Tehran")
        page.locator.return_value = mock_loc
        page.on = MagicMock()
        return page

    async def test_detect_google_map(self):
        page = self._create_mock_page()
        # Mock evaluate to return true for Google Maps check (first call)
        page.evaluate.side_effect = [True, False, False, False]

        controller = MapController(page)
        map_type = await controller.detect_map_type()
        self.assertEqual(map_type, "google_maps")

    async def test_location_selector_direct_fill_success(self):
        """انتخاب مکان به صورت متنی مستقیم."""
        page = self._create_mock_page()
        selector = LocationSelector(page)

        selector._try_utcms_direct_fill = AsyncMock(
            return_value={"success": True, "method": "utcms_direct_text", "province": "Tehran", "city": "Tehran"}
        )

        location_data = {"province": "Tehran", "city": "Tehran", "address": "Azadi"}
        result = await selector.select_location(location_data)

        self.assertTrue(result["success"])
        self.assertEqual(result["method"], "utcms_direct_text")
        selector._try_utcms_direct_fill.assert_awaited_once()

    async def test_location_selector_with_coordinates_uses_direct_fill(self):
        """در حالت فعلی بدون وابستگی به GPS از جریان متنی استفاده می‌شود."""
        page = self._create_mock_page()
        selector = LocationSelector(page)

        selector._try_utcms_direct_fill = AsyncMock(
            return_value={
                "success": True,
                "method": "utcms_direct_text",
                "coordinates_used": False,
            }
        )

        location_data = {
            "province": "Tehran",
            "city": "Tehran",
            "address": "Azadi",
            "coordinates": {"lat": 35.0, "lng": 51.0},
        }
        result = await selector.select_location(location_data)

        self.assertTrue(result["success"])
        self.assertEqual(result["method"], "utcms_direct_text")

    async def test_location_selector_direct_fill_failure_raises(self):
        """شکست در انتخاب متنی مکان باید LocationSelectionError بدهد."""
        page = self._create_mock_page()
        selector = LocationSelector(page)

        selector._try_utcms_direct_fill = AsyncMock(
            return_value={"success": False, "error": "استان یافت نشد"}
        )

        location_data = {
            "province": "Tehran",
            "city": "Tehran",
            "address": "Azadi",
        }
        with self.assertRaises(LocationSelectionError):
            await selector.select_location(location_data)

    async def test_haversine_calculation(self):
        page = self._create_mock_page()
        from app.automation.location_selector import RouteCalculator

        calculator = RouteCalculator(page)
        page.evaluate.side_effect = Exception("JS Error")

        origin = GeoCoordinate(35.6892, 51.3890)
        dest = GeoCoordinate(36.2972, 59.6067)

        result = await calculator.calculate_distance(origin, dest)

        self.assertEqual(result["method"], "haversine")
        self.assertTrue("km" in result["distance"])
        self.assertTrue(result["distance_value"] > 700000)

    async def test_search_address(self):
        page = self._create_mock_page()
        controller = MapController(page)

        expected_suggestions = [
            {"text": "Place A", "lat": 10.0, "lng": 20.0},
            {"text": "Place B", "lat": 11.0, "lng": 21.0},
        ]
        page.evaluate = AsyncMock(return_value=expected_suggestions)
        page.fill = AsyncMock()

        query = "Test Place"
        input_selector = "#search"

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await controller.search_address(query, input_selector)

        page.fill.assert_awaited_with(input_selector, query)
        self.assertEqual(result, expected_suggestions)


if __name__ == "__main__":
    unittest.main()
