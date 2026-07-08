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
    async def test_detect_google_map(self):
        page = AsyncMock()
        # Mock evaluate to return true for Google Maps check (first call)
        page.evaluate.side_effect = [True, False, False, False]

        controller = MapController(page)
        map_type = await controller.detect_map_type()
        self.assertEqual(map_type, "google_maps")

    async def test_location_selector_no_coordinates_falls_back_to_dropdown(self):
        """بدون مختصات، ابتدا dropdown امتحان شود."""
        page = AsyncMock()
        selector = LocationSelector(page)

        selector._assess_dropdown_runtime = AsyncMock(return_value={"viable": True, "undefined_only": False})
        selector._try_dropdown_selection = AsyncMock(return_value={"success": True, "method": "dropdown"})
        selector._try_internal_map_search = AsyncMock(return_value={"success": False, "error": "Not available"})
        selector._try_text_input = AsyncMock(return_value={"success": False, "error": "متن"})

        location_data = {"province": "Tehran", "city": "Tehran", "address": "Azadi"}
        result = await selector.select_location(location_data)

        self.assertTrue(result["success"])
        self.assertEqual(result["method"], "dropdown")
        selector._try_dropdown_selection.assert_awaited_once()

    async def test_location_selector_with_coordinates_tries_explicit_first(self):
        """با مختصات، اول explicit_coordinates امتحان شود."""
        page = AsyncMock()
        selector = LocationSelector(page)

        selector._try_explicit_coordinates = AsyncMock(
            return_value={"success": True, "method": "explicit_coordinates", "coordinates": {"lat": 35.0, "lng": 51.0}}
        )
        selector._try_map_selection = AsyncMock(
            return_value={"success": True, "method": "map", "coordinates": {"lat": 35.0, "lng": 51.0}}
        )
        selector._try_internal_map_search = AsyncMock(return_value={"success": False, "error": "Not available"})
        selector._assess_dropdown_runtime = AsyncMock(return_value={"viable": True, "undefined_only": False})
        selector._try_dropdown_selection = AsyncMock(return_value={"success": True, "method": "dropdown"})

        location_data = {
            "province": "Tehran",
            "city": "Tehran",
            "address": "Azadi",
            "coordinates": {"lat": 35.0, "lng": 51.0},
        }
        result = await selector.select_location(location_data)

        self.assertTrue(result["success"])
        self.assertEqual(result["method"], "explicit_coordinates")
        selector._try_explicit_coordinates.assert_awaited_once()
        selector._try_map_selection.assert_not_called()

    async def test_location_selector_explicit_fails_falls_back_to_map(self):
        """وقتی explicit_coordinates fail کند، به نقشه برود."""
        page = AsyncMock()
        selector = LocationSelector(page)

        selector._try_explicit_coordinates = AsyncMock(
            return_value={"success": False, "method": "explicit_coordinates", "error": "Fail"}
        )
        selector._try_map_selection = AsyncMock(
            return_value={"success": True, "method": "map", "coordinates": {"lat": 35.0, "lng": 51.0}}
        )
        selector._try_internal_map_search = AsyncMock(return_value={"success": False, "error": "Not available"})
        selector._assess_dropdown_runtime = AsyncMock(return_value={"viable": True, "undefined_only": False})
        selector._try_dropdown_selection = AsyncMock(return_value={"success": True, "method": "dropdown"})

        location_data = {
            "province": "Tehran",
            "city": "Tehran",
            "address": "Azadi",
            "coordinates": {"lat": 35.0, "lng": 51.0},
        }
        result = await selector.select_location(location_data)

        self.assertTrue(result["success"])
        self.assertEqual(result["method"], "map")
        selector._try_explicit_coordinates.assert_awaited_once()
        selector._try_map_selection.assert_awaited_once()

    async def test_location_selector_map_failure_falls_back_to_dropdown(self):
        """وقتی نقشه fail کند، به dropdown برود."""
        page = AsyncMock()
        selector = LocationSelector(page)

        selector._try_explicit_coordinates = AsyncMock(
            return_value={"success": False, "method": "explicit_coordinates", "error": "Fail"}
        )
        selector._try_map_selection = AsyncMock(return_value={"success": False, "method": "map", "error": "Fail"})
        selector._assess_dropdown_runtime = AsyncMock(return_value={"viable": True, "undefined_only": False})
        selector._try_dropdown_selection = AsyncMock(return_value={"success": True, "method": "dropdown"})
        selector._try_internal_map_search = AsyncMock(return_value={"success": False, "error": "Not available"})
        selector._try_text_input = AsyncMock(return_value={"success": False, "error": "متن"})

        location_data = {
            "province": "Tehran",
            "city": "Tehran",
            "address": "Azadi",
            "coordinates": {"lat": 35.0, "lng": 51.0},
        }
        result = await selector.select_location(location_data)

        self.assertTrue(result["success"])
        self.assertEqual(result["method"], "dropdown")
        selector._try_map_selection.assert_awaited_once()
        selector._try_dropdown_selection.assert_awaited_once()

    async def test_location_selector_all_methods_fail_raises(self):
        """وقتی همه روش‌ها fail شوند باید LocationSelectionError بدهد."""
        page = AsyncMock()
        selector = LocationSelector(page)

        selector._try_explicit_coordinates = AsyncMock(return_value={"success": False, "error": "explicit fail"})
        selector._try_map_selection = AsyncMock(return_value={"success": False, "error": "map fail"})
        selector._try_internal_map_search = AsyncMock(return_value={"success": False, "error": "internal map fail"})
        selector._try_dropdown_selection = AsyncMock(return_value={"success": False, "error": "dropdown fail"})
        selector._try_text_input = AsyncMock(return_value={"success": False, "error": "text fail"})

        location_data = {
            "province": "Tehran",
            "city": "Tehran",
            "address": "Azadi",
            "coordinates": {"lat": 35.0, "lng": 51.0},
        }

        with self.assertRaises(LocationSelectionError):
            await selector.select_location(location_data)

    async def test_haversine_calculation(self):
        page = AsyncMock()
        from app.automation.location_selector import RouteCalculator

        calculator = RouteCalculator(page)
        page.evaluate.side_effect = Exception("JS Error")

        origin = GeoCoordinate(35.6892, 51.3890)
        dest = GeoCoordinate(36.2972, 59.6067)

        result = await calculator.calculate_distance(origin, dest)

        self.assertEqual(result["method"], "haversine")
        self.assertTrue("km" in result["distance"])
        self.assertTrue(result["distance_value"] > 700000)

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_search_address(self, mock_sleep):
        page = AsyncMock()
        controller = MapController(page)

        expected_suggestions = [
            {"text": "Place A", "lat": 10.0, "lng": 20.0},
            {"text": "Place B", "lat": 11.0, "lng": 21.0},
        ]
        page.evaluate.return_value = expected_suggestions

        query = "Test Place"
        input_selector = "#search"

        result = await controller.search_address(query, input_selector)

        page.fill.assert_awaited_with(input_selector, query)
        page.evaluate.assert_awaited_once()

        self.assertEqual(result, expected_suggestions)
        self.assertEqual(mock_sleep.await_count, 2)


if __name__ == "__main__":
    unittest.main()
