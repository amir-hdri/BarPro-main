"""Playwright automation scraper for fuel quota inquiries on UTCMS using public ShowFuelQuota.aspx page."""

import asyncio
import logging
import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from playwright.async_api import BrowserContext, Page

from app.automation.auth import UTCMSAuthenticator
from app.automation.captcha import get_captcha_provider
from app.core.exceptions import WaybillError
from app.monitoring import (
    track_captcha_attempt,
    track_captcha_failure,
    track_captcha_success,
)

logger = logging.getLogger(__name__)


def parse_plate(plate_number: str) -> dict[str, str]:
    # Normalize digits and text
    norm = plate_number.strip().replace(" ", "").replace("‌", "")
    for index, digit in enumerate("۰۱۲۳۴۵۶۷۸۹"):
        norm = norm.replace(digit, str(index))
    for index, digit in enumerate("٠١٢٣٤٥٦٧٨٩"):
        norm = norm.replace(digit, str(index))
    norm = norm.replace("ایران", "")

    # Match pattern like: 12ب34567
    match = re.fullmatch(r"(\d{2})([^\d]+)(\d{3})(\d{2})", norm)
    if not match:
        raise ValueError(f"فرمت پلاک نامعتبر است: {plate_number}")

    letter_map = {
        "الف": "1", "ب": "2", "ت": "4", "ج": "6", "ح": "8", "د": "10",
        "ژ": "14", "س": "15", "ص": "17", "ط": "19", "ع": "21", "ق": "24",
        "ک": "25", "ل": "27", "م": "28", "ن": "29", "و": "30", "ه": "31",
        "ی": "32"
    }

    char = match.group(2)
    char_val = letter_map.get(char)
    if not char_val:
        raise ValueError(f"حرف پلاک نامعتبر است: {char}")

    return {
        "first": match.group(1),
        "char_val": char_val,
        "center": match.group(3),
        "ir": match.group(4)
    }


