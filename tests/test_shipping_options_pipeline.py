"""
Tests for shipping_options end-to-end pipeline, dry_run validation summary,
_check_checkbox_with_fallback, and _check_account_eligibility.
"""
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.automation.waybill_enhanced import EnhancedWaybillManager
from app.core.exceptions import WaybillError
from app.schemas.waybill import (
    CargoModel,
    FinancialModel,
    GeoCoordinateModel,
    LocationModel,
    OperationMode,
    ReceiverModel,
    SenderModel,
    ShippingOptionsModel,
    VehicleModel,
    WaybillMapRequest,
)
from app.services.waybill_service import WaybillService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_request(**kwargs) -> WaybillMapRequest:
    """Return a minimal valid WaybillMapRequest, optionally overriding fields."""
    defaults = dict(
        session_id="shipping-opts-test",
        operation_mode=OperationMode.SAFE,
        sender=SenderModel(name="Alice", phone="09121111111", address="Addr A", national_code="1234567890"),
        receiver=ReceiverModel(name="Bob", phone="09122222222", address="Addr B"),
        origin=LocationModel(
            province="تهران", city="تهران", address="خ آزادی",
            coordinates=GeoCoordinateModel(lat=35.6892, lng=51.3890),
        ),
        destination=LocationModel(
            province="مشهد", city="مشهد", address="خ امام رضا",
            coordinates=GeoCoordinateModel(lat=36.2972, lng=59.6067),
        ),
        cargo=CargoModel(type="General", weight=1000, count=1, description="test"),
        vehicle=VehicleModel(driver_national_code="1234567890", driver_phone="09121111111",
                             plate="12A34567", type="Truck"),
        financial=FinancialModel(cost=1000, payment_method="Cash"),
    )
    defaults.update(kwargs)
    return WaybillMapRequest(**defaults)


def _base_data() -> dict:
    """Return a minimal payload dict for EnhancedWaybillManager.create_waybill_with_map."""
    return {
        "sender": {"name": "Alice"},
        "receiver": {"name": "Bob"},
        "origin": {"province": "تهران", "coordinates": {"lat": 35.6892, "lng": 51.3890}},
        "destination": {"province": "مشهد", "coordinates": {"lat": 36.2972, "lng": 59.6067}},
        "cargo": {"type": "General", "weight": 1000},
        "vehicle": {"plate": "12A34567"},
        "financial": {"cost": 5000000},
    }


# ---------------------------------------------------------------------------
# 1. Schema – ShippingOptionsModel serialisation
# ---------------------------------------------------------------------------

class TestShippingOptionsModel:
    def test_defaults(self):
        opts = ShippingOptionsModel()
        assert opts.two_way is False
        assert opts.time_limit is None
        assert opts.end_shipping is None
        assert opts.otp is None

    def test_full_round_trip(self):
        opts = ShippingOptionsModel(two_way=True, time_limit=120, end_shipping="1402-05-20", otp="654321")
        dumped = opts.model_dump(exclude_none=True)
        assert dumped == {"two_way": True, "time_limit": 120, "end_shipping": "1402-05-20", "otp": "654321"}
        restored = ShippingOptionsModel.model_validate(dumped)
        assert restored == opts

    def test_missing_from_waybill_request_defaults_to_none(self):
        req = _base_request()
        assert req.shipping_options is None

    def test_shipping_options_attached_to_request(self):
        opts = ShippingOptionsModel(two_way=True, time_limit=60)
        req = _base_request(shipping_options=opts)
        assert req.shipping_options.two_way is True
        assert req.shipping_options.time_limit == 60


# ---------------------------------------------------------------------------
# 2. WaybillService._build_waybill_payload includes shipping_options
# ---------------------------------------------------------------------------

class TestBuildWaybillPayload:
    def test_no_shipping_options_omitted_from_payload(self):
        req = _base_request()
        payload = WaybillService._build_waybill_payload(req)
        assert "shipping_options" not in payload

    def test_shipping_options_included_in_payload(self):
        opts = ShippingOptionsModel(two_way=True, time_limit=90, otp="999")
        req = _base_request(shipping_options=opts)
        payload = WaybillService._build_waybill_payload(req)
        assert "shipping_options" in payload
        so = payload["shipping_options"]
        assert so["two_way"] is True
        assert so["time_limit"] == 90
        assert so["otp"] == "999"
        # exclude_none: end_shipping should not appear
        assert "end_shipping" not in so

    def test_none_values_excluded_from_shipping_options(self):
        opts = ShippingOptionsModel(two_way=False)
        req = _base_request(shipping_options=opts)
        payload = WaybillService._build_waybill_payload(req)
        so = payload["shipping_options"]
        # two_way=False is not None → included; others are None → excluded
        assert "two_way" in so
        assert "time_limit" not in so
        assert "end_shipping" not in so
        assert "otp" not in so


