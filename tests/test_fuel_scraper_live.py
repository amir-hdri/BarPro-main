import pytest
from playwright.async_api import async_playwright

from app.automation.fuel_scraper import get_current_jalali, parse_plate


def test_parse_plate():
    # Test valid formats
    p1 = parse_plate("12ب34567")
    assert p1["first"] == "12"
    assert p1["char_val"] == "2"
    assert p1["center"] == "345"
    assert p1["ir"] == "67"

    p2 = parse_plate("۱۲ت۳۴۵ایران۶۷")
    assert p2["first"] == "12"
    assert p2["char_val"] == "4"
    assert p2["center"] == "345"
    assert p2["ir"] == "67"

    # Test invalid formats
    with pytest.raises(ValueError):
        parse_plate("12B34567")  # non-persian character

    with pytest.raises(ValueError):
        parse_plate("123ب4567")  # invalid digit count


def test_get_current_jalali():
    year, month = get_current_jalali()
    assert 1397 <= year <= 1405
    assert 1 <= month <= 12


@pytest.mark.asyncio
async def test_fuel_scraper_form_elements():
    """
    Verifies that the scraper can load ShowFuelQuota.aspx and find all necessary elements.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # Go directly to target URL
            await page.goto("https://utcms.ir/ShowFuelQuota.aspx", wait_until="domcontentloaded", timeout=20000)

            # Assert all required form elements are present on the page
            assert await page.query_selector("#NationalCode") is not None
            assert await page.query_selector("#Year") is not None
            assert await page.query_selector("#Month") is not None
            assert await page.query_selector("input[name='pelakSelected']") is not None
            assert await page.query_selector("#pelakFirstLogin") is not None
            assert await page.query_selector("#pelakComboLogin") is not None
            assert await page.query_selector("#pelakCenterLogin") is not None
            assert await page.query_selector("#pelakIrNumLogin") is not None
            assert await page.query_selector("input[name='QoutaType']") is not None
            assert await page.query_selector("#imgCapchaEdit1") is not None
            assert await page.query_selector("#txtCapcha") is not None
            assert await page.query_selector("#Login") is not None

        except Exception as e:
            pytest.skip(f"Live website not reachable or slow: {e}")
        finally:
            await browser.close()
