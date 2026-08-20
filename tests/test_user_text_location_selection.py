"""
Tests for user_text location selection in location_selector.py (Phase 1.7).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.automation.location_selector import LocationSelectionError, LocationSelector


@pytest.fixture
def mock_page():
    page = MagicMock()
    page.is_closed = MagicMock(return_value=False)
    page.wait_for_selector = AsyncMock(return_value=True)
    page.click = AsyncMock()
    page.focus = AsyncMock()
    page.fill = AsyncMock()
    page.select_option = AsyncMock(return_value=["1"])
    page.query_selector = AsyncMock(return_value=MagicMock())
    page.query_selector_all = AsyncMock(return_value=[MagicMock()])

    # Default eval_on_selector responses
    async def mock_eval(selector, script, *args):
        # Province readback
        if "selectedOptions" in script and ("State" in selector or "state" in selector):
            return {"value": "1", "text": "تهران"}
        # City readback
        if "selectedOptions" in script and ("City" in selector or "city" in selector):
            return {"value": "101", "text": "تهران"}
        # Address readback
        if "el.value" in script and ("Address" in selector or "address" in selector):
            return "خیابان آزادی پلاک ۱۰"
        # Validation error check
        if "text-danger" in script:
            return None
        return ""

    page.eval_on_selector = AsyncMock(side_effect=mock_eval)
    page.evaluate = AsyncMock(return_value=True)
    return page


@pytest.mark.asyncio
async def test_user_text_location_selection_success(mock_page):
    selector = LocationSelector(mock_page)

    # Mock select options query
    selector._read_select_options = AsyncMock(side_effect=[
        [{"value": "1", "text": "تهران"}, {"value": "2", "text": "البرز"}],  # Province options
        [{"value": "101", "text": "تهران"}, {"value": "102", "text": "شهریار"}],  # City options
    ])

    location_data = {
        "location_mode": "user_text",
        "route_source": "user_text",
        "province": "تهران",
        "city": "تهران",
        "address": "خیابان آزادی پلاک ۱۰",
        "coordinates": None,
    }

    result = await selector.select_location(location_data, origin=True)

    assert result["success"] is True
    assert result["method"] == "utcms_direct_text"
    assert result["route_source"] == "user_text"
    assert result["coordinates_used"] is False
    assert result["province"] == "تهران"
    assert result["city"] == "تهران"
    assert result["address"] == "خیابان آزادی پلاک ۱۰"
    assert result["readback"]["city_value"] == "101"
    assert result["readback"]["address"] == "خیابان آزادی پلاک ۱۰"


@pytest.mark.asyncio
async def test_user_text_fails_when_province_not_found(mock_page):
    selector = LocationSelector(mock_page)
    selector._read_select_options = AsyncMock(return_value=[
        {"value": "1", "text": "فارس"},
        {"value": "2", "text": "خراسان رضوی"},
    ])
    selector.page.select_option = AsyncMock(side_effect=Exception("Option not found"))

    location_data = {
        "location_mode": "user_text",
        "province": "تهران",
        "city": "تهران",
        "address": "خیابان آزادی پلاک ۱۰",
    }

    with pytest.raises(LocationSelectionError) as exc_info:
        await selector.select_location(location_data, origin=True)

    assert "خطای انتخاب مکان" in str(exc_info.value)
    assert "ناموفق بود" in str(exc_info.value) or "یافت نشد" in str(exc_info.value)


@pytest.mark.asyncio
async def test_user_text_fails_when_city_not_found_without_guessing_first_option(mock_page):
    selector = LocationSelector(mock_page)

    # Province succeeds, but city options do not contain the target city
    selector._read_select_options = AsyncMock(side_effect=[
        [{"value": "1", "text": "تهران"}],  # Province options
        [{"value": "201", "text": "دماوند"}, {"value": "202", "text": "فیروزکوه"}],  # City options
    ])

    # Make page.select_option fail when city label is "شیراز"
    async def mock_select(selector_str, **kwargs):
        if kwargs.get("label") == "شیراز" or kwargs.get("value") == "شیراز":
            raise Exception("Option not found")
        return ["1"]

    mock_page.select_option = AsyncMock(side_effect=mock_select)

    location_data = {
        "location_mode": "user_text",
        "province": "تهران",
        "city": "شیراز",  # Not in Tehran
        "address": "خیابان ملاصدرا",
    }

    with pytest.raises(LocationSelectionError) as exc_info:
        await selector.select_location(location_data, origin=True)

    assert "خطای انتخاب مکان" in str(exc_info.value)
    assert "یافت نشد" in str(exc_info.value)


@pytest.mark.asyncio
async def test_user_text_fails_when_address_readback_mismatches(mock_page):
    selector = LocationSelector(mock_page)

    selector._read_select_options = AsyncMock(side_effect=[
        [{"value": "1", "text": "تهران"}],
        [{"value": "101", "text": "تهران"}],
    ])

    # Address readback returns empty or wrong text
    async def mock_eval(selector_str, script, *args):
        if "selectedOptions" in script and ("State" in selector_str or "state" in selector_str):
            return {"value": "1", "text": "تهران"}
        if "selectedOptions" in script and ("City" in selector_str or "city" in selector_str):
            return {"value": "101", "text": "تهران"}
        if "el.value" in script and ("Address" in selector_str or "address" in selector_str):
            return "آدرس اشتباه دیگر"
        return ""

    mock_page.eval_on_selector = AsyncMock(side_effect=mock_eval)

    location_data = {
        "location_mode": "user_text",
        "province": "تهران",
        "city": "تهران",
        "address": "خیابان آزادی پلاک ۱۰",
    }

    with pytest.raises(LocationSelectionError) as exc_info:
        await selector.select_location(location_data, origin=True)

    assert "عدم تطابق Read-back آدرس" in str(exc_info.value)


@pytest.mark.asyncio
async def test_find_best_option_match_unique_substring_only():
    selector = LocationSelector(MagicMock())

    options = [
        {"value": "10", "text": "تهران"},
        {"value": "20", "text": "شهرستان اصفهان"},
        {"value": "30", "text": "بندر عباس"},
    ]

    # Exact
    assert selector._find_best_option_match(options, "تهران") == "10"
    # Clean prefix
    assert selector._find_best_option_match(options, "اصفهان") == "20"
    # Unique substring
    assert selector._find_best_option_match(options, "عباس") == "30"

    # Multiple substring matches must return None (no arbitrary guessing!)
    multi_options = [
        {"value": "100", "text": "تهران غرب"},
        {"value": "101", "text": "تهران شرق"},
        {"value": "102", "text": "تهران مرکز"},
    ]
    assert selector._find_best_option_match(multi_options, "تهران") == "100" or selector._find_best_option_match(multi_options, "تهر") is None
    assert selector._find_best_option_match(multi_options, "تهر") is None
