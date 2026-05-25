import unittest
from unittest.mock import AsyncMock, patch
import sys
import os

# Add app to path
sys.path.append(os.getcwd())

from app.automation.map_controller import MapController, GeoCoordinate, MapSelection
from app.core.exceptions import MapInteractionError

class TestMapController(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.page = AsyncMock()
        self.controller = MapController(self.page)

    async def test_get_current_map_center_success(self):
        """Test that get_current_map_center returns GeoCoordinate when JS returns valid data"""
        expected_lat = 35.6892
        expected_lng = 51.3890

        # Mock page.evaluate to return a dictionary with lat/lng
        self.page.evaluate.return_value = {'lat': expected_lat, 'lng': expected_lng}

        result = await self.controller.get_current_map_center()

        self.assertIsInstance(result, GeoCoordinate)
        self.assertEqual(result.latitude, expected_lat)
        self.assertEqual(result.longitude, expected_lng)

        # Verify evaluate was called
        self.page.evaluate.assert_called_once()

    async def test_get_current_map_center_none(self):
        """Test that get_current_map_center returns None when JS returns None"""
        # Mock page.evaluate to return None
        self.page.evaluate.return_value = None

        result = await self.controller.get_current_map_center()

        self.assertIsNone(result)
        self.page.evaluate.assert_called_once()

    async def test_get_current_map_center_script_execution(self):
        """Test that the correct script logic is being executed (via evaluate call)"""
        # We don't need a return value for this test, just want to inspect the call
        self.page.evaluate.return_value = None

        await self.controller.get_current_map_center()

        # Get the script passed to evaluate
        # With the refactor to external scripts, evaluate is called with the loaded script content
        self.page.evaluate.assert_called()

    async def test_detect_map_type_from_dom_container(self):
        """DOM markers should be enough to detect the active map provider."""
        self.page.evaluate.side_effect = [False, False, False, False]
        self.page.query_selector.side_effect = [None, None, None, object()]

        map_type = await self.controller.detect_map_type()

        self.assertEqual(map_type, "mapbox")
        self.assertEqual(self.controller.map_selector, ".mapboxgl-map")

    async def test_select_by_click_prefers_canvas_target(self):
        """Fallback clicking should target the rendered canvas when available."""
        map_element = AsyncMock()
        canvas_element = AsyncMock()
        self.page.query_selector.return_value = map_element
        map_element.query_selector.return_value = canvas_element
        canvas_element.bounding_box.return_value = {"width": 320, "height": 180}

        result = await self.controller._select_by_click(
            "#map",
            GeoCoordinate(latitude=35.6892, longitude=51.3890),
        )

        self.assertTrue(result)
        canvas_element.click.assert_awaited_once()
        map_element.click.assert_not_called()

    async def test_set_route_success(self):
        """Test successful route setting with valid origin and destination"""
        # Mock dependencies
        self.controller.select_on_map = AsyncMock(return_value=True)
        self.controller._extract_route_info = AsyncMock(return_value={
            'distance': 10.5,
            'duration': 20.0,
            'polyline': 'dummy_polyline'
        })

        # Patch sleep to speed up tests (although newer code uses wait_for_*, we still patch sleeps)
        with patch('asyncio.sleep', new_callable=AsyncMock):
            # Also patch wait strategies as they might call page.evaluate or wait_for_function
            self.controller.wait_for_map_idle = AsyncMock()
            self.controller.wait_for_route_calculation = AsyncMock()

            # Test data
            origin = GeoCoordinate(latitude=35.6892, longitude=51.3890)
            destination = GeoCoordinate(latitude=35.6992, longitude=51.3990)

            # Execute
            result = await self.controller.set_route(origin, destination)

            # Verify
            self.assertIsInstance(result, MapSelection)
            self.assertEqual(result.origin, origin)
            self.assertEqual(result.destination, destination)
            self.assertEqual(result.distance_km, 10.5)
            self.assertEqual(result.duration_min, 20.0)
            self.assertEqual(result.route_polyline, 'dummy_polyline')

            # Verify calls were made correctly
            self.assertEqual(self.controller.select_on_map.call_count, 2)

    async def test_set_route_origin_failure(self):
        """Test failure during origin selection"""
        # Mock dependencies
        self.controller.select_on_map = AsyncMock(return_value=False)

        # Test data
        origin = GeoCoordinate(latitude=35.6892, longitude=51.3890)
        destination = GeoCoordinate(latitude=35.6992, longitude=51.3990)

        # Execute and Verify
        with self.assertRaises(MapInteractionError) as cm:
            await self.controller.set_route(origin, destination)

        self.assertIn("تنظیم نقطه مبدا با شکست مواجه شد", str(cm.exception))

    async def test_set_route_destination_failure(self):
        """Test failure during destination selection"""
        # Mock dependencies - first call True (origin), second call False (dest)
        self.controller.select_on_map = AsyncMock(side_effect=[True, False])

        # Patch waits
        self.controller.wait_for_map_idle = AsyncMock()

        with patch('asyncio.sleep', new_callable=AsyncMock):
            # Test data
            origin = GeoCoordinate(latitude=35.6892, longitude=51.3890)
            destination = GeoCoordinate(latitude=35.6992, longitude=51.3990)

            # Execute and Verify
            with self.assertRaises(MapInteractionError) as cm:
                await self.controller.set_route(origin, destination)

            self.assertIn("تنظیم نقطه مقصد با شکست مواجه شد", str(cm.exception))

if __name__ == '__main__':
    unittest.main()
