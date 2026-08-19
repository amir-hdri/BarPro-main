"""Playwright automation scraper for fuel quota inquiries on UTCMS using public ShowFuelQuota.aspx page."""

import asyncio
import hashlib
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from playwright.async_api import BrowserContext, Page

from app.automation.auth import UTCMSAuthenticator
from app.automation.captcha import get_captcha_provider
from app.core.exceptions import ErrorCode, WaybillError
from app.monitoring import (
    track_captcha_attempt,
    track_captcha_failure,
    track_captcha_success,
)

logger = logging.getLogger(__name__)
FUEL_SCREENSHOTS_DIR = Path(os.getenv("FUEL_SCREENSHOTS_DIR", "runtime/screenshots/fuel"))


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
        "الف": "1",
        "ب": "2",
        "ت": "4",
        "ج": "6",
        "ح": "8",
        "د": "10",
        "ژ": "14",
        "س": "15",
        "ص": "17",
        "ط": "19",
        "ع": "21",
        "ق": "24",
        "ک": "25",
        "ل": "27",
        "م": "28",
        "ن": "29",
        "و": "30",
        "ه": "31",
        "ی": "32",
    }

    char = match.group(2)
    char_val = letter_map.get(char)
    if not char_val:
        raise ValueError(f"حرف پلاک نامعتبر است: {char}")

    return {"first": match.group(1), "char_val": char_val, "center": match.group(3), "ir": match.group(4)}


