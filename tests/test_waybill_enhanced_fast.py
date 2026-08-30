"""Fast, isolated unit tests for EnhancedWaybillManager.

These tests focus on:
- Pure logic methods without heavy integration
- Selector inventory tracking
- Monitoring event emission
- Error handling paths
"""

import os
import sys
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.append(os.getcwd())

from app.automation.waybill_enhanced import EnhancedWaybillManager
from app.core.exceptions import WaybillError


class TestWaybillEnhancedFast(unittest.IsolatedAsyncioTestCase):
    """Fast unit tests with minimal setup."""

    def setUp(self):
        """Minimal setup for pure logic tests."""
        self.mock_page = AsyncMock()
        self.mock_page.on = Mock()
        self.mock_page.remove_listener = Mock()
        self.mock_context = AsyncMock()

        # Patch only what's needed
        self.patcher_interactor = patch("app.automation.waybill_enhanced.PageInteractor")
        self.patcher_map = patch("app.automation.waybill_enhanced.MapController")
        self.patcher_location = patch("app.automation.waybill_enhanced.LocationSelector")
        self.patcher_route = patch("app.automation.waybill_enhanced.RouteCalculator")
        self.patcher_smart_locator = patch("app.automation.waybill_enhanced.SmartLocator")

        self.mock_interactor_cls = self.patcher_interactor.start()
        self.mock_map_cls = self.patcher_map.start()
        self.mock_location_cls = self.patcher_location.start()
        self.mock_route_cls = self.patcher_route.start()
        self.mock_smart_locator_cls = self.patcher_smart_locator.start()

        self.manager = EnhancedWaybillManager(self.mock_page, self.mock_context)

    def tearDown(self):
        """Clean teardown."""
        self.patcher_interactor.stop()
        self.patcher_map.stop()
        self.patcher_location.stop()
        self.patcher_route.stop()
        self.patcher_smart_locator.stop()

    def test_pill_name_mapping(self):
        """Test pill name generation from step numbers."""
        self.assertEqual(self.manager._pill_name(1), "sender")
        self.assertEqual(self.manager._pill_name(2), "receiver")
        self.assertEqual(self.manager._pill_name(3), "vehicle")
        self.assertEqual(self.manager._pill_name(4), "cargo")
        self.assertEqual(self.manager._pill_name(5), "origin")
        self.assertEqual(self.manager._pill_name(6), "destination")
        self.assertEqual(self.manager._pill_name(7), "address_preview")
        self.assertEqual(self.manager._pill_name(8), "financial")
        self.assertEqual(self.manager._pill_name(99), "pill_99")

    def test_record_selector_inventory(self):
        """Test selector inventory recording."""
        self.manager._record_selector_inventory(
            field_label="نام فرستنده",
            selectors=["#txtSenderFirstName", "#senderName"],
            status="filled",
            selector_used="#txtSenderFirstName",
            value="علی",
            pill="sender",
        )

        key = "sender:نام فرستنده"
        self.assertIn(key, self.manager._selector_inventory)

        record = self.manager._selector_inventory[key]
        self.assertEqual(record["pill"], "sender")
        self.assertEqual(record["field"], "نام فرستنده")
        self.assertEqual(record["status"], "filled")
        self.assertEqual(record["selector_used"], "#txtSenderFirstName")
        self.assertEqual(len(record["selectors"]), 2)

    def test_pill_field_summary(self):
        """Test pill field summary generation."""
        self.manager._record_selector_inventory(
            field_label="نام", selectors=["#name"], status="filled", selector_used="#name", value="test", pill="sender"
        )
        self.manager._record_selector_inventory(
            field_label="کد ملی", selectors=["#nationalId"], status="skipped", pill="sender"
        )

        summary = self.manager._pill_field_summary("sender")

        self.assertEqual(len(summary), 2)
        self.assertIn("نام", summary)
        self.assertIn("کد ملی", summary)
        self.assertEqual(summary["نام"]["status"], "filled")
        self.assertEqual(summary["کد ملی"]["status"], "skipped")

    def test_summarize_field_value(self):
        """Test field value summarization."""
        # Short string
        self.assertEqual(self.manager._summarize_field_value("test"), "test")

        # Long string
        long_str = "a" * 200
        summary = self.manager._summarize_field_value(long_str)
        self.assertTrue(len(summary) <= 103)

        # None
        self.assertEqual(self.manager._summarize_field_value(None), "")

        # Number
        self.assertEqual(self.manager._summarize_field_value(12345), "12345")

    async def test_as_clean_text(self):
        """Test text cleaning utility."""
        result = await self.manager._as_clean_text("  test  ")
        self.assertEqual(result, "test")

        result = await self.manager._as_clean_text(None)
        self.assertEqual(result, "")

        result = await self.manager._as_clean_text("")
        self.assertEqual(result, "")

    async def test_detect_active_pane(self):
        """Test active pane detection."""
        self.mock_page.evaluate.return_value = "pane-2"

        result = await self.manager._detect_active_pane()

        self.assertEqual(result, "pane-2")
        self.mock_page.evaluate.assert_called_once()

    async def test_read_button_text(self):
        """Test button text reading."""
        self.mock_page.eval_on_selector.return_value = "  بعدی  "

        result = await self.manager._read_button_text("#btnNext")

        self.assertEqual(result, "بعدی")

    async def test_read_button_text_fallback(self):
        """Test button text reading with fallback."""
        self.mock_page.eval_on_selector.side_effect = Exception("Not found")

        result = await self.manager._read_button_text("#btnNext", "default")

        self.assertEqual(result, "default")

    def test_log_selector_inventory_audit(self):
        """Test selector inventory audit logging."""
        self.manager._record_selector_inventory(
            field_label="field1", selectors=["#sel1"], status="filled", pill="sender"
        )
        self.manager._record_selector_inventory(
            field_label="field2", selectors=["#sel2"], status="failed", pill="receiver"
        )

        with self.assertLogs("app.automation.waybill_enhanced", level="INFO") as logs:
            self.manager._log_selector_inventory_audit()

        log_output = "\n".join(logs.output)
        self.assertIn("waybill_selector_inventory_audit", log_output)

    async def test_fill_with_fallback_success_first_selector(self):
        """Test fill with fallback succeeds via smart_locator."""
        mock_locator = AsyncMock()
        mock_locator.fill = AsyncMock()
        self.manager.smart_locator.locate = AsyncMock(return_value=mock_locator)

        await self.manager._fill_with_fallback(["#primary", "#secondary"], "test_value", "test_field")

        self.manager.smart_locator.locate.assert_called_once()
        mock_locator.fill.assert_called_once_with("test_value")

    async def test_fill_with_fallback_tries_all_selectors(self):
        """Test fill with fallback tries fallback selectors when smart_locator fails."""
        self.manager.smart_locator.locate = AsyncMock(side_effect=Exception("Not found"))
        self.manager.interactor.safe_fill = AsyncMock(side_effect=[False, True])
        self.manager._set_value_with_js = AsyncMock(return_value=False)

        await self.manager._fill_with_fallback(["#first", "#second"], "test_value", "test_field")

        self.assertEqual(self.manager.interactor.safe_fill.call_count, 2)
        key = "bootstrap:test_field"
        self.assertEqual(self.manager._selector_inventory[key]["selector_used"], "#second")

    async def test_fill_with_fallback_records_inventory(self):
        """Test fill with fallback records selector inventory with smart_locator success."""
        mock_locator = AsyncMock()
        mock_locator.fill = AsyncMock()
        self.manager.smart_locator.locate = AsyncMock(return_value=mock_locator)

        await self.manager._fill_with_fallback(["#primary", "#secondary"], "value", "field_name")

        key = "bootstrap:field_name"
        self.assertIn(key, self.manager._selector_inventory)
        self.assertEqual(self.manager._selector_inventory[key]["status"], "filled")

    async def test_fill_with_fallback_records_inventory_fallback(self):
        """Test fill with fallback records selector inventory when using fallback."""
        self.manager.smart_locator.locate = AsyncMock(side_effect=Exception("Not found"))
        self.manager.interactor.safe_fill = AsyncMock(return_value=True)

        await self.manager._fill_with_fallback(["#primary", "#secondary"], "value", "field_name")

        key = "bootstrap:field_name"
        self.assertIn(key, self.manager._selector_inventory)
        self.assertEqual(self.manager._selector_inventory[key]["status"], "fallback-only")
        self.assertEqual(self.manager._selector_inventory[key]["selector_used"], "#primary")

    async def test_fill_with_fallback_all_fail_not_required(self):
        """Test fill with fallback when all fail but not required."""
        self.manager.smart_locator.locate = AsyncMock(side_effect=Exception("Not found"))
        self.manager.interactor.safe_fill = AsyncMock(return_value=False)
        self.manager._set_value_with_js = AsyncMock(return_value=False)

        await self.manager._fill_with_fallback(["#sel1", "#sel2"], "value", "field", required=False)

        key = "bootstrap:field"
        self.assertIn(key, self.manager._selector_inventory)
        self.assertEqual(self.manager._selector_inventory[key]["status"], "unsupported")

    async def test_fill_with_fallback_all_fail_required_raises(self):
        """Test fill with fallback raises when all fail and required."""
        self.manager.smart_locator.locate = AsyncMock(side_effect=Exception("Not found"))
        self.manager.interactor.safe_fill = AsyncMock(return_value=False)
        self.manager._set_value_with_js = AsyncMock(return_value=False)

        with self.assertRaises(WaybillError) as ctx:
            await self.manager._fill_with_fallback(["#sel1"], "value", "critical_field", required=True)

        self.assertIn("critical_field", str(ctx.exception))

    async def test_fill_with_fallback_skips_empty_value(self):
        """Test fill with fallback skips when value is empty."""
        await self.manager._fill_with_fallback(["#sel1"], "", "empty_field")

        key = "bootstrap:empty_field"
        self.assertIn(key, self.manager._selector_inventory)
        self.assertEqual(self.manager._selector_inventory[key]["status"], "skipped")

    def test_submit_response_parser_accepts_live_top_level_fixture(self):
        payload = {
            "resultCode": 200,
            "resultMessage": "بارنامه با موفقیت صادر شد",
            "isOtpNeeded": False,
            "obj": {"documentId": 123456, "trackingCode": "987654321"},
        }
        parsed = self.manager._parse_register_submit_payload(payload)
        self.assertIsNotNone(parsed)
        self.assertTrue(parsed["success"])
        self.assertFalse(parsed["is_otp_needed"])
        self.assertEqual(parsed["document_id"], 123456)
        self.assertEqual(parsed["tracking_code"], "987654321")

    def test_otp_response_parser_accepts_nested_fixture(self):
        payload = {
            "data": {
                "resultCode": 200,
                "resultMessage": "کد اعتبارسنجی پیامک شد",
                "obj": {"documentId": 123456},
            }
        }
        parsed = self.manager._parse_otp_submit_payload(payload)
        self.assertIsNotNone(parsed)
        self.assertTrue(parsed["success"])
        self.assertEqual(parsed["document_id"], 123456)

    def test_submit_watchers_match_canonical_utcms_action_only(self):
        class Response:
            def __init__(self, url):
                self.url = url

        self.assertTrue(
            self.manager._is_register_submit_response(
                Response("https://barname.utcms.ir/Barname/PrintReport/printbarnameNew?x=1")
            )
        )
        self.assertFalse(self.manager._is_register_submit_response(Response("https://example.test/UpdateRegisterNewOld")))
        self.assertTrue(
            self.manager._is_otp_submit_response(Response("https://barname.utcms.ir/Barname/Document/IssueDocumentByOtpNew"))
        )

    async def test_exact_dropdown_requires_unique_readback(self):
        self.manager.smart_locator.locate = AsyncMock(return_value=AsyncMock())
        self.mock_page.eval_on_selector_all = AsyncMock(
            return_value=[
                {"text": "فله", "value": "7"},
                {"text": "کیسه", "value": "8"},
            ]
        )
        self.mock_page.eval_on_selector = AsyncMock(return_value={"value": "7", "text": "فله"})
        selected = await self.manager._select_exact_dropdown_with_fallback(["#ddBoxType"], "فله", "نوع بسته بندی")
        self.assertTrue(selected)
        self.manager.smart_locator.locate.return_value.select_option.assert_awaited_once_with(value="7")

    async def test_close_detaches_dialog_listener(self):
        await self.manager.close()
        self.mock_page.remove_listener.assert_called_once()
        self.assertTrue(self.manager._closed)

    async def test_waybill_recovery_uses_authenticated_menu_click_before_direct_urls(self):
        """UTCMS accepts the form after menu navigation but returns 408 on a cold URL GET."""
        link = AsyncMock()
        self.mock_page.query_selector = AsyncMock(return_value=link)
        self.mock_page.wait_for_load_state = AsyncMock()
        self.manager._current_url = AsyncMock(return_value="https://barname.utcms.ir/Barname/Notification/Notification")
        self.manager._looks_like_not_found_page = AsyncMock(return_value=False)
        self.manager._is_waybill_form_ready = AsyncMock(side_effect=[False, True])
        self.manager._waybill_url_candidates = Mock(return_value=[])
        self.manager._partition_internal_links = Mock(return_value=([], []))

        await self.manager._ensure_waybill_form_page()

        link.click.assert_awaited_once_with(timeout=5000)
        self.mock_page.goto.assert_not_called()

    async def test_dom_only_form_without_javascript_is_rejected(self):
        """A DOM-complete form whose scripts were reset must never be filled."""
        self.manager._open_waybill_form_page = AsyncMock()
        self.mock_page.evaluate = AsyncMock(
            return_value={
                "jquery": False,
                "jquery_ui": False,
                "validator": False,
                "handler": "GoLVL2",
                "handler_ready": False,
            }
        )

        with self.assertRaises(WaybillError) as ctx:
            await self.manager._require_live_form_javascript(timeout_ms=0)

        self.assertIn("اسکریپت", str(ctx.exception))

    async def test_live_form_javascript_passes_the_gate(self):
        self.manager._open_waybill_form_page = AsyncMock()
        self.mock_page.evaluate = AsyncMock(
            return_value={
                "jquery": True,
                "jquery_ui": True,
                "validator": True,
                "handler": "GoLVL2",
                "handler_ready": True,
            }
        )

        await self.manager._ensure_waybill_form_page()

        self.mock_page.evaluate.assert_awaited()

    async def test_unavailable_javascript_probe_does_not_fail_closed(self):
        """Other gates own page-level failures; the probe must stay diagnostic."""
        self.manager._open_waybill_form_page = AsyncMock()
        self.mock_page.evaluate = AsyncMock(side_effect=RuntimeError("no execution context"))

        await self.manager._ensure_waybill_form_page()


