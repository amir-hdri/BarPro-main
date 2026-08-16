"""
Mandatory Comprehensive 21-Scenario Test Suite for UTCMS RPA Overhaul (Phase 1.15).
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.automation.location_selector import LocationSelectionError, LocationSelector
from app.automation.multitenant_payload_adapter import (
    _validate_iranian_national_code,
    build_enhanced_waybill_payload,
    compute_canonical_route_key,
    validate_enhanced_waybill_payload,
)
from app.models_rpa import GateStateValue
from app.orchestrator.utcms_reconciliation_scraper import (
    ReconciliationResult,
    ScraperOutcome,
    UTCMSReconciliationScraper,
)
from app.services.utcms_submission_gate import UTCMSSubmissionGate


@pytest.fixture
def mock_playwright_page():
    page = MagicMock()
    page.is_closed = MagicMock(return_value=False)
    page.wait_for_selector = AsyncMock(return_value=True)
    page.click = AsyncMock()
    page.focus = AsyncMock()
    page.fill = AsyncMock()
    page.select_option = AsyncMock(return_value=["1"])
    page.query_selector = AsyncMock(return_value=MagicMock())
    page.query_selector_all = AsyncMock(return_value=[MagicMock()])

    async def mock_eval(selector, script, *args):
        if "selectedOptions" in script and ("State" in selector or "state" in selector):
            return {"value": "1", "text": "تهران"}
        if "selectedOptions" in script and ("City" in selector or "city" in selector):
            return {"value": "101", "text": "تهران"}
        if "el.value" in script and ("Address" in selector or "address" in selector):
            return "خیابان آزادی، پلاک ۱۰"
        if "text-danger" in script:
            return None
        return ""

    page.eval_on_selector = AsyncMock(side_effect=mock_eval)
    page.evaluate = AsyncMock(return_value=True)
    return page


# ==================== SCENARIOS 1 - 8: LOCATION SELECTOR & READBACK ====================

@pytest.mark.asyncio
async def test_01_user_text_location_selection_without_coordinates(mock_playwright_page):
    """1. user_text origin selection without GPS/coordinates."""
    selector = LocationSelector(mock_playwright_page)
    selector._read_select_options = AsyncMock(side_effect=[
        [{"value": "1", "text": "تهران"}],
        [{"value": "101", "text": "تهران"}],
    ])

    data = {
        "location_mode": "user_text",
        "province": "تهران",
        "city": "تهران",
        "address": "خیابان آزادی، پلاک ۱۰",
        "coordinates": None,
    }
    res = await selector.select_location(data, origin=True)
    assert res["success"] is True
    assert res["method"] == "utcms_direct_text"
    assert res["route_source"] == "user_text"
    assert res["coordinates_used"] is False


@pytest.mark.asyncio
async def test_02_missing_province_fails_immediately(mock_playwright_page):
    """2. Missing province -> immediate failure."""
    selector = LocationSelector(mock_playwright_page)
    data = {"location_mode": "user_text", "province": "", "city": "تهران", "address": "خیابان آزادی"}
    with pytest.raises(LocationSelectionError) as exc:
        await selector.select_location(data, origin=True)
    assert "ناقص است" in str(exc.value)


@pytest.mark.asyncio
async def test_03_missing_city_fails_immediately(mock_playwright_page):
    """3. Missing city -> immediate failure."""
    selector = LocationSelector(mock_playwright_page)
    data = {"location_mode": "user_text", "province": "تهران", "city": "", "address": "خیابان آزادی"}
    with pytest.raises(LocationSelectionError) as exc:
        await selector.select_location(data, origin=True)
    assert "ناقص است" in str(exc.value)


@pytest.mark.asyncio
async def test_04_missing_address_fails_immediately(mock_playwright_page):
    """4. Missing address -> immediate failure."""
    selector = LocationSelector(mock_playwright_page)
    data = {"location_mode": "user_text", "province": "تهران", "city": "تهران", "address": ""}
    with pytest.raises(LocationSelectionError) as exc:
        await selector.select_location(data, origin=True)
    assert "ناقص است" in str(exc.value)


@pytest.mark.asyncio
async def test_05_city_not_in_options_fails_without_guessing_first_option(mock_playwright_page):
    """5. City not in options -> fails without picking first option."""
    selector = LocationSelector(mock_playwright_page)
    selector._read_select_options = AsyncMock(side_effect=[
        [{"value": "1", "text": "تهران"}],
        [{"value": "201", "text": "دماوند"}, {"value": "202", "text": "فیروزکوه"}],
    ])
    mock_playwright_page.select_option = AsyncMock(side_effect=Exception("Option not found"))

    data = {"location_mode": "user_text", "province": "تهران", "city": "اصفهان", "address": "خیابان چهارباغ"}
    with pytest.raises(LocationSelectionError) as exc:
        await selector.select_location(data, origin=True)
    assert "یافت نشد" in str(exc.value) or "ناموفق بود" in str(exc.value)


@pytest.mark.asyncio
async def test_06_ajax_cities_timeout_fails(mock_playwright_page):
    """6. AJAX cities cascade wait timeout -> failure."""
    selector = LocationSelector(mock_playwright_page)
    selector._wait_for_select_options = AsyncMock(side_effect=[True, False])  # Province ok, city timeout

    data = {"location_mode": "user_text", "province": "تهران", "city": "تهران", "address": "خیابان آزادی"}
    with pytest.raises(LocationSelectionError) as exc:
        await selector.select_location(data, origin=True)
    assert "بارگذاری نشدند" in str(exc.value)


@pytest.mark.asyncio
async def test_07_readback_mismatch_on_city_aborts(mock_playwright_page):
    """7. Readback mismatch on city -> aborts."""
    selector = LocationSelector(mock_playwright_page)
    selector._read_select_options = AsyncMock(side_effect=[
        [{"value": "1", "text": "تهران"}],
        [{"value": "101", "text": "تهران"}],
    ])

    async def mock_mismatched_eval(selector_str, script, *args):
        if "selectedOptions" in script and ("State" in selector_str or "state" in selector_str):
            return {"value": "1", "text": "تهران"}
        if "selectedOptions" in script and ("City" in selector_str or "city" in selector_str):
            return {"value": "102", "text": "شهریار"}  # Mismatched city readback
        if "el.value" in script and ("Address" in selector_str or "address" in selector_str):
            return "خیابان آزادی، پلاک ۱۰"
        return ""

    mock_playwright_page.eval_on_selector = AsyncMock(side_effect=mock_mismatched_eval)

    data = {"location_mode": "user_text", "province": "تهران", "city": "تهران", "address": "خیابان آزادی، پلاک ۱۰"}
    with pytest.raises(LocationSelectionError) as exc:
        await selector.select_location(data, origin=True)
    assert "عدم تطابق Read-back شهر" in str(exc.value)


@pytest.mark.asyncio
async def test_08_readback_mismatch_on_address_aborts(mock_playwright_page):
    """8. Readback mismatch on address -> aborts."""
    selector = LocationSelector(mock_playwright_page)
    selector._read_select_options = AsyncMock(side_effect=[
        [{"value": "1", "text": "تهران"}],
        [{"value": "101", "text": "تهران"}],
    ])

    async def mock_mismatched_addr(selector_str, script, *args):
        if "selectedOptions" in script and ("State" in selector_str or "state" in selector_str):
            return {"value": "1", "text": "تهران"}
        if "selectedOptions" in script and ("City" in selector_str or "city" in selector_str):
            return {"value": "101", "text": "تهران"}
        if "el.value" in script and ("Address" in selector_str or "address" in selector_str):
            return "آدرس مغایر دیگری"  # Mismatch
        return ""

    mock_playwright_page.eval_on_selector = AsyncMock(side_effect=mock_mismatched_addr)

    data = {"location_mode": "user_text", "province": "تهران", "city": "تهران", "address": "خیابان آزادی، پلاک ۱۰"}
    with pytest.raises(LocationSelectionError) as exc:
        await selector.select_location(data, origin=True)
    assert "عدم تطابق Read-back آدرس" in str(exc.value)


# ==================== SCENARIOS 9 - 11: ROUTE CONTRACT & KEYS ====================

def test_09_route_key_determinism():
    """9. Route key determinism (canonical text only, no coordinates)."""
    o1 = {"province": "تهران", "city": "تهران", "district": "منطقه ۱", "address": "خیابان مطهری"}
    d1 = {"province": "البرز", "city": "کرج", "district": "", "address": "میدان مادر"}
    key1 = compute_canonical_route_key(o1, d1)

    o2 = {"province": " تهران ", "city": "تهران", "district": "منطقه ۱", "address": "خیابان  مطهری"}
    d2 = {"province": "البرز", "city": "کرج", "district": None, "address": "میدان مادر "}
    key2 = compute_canonical_route_key(o2, d2)

    assert key1 == key2


def test_10_distinct_route_keys_for_different_addresses():
    """10. Distinct route keys for different addresses in same city."""
    o1 = {"province": "تهران", "city": "تهران", "address": "خیابان آزادی پلاک ۱"}
    o2 = {"province": "تهران", "city": "تهران", "address": "خیابان انقلاب پلاک ۲"}
    d = {"province": "اصفهان", "city": "اصفهان", "address": "بلوار دانشگاه"}

    key1 = compute_canonical_route_key(o1, d)
    key2 = compute_canonical_route_key(o2, d)
    assert key1 != key2


def test_11_coordinates_ignored_in_user_text_payload():
    """11. Coordinates ignored in user_text mode."""
    raw = {
        "sender": {"name": "علی رضایی", "type": "individual"},
        "receiver": {"name": "حسن کاظمی", "type": "individual"},
        "origin": {"province": "تهران", "city": "تهران", "address": "خ آزادی", "coordinates": {"lat": 35.7, "lng": 51.4}},
        "destination": {"province": "قم", "city": "قم", "address": "خ ارم", "coordinates": {"lat": 34.6, "lng": 50.8}},
        "cargo": {"type": "کارتن", "packaging": "کارتن", "weight": 1.0, "value": "1000000"},
        "vehicle": {"driver_national_code": "0084575948", "plate": "12ب345ایران11"},
    }
    enhanced = build_enhanced_waybill_payload(raw)
    assert enhanced["origin"]["coordinates"] is None
    assert enhanced["destination"]["coordinates"] is None


# ==================== SCENARIOS 12 - 17: PAYLOAD VALIDATION ====================

def test_12_validation_individual_valid_name():
    """12. Validation: Individual sender valid name passes."""
    payload = {
        "sender": {"name": "حمید احمدی", "type": "individual"},
        "receiver": {"name": "رضا صادقی", "type": "individual"},
        "origin": {"province": "تهران", "city": "تهران", "address": "خ آزادی"},
        "destination": {"province": "البرز", "city": "کرج", "address": "خ بهشتی"},
        "cargo": {"type": "کالا", "packaging": "جعبه", "weight": 2.0, "value": "500000"},
        "vehicle": {"driver_national_code": "0084575948", "plate": "12ب345ایران11"},
    }
    errors = validate_enhanced_waybill_payload(payload)
    assert errors == []


def test_13_validation_sender_duplicate_single_word_rejected():
    """13. Validation: Individual sender duplicate single word -> rejected."""
    payload = {
        "sender": {"name": "علی علی", "type": "individual"},
        "receiver": {"name": "رضا صادقی", "type": "individual"},
        "origin": {"province": "تهران", "city": "تهران", "address": "خ آزادی"},
        "destination": {"province": "البرز", "city": "کرج", "address": "خ بهشتی"},
        "cargo": {"type": "کالا", "packaging": "جعبه", "weight": 2.0, "value": "500000"},
        "vehicle": {"driver_national_code": "0084575948", "plate": "12ب345ایران11"},
    }
    errors = validate_enhanced_waybill_payload(payload)
    assert any("تکراری" in e for e in errors)


def test_14_validation_legal_entity_missing_office_name_rejected():
    """14. Validation: Legal entity sender without office name -> rejected."""
    payload = {
        "sender": {"type": "company", "name": "", "office_name": ""},
        "receiver": {"name": "رضا صادقی", "type": "individual"},
        "origin": {"province": "تهران", "city": "تهران", "address": "خ آزادی"},
        "destination": {"province": "البرز", "city": "کرج", "address": "خ بهشتی"},
        "cargo": {"type": "کالا", "packaging": "جعبه", "weight": 2.0, "value": "500000"},
        "vehicle": {"driver_national_code": "0084575948", "plate": "12ب345ایران11"},
    }
    errors = validate_enhanced_waybill_payload(payload)
    assert any("نام حقوقی" in e for e in errors)


def test_15_validation_driver_national_code_invalid_checksum():
    """15. Validation: Driver national code invalid checksum -> rejected."""
    payload = {
        "sender": {"name": "حمید احمدی", "type": "individual"},
        "receiver": {"name": "رضا صادقی", "type": "individual"},
        "origin": {"province": "تهران", "city": "تهران", "address": "خ آزادی"},
        "destination": {"province": "البرز", "city": "کرج", "address": "خ بهشتی"},
        "cargo": {"type": "کالا", "packaging": "جعبه", "weight": 2.0, "value": "500000"},
        "vehicle": {"driver_national_code": "0012345678", "plate": "12ب345ایران11"},  # Invalid checksum
    }
    errors = validate_enhanced_waybill_payload(payload)
    assert any("کد ملی راننده" in e for e in errors)


def test_16_validation_cargo_packaging_missing_rejected():
    """16. Validation: Cargo packaging missing -> rejected."""
    payload = {
        "sender": {"name": "حمید احمدی", "type": "individual"},
        "receiver": {"name": "رضا صادقی", "type": "individual"},
        "origin": {"province": "تهران", "city": "تهران", "address": "خ آزادی"},
        "destination": {"province": "البرز", "city": "کرج", "address": "خ بهشتی"},
        "cargo": {"type": "کالا", "packaging": None, "weight": 2.0, "value": "500000"},
        "vehicle": {"driver_national_code": "0084575948", "plate": "12ب345ایران11"},
    }
    errors = validate_enhanced_waybill_payload(payload)
    assert any("نوع بسته‌بندی" in e for e in errors)


def test_17_validation_cargo_negative_weight_rejected():
    """17. Validation: Cargo negative weight -> rejected."""
    payload = {
        "sender": {"name": "حمید احمدی", "type": "individual"},
        "receiver": {"name": "رضا صادقی", "type": "individual"},
        "origin": {"province": "تهران", "city": "تهران", "address": "خ آزادی"},
        "destination": {"province": "البرز", "city": "کرج", "address": "خ بهشتی"},
        "cargo": {"type": "کالا", "packaging": "کارتن", "weight": -10, "value": "500000"},
        "vehicle": {"driver_national_code": "0084575948", "plate": "12ب345ایران11"},
    }
    errors = validate_enhanced_waybill_payload(payload)
    assert any("وزن کالا" in e for e in errors)


# ==================== SCENARIOS 18 - 20: SUBMISSION GATE ====================

@pytest.mark.asyncio
async def test_18_submission_gate_otp_required_blocks():
    """18. Submission gate: OTP state blocks submission in OTP_REQUIRED."""
    gate = UTCMSSubmissionGate()
    with patch.object(gate, "get_state", AsyncMock(return_value=GateStateValue.OTP_REQUIRED)):
        allowed = await gate.is_submission_allowed()
        assert allowed is False


@pytest.mark.asyncio
async def test_19_submission_gate_otp_free_allows():
    """19. Submission gate: Free window allows submission in OTP_FREE."""
    gate = UTCMSSubmissionGate()
    with patch.object(gate, "get_state", AsyncMock(return_value=GateStateValue.OTP_FREE)):
        allowed = await gate.is_submission_allowed()
        assert allowed is True


@pytest.mark.asyncio
async def test_20_submission_gate_unknown_defaults_to_safe():
    """20. Submission gate: Ambiguous/UNKNOWN state defaults to safe mode (ALLOW_LIVE_SUBMIT=False)."""
    gate = UTCMSSubmissionGate()
    with patch.object(gate, "get_state", AsyncMock(return_value=GateStateValue.UNKNOWN)):
        with patch("app.core.config.utcms_config.ALLOW_LIVE_SUBMIT", False):
            allowed = await gate.is_submission_allowed()
            assert allowed is False


# ==================== SCENARIO 21: RECONCILIATION MATCHING ====================

def test_21_reconciliation_scraper_matches_row_by_tracking_code():
    """21. Real reconciliation scraper: matches DataTables row by tracking code & parameters."""
    scraper = UTCMSReconciliationScraper()
    row = {
        "docNo": "987654321",
        "driverNationalCode": "0084575948",
        "car": "12ب345ایران11",
        "sourceAddress": "تهران خ آزادی",
        "destAddress": "کرج خ بهشتی",
    }
    assert scraper._match_row(row, tracking_code="987654321", national_code="0084575948", plate_number="12ب345ایران11", origin_city="تهران", dest_city="کرج") is True
    assert scraper._match_row(row, tracking_code="111111111", national_code="0084575948", plate_number="12ب345ایران11", origin_city="تهران", dest_city="کرج") is True
    assert scraper._match_row(row, tracking_code="111111111", national_code="9999999999", plate_number="99ب999ایران99", origin_city="شیراز", dest_city="اصفهان") is False