# ---------------------------------------------------------------------------
# 3. Queue serialisation round-trip keeps shipping_options
# ---------------------------------------------------------------------------

class TestQueueSerialisation:
    def test_model_dump_preserves_shipping_options(self):
        opts = ShippingOptionsModel(two_way=True, time_limit=45, end_shipping="1402-01-01")
        req = _base_request(shipping_options=opts)
        dumped = req.model_dump()
        # Round-trip via JSON (simulates Redis queue)
        import json
        serialised = json.dumps(dumped)
        reloaded = json.loads(serialised)
        restored = WaybillMapRequest.model_validate(reloaded)
        assert restored.shipping_options is not None
        assert restored.shipping_options.two_way is True
        assert restored.shipping_options.time_limit == 45
        assert restored.shipping_options.end_shipping == "1402-01-01"


# ---------------------------------------------------------------------------
# 4. WaybillService._categorize_exception
# ---------------------------------------------------------------------------

class TestCategorizeException:
    def test_captcha(self):
        assert WaybillService._categorize_exception(Exception("captcha required")) == "captcha"

    def test_auth(self):
        assert WaybillService._categorize_exception(Exception("login failed")) == "auth"

    def test_map(self):
        assert WaybillService._categorize_exception(Exception("map timeout")) == "map"

    def test_network_timeout(self):
        assert WaybillService._categorize_exception(Exception("connection timed out")) == "network"

    def test_form(self):
        assert WaybillService._categorize_exception(Exception("validation error in field")) == "form"

    def test_unknown(self):
        assert WaybillService._categorize_exception(Exception("something unrecognised xyz")) == "unknown"

    def test_network_with_real_exception_object(self):
        """Ensures the fix (passing exception not string) still classifies correctly."""
        exc = TimeoutError("connection timed out")
        result = WaybillService._categorize_exception(exc)
        assert result == "network"


# ---------------------------------------------------------------------------
# 5. EnhancedWaybillManager – _check_account_eligibility
# ---------------------------------------------------------------------------

class TestCheckAccountEligibility:
    def _make_manager(self):
        page = AsyncMock()
        ctx = AsyncMock()
        with patch("app.automation.waybill_enhanced.PageInteractor"), \
             patch("app.automation.waybill_enhanced.MapController"), \
             patch("app.automation.waybill_enhanced.LocationSelector"), \
             patch("app.automation.waybill_enhanced.RouteCalculator"):
            mgr = EnhancedWaybillManager(page, ctx)
        mgr.page = page
        return mgr

    @pytest.mark.asyncio
    async def test_clean_page_passes(self):
        mgr = self._make_manager()
        mgr.page.text_content = AsyncMock(return_value="خوش آمدید")
        # Should not raise
        await mgr._check_account_eligibility()

    @pytest.mark.asyncio
    async def test_blocked_account_raises(self):
        mgr = self._make_manager()
        mgr.page.text_content = AsyncMock(return_value="err_blocked در سامانه")
        with pytest.raises(WaybillError, match="حساب مسدود"):
            await mgr._check_account_eligibility()

    @pytest.mark.asyncio
    async def test_suspended_account_raises(self):
        mgr = self._make_manager()
        mgr.page.text_content = AsyncMock(return_value="err_suspend موجود است")
        with pytest.raises(WaybillError, match="حساب معلق"):
            await mgr._check_account_eligibility()

    @pytest.mark.asyncio
    async def test_license_missing_raises(self):
        mgr = self._make_manager()
        mgr.page.text_content = AsyncMock(return_value="err_4001_faghed_parvane")
        with pytest.raises(WaybillError, match="پروانه"):
            await mgr._check_account_eligibility()

    @pytest.mark.asyncio
    async def test_persian_block_phrase_raises(self):
        mgr = self._make_manager()
        mgr.page.text_content = AsyncMock(return_value="شما مجاز به استفاده از این بخش نمی‌باشید")
        with pytest.raises(WaybillError):
            await mgr._check_account_eligibility()

    @pytest.mark.asyncio
    async def test_page_error_swallowed(self):
        """If page.text_content raises a non-WaybillError, eligibility check is silently skipped."""
        mgr = self._make_manager()
        mgr.page.text_content = AsyncMock(side_effect=Exception("page crashed"))
        # Should not raise
        await mgr._check_account_eligibility()


