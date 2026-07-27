import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

# Add app to path
sys.path.append(os.getcwd())

from app.automation.waybill_enhanced import EnhancedWaybillManager
from app.core.config import utcms_config
from app.core.exceptions import WaybillError


class TestEnhancedWaybillManager(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        """Setup lightweight mocks for fast, isolated tests."""
        self.mock_page = self._create_mock_page()
        self.mock_context = AsyncMock()

        # Use patch.object for cleaner teardown
        self.patches = []
        self._setup_patches()

        # Initialize manager with mocked dependencies
        self.manager = EnhancedWaybillManager(self.mock_page, self.mock_context)
        self._configure_manager_mocks()

    def _create_mock_page(self):
        """Create a reusable mock page with common methods."""
        from unittest.mock import MagicMock

        mock = AsyncMock()
        mock.goto = AsyncMock()
        mock.query_selector = AsyncMock()
        mock.query_selector_all = AsyncMock(return_value=[])
        mock.evaluate = AsyncMock(return_value=False)
        mock.wait_for_selector = AsyncMock(return_value=None)
        mock.wait_for_timeout = AsyncMock()

        # Setup locator mock to avoid coroutine warnings in _is_element_visible / _element_exists
        mock.locator = MagicMock()
        mock_loc = MagicMock()
        mock_loc.first = mock_loc
        mock_loc.count = AsyncMock(return_value=1)
        mock_loc.is_visible = AsyncMock(return_value=True)
        mock_loc.all = AsyncMock(return_value=[])
        mock_loc.wait_for = AsyncMock()
        mock.locator.return_value = mock_loc

        # page.on() is synchronous in Playwright — MagicMock prevents
        # RuntimeWarning "coroutine 'AsyncMockMixin._execute_mock_call' was never awaited"
        mock.on = MagicMock()

        return mock

    def _setup_patches(self):
        """Setup all patches in one place for easier management."""
        patch_targets = [
            ("app.automation.waybill_enhanced.PageInteractor", "mock_interactor"),
            ("app.automation.waybill_enhanced.MapController", "mock_map_controller"),
            ("app.automation.waybill_enhanced.LocationSelector", "mock_location_selector"),
            ("app.automation.waybill_enhanced.RouteCalculator", "mock_route_calculator"),
        ]

        for target, attr_name in patch_targets:
            patcher = patch(target)
            self.patches.append(patcher)
            mock_class = patcher.start()
            mock_instance = mock_class.return_value
            setattr(self, attr_name, mock_instance)

    def _configure_manager_mocks(self):
        """Configure common mock behaviors."""
        self.mock_interactor.safe_fill = AsyncMock(return_value=True)
        self.mock_interactor.safe_click = AsyncMock(return_value=True)
        self.mock_interactor.screenshot = AsyncMock()

        self.mock_location_selector.select_location = AsyncMock()
        self.mock_route_calculator.calculate_distance = AsyncMock()

        self.manager._handle_submit_captcha_if_present = AsyncMock()
        self.manager.smart_locator = AsyncMock()

        def mock_locate(page, selectors, *args, **kwargs):
            if any("otp" in str(sel).lower() for sel in selectors):
                raise Exception("OTP selector not present in mock")
            return AsyncMock()

        self.manager.smart_locator.locate = AsyncMock(side_effect=mock_locate)

        async def mock_locator_current_value(loc):
            if loc.fill.called:
                return loc.fill.call_args[0][0]
            if loc.type.called:
                return loc.type.call_args[0][0]
            if loc.select_option.called:
                kwargs = loc.select_option.call_args[1]
                return kwargs.get("value") or kwargs.get("label") or ""
            return ""

        self.manager._locator_current_value = mock_locator_current_value

    async def asyncTearDown(self):
        """Clean teardown of all patches."""
        for patcher in self.patches:
            patcher.stop()
        self.patches.clear()

    async def test_initialization(self):
        """Test that the manager initializes its components correctly."""
        self.assertIs(self.manager.page, self.mock_page)
        self.assertIs(self.manager.context, self.mock_context)
        self.assertIs(self.manager.interactor, self.mock_interactor)
        self.assertIs(self.manager.map_controller, self.mock_map_controller)
        self.assertIs(self.manager.location_selector, self.mock_location_selector)
        self.assertIs(self.manager.route_calculator, self.mock_route_calculator)

    async def test_create_waybill_success(self):
        """Test the happy path for creating a waybill."""
        # Setup data
        data = {
            "sender": {"name": "Sender"},
            "receiver": {"name": "Receiver"},
            "origin": {"province": "Tehran", "coordinates": {"lat": 35.6892, "lng": 51.3890}},
            "destination": {"province": "Mashhad", "coordinates": {"lat": 36.2972, "lng": 59.6067}},
            "cargo": {"type": "General", "weight": 1000},
            "vehicle": {"plate": "12A34567"},
            "financial": {"cost": 5000000},
        }

        # Mock location selection
        self.mock_location_selector.select_location.side_effect = [
            {"success": True, "method": "map", "coordinates": data["origin"]["coordinates"]},  # Origin
            {"success": True, "method": "map", "coordinates": data["destination"]["coordinates"]},  # Destination
        ]

        # Mock route calculation
        route_info = {"distance": "900 km", "duration": "10h"}
        self.mock_route_calculator.calculate_distance.return_value = route_info

        # Mock tracking code extraction (inside _submit_waybill)
        # We need to mock _extract_tracking_code method on the instance or simulate page behavior
        # Since _extract_tracking_code calls page methods, we can mock page.query_selector
        mock_element = AsyncMock()
        mock_element.text_content.return_value = "Code: 123456"
        self.mock_page.query_selector.return_value = mock_element

        # Run
        result = await self.manager.create_waybill_with_map(data)

        # Assertions
        self.assertTrue(result["success"])
        self.assertEqual(result["tracking_code"], "123456")
        self.assertEqual(result["route"], route_info)

        # Verify calls
        self.mock_page.goto.assert_called_with(
            utcms_config.WAYBILL_URL,
            wait_until="domcontentloaded",
            timeout=utcms_config.PAGE_NAVIGATION_TIMEOUT,
        )
        # Verify filled values using selector inventory
        inventory = self.manager._selector_inventory
        self.assertIn("sender:نام فرستنده", inventory)
        self.assertEqual(inventory["sender:نام فرستنده"]["value_summary"], "Sender")
        self.assertIn("receiver:نام گیرنده", inventory)
        self.assertEqual(inventory["receiver:نام گیرنده"]["value_summary"], "Receiver")
        self.assertIn("cargo:وزن کالا", inventory)
        self.assertEqual(inventory["cargo:وزن کالا"]["value_summary"], "1000")
        self.assertIn("vehicle:پلاک خودرو", inventory)
        self.assertEqual(inventory["vehicle:پلاک خودرو"]["value_summary"], "12A34567")

        # Check select_location calls
        self.assertEqual(self.mock_location_selector.select_location.call_count, 2)
        self.mock_location_selector.select_location.assert_any_call(data["origin"], origin=True)
        self.mock_location_selector.select_location.assert_any_call(data["destination"], origin=False)

        # Check route calculation
        self.mock_route_calculator.calculate_distance.assert_called_once()

    async def test_create_waybill_origin_failure(self):
        """Test failure when origin selection fails."""
        data = {
            "sender": {},
            "receiver": {},
            "vehicle": {"plate": "12A34567"},
            "cargo": {"type": "General", "weight": 1000},
            "origin": {},
            "destination": {},
        }

        # Mock origin failure
        self.mock_location_selector.select_location.return_value = {"success": False, "error": "Map error"}

        with self.assertRaises(WaybillError) as context:
            await self.manager.create_waybill_with_map(data)

        self.assertIn("انتخاب مبدا با شکست مواجه شد", str(context.exception))
        self.mock_interactor.screenshot.assert_called_once_with("waybill_map_error")

    async def test_create_waybill_destination_failure(self):
        """Test failure when destination selection fails."""
        data = {
            "sender": {},
            "receiver": {},
            "vehicle": {"plate": "12A34567"},
            "cargo": {"type": "General", "weight": 1000},
            "origin": {},
            "destination": {},
        }

        # Mock origin success, destination failure
        self.mock_location_selector.select_location.side_effect = [
            {"success": True, "coordinates": {"lat": 1, "lng": 1}},
            {"success": False, "error": "Map error"},
        ]

        with self.assertRaises(WaybillError) as context:
            await self.manager.create_waybill_with_map(data)

        self.assertIn("انتخاب مقصد با شکست مواجه شد", str(context.exception))
        self.mock_interactor.screenshot.assert_called_once_with("waybill_map_error")

    async def test_route_calculation_logic(self):
        """Test that route calculation is skipped if coordinates are missing."""
        data = {
            "sender": {},
            "receiver": {},
            "vehicle": {"plate": "12A34567"},
            "cargo": {"type": "General", "weight": 1000},
            "origin": {"province": "Tehran"},
            "destination": {"province": "Mashhad"},
        }

        # Mock success but no coordinates returned
        self.mock_location_selector.select_location.side_effect = [
            {"success": True, "coordinates": None},
            {"success": True, "coordinates": None},
        ]

        # Mock tracking code extraction to avoid failure later
        mock_element = AsyncMock()
        mock_element.text_content.return_value = "123456"
        self.mock_page.query_selector.return_value = mock_element

        result = await self.manager.create_waybill_with_map(data)

        self.mock_route_calculator.calculate_distance.assert_not_called()
        self.assertIsNone(result.get("route"))

    async def test_fill_financial_info(self):
        """Test financial info filling logic."""
        financial_data = {"cost": 1000, "payment_method": "Cash"}

        # We need to test the private method _fill_financial_info indirectly or call it directly
        # Calling directly for unit testing is acceptable in Python
        self.manager._set_active_pill("financial")
        await self.manager._fill_financial_info(financial_data)

        # Verify filled values using selector inventory
        inventory = self.manager._selector_inventory
        self.assertIn("financial:هزینه حمل", inventory)
        self.assertEqual(inventory["financial:هزینه حمل"]["value_summary"], "1000")

    async def test_submit_waybill_tracking_extraction(self):
        """Test extraction of tracking code from different sources."""
        # 1. Test extraction from element text
        mock_element = AsyncMock()
        mock_element.text_content.return_value = "شماره رهگیری: 987654"
        self.mock_page.query_selector.return_value = mock_element
        self.mock_page.evaluate = AsyncMock(return_value="")

        code = await self.manager._extract_tracking_code()
        self.assertEqual(code, "987654")

        # 2. Test extraction from URL fallback
        self.mock_page.query_selector.side_effect = Exception("Not found")
        self.mock_page.url = "http://example.com/waybill/TRACK12345678"

        code = await self.manager._extract_tracking_code()
        self.assertEqual(code, "TRACK12345678")

    async def test_parse_register_submit_payload_reads_document_id_and_otp_flag(self):
        payload = {
            "success": True,
            "data": {
                "resultCode": 200,
                "resultMessage": "عملیات با موفقیت انجام شد",
                "obj": {"id": 79791831, "isOtpNeeded": True},
            },
        }

        result = self.manager._parse_register_submit_payload(payload)

        self.assertTrue(result["success"])
        self.assertEqual(result["document_id"], 79791831)
        self.assertTrue(result["is_otp_needed"])

    async def test_detect_otp_required_uses_submit_state_first(self):
        self.mock_page.query_selector = AsyncMock(return_value=None)

        detected = await self.manager._detect_otp_required(submit_state={"document_id": 1, "is_otp_needed": True})

        self.assertTrue(detected)

    async def test_submit_waybill_rejects_click_failure(self):
        """Submit should fail when click action cannot be performed."""
        self.mock_interactor.safe_click = AsyncMock(return_value=False)
        self.mock_page.query_selector = AsyncMock(return_value=None)
        self.manager.smart_locator.locate = AsyncMock(side_effect=Exception("Smart locator click failed"))

        with self.assertRaises(WaybillError) as context:
            await self.manager._submit_waybill()

        self.assertIn("کلیک روی دکمه ثبت ناموفق بود", str(context.exception))
        self.assertGreaterEqual(self.mock_interactor.safe_click.await_count, 2)

    async def test_submit_waybill_rejects_unconfirmed_result(self):
        """Submit should fail when no tracking code or success marker exists."""
        self.mock_interactor.safe_click = AsyncMock(return_value=True)
        self.manager._extract_tracking_code = AsyncMock(return_value=None)
        self.manager._is_submission_successful = AsyncMock(return_value=False)
        self.manager._extract_form_errors = AsyncMock(return_value="اعتبارسنجی فرم ناموفق بود")

        with self.assertRaises(WaybillError) as context:
            await self.manager._submit_waybill()

        self.assertIn("اعتبارسنجی فرم ناموفق بود", str(context.exception))

    async def test_create_waybill_generic_error(self):
        """Test handling of unexpected exceptions."""
        data = {"sender": {}}
        # Mock page.goto to raise an exception
        self.mock_page.goto.side_effect = Exception("Network Error")

        with self.assertRaises(WaybillError) as context:
            await self.manager.create_waybill_with_map(data)

        self.assertIn("ایجاد بارنامه با شکست مواجه شد: Network Error", str(context.exception))
        self.mock_interactor.screenshot.assert_called_once_with("waybill_map_error")

    async def test_fill_with_fallback_records_selector_inventory_status(self):
        self.manager.smart_locator.locate = AsyncMock(side_effect=Exception("not found"))
        self.mock_interactor.safe_fill = AsyncMock(side_effect=[False, True])
        self.manager._set_value_with_js = AsyncMock(return_value=False)

        await self.manager._fill_with_fallback(
            ["#primary", "#secondary"],
            "value-1",
            "field-x",
            required=False,
        )

        inventory = self.manager._selector_inventory["bootstrap:field-x"]
        self.assertEqual(inventory["status"], "fallback-only")
        self.assertEqual(inventory["selector_used"], "#secondary")
        self.assertEqual(inventory["value_summary"], "value-1")

    async def test_selector_inventory_audit_emits_monitoring_schema(self):
        self.manager._record_selector_inventory(
            field_label="نام فرستنده",
            selectors=["#txtSenderFirstName"],
            status="filled",
            selector_used="#txtSenderFirstName",
            value="Ali",
            pill="sender",
        )

        with self.assertLogs("app.automation.waybill_enhanced", level="INFO") as captured:
            self.manager._log_selector_inventory_audit()

        message = "\n".join(captured.output)
        self.assertIn("waybill_selector_inventory_audit", message)
        inventory = self.manager._selector_inventory["sender:نام فرستنده"]
        self.assertEqual(inventory["status"], "filled")

    async def test_parse_free_zone_plate(self):
        parsed = self.manager._parse_free_zone_plate("12345 اروند")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["number"], "12345")
        self.assertEqual(parsed["two_digit"], "")
        self.assertEqual(parsed["zone_id"], "1")
        self.assertEqual(parsed["zone_name"], "اروند")

        parsed2 = self.manager._parse_free_zone_plate("12345-12 اروند")
        self.assertIsNotNone(parsed2)
        self.assertEqual(parsed2["number"], "12345")
        self.assertEqual(parsed2["two_digit"], "12")

        parsed3 = self.manager._parse_free_zone_plate("12345 34 اروند")
        self.assertIsNotNone(parsed3)
        self.assertEqual(parsed3["number"], "12345")
        self.assertEqual(parsed3["two_digit"], "34")

        # Non-matching
        self.assertIsNone(self.manager._parse_free_zone_plate("12345678"))

    async def test_create_waybill_free_zone_plate_success(self):
        data = {
            "sender": {"name": "Sender"},
            "receiver": {"name": "Receiver"},
            "origin": {"province": "Tehran", "coordinates": {"lat": 35.6892, "lng": 51.3890}},
            "destination": {"province": "Mashhad", "coordinates": {"lat": 36.2972, "lng": 59.6067}},
            "cargo": {"type": "General", "weight": 1000},
            "vehicle": {"plate": "12345 اروند"},
            "financial": {"cost": 5000000},
        }

        # Mock location selection
        self.mock_location_selector.select_location.side_effect = [
            {"success": True, "method": "map", "coordinates": data["origin"]["coordinates"]},
            {"success": True, "method": "map", "coordinates": data["destination"]["coordinates"]},
        ]

        # Mock tracking code extraction
        mock_element = AsyncMock()
        mock_element.text_content.return_value = "Code: 123456"
        self.mock_page.query_selector.return_value = mock_element

        result = await self.manager.create_waybill_with_map(data)
        self.assertTrue(result["success"])

        # Verify free zone plate was logged in inventory
        inventory = self.manager._selector_inventory
        self.assertIn("vehicle:منطقه آزاد", inventory)
        self.assertEqual(inventory["vehicle:منطقه آزاد"]["value_summary"], "1")
        self.assertIn("vehicle:شماره پلاک منطقه آزاد", inventory)
        self.assertEqual(inventory["vehicle:شماره پلاک منطقه آزاد"]["value_summary"], "12345")


if __name__ == "__main__":
    unittest.main()