def get_current_jalali() -> tuple[int, int]:
    # Determine current Jalali year and month from Gregorian (using Tehran offset)
    tehran_time = datetime.now(UTC) + timedelta(hours=3.5)
    gy, gm, gd = tehran_time.year, tehran_time.month, tehran_time.day

    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 335]
    jy = gy - 621
    g_day_no = 365 * (gy - 1) + (gy - 1) // 4 - (gy - 1) // 100 + (gy - 1) // 400 + g_d_m[gm - 1] + gd
    if gm > 2 and ((gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0):
        g_day_no += 1

    j_day_no = g_day_no - (365 * (jy + 620) + (jy + 620) // 4 - (jy + 620) // 100 + (jy + 620) // 400) - 79
    if j_day_no < 0:
        jy -= 1
        j_day_no += 366 if ((jy % 33) in [1, 5, 9, 13, 17, 22, 26, 30]) else 365

    if j_day_no < 186:
        jm = 1 + j_day_no // 31
    else:
        j_day_no -= 186
        jm = 7 + j_day_no // 30

    return jy, jm


class FuelScraper:
    """Automates fuel quota retrieval from the UTCMS public portal."""

    def __init__(self, page: Page, context: BrowserContext):
        self.page = page
        self.context = context
        self.authenticator = UTCMSAuthenticator(page, context)

    async def scrape_fuel_quota(
        self,
        username: str,
        plate_number: str,
        inquiry_id: int,
    ) -> dict[str, Any]:
        """
        Queries fuel quota on ShowFuelQuota.aspx using driver national code and plate details.
        """
        logger.info(f"Starting fuel quota scrape on ShowFuelQuota.aspx for driver {username} and plate {plate_number}")

        # Parse plate components
        try:
            plate_info = parse_plate(plate_number)
        except Exception as e:
            logger.error(f"Failed to parse plate number {plate_number}: {e}")
            raise WaybillError(f"فرمت پلاک خودرو نامعتبر است: {e}") from e

        # Determine Jalali date
        j_year, j_month = get_current_jalali()
        logger.info(f"Using current Jalali period: {j_year}/{j_month:02d}")

        base_rows = []
        perf_rows = []

        # Pass 1: Query Base Quota (1)
        logger.info("Querying base quota...")
        base_rows = await self._query_quota_type(
            username=username,
            plate_info=plate_info,
            j_year=j_year,
            j_month=j_month,
            quota_type="1",
            inquiry_id=inquiry_id
        )

        # Pass 2: Query Performance Quota (2)
        logger.info("Querying performance quota...")
        perf_rows = await self._query_quota_type(
            username=username,
            plate_info=plate_info,
            j_year=j_year,
            j_month=j_month,
            quota_type="2",
            inquiry_id=inquiry_id
        )

        # Build tables output compatible with frontend schema
        tables_data = []
        headers = ["ردیف", "دوره", "سهمیه (لیتر)"]

        if base_rows:
            tables_data.append({
                "table_index": 0,
                "headers": headers,
                "rows": base_rows
            })

        if perf_rows:
            tables_data.append({
                "table_index": 1,
                "headers": headers,
                "rows": perf_rows
            })

        # Calculate summaries (liter totals)
        def parse_liters(rows_list) -> str:
            total_liters = 0.0
            for r in rows_list:
                if len(r) >= 3:
                    liters_str = r[2].replace(",", "").strip()
                    # Convert Persian digits if any
                    for index, digit in enumerate("۰۱۲۳۴۵۶۷۸۹"):
                        liters_str = liters_str.replace(digit, str(index))
                    try:
                        total_liters += float(liters_str)
                    except ValueError:
                        logger.debug("fuel_liters_parse_failed_skipping", extra={"extra_fields": {"raw": liters_str}})
            return f"{total_liters:.1f}" if total_liters > 0 else ""

        base_quota_sum = parse_liters(base_rows)
        perf_quota_sum = parse_liters(perf_rows)

        # Save screenshot
        screenshots_dir = "app/ui/assets/screenshots"
        os.makedirs(screenshots_dir, exist_ok=True)
        screenshot_filename = f"fuel_inquiry_{inquiry_id}.png"
        screenshot_path = os.path.join(screenshots_dir, screenshot_filename)

        screenshot_url = None
        try:
            await self.page.screenshot(path=screenshot_path, full_page=True)
            screenshot_url = f"/assets/screenshots/{screenshot_filename}"
            logger.info(f"Fuel inquiry screenshot saved to {screenshot_path}")
        except Exception as e:
            logger.error(f"Failed to capture screenshot: {e}")

        quota_data = {
            "tables": tables_data,
            "key_values": {
                "سهمیه پایه": base_quota_sum,
                "سهمیه عملکردی": perf_quota_sum
            },
            "summary": {
                "base_quota": base_quota_sum,
                "performance_quota": perf_quota_sum,
                "card_number": ""
            }
        }

        return {
            "success": True,
            "quota_data": quota_data,
            "screenshot_url": screenshot_url,
        }

    async def _query_quota_type(
        self,
        username: str,
        plate_info: dict[str, str],
        j_year: int,
        j_month: int,
        quota_type: str,
        inquiry_id: int
    ) -> list[list[str]]:
        max_attempts = 4
        url = "https://utcms.ir/ShowFuelQuota.aspx"

        for attempt in range(1, max_attempts + 1):
            logger.info(f"Form submission attempt {attempt} for quota type {quota_type}")
            try:
                # Go to the guest page directly
                await self.page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await self.page.wait_for_load_state("networkidle", timeout=5000)
            except Exception as e:
                logger.warning(f"Timeout loading ShowFuelQuota.aspx on attempt {attempt}: {e}")
                if attempt == max_attempts:
                    raise WaybillError(f"صفحه استعلام سوخت بارگذاری نشد: {e}") from e
                continue

            try:
                # Fill form
                await self.page.fill("#NationalCode", username)
                await self.page.select_option("#Year", str(j_year))
                await self.page.select_option("#Month", str(j_month))

                # Select plate type (mili = value 1)
                await self.page.check("input[name='pelakSelected'][value='1']")

                # Fill plate components
                await self.page.fill("#pelakFirstLogin", plate_info["first"])
                await self.page.select_option("#pelakComboLogin", plate_info["char_val"])
                await self.page.fill("#pelakCenterLogin", plate_info["center"])
                await self.page.fill("#pelakIrNumLogin", plate_info["ir"])

                # Select Quota Type
                await self.page.check(f"input[name='QoutaType'][value='{quota_type}']")

                # Solve Captcha with observability metrics tracking
                solve_start = asyncio.get_running_loop().time()
                track_captcha_attempt("provider", phase="fuel_quota", attempt=attempt)

                try:
                    solved_value, captcha_provider_name = await self._solve_page_captcha()
                except Exception as exc:
                    elapsed = asyncio.get_running_loop().time() - solve_start
                    reason = "solver_error"
                    if isinstance(exc, WaybillError):
                        reason = str(exc) or "captcha_failed"
                    track_captcha_failure(
                        reason,
                        phase="fuel_quota",
                        strategy="provider",
                        latency_seconds=elapsed,
                        attempt=attempt,
                    )
                    raise exc

                await self.page.fill("#txtCapcha", solved_value)

                # Submit
                await self.page.click("#Login")
                await asyncio.sleep(1.0)  # Wait for submission processing

                # Detect result modal or error
                try:
                    # Wait for either result modal or Swall error / validation summary error
                    await self.page.wait_for_selector("#ViewShowFuelQuota, .validation-summary-errors, .alert-danger, .swal2-html-container", timeout=8000)
                except Exception:
                    # Fallback wait
                    await asyncio.sleep(2.0)

                # Check if modal is visible
                modal = await self.page.query_selector("#ViewShowFuelQuota")
                is_modal_visible = modal and await modal.is_visible()

                if is_modal_visible:
                    # Scrape table rows
                    rows = []
                    tbody_rows = await self.page.query_selector_all("#GridBody tr")
                    for tr in tbody_rows:
                        tds = await tr.query_selector_all("td")
                        if tds:
                            row_data = [(await td.inner_text()).strip() for td in tds]
                            if any(row_data):
                                rows.append(row_data)
                    logger.info(f"Successfully scraped {len(rows)} rows of quota data")

                    # Close modal so we can query again
                    close_btn = await self.page.query_selector("#ViewShowFuelQuota button[data-bs-dismiss='modal'], #ViewShowFuelQuota .btn-default")
                    if close_btn:
                        await close_btn.click()
                        await asyncio.sleep(0.5)

                    elapsed = asyncio.get_running_loop().time() - solve_start
                    track_captcha_success(
                        strategy="provider",
                        phase="fuel_quota",
                        latency_seconds=elapsed,
                        attempt=attempt,
                    )
                    return rows

                # Check for errors
                error_msg = None
                for selector in (".validation-summary-errors", ".alert-danger", ".text-danger", ".swal2-html-container"):
                    element = await self.page.query_selector(selector)
                    if element and await element.is_visible():
                        error_msg = (await element.inner_text()).strip()
                        if error_msg:
                            break

                if error_msg:
                    logger.warning(f"Error returned on attempt {attempt}: {error_msg}")
                    elapsed = asyncio.get_running_loop().time() - solve_start
                    if "کد امنیتی" in error_msg or "کپچا" in error_msg or "کد امنیتی صحیح نمی باشد" in error_msg:
                        # Retrying on captcha failure
                        track_captcha_failure(
                            "incorrect_solution",
                            phase="fuel_quota",
                            strategy="provider",
                            latency_seconds=elapsed,
                            attempt=attempt,
                        )
                        continue
                    else:
                        # Non-captcha error (e.g. invalid plate or national code)
                        logger.error(f"Permanent form validation error: {error_msg}")
                        # Captcha was solved correctly, but validation failed on other credentials
                        track_captcha_success(
                            strategy="provider",
                            phase="fuel_quota",
                            latency_seconds=elapsed,
                            attempt=attempt,
                        )
                        # Return empty rows for this quota type if it's not registered
                        return []

            except Exception as e:
                logger.error(f"Exception during quota query attempt {attempt}: {e}")
                if attempt == max_attempts:
                    if isinstance(e, WaybillError):
                        raise e
                    raise WaybillError(f"خطا در پر کردن فرم استعلام سوخت: {e}") from e

        logger.error(f"Failed to solve captcha after {max_attempts} attempts for quota type {quota_type}")
        raise WaybillError(
            f"عدم موفقیت در حل کپچا پس از {max_attempts} تلاش برای سهمیه {quota_type}"
        )

    async def _solve_page_captcha(self) -> tuple[str, str]:
        provider = get_captcha_provider()
        if not provider:
            raise WaybillError("کلاس حل کپچا پیکربندی نشده است")

        captcha_element = await self.page.query_selector("#imgCapchaEdit1")
        if not captcha_element:
            raise WaybillError("تصویر کپچا در صفحه یافت نشد")

        # Capture element screenshot
        image_bytes = await captcha_element.screenshot(type="png")
        import base64
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        # Solve via model
        result = await provider.solve_text_captcha(image_base64)
        if not result.solved or not result.value:
            raise WaybillError(
                result.error or "مدل موفق به حل کپچا نشد"
            )

        return result.value, result.provider
