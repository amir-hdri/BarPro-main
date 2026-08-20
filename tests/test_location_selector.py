import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

# Add app to path
sys.path.append(os.getcwd())

from app.automation.location_selector import LocationSelector


class TestLocationSelector(unittest.IsolatedAsyncioTestCase):
    async def test_assess_dropdown_runtime_skips_when_only_undefined_options_exist(self):
        page = AsyncMock()
        selector = LocationSelector(page)
        selector._inspect_select_runtime = AsyncMock(
            side_effect=[
                {
                    "selector": "#ddStateSource",
                    "visible": True,
                    "total_options": 2,
                    "placeholder_count": 0,
                    "undefined_count": 2,
                    "real_option_count": 0,
                    "real_option_samples": [],
                },
                {
                    "selector": "#ddStateSourceBackup",
                    "visible": True,
                    "total_options": 1,
                    "placeholder_count": 0,
                    "undefined_count": 1,
                    "real_option_count": 0,
                    "real_option_samples": [],
                },
            ]
        )

        runtime = await selector._assess_dropdown_runtime(
            {"province": ["#ddStateSource", "#ddStateSourceBackup"]},
            "Origin",
        )

        self.assertFalse(runtime["viable"])
        self.assertTrue(runtime["undefined_only"])
        self.assertEqual(runtime["decision"], "skip_to_favorite_or_select2")

    async def test_select_location_skips_dropdown_when_runtime_marks_it_unusable(self):
        page = AsyncMock()
        selector = LocationSelector(page)
        selector._try_utcms_direct_fill = AsyncMock(return_value={"success": True, "method": "utcms_direct_text"})

        result = await selector.select_location(
            {"province": "Tehran", "city": "Tehran", "address": "Azadi"},
            origin=True,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["method"], "utcms_direct_text")
        selector._try_utcms_direct_fill.assert_awaited_once()

    async def test_try_dropdown_selection_success(self):
        # Setup
        page = AsyncMock()
        selector = LocationSelector(page)

        # Mock _select_from_options to always return True
        selector._select_from_options = AsyncMock(return_value=True)

        # Mock page.fill for address
        page.fill = AsyncMock()
        page.eval_on_selector = AsyncMock(return_value=False)
        selector._wait_for_select_options = AsyncMock(return_value=True)
        selector._log_select_diagnostics = AsyncMock()

        # Mock asyncio.sleep to speed up tests
        with patch("asyncio.sleep", new_callable=AsyncMock):
            location_data = {
                "province": "Tehran",
                "city": "Tehran City",
                "district": "District 1",
                "address": "Azadi Square",
            }
            prefix = "Origin"

            # Execute
            result = await selector._try_dropdown_selection(location_data, prefix)

            # Verify Result
            self.assertTrue(result["success"])
            self.assertEqual(result["method"], "dropdown")
            self.assertEqual(result["province"], "Tehran")

            # Verify Interactions
            # 1. Province Selection
            self.assertTrue(selector._select_from_options.called)
            # check calls
            calls = selector._select_from_options.call_args_list

            # Province call
            self.assertIn('select[name="OriginProvince"]', calls[0][0][0])
            self.assertEqual(calls[0][0][1], "Tehran")

            # City call
            self.assertIn('select[name="OriginCity"]', calls[1][0][0])
            self.assertEqual(calls[1][0][1], "Tehran City")

            # District call
            self.assertIn('select[name="OriginDistrict"]', calls[2][0][0])
            self.assertEqual(calls[2][0][1], "District 1")

            # Address fill
            page.fill.assert_called()
            fill_args = page.fill.call_args[0]
            self.assertIn("#txtAddressSource", fill_args[0] or str(fill_args))
            self.assertEqual(fill_args[1], "Azadi Square")

    async def test_try_dropdown_selection_province_fail(self):
        # Setup
        page = AsyncMock()
        selector = LocationSelector(page)

        # Mock province failure
        selector._select_from_options = AsyncMock(side_effect=[False, True, True])
        selector._wait_for_select_options = AsyncMock(return_value=True)
        selector._log_select_diagnostics = AsyncMock()

        location_data = {"province": "Unknown"}
        prefix = "Origin"

        # Execute
        result = await selector._try_dropdown_selection(location_data, prefix)

        # Verify
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "انتخاب استان با شکست مواجه شد")

        # Should only try province
        self.assertEqual(selector._select_from_options.call_count, 1)

    async def test_try_dropdown_selection_city_fail(self):
        # Setup
        page = AsyncMock()
        selector = LocationSelector(page)

        # Mock province success, city failure
        selector._select_from_options = AsyncMock(side_effect=[True, False, True])
        selector._wait_for_select_options = AsyncMock(return_value=True)
        selector._log_select_diagnostics = AsyncMock()

        with patch("asyncio.sleep", new_callable=AsyncMock):
            location_data = {"province": "Tehran", "city": "Unknown"}
            prefix = "Origin"

            # Execute
            result = await selector._try_dropdown_selection(location_data, prefix)

            # Verify
            self.assertFalse(result["success"])
            self.assertEqual(result["error"], "انتخاب شهر با شکست مواجه شد")

            # Should try province and city
            self.assertEqual(selector._select_from_options.call_count, 2)

    async def test_try_map_selection_uses_explicit_click_coordinates_only(self):
        page = AsyncMock()
        selector = LocationSelector(page)

        selector.map_controller.detect_map_type = AsyncMock(return_value="google_maps")
        selector.map_controller.select_on_map = AsyncMock(return_value=True)
        selector.map_controller.wait_for_map_idle = AsyncMock()
        selector._find_map_search_input = AsyncMock(return_value="#search")
        selector._geocode_address = AsyncMock(return_value={"lat": 0, "lng": 0})

        location_data = {
            "province": "Tehran",
            "city": "Tehran",
            "address": "Azadi",
            "coordinates": {"lat": 35.7, "lng": 51.4},
        }

        result = await selector._try_map_selection(location_data, "Origin")

        self.assertTrue(result["success"])
        selector.map_controller.select_on_map.assert_awaited_once()
        call = selector.map_controller.select_on_map.await_args
        self.assertEqual(call.kwargs["search_input_selector"], "#AddressSearch")
        selector._find_map_search_input.assert_not_called()
        selector._geocode_address.assert_not_called()

    async def test_fill_coordinate_hidden_fields_case_insensitivity_and_scoping(self):
        page = AsyncMock()
        selector = LocationSelector(page)
        selector._fill_input_like = AsyncMock(return_value=True)

        result = await selector._fill_coordinate_hidden_fields(35.7, 51.4, "Origin")

        self.assertTrue(result)
        # Check that case-insensitive and scoped selectors were passed to _fill_input_like
        calls = [call[0][0] for call in selector._fill_input_like.call_args_list]
        self.assertTrue(any('#pills-5 input[name*="lat"]' in c for c in calls))
        self.assertTrue(any('#pills-5 input[name*="lng"]' in c for c in calls))
        self.assertTrue(any('input[name*="lat"' in c for c in calls))
        self.assertTrue(any('input[name*="lng"' in c for c in calls))

    async def test_inject_coordinates_via_js_contains_value_tracker(self):
        page = AsyncMock()
        selector = LocationSelector(page)
        page.evaluate = AsyncMock(return_value=True)

        result = await selector._inject_coordinates_via_js(35.7, 51.4, "Origin")

        self.assertTrue(result)
        page.evaluate.assert_called_once()
        script = page.evaluate.call_args[0][0]
        self.assertIn("_valueTracker", script)
        self.assertIn("setValue", script)


if __name__ == "__main__":
    unittest.main()
