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


if __name__ == "__main__":
    unittest.main()