# ---------------------------------------------------------------------------
# 6. EnhancedWaybillManager – _check_checkbox_with_fallback
# ---------------------------------------------------------------------------

class TestCheckboxWithFallback:
    def _make_manager(self):
        page = AsyncMock()
        ctx = AsyncMock()
        with patch("app.automation.waybill_enhanced.PageInteractor"), \
             patch("app.automation.waybill_enhanced.MapController"), \
             patch("app.automation.waybill_enhanced.LocationSelector"), \
             patch("app.automation.waybill_enhanced.RouteCalculator"):
            mgr = EnhancedWaybillManager(page, ctx)
        mgr.page = page
        return mgr

    @pytest.mark.asyncio
    async def test_checkbox_already_checked(self):
        mgr = self._make_manager()
        mock_el = AsyncMock()
        mock_el.is_checked = AsyncMock(return_value=True)
        mgr.page.query_selector = AsyncMock(return_value=mock_el)

        result = await mgr._check_checkbox_with_fallback(["#two-way"], "دو طرفه")
        assert result is True
        mock_el.check.assert_not_called()

    @pytest.mark.asyncio
    async def test_checkbox_unchecked_gets_checked(self):
        mgr = self._make_manager()
        mock_el = AsyncMock()
        mock_el.is_checked = AsyncMock(return_value=False)
        mock_el.check = AsyncMock()
        mgr.page.query_selector = AsyncMock(return_value=mock_el)

        result = await mgr._check_checkbox_with_fallback(["#two-way"], "دو طرفه")
        assert result is True
        mock_el.check.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_first_selector_missing_falls_to_second(self):
        mgr = self._make_manager()
        mock_el = AsyncMock()
        mock_el.is_checked = AsyncMock(return_value=False)
        mock_el.check = AsyncMock()
        # first selector returns None, second returns element
        mgr.page.query_selector = AsyncMock(side_effect=[None, mock_el])

        result = await mgr._check_checkbox_with_fallback(["#missing", "#two-way"], "دو طرفه")
        assert result is True

    @pytest.mark.asyncio
    async def test_no_selector_found_returns_false(self):
        mgr = self._make_manager()
        mgr.page.query_selector = AsyncMock(return_value=None)

        result = await mgr._check_checkbox_with_fallback(["#missing1", "#missing2"], "دو طرفه")
        assert result is False

    @pytest.mark.asyncio
    async def test_check_raises_falls_back_to_label_click(self):
        mgr = self._make_manager()
        mock_el = AsyncMock()
        mock_el.is_checked = AsyncMock(return_value=False)
        mock_el.check = AsyncMock(side_effect=Exception("check failed"))

        mock_label = AsyncMock()
        mock_label.click = AsyncMock()

        async def qs(selector):
            if "label" in selector:
                return mock_label
            return mock_el

        mgr.page.query_selector = qs

        result = await mgr._check_checkbox_with_fallback(["#two-way"], "دو طرفه")
        assert result is True
        mock_label.click.assert_awaited_once()


# ---------------------------------------------------------------------------
# 7. EnhancedWaybillManager – dry_run validation_summary fields
# ---------------------------------------------------------------------------