class TestFormJavascriptGate(unittest.TestCase):
    def test_liveness_requires_every_critical_layer(self):
        base = {"jquery": True, "jquery_ui": True, "validator": True, "handler_ready": True}
        self.assertTrue(EnhancedWaybillManager._form_javascript_is_live(base))
        for key in ("jquery", "jquery_ui", "validator", "handler_ready"):
            broken = dict(base)
            broken[key] = False
            self.assertFalse(EnhancedWaybillManager._form_javascript_is_live(broken))


class TestDriverFieldSelectors(unittest.IsolatedAsyncioTestCase):
    """The driver step used to die on a field id UTCMS never had."""

    def setUp(self):
        self.mock_page = AsyncMock()
        self.mock_page.on = Mock()
        self.mock_page.remove_listener = Mock()
        self.patchers = [
            patch("app.automation.waybill_enhanced.PageInteractor"),
            patch("app.automation.waybill_enhanced.MapController"),
            patch("app.automation.waybill_enhanced.LocationSelector"),
            patch("app.automation.waybill_enhanced.RouteCalculator"),
            patch("app.automation.waybill_enhanced.SmartLocator"),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.manager = EnhancedWaybillManager(self.mock_page, AsyncMock())
        self.manager._wait_for_loading_overlays_to_disappear = AsyncMock()
        self.manager._is_element_visible = AsyncMock(return_value=False)
        self.manager._fill_verified_text_field = AsyncMock(return_value=True)

    def tearDown(self):
        for patcher in self.patchers:
            patcher.stop()

    async def test_mobile_is_filled_through_the_real_utcms_field_ids(self):
        self.manager._wait_for_non_empty_value = AsyncMock(return_value=None)

        await self.manager._fill_fallback_driver_info("", "09160652050")

        selectors = self.manager._fill_verified_text_field.await_args.args[0]
        self.assertIn('input[id="DriverMobile"]', selectors)
        self.assertIn('input[id="DriverMobileTajmi"]', selectors)
        self.assertNotIn('input[id="DriverPhone"]', selectors)
        self.assertNotIn('input[name="DriverPhone"]', selectors)

    async def test_tajmi_mode_prefers_the_tajmi_mobile_field(self):
        self.manager._wait_for_non_empty_value = AsyncMock(return_value=None)

        await self.manager._fill_fallback_driver_info("", "09160652050", tajmi_mode=True)

        selectors = self.manager._fill_verified_text_field.await_args.args[0]
        self.assertEqual(selectors[0], 'input[id="DriverMobileTajmi"]')

    async def test_a_mobile_utcms_already_filled_is_never_overwritten(self):
        """UTCMS fills the registered number itself; that value is authoritative."""
        self.manager._wait_for_non_empty_value = AsyncMock(return_value="09160652050")

        await self.manager._fill_fallback_driver_info("", "09160652050", tajmi_mode=True)

        self.manager._fill_verified_text_field.assert_not_awaited()

    async def test_tajmi_driver_is_matched_by_mobile_when_no_national_code(self):
        self.manager._element_exists = AsyncMock(return_value=True)
        self.manager._wait_for_select_options_count = AsyncMock()
        self.manager._log_select_options = AsyncMock()
        self.manager._wait_for_non_empty_value = AsyncMock(return_value="09160652050")
        self.manager._set_select_value_with_js = AsyncMock(return_value=True)
        self.mock_page.eval_on_selector_all = AsyncMock(
            return_value=[
                {"text": "", "value": "", "mobile": ""},
                {"text": "بهروز بغلانی", "value": "77", "mobile": "09160652050"},
            ]
        )

        selected = await self.manager._handle_tajmi_driver_selection("", driver_name="", driver_phone="09160652050")

        self.assertTrue(selected)
        self.manager._set_select_value_with_js.assert_awaited_once_with("#DriverListTajmi", "77")

    async def test_tajmi_driver_is_matched_by_name_as_a_last_resort(self):
        self.manager._element_exists = AsyncMock(return_value=True)
        self.manager._wait_for_select_options_count = AsyncMock()
        self.manager._log_select_options = AsyncMock()
        self.manager._wait_for_non_empty_value = AsyncMock(return_value="09160652050")
        self.manager._set_select_value_with_js = AsyncMock(return_value=True)
        self.mock_page.eval_on_selector_all = AsyncMock(
            return_value=[{"text": "بهروز بغلانی - ۱۲۳", "value": "77", "mobile": ""}]
        )

        selected = await self.manager._handle_tajmi_driver_selection("", driver_name="بهروز بغلانی", driver_phone="")

        self.assertTrue(selected)
        self.manager._set_select_value_with_js.assert_awaited_once_with("#DriverListTajmi", "77")

    async def test_a_blank_placeholder_option_is_never_selected(self):
        self.manager._element_exists = AsyncMock(return_value=True)
        self.manager._wait_for_select_options_count = AsyncMock()
        self.manager._log_select_options = AsyncMock()
        self.manager._wait_for_non_empty_value = AsyncMock(return_value=None)
        self.manager._set_select_value_with_js = AsyncMock(return_value=True)
        self.mock_page.eval_on_selector_all = AsyncMock(
            return_value=[{"text": "انتخاب کنید", "value": "", "mobile": ""}]
        )

        selected = await self.manager._handle_tajmi_driver_selection("", driver_name="انتخاب کنید", driver_phone="")

        self.assertFalse(selected)
        self.manager._set_select_value_with_js.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()


class TestCargoCatalogueLookup(unittest.IsolatedAsyncioTestCase):
    """Run 4 (2026-08-28) failed with "نوع کالا 'سیمان' در فهرست UTCMS پیدا نشد"
    while a direct authenticated session got an exact ``سیمان`` (id 15122) from
    the same endpoint: the page-side jQuery autocomplete never initialised
    because its script is one of the stubbed non-critical assets.  The lookup
    must therefore not depend on page JS."""

    def setUp(self):
        self.mock_page = AsyncMock()
        self.mock_page.on = Mock()
        self.mock_page.remove_listener = Mock()
        self.mock_page.url = "https://barname.utcms.ir/Barname/Document/HagigiHogugi"
        self.patchers = [
            patch("app.automation.waybill_enhanced.PageInteractor"),
            patch("app.automation.waybill_enhanced.MapController"),
            patch("app.automation.waybill_enhanced.LocationSelector"),
            patch("app.automation.waybill_enhanced.RouteCalculator"),
            patch("app.automation.waybill_enhanced.SmartLocator"),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.manager = EnhancedWaybillManager(self.mock_page, AsyncMock())

    def tearDown(self):
        for patcher in self.patchers:
            patcher.stop()

    def _bridge(self, **kwargs):
        bridge = Mock()
        bridge.fetch_json = AsyncMock(**kwargs)
        return patch(
            "app.automation.http_browser_bridge.get_utcms_http_browser_bridge",
            return_value=bridge,
        ), bridge

    async def test_bridge_result_is_preferred_and_page_js_is_not_touched(self):
        catalogue = [{"id": 15122, "label": "سیمان", "value": "سیمان"}]
        patcher, bridge = self._bridge(return_value=catalogue)
        with patcher:
            results = await self.manager._lookup_cargo_catalogue("سیمان")

        self.assertEqual(results, catalogue)
        bridge.fetch_json.assert_awaited_once()
        args, kwargs = bridge.fetch_json.await_args
        self.assertEqual(args[0], "https://barname.utcms.ir/Barname/Document/KalaSearch")
        self.assertEqual(args[1], {"txtkala": "سیمان"})
        self.assertEqual(kwargs["referer"], self.mock_page.url)
        self.mock_page.evaluate.assert_not_awaited()

    async def test_falls_back_to_page_ajax_when_the_bridge_lookup_is_empty(self):
        catalogue = [{"id": 15122, "label": "سیمان", "value": "سیمان"}]
        self.mock_page.evaluate = AsyncMock(return_value=catalogue)
        patcher, bridge = self._bridge(return_value=None)
        with patcher:
            results = await self.manager._lookup_cargo_catalogue("سیمان")

        self.assertEqual(results, catalogue)
        self.mock_page.evaluate.assert_awaited_once()

    async def test_no_bridge_installed_still_uses_page_ajax(self):
        self.mock_page.evaluate = AsyncMock(return_value=[])
        with patch(
            "app.automation.http_browser_bridge.get_utcms_http_browser_bridge",
            return_value=None,
        ):
            self.assertEqual(await self.manager._lookup_cargo_catalogue("سیمان"), [])
        self.mock_page.evaluate.assert_awaited_once()

    async def test_a_page_ajax_error_returns_an_empty_list(self):
        self.mock_page.evaluate = AsyncMock(side_effect=RuntimeError("no jQuery"))
        patcher, _ = self._bridge(return_value=None)
        with patcher:
            self.assertEqual(await self.manager._lookup_cargo_catalogue("سیمان"), [])


class TestBoxTypeCatalogue(unittest.IsolatedAsyncioTestCase):
    """``نوع بسته‌بندی`` is required by UTCMS's own validation and UTCMS never
    defaults it, so the ids must come from ``fillBoxType`` -- never invented."""

    def setUp(self):
        self.mock_page = AsyncMock()
        self.mock_page.on = Mock()
        self.mock_page.remove_listener = Mock()
        self.mock_page.url = "https://barname.utcms.ir/Barname/Document/HagigiHogugi"
        self.patchers = [
            patch("app.automation.waybill_enhanced.PageInteractor"),
            patch("app.automation.waybill_enhanced.MapController"),
            patch("app.automation.waybill_enhanced.LocationSelector"),
            patch("app.automation.waybill_enhanced.RouteCalculator"),
            patch("app.automation.waybill_enhanced.SmartLocator"),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.manager = EnhancedWaybillManager(self.mock_page, AsyncMock())

    def tearDown(self):
        for patcher in self.patchers:
            patcher.stop()

    def _bridge(self, payload):
        bridge = Mock()
        bridge.fetch_json = AsyncMock(return_value=payload)
        return patch(
            "app.automation.http_browser_bridge.get_utcms_http_browser_bridge",
            return_value=bridge,
        ), bridge

    async def test_options_are_rebuilt_from_the_fillboxtype_envelope(self):
        payload = {
            "resultCode": 200,
            "obj": [{"id": 10, "type": 5, "name": "کیسه"}, {"id": 18074, "type": 5, "name": "فله"}],
        }
        patcher, bridge = self._bridge(payload)
        with patcher:
            self.assertTrue(await self.manager._populate_box_type_options_via_bridge())

        bridge.fetch_json.assert_awaited_once()
        self.assertEqual(
            bridge.fetch_json.await_args.args[0],
            "https://barname.utcms.ir/Barname/Document/fillBoxType",
        )
        options = self.mock_page.eval_on_selector_all.await_args.args[2]
        self.assertEqual(options, [{"id": "10", "name": "کیسه"}, {"id": "18074", "name": "فله"}])

    async def test_an_empty_catalogue_is_not_treated_as_success(self):
        patcher, _ = self._bridge({"resultCode": 200, "obj": []})
        with patcher:
            self.assertFalse(await self.manager._populate_box_type_options_via_bridge())
        self.mock_page.eval_on_selector_all.assert_not_awaited()

    async def test_no_bridge_means_no_invented_options(self):
        with patch(
            "app.automation.http_browser_bridge.get_utcms_http_browser_bridge",
            return_value=None,
        ):
            self.assertFalse(await self.manager._populate_box_type_options_via_bridge())
        self.mock_page.eval_on_selector_all.assert_not_awaited()

    async def test_the_placeholder_is_not_reported_as_an_available_choice(self):
        self.mock_page.eval_on_selector_all = AsyncMock(return_value=["کیسه", "فله"])
        self.assertEqual(await self.manager._read_box_type_option_labels(), ["کیسه", "فله"])


class TestTajmiFleetBackfill(unittest.IsolatedAsyncioTestCase):
    """Dry-run 6: ``#PelakComboTajmi`` held only its placeholder, so no plate was
    chosen, so UTCMS never called ``GetFleetDriverList`` and the driver list stayed
    empty.  The fleet has to come from the endpoint, not from page JS."""

    FLEET = [
        {
            "ncarTag": 248221338,
            "hasFreeZoneCarTag": False,
            "irTagPart1": 24,
            "irTagPart2": 82,
            "irTagPart3": 21,
            "irTagPart4": 338,
        },
        {
            "ncarTag": 111111111,
            "hasFreeZoneCarTag": False,
            "irTagPart1": 24,
            "irTagPart2": 11,
            "irTagPart3": 21,
            "irTagPart4": 999,
        },
    ]
    PLATE = {"iran": "24", "first": "82", "center": "338", "letter": "ع"}

    def setUp(self):
        self.mock_page = AsyncMock()
        self.mock_page.on = Mock()
        self.mock_page.remove_listener = Mock()
        self.mock_page.url = "https://barname.utcms.ir/Barname/Document/HagigiHogugi"
        self.patchers = [
            patch("app.automation.waybill_enhanced.PageInteractor"),
            patch("app.automation.waybill_enhanced.MapController"),
            patch("app.automation.waybill_enhanced.LocationSelector"),
            patch("app.automation.waybill_enhanced.RouteCalculator"),
            patch("app.automation.waybill_enhanced.SmartLocator"),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.manager = EnhancedWaybillManager(self.mock_page, AsyncMock())

    def tearDown(self):
        for patcher in self.patchers:
            patcher.stop()

    def test_plate_is_matched_on_digits_never_on_the_letter(self):
        """``GetPelakChar`` is a page-side table; guessing it could pick another car."""
        matches = [
            record
            for record in self.FLEET
            if EnhancedWaybillManager._fleet_record_matches_plate(record, self.PLATE, None)
        ]
        self.assertEqual([record["ncarTag"] for record in matches], [248221338])

    def test_a_free_zone_plate_never_matches_a_national_record(self):
        self.assertFalse(
            EnhancedWaybillManager._fleet_record_matches_plate(
                self.FLEET[0], None, {"number": "338", "zone_name": "اروند"}
            )
        )

    def test_envelope_unwrapping_ignores_non_objects(self):
        self.assertEqual(
            EnhancedWaybillManager._unwrap_utcms_envelope({"resultCode": 200, "obj": [{"a": 1}, "junk"]}),
            [{"a": 1}],
        )
        self.assertEqual(EnhancedWaybillManager._unwrap_utcms_envelope(None), [])

    async def test_the_chosen_fleet_record_is_returned_for_the_driver_lookup(self):
        self.manager._fetch_via_bridge = AsyncMock(return_value={"resultCode": 200, "obj": self.FLEET})
        chosen = await self.manager._select_tajmi_plate_via_bridge(self.PLATE, None)
        self.assertEqual(chosen["ncarTag"], 248221338)
        # selectedIndex is offset by one for the placeholder option.
        self.assertEqual(self.mock_page.evaluate.await_args.args[1]["chosenIndex"], 0)

    async def test_an_ambiguous_plate_is_never_guessed(self):
        self.manager._fetch_via_bridge = AsyncMock(
            return_value={"resultCode": 200, "obj": [self.FLEET[0], dict(self.FLEET[0])]}
        )
        self.assertIsNone(await self.manager._select_tajmi_plate_via_bridge(self.PLATE, None))
        self.mock_page.evaluate.assert_not_awaited()

    async def test_driver_list_is_fetched_with_the_plates_ncartag(self):
        self.manager._fetch_via_bridge = AsyncMock(
            return_value={"resultCode": 200, "obj": [{"driverNationalCode": "1810364371"}]}
        )
        self.assertEqual(await self.manager._populate_tajmi_driver_options_via_bridge(248221338), 1)
        self.assertEqual(
            self.manager._fetch_via_bridge.await_args.args,
            ("https://barname.utcms.ir/Barname/Document/GetFleetDriverList", {"carTag": "248221338"}),
        )

    async def test_no_plate_means_no_driver_request(self):
        self.manager._fetch_via_bridge = AsyncMock()
        self.assertEqual(await self.manager._populate_tajmi_driver_options_via_bridge(None), 0)
        self.manager._fetch_via_bridge.assert_not_awaited()


class TestOtpFalsePositiveGuards(unittest.IsolatedAsyncioTestCase):
    """A closed OTP modal must never read as an OTP challenge.

    UTCMS ships ``#submitOtp`` and the whole ``FormSendOtpCode`` form inside a
    Bootstrap modal that is present from the first paint; only
    ``.modal { display: none }`` keeps it hidden.  Any run whose stylesheets are
    missing sees a fully laid-out dialog, so geometric visibility alone reported
    an OTP challenge on every job and closed the submission gate.
    """

    def setUp(self):
        self.mock_page = AsyncMock()
        self.mock_page.on = Mock()
        self.mock_page.remove_listener = Mock()
        self.patchers = [
            patch("app.automation.waybill_enhanced.PageInteractor"),
            patch("app.automation.waybill_enhanced.MapController"),
            patch("app.automation.waybill_enhanced.LocationSelector"),
            patch("app.automation.waybill_enhanced.RouteCalculator"),
            patch("app.automation.waybill_enhanced.SmartLocator"),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.manager = EnhancedWaybillManager(self.mock_page, AsyncMock())

    def tearDown(self):
        for patcher in self.patchers:
            patcher.stop()

    async def test_a_visible_control_in_a_closed_modal_is_not_an_otp_challenge(self):
        self.manager._is_selector_visible = AsyncMock(return_value=True)
        self.manager._is_inside_closed_modal = AsyncMock(return_value=True)
        self.mock_page.evaluate = AsyncMock(return_value="")

        detected, evidence = await self.manager._detect_otp_required_with_evidence()

        self.assertFalse(detected)
        self.assertEqual(evidence, {})

    async def test_a_control_in_an_open_modal_is_an_otp_challenge(self):
        self.manager._is_selector_visible = AsyncMock(return_value=True)
        self.manager._is_inside_closed_modal = AsyncMock(return_value=False)

        detected, evidence = await self.manager._detect_otp_required_with_evidence()

        self.assertTrue(detected)
        self.assertEqual(evidence.get("source"), "dom_selector")

    async def test_only_open_dialogs_are_scanned_for_otp_wording(self):
        self.manager._is_selector_visible = AsyncMock(return_value=False)
        self.mock_page.evaluate = AsyncMock(return_value="")

        await self.manager._detect_otp_required_with_evidence()

        script = self.mock_page.evaluate.await_args_list[0].args[0]
        self.assertIn(".modal.show", script)
        self.assertNotIn("#FormSendOtpCode", script)


class TestOptionalShippingFields(unittest.IsolatedAsyncioTestCase):
    """UTCMS has no time-limit or end-of-shipping control.

    A live inventory of the issuance form on 2026-08-30 listed 123 fields whose
    only time-related one is ``loadingTime``.  Probing five selectors for a
    control that does not exist cost a 5s SmartLocator timeout each -- 25s per
    run -- and ended in a warning that read like a regression.
    """

    def setUp(self):
        self.mock_page = AsyncMock()
        self.mock_page.on = Mock()
        self.mock_page.remove_listener = Mock()
        self.patchers = [
            patch("app.automation.waybill_enhanced.PageInteractor"),
            patch("app.automation.waybill_enhanced.MapController"),
            patch("app.automation.waybill_enhanced.LocationSelector"),
            patch("app.automation.waybill_enhanced.RouteCalculator"),
            patch("app.automation.waybill_enhanced.SmartLocator"),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.manager = EnhancedWaybillManager(self.mock_page, AsyncMock())
        self.manager._fill_with_fallback = AsyncMock()

    def tearDown(self):
        for patcher in self.patchers:
            patcher.stop()

    async def test_an_absent_control_is_never_probed_selector_by_selector(self):
        self.mock_page.query_selector = AsyncMock(return_value=None)

        await self.manager._fill_shipping_options({"time_limit": 60})

        self.manager._fill_with_fallback.assert_not_awaited()
        key = "bootstrap:محدودیت زمانی"
        self.assertEqual(self.manager._selector_inventory[key]["status"], "absent-in-utcms")

    async def test_a_present_control_is_still_filled(self):
        self.mock_page.query_selector = AsyncMock(return_value=object())

        await self.manager._fill_shipping_options({"time_limit": 60})

        self.manager._fill_with_fallback.assert_awaited_once()
        self.assertEqual(self.manager._fill_with_fallback.await_args.args[1], "60")
