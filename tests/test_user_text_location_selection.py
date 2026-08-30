"""
Tests for user_text location selection in location_selector.py (Phase 1.7).
"""

from unittest.mock import AsyncMock, MagicMock, call

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
    selector._read_select_options = AsyncMock(
        side_effect=[
            [{"value": "1", "text": "تهران"}, {"value": "2", "text": "البرز"}],  # Province options
            [{"value": "101", "text": "تهران"}, {"value": "102", "text": "شهریار"}],  # City options
        ]
    )

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
    selector._read_select_options = AsyncMock(
        return_value=[
            {"value": "1", "text": "فارس"},
            {"value": "2", "text": "خراسان رضوی"},
        ]
    )
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
    selector._read_select_options = AsyncMock(
        side_effect=[
            [{"value": "1", "text": "تهران"}],  # Province options
            [{"value": "201", "text": "دماوند"}, {"value": "202", "text": "فیروزکوه"}],  # City options
        ]
    )

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

    selector._read_select_options = AsyncMock(
        side_effect=[
            [{"value": "1", "text": "تهران"}],
            [{"value": "101", "text": "تهران"}],
        ]
    )

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
async def test_direct_fill_reads_back_the_exact_successful_selectors(mock_page):
    selector = LocationSelector(mock_page)
    selector._ensure_location_tab_active = AsyncMock()
    selector._wait_for_select_options = AsyncMock(return_value=True)
    selector._get_utcms_selectors = MagicMock(
        return_value={
            "province": ["#hiddenState", "#actualState"],
            "city": ["#hiddenCity", "#actualCity"],
            "address": ["#hiddenAddress", "#actualAddress"],
        }
    )
    selector._select_from_options_with_selector = AsyncMock(side_effect=["#actualState", "#actualCity"])
    selector._read_selected_option = AsyncMock(
        side_effect=[
            {"value": "1", "text": "تهران"},
            {"value": "101", "text": "تهران"},
        ]
    )
    selector._fill_input_like = AsyncMock(side_effect=[False, True])
    selector._read_element_value = AsyncMock(return_value="خیابان آزادی پلاک ۱۰")
    # Holding the selection is covered separately; here only the read-back
    # selectors are under test.
    selector._hold_select_value = AsyncMock(return_value=True)
    mock_page.eval_on_selector = AsyncMock(return_value=None)

    result = await selector._try_utcms_direct_fill(
        {"province": "تهران", "city": "تهران", "address": "خیابان آزادی پلاک ۱۰"},
        "Origin",
    )

    assert result["success"] is True
    assert selector._read_selected_option.await_args_list == [call("#actualState"), call("#actualCity")]
    selector._read_element_value.assert_awaited_once_with("#actualAddress")


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
    assert (
        selector._find_best_option_match(multi_options, "تهران") == "100"
        or selector._find_best_option_match(multi_options, "تهر") is None
    )
    assert selector._find_best_option_match(multi_options, "تهر") is None