class TestDryRunValidationSummary:
    def _make_manager(self, page=None, ctx=None):
        from unittest.mock import Mock
        page = page or AsyncMock()
        page.locator = Mock()
        page.evaluate.return_value = False
        ctx = ctx or AsyncMock()
        with patch("app.automation.waybill_enhanced.PageInteractor"), \
             patch("app.automation.waybill_enhanced.MapController"), \
             patch("app.automation.waybill_enhanced.LocationSelector"), \
             patch("app.automation.waybill_enhanced.RouteCalculator"):
            mgr = EnhancedWaybillManager(page, ctx)
        mgr.page = page
        mgr.context = ctx
        return mgr

    @pytest.mark.asyncio
    async def test_dry_run_with_shipping_options(self):
        """dry_run=True must return validation_summary with two_way, end_shipping, time_limit, otp_required."""
        mgr = self._make_manager()

        data = _base_data()
        data["shipping_options"] = {"two_way": True, "time_limit": 60, "end_shipping": "1402-05-20", "otp": "111222"}

        # Patch every internal method that would require real page interaction
        mgr._ensure_waybill_form_page = AsyncMock()
        mgr._check_account_eligibility = AsyncMock()
        mgr._fill_sender_info = AsyncMock()
        mgr._fill_receiver_info = AsyncMock()
        mgr._fill_vehicle_info = AsyncMock()
        mgr._fill_cargo_info = AsyncMock()
        mgr._fill_financial_info = AsyncMock()
        mgr.location_selector.select_location = AsyncMock(
            return_value={"success": True, "method": "map"}
        )
        mgr._goto_with_retry = AsyncMock()
        mgr._click_with_fallback = AsyncMock()
        mgr._check_checkbox_with_fallback = AsyncMock(return_value=True)
        mgr._fill_with_fallback = AsyncMock()
        mgr._current_url = AsyncMock(return_value="https://utcms.ir/waybill/form")
        mgr.route_calculator.calculate_distance = AsyncMock(return_value=None)
        mgr.interactor.screenshot = AsyncMock()

        result = await mgr.create_waybill_with_map(data, dry_run=True)

        assert result["success"] is True
        assert result["status"] == "validated"
        vs = result["validation_summary"]
        assert vs["ready_for_submit"] is True
        assert vs["two_way"] is True
        assert vs["end_shipping"] == "1402-05-20"
        assert vs["time_limit"] == 60
        assert vs["otp_required"] is True

    @pytest.mark.asyncio
    async def test_dry_run_without_shipping_options(self):
        mgr = self._make_manager()
        data = _base_data()

        mgr._ensure_waybill_form_page = AsyncMock()
        mgr._check_account_eligibility = AsyncMock()
        mgr._fill_sender_info = AsyncMock()
        mgr._fill_receiver_info = AsyncMock()
        mgr._fill_vehicle_info = AsyncMock()
        mgr._fill_cargo_info = AsyncMock()
        mgr._fill_financial_info = AsyncMock()
        mgr.location_selector.select_location = AsyncMock(
            return_value={"success": True, "method": "dropdown"}
        )
        mgr._goto_with_retry = AsyncMock()
        mgr._click_with_fallback = AsyncMock()
        mgr._check_checkbox_with_fallback = AsyncMock(return_value=False)
        mgr._fill_with_fallback = AsyncMock()
        mgr._current_url = AsyncMock(return_value="https://utcms.ir/waybill/form")
        mgr.route_calculator.calculate_distance = AsyncMock(return_value=None)
        mgr.interactor.screenshot = AsyncMock()

        result = await mgr.create_waybill_with_map(data, dry_run=True)

        assert result["success"] is True
        vs = result["validation_summary"]
        assert vs["two_way"] is False
        assert vs["end_shipping"] is None
        assert vs["time_limit"] is None
        assert vs["otp_required"] is False


# ---------------------------------------------------------------------------
# 8. WaybillService end-to-end with shipping_options passed to manager
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_service_passes_shipping_options_to_manager():
    """Verify that shipping_options survive through the service layer into the manager."""
    opts = ShippingOptionsModel(two_way=True, time_limit=30)
    request = _base_request(shipping_options=opts)

    service = WaybillService()
    captured_payload = {}

    async def fake_create(payload, dry_run=True):
        captured_payload.update(payload)
        return {
            "success": True,
            "status": "validated",
            "validation_summary": {"ready_for_submit": True},
        }

    with patch("app.automation.browser.browser_manager.initialize", AsyncMock()), \
         patch("app.automation.browser.browser_manager.create_context",
               AsyncMock(return_value=("sid", AsyncMock()))), \
         patch("app.automation.browser.browser_manager.new_page", AsyncMock(return_value=AsyncMock())), \
         patch("app.automation.browser.browser_manager.close_context", AsyncMock()), \
         patch("app.automation.auth.UTCMSAuthenticator") as auth_cls, \
         patch("app.automation.waybill_enhanced.EnhancedWaybillManager") as mgr_cls, \
         patch("app.automation.reporting.report_service.record_request", AsyncMock()), \
         patch("app.automation.reporting.report_service.record_success", AsyncMock()), \
         patch("app.automation.reporting.report_service.record_map_usage", AsyncMock()), \
         patch("app.core.config.utcms_config.UTCMS_USERNAME", "user"), \
         patch("app.core.config.utcms_config.UTCMS_PASSWORD", "pass"):

        auth_cls.return_value._is_logged_in = AsyncMock(return_value=True)
        mgr_instance = mgr_cls.return_value
        mgr_instance.create_waybill_with_map = fake_create

        await service.create_waybill_with_map(request)

    assert "shipping_options" in captured_payload
    so = captured_payload["shipping_options"]
    assert so["two_way"] is True
    assert so["time_limit"] == 30