def get_current_jalali() -> tuple[int, int]:
    # Determine current Jalali year and month using the IANA timezone database.
    # A fixed ``+03:30`` offset becomes wrong when the host's tzdata reports a
    # different Tehran offset, which can shift the inquiry period around the
    # month boundary and make time-based CAPTCHA observations misleading.
    tehran_time = datetime.now(UTC).astimezone(ZoneInfo("Asia/Tehran"))
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
        national_code: str,
        plate_number: str,
        inquiry_id: int,
        j_year: int | None = None,
        j_month: int | None = None,
    ) -> dict[str, Any]:
        """
        Queries fuel quota on ShowFuelQuota.aspx using driver national code and plate details.
        """
        logger.info("Starting fuel quota scrape on ShowFuelQuota.aspx for inquiry %s", inquiry_id)

        # Parse plate components
        try:
            plate_info = parse_plate(plate_number)
        except Exception as e:
            logger.error(f"Failed to parse plate number {plate_number}: {e}")
            raise WaybillError(f"فرمت پلاک خودرو نامعتبر است: {e}") from e

        # Determine Jalali date
        if not j_year or not j_month:
            current_y, current_m = get_current_jalali()
            j_year = j_year or current_y
            j_month = j_month or current_m
        logger.info(f"Using Jalali period: {j_year}/{j_month:02d}")

        base_rows = []
        perf_rows = []
        base_error = None
        perf_error = None
        base_screenshot_bytes: bytes | None = None
        perf_screenshot_bytes: bytes | None = None

        # Setup route optimization to block unnecessary assets (fonts, media, non-captcha images)
        async def optimize_routes(p: Page):
            try:
                await p.route(
                    "**/*",
                    lambda route: route.abort()
                    if route.request.resource_type in ["media", "font"]
                    or (
                        route.request.resource_type == "image"
                        and "Cap.aspx" not in route.request.url
                        and "captcha" not in route.request.url.lower()
                    )
                    else route.continue_(),
                )
            except Exception as e:
                logger.debug(f"Could not attach route optimization: {e}")

        await optimize_routes(self.page)

        logger.info("Executing Base Quota and Performance Quota sequentially in single tab...")

        # Step 1: Query Base Quota (QuotaType = 1)
        try:
            logger.info("Querying base quota (Type 1)...")
            base_rows, base_screenshot_bytes = await self._query_quota_type(
                national_code=national_code,
                plate_info=plate_info,
                j_year=j_year,
                j_month=j_month,
                quota_type="1",
                inquiry_id=inquiry_id,
                page=self.page,
                skip_navigation=False,
            )
        except Exception as e:
            base_error = str(e)
            logger.warning(f"Base quota query failed: {e}")

        # Step 2: Query Performance Quota (QuotaType = 2) in-place on same page
        skip_nav_perf = (len(base_rows) > 0)
        try:
            logger.info("Querying performance quota (Type 2) in-place...")
            perf_rows, perf_screenshot_bytes = await self._query_quota_type(
                national_code=national_code,
                plate_info=plate_info,
                j_year=j_year,
                j_month=j_month,
                quota_type="2",
                inquiry_id=inquiry_id,
                page=self.page,
                skip_navigation=skip_nav_perf,
            )
        except Exception as e:
            logger.warning(f"In-place performance quota query failed: {e}. Retrying with fresh page load...")
            try:
                perf_rows, perf_screenshot_bytes = await self._query_quota_type(
                    national_code=national_code,
                    plate_info=plate_info,
                    j_year=j_year,
                    j_month=j_month,
                    quota_type="2",
                    inquiry_id=inquiry_id,
                    page=self.page,
                    skip_navigation=False,
                )
            except Exception as e2:
                perf_error = str(e2)
                logger.warning(f"Performance quota query fallback failed: {e2}")

        # If both failed, raise error
        if not base_rows and not perf_rows:
            err_msg = f"استعلام سوخت ناموفق بود. خطای پایه: {base_error} | خطای عملکردی: {perf_error}"
            logger.error(err_msg)
            raise WaybillError(err_msg)

        # Build tables output compatible with frontend schema
        tables_data = []
        headers = ["ردیف", "دوره", "سهمیه (لیتر)"]

        if base_rows:
            tables_data.append({"table_index": 0, "headers": headers, "rows": base_rows})

        if perf_rows:
            tables_data.append({"table_index": 1, "headers": headers, "rows": perf_rows})

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

        # Handle screenshot
        FUEL_SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        screenshot_filename = f"fuel_inquiry_{inquiry_id}.png"
        screenshot_path = FUEL_SCREENSHOTS_DIR / screenshot_filename

        primary_screenshot_bytes = perf_screenshot_bytes or base_screenshot_bytes
        if not primary_screenshot_bytes:
            try:
                primary_screenshot_bytes = await self.page.screenshot(full_page=False)
            except Exception as e:
                logger.debug(f"Fallback full page screenshot failed: {e}")

        screenshot_url = None
        screenshot_data_uri = None
        if primary_screenshot_bytes:
            try:
                # Save locally for file endpoint / inspection
                with open(screenshot_path, "wb") as f:
                    f.write(primary_screenshot_bytes)
                import base64
                screenshot_data_uri = f"data:image/png;base64,{base64.b64encode(primary_screenshot_bytes).decode('utf-8')}"
                screenshot_url = screenshot_data_uri
                logger.info(f"Fuel inquiry screenshot saved to {screenshot_path} and Data URI created")
            except Exception as e:
                logger.error(f"Failed to save screenshot file or encode base64: {e}")
                screenshot_url = f"/api/v1/fuel-inquiries/{inquiry_id}/screenshot"
        else:
            screenshot_url = f"/api/v1/fuel-inquiries/{inquiry_id}/screenshot"

        quota_data = {
            "tables": tables_data,
            "key_values": {"سهمیه پایه": base_quota_sum, "سهمیه عملکردی": perf_quota_sum},
            "summary": {"base_quota": base_quota_sum, "performance_quota": perf_quota_sum, "card_number": ""},
        }

        return {
            "success": True,
            "quota_data": quota_data,
            "screenshot_url": screenshot_url,
        }

    async def _trigger_and_wait_for_captcha_reload(self, page: Page | None = None):
        """Forces captcha refresh and waits for the image load event to complete."""
        p = page or self.page
        try:
            # 1. Register a load listener in the page context
            await p.evaluate("""() => {
                const img = document.querySelector("#imgCapchaEdit1");
                if (img) {
                    window.captchaLoaded = false;
                    if (window.captchaLoadHandler) {
                        img.removeEventListener('load', window.captchaLoadHandler);
                    }
                    window.captchaLoadHandler = () => {
                        window.captchaLoaded = true;
                    };
                    img.addEventListener('load', window.captchaLoadHandler, { once: true });
                    img.src = "../../Cap.aspx?id=LoginShowFuelQuota&rand=" + Math.random();
                }
            }""")
            logger.info("Forced captcha refresh with random parameter via JS.")

            # 2. Wait reactively for the load event or complete state
            await p.wait_for_function(
                "() => window.captchaLoaded === true || (document.querySelector('#imgCapchaEdit1') && document.querySelector('#imgCapchaEdit1').complete && document.querySelector('#imgCapchaEdit1').naturalWidth > 0)",
                timeout=4000,
            )
            logger.info("Captcha image reload event detected and complete.")
        except Exception as e:
            logger.warning(f"Error/timeout waiting for captcha reload event: {e}")
            await asyncio.sleep(0.3)

    async def _dismiss_error_modal(self, page: Page | None = None):
        p = page or self.page
        try:
            modal = await p.query_selector("#modal-msg-error")
            if modal and await modal.is_visible():
                logger.info("Dismissing visible error modal...")
                close_btn = await modal.query_selector("button:has-text('بستن'), button")
                if close_btn:
                    await close_btn.click()
                    try:
                        await p.wait_for_selector("#modal-msg-error", state="hidden", timeout=1000)
                    except Exception:
                        await asyncio.sleep(0.2)
        except Exception as e:
            logger.warning(f"Error dismissing modal: {e}")

    async def _query_quota_type(
        self,
        national_code: str,
        plate_info: dict[str, str],
        j_year: int,
        j_month: int,
        quota_type: str,
        inquiry_id: int,
        skip_navigation: bool = False,
        page: Page | None = None,
    ) -> tuple[list[list[str]], bytes | None]:
        p = page or self.page
        url = "https://utcms.ir/ShowFuelQuota.aspx"

        if not skip_navigation:
            try:
                logger.info(f"Navigating directly to fuel quota inquiry page: {url}")
                await p.goto(url, wait_until="domcontentloaded", timeout=25000)
                try:
                    await p.wait_for_load_state("networkidle", timeout=3000)
                except Exception:
                    pass
            except Exception as direct_err:
                logger.warning(f"Direct navigation failed: {direct_err}. Trying WAF warmup via homepage...")
                try:
                    await p.goto("https://utcms.ir", wait_until="domcontentloaded", timeout=10000)
                    await asyncio.sleep(0.5)
                except Exception:
                    pass
                try:
                    await p.goto(url, wait_until="domcontentloaded", timeout=35000)
                except Exception as e2:
                    logger.error(f"Failed to load ShowFuelQuota.aspx: {e2}")
                    raise WaybillError(f"صفحه استعلام سوخت بارگذاری نشد: {e2}") from e2

            # Dismiss any initial blank error modal if visible
            await self._dismiss_error_modal(page=p)

            # Wait briefly for dynamically loaded QuotaType radio buttons to appear
            logger.info("Waiting for dynamically loaded QuotaType radio buttons...")
            try:
                await p.wait_for_selector("input[name='QoutaType']", timeout=2000)
            except Exception as e:
                logger.warning(f"Timeout waiting for QuotaType radio inputs, will inject manually: {e}")

            # Dismiss modal again right before filling in case it loaded late
            await self._dismiss_error_modal(page=p)

            # Fill form fields once
            try:
                await p.fill("#NationalCode", national_code)

                # Validate available options in #Year dropdown
                try:
                    y_opts = await p.locator("#Year option").all()
                    available_year_vals = []
                    for y_opt in y_opts:
                        val = await y_opt.get_attribute("value")
                        txt = await y_opt.inner_text()
                        if val:
                            available_year_vals.append(val.strip())
                        if txt:
                            available_year_vals.append(txt.strip())

                    target_y_str = str(j_year)
                    if available_year_vals and target_y_str not in available_year_vals:
                        numeric_years = sorted([int(y) for y in available_year_vals if y.isdigit()])
                        if numeric_years and j_year > numeric_years[-1]:
                            logger.info(
                                f"Requested year {j_year} exceeds max available year {numeric_years[-1]} in UTCMS. Using {numeric_years[-1]}."
                            )
                            target_y_str = str(numeric_years[-1])
                        else:
                            logger.warning(f"Requested year {j_year} not found in UTCMS options: {available_year_vals}")
                            raise WaybillError(
                                f"سال {j_year} در گزینه‌های سامانه سوخت موجود نیست",
                                error_code=ErrorCode.WB_VALIDATION_FAILED,
                            )
                except WaybillError:
                    raise
                except Exception as ex_opt:
                    logger.debug(f"Could not pre-check #Year options: {ex_opt}")

                await p.select_option("#Year", target_y_str)
                await p.select_option("#Month", str(j_month))

                # Select plate type (mili = value 1)
                await p.click("input[name='pelakSelected'][value='1']")
                await p.evaluate("""() => {
                    FreeZoneId = 2;
                    $("input[name='pelakSelected'][value='1']").prop('checked', true);
                    $("#PAddi").show();
                    $("#PAzadType").hide();
                    $("#PAzad").hide();
                }""")
                logger.info("Plate type selected and forced FreeZoneId = 2 via JS")

                # Log the options for debugging
                try:
                    options = await p.locator("#pelakComboLogin option").all()
                    opts_text = []
                    for opt in options:
                        val = await opt.get_attribute("value")
                        text = await opt.inner_text()
                        opts_text.append(f"{text.strip()}:{val}")
                    logger.info("pelakComboLogin OPTIONS: " + " | ".join(opts_text))
                except Exception as e:
                    logger.warning(f"Could not dump options: {e}")

                # Fill plate components
                await p.fill("#pelakFirstLogin", plate_info["first"])
                await p.select_option("#pelakComboLogin", plate_info["char_val"])
                await p.fill("#pelakCenterLogin", plate_info["center"])
                await p.fill("#pelakIrNumLogin", plate_info["ir"])
            except WaybillError:
                raise
            except Exception as e:
                logger.error(f"Error filling form: {e}")
                raise WaybillError(f"خطا در پر کردن فرم استعلام سوخت: {e}") from e

        # Ensure Quota Type radio inputs are loaded by retrying the page's own AJAX function or manual fallback
        try:
            quota_radio = f"input[name='QoutaType'][value='{quota_type}']"

            # Wait for the page's own $(document).ready AJAX call to finish
            try:
                quota_element = await p.wait_for_selector(quota_radio, state="attached", timeout=5000)
            except Exception:
                quota_element = None

            if not quota_element:
                logger.info("QuotaType radio inputs not found in DOM after 5s. Retrying GetQoutaType AJAX call...")
                for load_attempt in range(1, 4):
                    # Dismiss any error modal first
                    await self._dismiss_error_modal(page=p)

                    # Execute page's own GetQoutaType function
                    try:
                        await p.evaluate("GetQoutaType()")
                        # Wait for selector to appear
                        await p.wait_for_selector(quota_radio, timeout=5000)
                        quota_element = await p.query_selector(quota_radio)
                        if quota_element:
                            logger.info(
                                f"Successfully loaded QuotaType radio inputs via GetQoutaType() on attempt {load_attempt}"
                            )
                            # Wait a bit for the DOM to settle after the AJAX callback fully executes
                            await asyncio.sleep(0.5)
                            break
                    except Exception as ex:
                        logger.warning(f"Attempt {load_attempt} to call GetQoutaType() failed: {ex}")
                        await asyncio.sleep(0.5)

            # If still not found, apply manual injection fallback registered with FormValidation
            if not quota_element:
                logger.info(
                    "GetQoutaType AJAX call failed. Applying manual HTML injection fallback with FormValidation registration..."
                )
                inject_js = """
                () => {
                    const box = document.getElementById('QoutaTypeBoxs');
                    if (box) {
                        box.innerHTML = `
                            <div class="radio-inline no-margin no-padding col-md-6 col-xs-6">
                                <div class="radio">
                                    <label>
                                        <input style="margin-right:0px" name="QoutaType" value="1" type="radio" id="quota_base">
                                        <span class="text">سهمیه پایه</span>
                                    </label>
                                </div>
                            </div>
                            <div class="radio-inline no-margin no-padding col-md-6 col-xs-6">
                                <div class="radio">
                                    <label>
                                        <input style="margin-right:0px" name="QoutaType" value="2" type="radio" id="quota_perf">
                                        <span class="text">سهمیه عملکردی</span>
                                    </label>
                                </div>
                            </div>
                        `;
                    }
                    // Register dynamic field with FormValidation instance
                    try {
                        $('#frmMethodOne').formValidation('addField', 'QoutaType');
                    } catch (e) {
                        console.log("Failed to register QoutaType with FormValidation:", e);
                    }
                }
                """
                await p.evaluate(inject_js)
                quota_element = await p.query_selector(quota_radio)

            if quota_element:
                # Force checking using evaluation to bypass any potential modal overlay pointer blocking
                check_js = f"""
                () => {{
                    const el = $('input[name="QoutaType"][value="{quota_type}"]');
                    el.prop('checked', true).trigger('change');
                    try {{
                        $('#frmMethodOne').formValidation('revalidateField', 'QoutaType');
                    }} catch (e) {{
                        console.log("Failed to revalidate QoutaType:", e);
                    }}
                }}
                """
                await p.evaluate(check_js)
                logger.info(f"Checked QuotaType radio with value: {quota_type} via JS")
            else:
                logger.error("Failed to load and check QuotaType radio buttons")
                raise WaybillError("عدم موفقیت در بارگذاری گزینه‌های نوع سهمیه")
        except Exception as e:
            logger.error(f"Error selecting quota type: {e}")
            raise WaybillError(f"خطا در انتخاب نوع سهمیه: {e}") from e

        # Wait to ensure any page load / AJAX error captcha reload is complete before first attempt
        if not skip_navigation:
            try:
                await p.wait_for_function(
                    "() => document.querySelector('#imgCapchaEdit1') && document.querySelector('#imgCapchaEdit1').complete && document.querySelector('#imgCapchaEdit1').naturalWidth > 0",
                    timeout=3000,
                )
            except Exception:
                await asyncio.sleep(0.3)

        # Captcha Solve Loop (in-place retry, no page reload)
        max_attempts = 6
        for attempt in range(1, max_attempts + 1):
            logger.info(f"Captcha attempt {attempt} of {max_attempts} for quota type {quota_type}")

            if attempt > 1:
                # Force refresh using the cache-bypassing reload method
                logger.info("Forcing manual captcha reload to bypass cache...")
                await self._trigger_and_wait_for_captcha_reload(page=p)
            elif skip_navigation:
                # Reusing page from a previous successful query, so trigger a new captcha manually
                logger.info("Reusing page for second quota type. Triggering manual captcha reload...")
                await self._trigger_and_wait_for_captcha_reload(page=p)

            # Solve Captcha
            solve_start = asyncio.get_running_loop().time()
            track_captcha_attempt("provider", phase="fuel_quota", attempt=attempt)

            try:
                solved_value, captcha_provider_name = await self._solve_page_captcha(page=p)
            except Exception as exc:
                elapsed = asyncio.get_running_loop().time() - solve_start
                track_captcha_failure(
                    "solver_error", phase="fuel_quota", strategy="provider", latency_seconds=elapsed, attempt=attempt
                )
                if attempt == max_attempts:
                    raise exc
                continue

            try:
                # Clear and refill captcha
                await p.fill("#txtCapcha", "")
                await p.fill("#txtCapcha", solved_value)
                logger.info(
                    "fuel_captcha_field_filled",
                    extra={"extra_fields": {"provider": captcha_provider_name, "value_len": len(solved_value)}},
                )

                # Double check and dismiss any error modal right before clicking submit
                await self._dismiss_error_modal(page=p)

                # Submit
                await p.click("#Login")
            except Exception as e:
                logger.error(f"Error submitting form on attempt {attempt}: {e}")
                if attempt == max_attempts:
                    raise WaybillError(f"خطا در پر کردن فرم استعلام سوخت: {e}") from e
                continue

            # Detect result modal or error
            try:
                await p.wait_for_selector(
                    "#ViewShowFuelQuota, #modal-msg-success, #modal-msg-error, .validation-summary-errors, .alert-danger",
                    timeout=15000,
                )
            except Exception:
                await asyncio.sleep(0.3)

            # Check if success modal is visible
            success_modal = await p.query_selector("#ViewShowFuelQuota")
            success_msg_modal = await p.query_selector("#modal-msg-success")

            is_success_visible = False
            rows = []
            modal_screenshot_bytes: bytes | None = None

            if success_modal and await success_modal.is_visible():
                is_success_visible = True
                # Scrape table rows (for Performance Quota)
                tbody_rows = await p.query_selector_all("#GridBody tr")
                for tr in tbody_rows:
                    tds = await tr.query_selector_all("td")
                    if tds:
                        row_data = [(await td.inner_text()).strip() for td in tds]
                        if any(row_data):
                            rows.append(row_data)
                logger.info(f"Successfully scraped {len(rows)} rows of quota data")

                # Capture screenshot of the modal content BEFORE closing
                try:
                    modal_content = await p.query_selector("#ViewShowFuelQuota .modal-content")
                    if modal_content and await modal_content.is_visible():
                        modal_screenshot_bytes = await modal_content.screenshot(type="png")
                    else:
                        modal_screenshot_bytes = await p.screenshot(type="png", full_page=False)
                except Exception as e_ss:
                    logger.debug(f"Failed to capture performance modal screenshot: {e_ss}")

                # Close modal
                close_btn = await p.query_selector(
                    "#ViewShowFuelQuota button[data-bs-dismiss='modal'], #ViewShowFuelQuota .btn-default"
                )
                if close_btn:
                    await close_btn.click()
                    try:
                        await p.wait_for_selector("#ViewShowFuelQuota", state="hidden", timeout=1000)
                    except Exception:
                        await asyncio.sleep(0.2)

            elif success_msg_modal and await success_msg_modal.is_visible():
                is_success_visible = True
                # Scrape text from success msg modal (for Base Quota)
                body_elem = await success_msg_modal.query_selector(".modal-body")
                msg_text = ""
                if body_elem:
                    msg_text = (await body_elem.inner_text()).strip()
                logger.info(f"Base Quota success message: {msg_text}")

                # Parse the quota value from message text (normalizing Persian/Arabic digits)
                import re

                norm_text = msg_text
                for idx, digit in enumerate("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩"):
                    norm_text = norm_text.replace(digit, str(idx % 10))

                num_match = re.search(r"(\d[\d,.]*)", norm_text)
                quota_val = num_match.group(1).replace(",", "") if num_match else "0"

                # Construct a synthetic row matching the table schema
                rows = [["1", "دوره جاری", quota_val]]

                # Capture screenshot of the modal content BEFORE closing
                try:
                    modal_content = await p.query_selector("#modal-msg-success .modal-content")
                    if modal_content and await modal_content.is_visible():
                        modal_screenshot_bytes = await modal_content.screenshot(type="png")
                    else:
                        modal_screenshot_bytes = await p.screenshot(type="png", full_page=False)
                except Exception as e_ss:
                    logger.debug(f"Failed to capture base modal screenshot: {e_ss}")

                # Close modal
                close_btn = await success_msg_modal.query_selector("button:has-text('بستن'), button")
                if close_btn:
                    await close_btn.click()
                    try:
                        await p.wait_for_selector("#modal-msg-success", state="hidden", timeout=1000)
                    except Exception:
                        await asyncio.sleep(0.2)

            if is_success_visible:
                elapsed = asyncio.get_running_loop().time() - solve_start
                track_captcha_success(strategy="provider", phase="fuel_quota", latency_seconds=elapsed, attempt=attempt)
                return rows, modal_screenshot_bytes

            # Check for errors
            error_msg = None
            for selector in ("#modal-msg-error", ".validation-summary-errors", ".alert-danger", ".text-danger"):
                element = await p.query_selector(selector)
                if element and await element.is_visible():
                    error_msg = (await element.inner_text()).strip()
                    if error_msg:
                        break

            if error_msg:
                logger.warning(f"Error returned on captcha attempt {attempt}: {error_msg}")
                elapsed = asyncio.get_running_loop().time() - solve_start

                # Check if it is a captcha-related error or a transient system error
                is_captcha_err = (
                    "کد امنیتی" in error_msg
                    or "کپچا" in error_msg
                    or "صحیح نمی باشد" in error_msg
                    or "اشتباه" in error_msg
                )
                is_transient_sys_err = (
                    "خطا در سامانه" in error_msg or "خطای نامشخص" in error_msg or "سیستم" in error_msg
                )

                if is_captcha_err or is_transient_sys_err:
                    track_captcha_failure(
                        "incorrect_solution" if is_captcha_err else "transient_system_error",
                        phase="fuel_quota",
                        strategy="provider",
                        latency_seconds=elapsed,
                        attempt=attempt,
                    )

                    # Dismiss the error modal so we can click refresh in the next loop
                    await self._dismiss_error_modal(page=p)
                    continue
                else:
                    # Permanent credential validation error
                    logger.error(f"Permanent validation error: {error_msg}")
                    raise WaybillError(error_msg)

        logger.error(f"Failed to solve captcha after {max_attempts} attempts for quota type {quota_type}")
        raise WaybillError(f"عدم موفقیت در حل کپچا پس از {max_attempts} تلاش برای سهمیه {quota_type}")

    async def _solve_page_captcha(self, page: Page | None = None) -> tuple[str, str]:
        p = page or self.page
        provider = get_captcha_provider()
        if not provider:
            raise WaybillError("کلاس حل کپچا پیکربندی نشده است")

        # Bypass CnnCaptchaProvider for the fuel page as it only solves math digits
        from app.automation.captcha import CnnCaptchaProvider, CompositeCaptchaProvider

        if isinstance(provider, CompositeCaptchaProvider):
            fuel_providers = [p_obj for p_obj in provider.providers if not isinstance(p_obj, CnnCaptchaProvider)]
            provider = CompositeCaptchaProvider(fuel_providers)

        captcha_element = await p.query_selector("#imgCapchaEdit1")
        if not captcha_element:
            raise WaybillError("تصویر کپچا در صفحه یافت نشد")

        # Extract original image bytes via HTML5 Canvas to avoid CSS scale/border distortion
        js_code = """
        () => {
            const img = document.querySelector("#imgCapchaEdit1");
            if (!img || !img.complete || img.naturalWidth === 0) return null;
            const canvas = document.createElement("canvas");
            canvas.width = img.naturalWidth;
            canvas.height = img.naturalHeight;
            const ctx = canvas.getContext("2d");
            ctx.drawImage(img, 0, 0);
            return canvas.toDataURL("image/png");
        }
        """
        try:
            data_url = await p.evaluate(js_code)
            if not data_url or "," not in data_url:
                raise ValueError("Canvas returned empty or invalid data url (image might not be loaded)")
            import base64

            image_bytes = base64.b64decode(data_url.split(",", 1)[1])
            logger.info("Successfully extracted captcha image via HTML5 canvas.")
        except Exception as e:
            logger.warning(f"Failed to extract captcha via canvas: {e}. Falling back to element screenshot.")
            await asyncio.sleep(0.5)
            image_bytes = await captcha_element.screenshot(type="png")

        try:
            import os

            scratch_dir = os.path.join(os.getcwd(), "scratch")
            os.makedirs(scratch_dir, exist_ok=True)
            with open(os.path.join(scratch_dir, "fuel_last_captcha.png"), "wb") as f:
                f.write(image_bytes)
        except Exception as exc:
            logger.debug(
                "fuel_scraper_captcha_artifacts_failed",
                extra={"extra_fields": {"error": str(exc)}},
            )
        import base64

        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        try:
            image_shape = await captcha_element.evaluate(
                "el => ({naturalWidth: el.naturalWidth || 0, naturalHeight: el.naturalHeight || 0})"
            )
        except Exception:
            image_shape = {"naturalWidth": 0, "naturalHeight": 0}
        logger.info(
            "utcms_fuel_captcha_signature",
            extra={
                "extra_fields": {
                    "selector": "#imgCapchaEdit1",
                    "image_bytes": len(image_bytes),
                    "natural_width": int(image_shape.get("naturalWidth") or 0),
                    "natural_height": int(image_shape.get("naturalHeight") or 0),
                    "image_digest": hashlib.sha256(image_bytes).hexdigest()[:12],
                }
            },
        )
        # Solve via model
        result = await provider.solve_text_captcha(image_base64)
        if not result.solved or not result.value:
            raise WaybillError(result.error or "مدل موفق به حل کپچا نشد")

        return result.value, result.provider

