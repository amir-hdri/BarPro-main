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
        j_year: int | None = None,
        j_month: int | None = None,
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
        if not j_year or not j_month:
            current_y, current_m = get_current_jalali()
            j_year = j_year or current_y
            j_month = j_month or current_m
        logger.info(f"Using Jalali period: {j_year}/{j_month:02d}")

        base_rows = []
        perf_rows = []
        base_error = None
        perf_error = None

        # Pass 1: Query Base Quota (1)
        logger.info("Querying base quota...")
        try:
            base_rows = await self._query_quota_type(
                username=username,
                plate_info=plate_info,
                j_year=j_year,
                j_month=j_month,
                quota_type="1",
                inquiry_id=inquiry_id,
            )
        except Exception as e:
            base_error = str(e)
            logger.warning(f"Base quota query failed: {e}")

        # Pass 2: Query Performance Quota (2)
        logger.info("Querying performance quota...")
        # If base query succeeded, we can reuse the page context and skip initial navigation
        skip_nav_perf = len(base_rows) > 0
        try:
            perf_rows = await self._query_quota_type(
                username=username,
                plate_info=plate_info,
                j_year=j_year,
                j_month=j_month,
                quota_type="2",
                inquiry_id=inquiry_id,
                skip_navigation=skip_nav_perf,
            )
        except Exception as e:
            logger.warning(
                f"Optimized performance quota query failed or skipped: {e}. Falling back to full page load query."
            )
            try:
                perf_rows = await self._query_quota_type(
                    username=username,
                    plate_info=plate_info,
                    j_year=j_year,
                    j_month=j_month,
                    quota_type="2",
                    inquiry_id=inquiry_id,
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
            "key_values": {"سهمیه پایه": base_quota_sum, "سهمیه عملکردی": perf_quota_sum},
            "summary": {"base_quota": base_quota_sum, "performance_quota": perf_quota_sum, "card_number": ""},
        }

        return {
            "success": True,
            "quota_data": quota_data,
            "screenshot_url": screenshot_url,
        }

    async def _trigger_and_wait_for_captcha_reload(self):
        """Forces captcha refresh and waits for the image load event to complete."""
        try:
            # 1. Register a load listener in the page context
            await self.page.evaluate(
                """() => {
                const img = document.querySelector("#imgCapchaEdit1");
                if (img) {
                    window.captchaLoaded = false;
                    // Remove any old listener if we saved it, or just add a clean one
                    if (window.captchaLoadHandler) {
                        img.removeEventListener('load', window.captchaLoadHandler);
                    }
                    window.captchaLoadHandler = () => {
                        window.captchaLoaded = true;
                    };
                    img.addEventListener('load', window.captchaLoadHandler, { once: true });

                    // Force refresh by appending random query parameter to bypass cache
                    img.src = "../../Cap.aspx?id=LoginShowFuelQuota&rand=" + Math.random();
                }
            }"""
            )
            logger.info("Forced captcha refresh with random parameter via JS.")

            # 2. Wait for the load event to fire
            await self.page.wait_for_function("() => window.captchaLoaded === true", timeout=6000)
            logger.info("Captcha image reload event detected and complete.")
        except Exception as e:
            logger.warning(f"Error/timeout waiting for captcha reload event: {e}")
            # Fallback: sleep to let it paint
            await asyncio.sleep(2.0)

    async def _dismiss_error_modal(self):
        try:
            modal = await self.page.query_selector("#modal-msg-error")
            if modal and await modal.is_visible():
                logger.info("Dismissing visible error modal...")
                close_btn = await modal.query_selector("button:has-text('بستن'), button")
                if close_btn:
                    await close_btn.click()
                    await asyncio.sleep(0.8)
        except Exception as e:
            logger.warning(f"Error dismissing modal: {e}")

    async def _query_quota_type(
        self,
        username: str,
        plate_info: dict[str, str],
        j_year: int,
        j_month: int,
        quota_type: str,
        inquiry_id: int,
        skip_navigation: bool = False,
    ) -> list[list[str]]:
        url = "https://utcms.ir/ShowFuelQuota.aspx"

        if not skip_navigation:
            # Load page once
            try:
                await self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(1.0)
                try:
                    await self.page.wait_for_load_state("networkidle", timeout=6000)
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Failed to load ShowFuelQuota.aspx: {e}")
                raise WaybillError(f"صفحه استعلام سوخت بارگذاری نشد: {e}") from e

            # Dismiss any initial blank error modal if visible
            await self._dismiss_error_modal()

            # Wait briefly for dynamically loaded QuotaType radio buttons to appear
            logger.info("Waiting for dynamically loaded QuotaType radio buttons...")
            try:
                await self.page.wait_for_selector("input[name='QoutaType']", timeout=2000)
            except Exception as e:
                logger.warning(f"Timeout waiting for QuotaType radio inputs, will inject manually: {e}")

            # Dismiss modal again right before filling in case it loaded late
            await self._dismiss_error_modal()

            # Fill form fields once
            try:
                await self.page.fill("#NationalCode", username)
                await self.page.select_option("#Year", str(j_year))
                await self.page.select_option("#Month", str(j_month))

                # Select plate type (mili = value 1)
                await self.page.click("input[name='pelakSelected'][value='1']")
                await self.page.evaluate(
                    """() => {
                    FreeZoneId = 2;
                    $("input[name='pelakSelected'][value='1']").prop('checked', true);
                    $("#PAddi").show();
                    $("#PAzadType").hide();
                    $("#PAzad").hide();
                }"""
                )
                logger.info("Plate type selected and forced FreeZoneId = 2 via JS")

                # Fill plate components
                await self.page.fill("#pelakFirstLogin", plate_info["first"])
                await self.page.select_option("#pelakComboLogin", plate_info["char_val"])
                await self.page.fill("#pelakCenterLogin", plate_info["center"])
                await self.page.fill("#pelakIrNumLogin", plate_info["ir"])
            except Exception as e:
                logger.error(f"Error filling form: {e}")
                raise WaybillError(f"خطا در پر کردن فرم استعلام سوخت: {e}") from e

        # Ensure Quota Type radio inputs are loaded by retrying the page's own AJAX function or manual fallback
        try:
            quota_radio = f"input[name='QoutaType'][value='{quota_type}']"
            quota_element = await self.page.query_selector(quota_radio)
            if not quota_element:
                logger.info("QuotaType radio inputs not found in DOM. Retrying GetQoutaType AJAX call...")
                for load_attempt in range(1, 4):
                    # Dismiss any error modal first
                    try:
                        modal = await self.page.query_selector("#modal-msg-error")
                        if modal and await modal.is_visible():
                            close_btn = await modal.query_selector("button:has-text('بستن'), button")
                            if close_btn:
                                await close_btn.click()
                                await asyncio.sleep(0.5)
                    except Exception:
                        pass

                    # Execute page's own GetQoutaType function
                    try:
                        await self.page.evaluate("GetQoutaType()")
                        # Wait for selector to appear
                        await self.page.wait_for_selector(quota_radio, timeout=3000)
                        quota_element = await self.page.query_selector(quota_radio)
                        if quota_element:
                            logger.info(
                                f"Successfully loaded QuotaType radio inputs via GetQoutaType() on attempt {load_attempt}"
                            )
                            break
                    except Exception as ex:
                        logger.warning(f"Attempt {load_attempt} to call GetQoutaType() failed: {ex}")
                        await asyncio.sleep(1.0)

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
                await self.page.evaluate(inject_js)
                quota_element = await self.page.query_selector(quota_radio)

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
                await self.page.evaluate(check_js)
                logger.info(f"Checked QuotaType radio with value: {quota_type} via JS")
            else:
                logger.error("Failed to load and check QuotaType radio buttons")
                raise WaybillError("عدم موفقیت در بارگذاری گزینه‌های نوع سهمیه")
        except Exception as e:
            logger.error(f"Error selecting quota type: {e}")
            raise WaybillError(f"خطا در انتخاب نوع سهمیه: {e}") from e

        # Wait to ensure any page load / AJAX error captcha reload is complete before first attempt
        if not skip_navigation:
            logger.info("Waiting for initial page load captcha reload to stabilize...")
            await asyncio.sleep(2.0)

        # Captcha Solve Loop (in-place retry, no page reload)
        max_attempts = 4
        for attempt in range(1, max_attempts + 1):
            logger.info(f"Captcha attempt {attempt} of {max_attempts} for quota type {quota_type}")

            if attempt > 1:
                # Force refresh using the cache-bypassing reload method
                logger.info("Forcing manual captcha reload to bypass cache...")
                await self._trigger_and_wait_for_captcha_reload()
            elif skip_navigation:
                # Reusing page from a previous successful query, so trigger a new captcha manually
                logger.info("Reusing page for second quota type. Triggering manual captcha reload...")
                await self._trigger_and_wait_for_captcha_reload()

            # Solve Captcha
            solve_start = asyncio.get_running_loop().time()
            track_captcha_attempt("provider", phase="fuel_quota", attempt=attempt)

            try:
                solved_value, captcha_provider_name = await self._solve_page_captcha()
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
                await self.page.fill("#txtCapcha", "")
                await self.page.fill("#txtCapcha", solved_value)
                logger.info(f"Filled captcha field with solved value: {solved_value}")

                # Double check and dismiss any error modal right before clicking submit
                modal = await self.page.query_selector("#modal-msg-error")
                if modal and await modal.is_visible():
                    logger.info("Modal detected right before submit, dismissing it.")
                    close_btn = await modal.query_selector("button:has-text('بستن'), button")
                    if close_btn:
                        await close_btn.click()
                        await asyncio.sleep(0.8)

                # Submit
                await self.page.click("#Login")
                await asyncio.sleep(3.0)  # Wait for submission processing
            except Exception as e:
                logger.error(f"Error submitting form on attempt {attempt}: {e}")
                if attempt == max_attempts:
                    raise WaybillError(f"خطا در پر کردن فرم استعلام سوخت: {e}") from e
                continue

            # Detect result modal or error
            try:
                await self.page.wait_for_selector(
                    "#ViewShowFuelQuota, #modal-msg-success, #modal-msg-error, .validation-summary-errors, .alert-danger",
                    timeout=20000,
                )
            except Exception:
                await asyncio.sleep(1.0)

            # Save screenshot for debugging
            try:
                scratch_dir = os.path.join(os.getcwd(), "scratch")
                os.makedirs(scratch_dir, exist_ok=True)
                await self.page.screenshot(path=os.path.join(scratch_dir, f"attempt_{attempt}_result.png"))
                logger.info(f"Saved attempt {attempt} screenshot for debugging.")
            except Exception as e:
                logger.warning(f"Failed to save debug screenshot: {e}")

            # Check if success modal is visible
            success_modal = await self.page.query_selector("#ViewShowFuelQuota")
            success_msg_modal = await self.page.query_selector("#modal-msg-success")

            is_success_visible = False
            rows = []

            if success_modal and await success_modal.is_visible():
                is_success_visible = True
                # Scrape table rows (for Performance Quota)
                tbody_rows = await self.page.query_selector_all("#GridBody tr")
                for tr in tbody_rows:
                    tds = await tr.query_selector_all("td")
                    if tds:
                        row_data = [(await td.inner_text()).strip() for td in tds]
                        if any(row_data):
                            rows.append(row_data)
                logger.info(f"Successfully scraped {len(rows)} rows of quota data")

                # Close modal
                close_btn = await self.page.query_selector(
                    "#ViewShowFuelQuota button[data-bs-dismiss='modal'], #ViewShowFuelQuota .btn-default"
                )
                if close_btn:
                    await close_btn.click()
                    await asyncio.sleep(0.5)

            elif success_msg_modal and await success_msg_modal.is_visible():
                is_success_visible = True
                # Scrape text from success msg modal (for Base Quota)
                body_elem = await success_msg_modal.query_selector(".modal-body")
                msg_text = ""
                if body_elem:
                    msg_text = (await body_elem.inner_text()).strip()
                logger.info(f"Base Quota success message: {msg_text}")

                # Parse the quota value from message text
                import re

                digits = re.findall(r"\d+", msg_text)
                quota_val = digits[0] if digits else "0"

                # Construct a synthetic row matching the table schema
                rows = [["1", "دوره جاری", quota_val]]

                # Close modal
                close_btn = await success_msg_modal.query_selector("button:has-text('بستن'), button")
                if close_btn:
                    await close_btn.click()
                    await asyncio.sleep(0.5)

            if is_success_visible:
                elapsed = asyncio.get_running_loop().time() - solve_start
                track_captcha_success(strategy="provider", phase="fuel_quota", latency_seconds=elapsed, attempt=attempt)
                return rows

            # Check for errors
            error_msg = None
            for selector in ("#modal-msg-error", ".validation-summary-errors", ".alert-danger", ".text-danger"):
                element = await self.page.query_selector(selector)
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
                    try:
                        modal = await self.page.query_selector("#modal-msg-error")
                        if modal and await modal.is_visible():
                            close_btn = await modal.query_selector("button:has-text('بستن'), button")
                            if close_btn:
                                await close_btn.click()
                                await asyncio.sleep(0.8)
                    except Exception as close_err:
                        logger.warning(f"Failed to close error modal: {close_err}")
                    continue
                else:
                    # Permanent credential validation error
                    logger.error(f"Permanent validation error: {error_msg}")
                    raise WaybillError(error_msg)

        logger.error(f"Failed to solve captcha after {max_attempts} attempts for quota type {quota_type}")
        raise WaybillError(f"عدم موفقیت در حل کپچا پس از {max_attempts} تلاش برای سهمیه {quota_type}")

    async def _solve_page_captcha(self) -> tuple[str, str]:
        provider = get_captcha_provider()
        if not provider:
            raise WaybillError("کلاس حل کپچا پیکربندی نشده است")

        # Bypass CnnCaptchaProvider for the fuel page as it only solves math digits
        from app.automation.captcha import CnnCaptchaProvider, CompositeCaptchaProvider

        if isinstance(provider, CompositeCaptchaProvider):
            fuel_providers = [p for p in provider.providers if not isinstance(p, CnnCaptchaProvider)]
            provider = CompositeCaptchaProvider(fuel_providers)

        captcha_element = await self.page.query_selector("#imgCapchaEdit1")
        if not captcha_element:
            raise WaybillError("تصویر کپچا در صفحه یافت نشد")

        # Extract original image bytes via HTML5 Canvas to avoid CSS scale/border distortion
        js_code = """
        () => {
            const img = document.querySelector("#imgCapchaEdit1");
            if (!img) return null;
            const canvas = document.createElement("canvas");
            canvas.width = img.naturalWidth || 300;
            canvas.height = img.naturalHeight || 40;
            const ctx = canvas.getContext("2d");
            ctx.drawImage(img, 0, 0);
            return canvas.toDataURL("image/png");
        }
        """
        try:
            data_url = await self.page.evaluate(js_code)
            if not data_url or "," not in data_url:
                raise ValueError("Canvas returned empty or invalid data url")
            import base64

            image_bytes = base64.b64decode(data_url.split(",", 1)[1])
            logger.info("Successfully extracted captcha image via HTML5 canvas.")
        except Exception as e:
            logger.warning(f"Failed to extract captcha via canvas: {e}. Falling back to element screenshot.")
            image_bytes = await captcha_element.screenshot(type="png")

        try:
            import os

            scratch_dir = os.path.join(os.getcwd(), "scratch")
            os.makedirs(scratch_dir, exist_ok=True)
            with open(os.path.join(scratch_dir, "fuel_last_captcha.png"), "wb") as f:
                f.write(image_bytes)
        except Exception:
            pass
        import base64

        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        # Solve via model
        result = await provider.solve_text_captcha(image_base64)
        if not result.solved or not result.value:
            raise WaybillError(result.error or "مدل موفق به حل کپچا نشد")

        return result.value, result.provider
