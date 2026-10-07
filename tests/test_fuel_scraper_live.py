import asyncio
import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from playwright.async_api import async_playwright

from app.automation.fuel_scraper import get_current_jalali, parse_plate
from app.core.jalali import gregorian_to_jalali


@pytest.mark.unit
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


@pytest.mark.unit
def test_get_current_jalali():
    year, month = get_current_jalali()
    assert 1397 <= year
    assert 1 <= month <= 12
    # No hardcoded upper year bound (the old `<= 1405` would start failing on
    # 1406-01-01): cross-check against today's date instead. ±1 tolerates the
    # Tehran-midnight boundary between the two clock reads.
    expected_year, _, _ = gregorian_to_jalali(*datetime.now(UTC).timetuple()[:3])
    assert abs(year - expected_year) <= 1


async def _require_iranian_egress() -> None:
    process = await asyncio.create_subprocess_exec(
        "curl",
        "-fsS",
        "--max-time",
        "10",
        "https://ipinfo.io/country",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _stderr = await process.communicate()
    if process.returncode != 0 or stdout.decode("ascii", errors="replace").strip() != "IR":
        pytest.fail("Live UTCMS test requires a successful Iranian egress check before accessing UTCMS")


@pytest.mark.unit
@pytest.mark.parametrize("country", [b"US\n", b"", b"IR\n"])
async def test_live_egress_guard_requires_ir(monkeypatch: pytest.MonkeyPatch, country: bytes) -> None:
    process = AsyncMock()
    process.returncode = 0
    process.communicate.return_value = (country, b"")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
    if country == b"IR\n":
        await _require_iranian_egress()
    else:
        with pytest.raises(pytest.fail.Exception, match="Iranian egress"):
            await _require_iranian_egress()


@pytest.mark.live_utcms
@pytest.mark.skipif(os.getenv("BARPRO_RUN_LIVE_UTCMS") != "1", reason="Explicit BARPRO_RUN_LIVE_UTCMS=1 required")
@pytest.mark.asyncio
async def test_fuel_scraper_form_elements():
    """Opt-in read-only UTCMS probe; transport and assertion failures remain failures."""
    async with asyncio.timeout(45):
        await _require_iranian_egress()
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, timeout=10000)
            context = await browser.new_context()
            try:
                page = await context.new_page()
                await page.goto("https://utcms.ir/ShowFuelQuota.aspx", wait_until="domcontentloaded", timeout=20000)
                for selector in (
                    "#NationalCode",
                    "#Year",
                    "#Month",
                    "input[name='pelakSelected']",
                    "#pelakFirstLogin",
                    "#pelakComboLogin",
                    "#pelakCenterLogin",
                    "#pelakIrNumLogin",
                    "input[name='QoutaType']",
                    "#imgCapchaEdit1",
                    "#txtCapcha",
                    "#Login",
                ):
                    assert (
                        await page.query_selector(selector) is not None
                    ), f"Missing live fuel form element: {selector}"
            finally:
                await asyncio.wait_for(context.close(), timeout=5)
                await asyncio.wait_for(browser.close(), timeout=5)