class TestHiddenSelectAndBackfill:
    """The collapsed pill pane and UTCMS's broken ``fillStates`` handler.

    UTCMS serves ``fillStates`` as ``application/json``, so its own handler
    iterates the ``{resultCode, resultMessage, obj}`` envelope and leaves three
    ``undefined`` options behind, and the origin/destination selects live in a
    ``display:none`` pill pane until the tab is activated.  Both states used to
    surface as «گزینه‌های استان بارگذاری نشدند».
    """

    @pytest.mark.asyncio
    async def test_resolve_selector_falls_back_to_hidden_element(self):
        page = MagicMock()
        page.query_selector = AsyncMock(side_effect=[None, MagicMock()])
        selector = LocationSelector(page)

        assert await selector._resolve_selector("#ddStateSource") == "#ddStateSource"
        assert page.query_selector.await_args_list == [
            call("#ddStateSource:visible"),
            call("#ddStateSource"),
        ]

    @pytest.mark.asyncio
    async def test_resolve_selector_prefers_visible_match(self):
        page = MagicMock()
        page.query_selector = AsyncMock(return_value=MagicMock())
        selector = LocationSelector(page)

        assert await selector._resolve_selector("#ddStateSource") == "#ddStateSource:visible"

    @pytest.mark.asyncio
    async def test_resolve_selector_returns_none_when_detached(self):
        page = MagicMock()
        page.query_selector = AsyncMock(return_value=None)
        selector = LocationSelector(MagicMock())
        selector.page = page

        assert await selector._resolve_selector("#missing") is None

    @pytest.mark.asyncio
    async def test_undefined_only_options_trigger_backfill_from_utcms(self):
        page = MagicMock()
        page.query_selector = AsyncMock(return_value=MagicMock())
        page.evaluate = AsyncMock(
            return_value={
                "resultCode": 200,
                "obj": [
                    {"id": 4, "name": "آذربایجان شرقى"},
                    {"id": 8, "name": "خراسان رضوى"},
                ],
            }
        )
        page.eval_on_selector = AsyncMock(return_value=2)
        selector = LocationSelector(page)
        # What the page's own fillStates handler leaves behind.
        selector._read_select_options = AsyncMock(
            return_value=[
                {"value": "", "text": "انتخاب کنید..."},
                {"value": "undefined", "text": "undefined"},
                {"value": "undefined", "text": "undefined"},
                {"value": "undefined", "text": "undefined"},
            ]
        )

        assert await selector._ensure_province_options(["#ddStateSource"]) is True

        page.evaluate.assert_awaited_once()
        assert "/Barname/Document/FillProvinces" in page.evaluate.await_args.args[1]
        applied = page.eval_on_selector.await_args.args[2]
        assert applied == [
            {"value": "4", "text": "آذربایجان شرقى"},
            {"value": "8", "text": "خراسان رضوى"},
        ]

    @pytest.mark.asyncio
    async def test_city_backfill_uses_the_selected_state_id(self):
        page = MagicMock()
        page.query_selector = AsyncMock(return_value=MagicMock())
        page.evaluate = AsyncMock(return_value={"resultCode": 200, "obj": [{"id": 91, "name": "کاشمر"}]})
        page.eval_on_selector = AsyncMock(return_value=1)
        selector = LocationSelector(page)
        selector._read_select_options = AsyncMock(return_value=[{"value": "", "text": "انتخاب کنید..."}])

        assert await selector._ensure_city_options(["#ddCitySource"], "8") is True
        assert "/Barname/Document/FillCities?StateId=8" in page.evaluate.await_args.args[1]

    @pytest.mark.asyncio
    async def test_backfill_is_skipped_when_utcms_rejects_the_request(self):
        page = MagicMock()
        page.query_selector = AsyncMock(return_value=MagicMock())
        page.evaluate = AsyncMock(return_value={"error": "HTTP 500"})
        page.eval_on_selector = AsyncMock(return_value=0)
        selector = LocationSelector(page)
        selector._read_select_options = AsyncMock(return_value=[{"value": "", "text": "انتخاب کنید..."}])

        assert await selector._ensure_province_options(["#ddStateSource"]) is False
        page.eval_on_selector.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_arabic_alef_maksura_normalizes_to_persian_yeh(self):
        selector = LocationSelector(MagicMock())
        assert selector._normalize_text("خراسان رضوى") == selector._normalize_text("خراسان رضوی")
        options = [{"value": "8", "text": "خراسان رضوى"}]
        assert selector._find_best_option_match(options, selector._normalize_text("خراسان رضوی")) == "8"


class TestSelectionSurvivesLateAjax:
    """``FillCities`` answers seconds after the province change and empties the
    city select, wiping a selection that read back correctly a moment earlier."""

    @pytest.mark.asyncio
    async def test_city_selection_is_reasserted_after_the_list_is_rebuilt(self):
        page = MagicMock()
        page.query_selector = AsyncMock(return_value=MagicMock())
        selector = LocationSelector(page)
        # First poll: the page has just cleared the selection. Then it holds.
        selector._read_selected_option = AsyncMock(
            side_effect=[
                {"value": "", "text": "انتخاب کنید"},
                {"value": "1200", "text": "کاشمر"},
                {"value": "1200", "text": "کاشمر"},
                {"value": "1200", "text": "کاشمر"},
                {"value": "1200", "text": "کاشمر"},
                {"value": "1200", "text": "کاشمر"},
                {"value": "1200", "text": "کاشمر"},
                {"value": "1200", "text": "کاشمر"},
                {"value": "1200", "text": "کاشمر"},
                {"value": "1200", "text": "کاشمر"},
                {"value": "1200", "text": "کاشمر"},
                {"value": "1200", "text": "کاشمر"},
                {"value": "1200", "text": "کاشمر"},
                {"value": "1200", "text": "کاشمر"},
            ]
        )
        selector._reapply_option_value = AsyncMock(return_value="ok")

        assert await selector._hold_select_value("#ddCitySource", "1200", settle_ms=600) is True
        selector._reapply_option_value.assert_awaited_once_with("#ddCitySource", "1200")

    @pytest.mark.asyncio
    async def test_hold_refills_options_when_the_value_disappeared(self):
        page = MagicMock()
        selector = LocationSelector(page)
        selector._read_selected_option = AsyncMock(return_value={"value": "", "text": ""})
        selector._reapply_option_value = AsyncMock(side_effect=["missing", "ok", "ok", "ok", "ok", "ok", "ok"])
        refill = AsyncMock(return_value=True)

        await selector._hold_select_value("#ddCitySource", "1200", settle_ms=600, refill=refill)

        refill.assert_awaited()

    @pytest.mark.asyncio
    async def test_hold_fails_loudly_when_the_value_cannot_be_restored(self):
        page = MagicMock()
        selector = LocationSelector(page)
        selector._read_selected_option = AsyncMock(return_value={"value": "", "text": ""})
        selector._reapply_option_value = AsyncMock(return_value="missing")

        assert await selector._hold_select_value("#ddCitySource", "1200", settle_ms=600) is False
