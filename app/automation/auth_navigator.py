"""Navigation and page-state detection for UTCMS authentication.

Provides AuthNavigator — the class responsible for every browser-level
interaction that does *not* belong to core CAPTCHA solving logic:
  - URL navigation with retry
  - Login page detection
  - Error page detection
  - Login-form element discovery
  - Post-login modal handling (rules acceptance)
  - Multi-factor authentication flow
  - Checkbox / iframe captcha detection
  - CAPTCHA image fingerprinting and refresh
  - Math-captcha hint text extraction from the DOM
  - Generic input-field fill with event dispatch
"""

import asyncio
import logging
import random
from collections.abc import Iterable

from playwright.async_api import BrowserContext, Page

from app.automation.auth_utils import (
    hint_candidates_from_text,
    is_authenticated_url,
    is_captcha_related_error,
    is_credential_related_error,
    is_login_url,
)
from app.automation.selectors import AuthSelectors
from app.bot.core.smart_locator import SmartLocator
from app.core.config import utcms_config
from app.core.network import is_retryable_network_error
from app.core.utils import resolve_maybe_awaitable

logger = logging.getLogger(__name__)


class AuthNavigator:
    """Browser-navigation and page-state detection for the UTCMS login flow.

    Every method operates on the ``page`` and ``context`` references passed
    at construction time.  The class deliberately holds **no** domain logic
    related to credential or captcha-value management — those belong in
    ``UTCMSAuthenticator`` (``auth.py``).
    """

    def __init__(self, page: Page, context: BrowserContext, smart_locator: SmartLocator):
        self.page = page
        self.context = context
        self.smart_locator = smart_locator

    # ------------------------------------------------------------------
    # Low-level page helpers
    # ------------------------------------------------------------------

    async def current_url(self) -> str:
        raw_url = getattr(self.page, "url", "")
        try:
            url_value = await resolve_maybe_awaitable(raw_url)
        except Exception:
            return ""
        if url_value is None:
            return ""
        return url_value if isinstance(url_value, str) else str(url_value)

    async def as_clean_text(self, value) -> str:
        try:
            resolved = await resolve_maybe_awaitable(value)
        except Exception:
            return ""
        if resolved is None:
            return ""
        return (resolved if isinstance(resolved, str) else str(resolved)).strip()

    async def goto_with_retry(self, url: str, wait_until: str = "domcontentloaded") -> None:
        attempts = max(1, utcms_config.PAGE_GOTO_MAX_RETRIES + 1)
        base_delay = max(0.1, utcms_config.PAGE_GOTO_RETRY_BASE_SECONDS)
        jitter = max(0.0, utcms_config.PAGE_GOTO_RETRY_JITTER_SECONDS)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                try:
                    await self.page.goto(url, wait_until=wait_until, timeout=utcms_config.PAGE_NAVIGATION_TIMEOUT)
                except Exception as goto_err:
                    if "timeout" in str(goto_err).lower():
                        try:
                            ready_state = await self.page.evaluate("document.readyState")
                            if ready_state in ("interactive", "complete"):
                                logger.warning(f"goto reached readyState '{ready_state}' despite timeout: {goto_err}")
                                return
                        except Exception as exc:
                            logger.debug(
                                "auth_navigator_readystate_check_failed",
                                extra={"extra_fields": {"error": str(exc)}},
                            )
                    raise goto_err
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=10000)
                except Exception as exc:
                    logger.debug(
                        "auth_navigator_domcontentloaded_timeout",
                        extra={"extra_fields": {"error": str(exc)}},
                    )
                return
            except Exception as exc:
                last_error = exc
                if attempt >= attempts or not is_retryable_network_error(exc):
                    raise
                delay = (base_delay * (2 ** (attempt - 1))) + random.uniform(0, jitter)
                await asyncio.sleep(delay)
        if last_error:
            raise last_error

    async def find_selector(
        self,
        selectors: Iterable[str],
        visible: bool = False,
        timeout: int = 3000,
    ) -> str | None:
        for selector in selectors:
            try:
                locator = await self.smart_locator.locate(self.page, [selector], timeout=timeout)
                if locator:
                    return selector
            except Exception:
                continue
        return None

    # ------------------------------------------------------------------
    # Login-URL / page detection
    # ------------------------------------------------------------------

    def candidate_login_urls(self, override_login_url: str | None = None) -> list[str]:
        base_url = utcms_config.BASE_URL.rstrip("/")
        candidates: list[str] = []
        if override_login_url:
            candidates.append(override_login_url.strip())
        candidates.append(utcms_config.LOGIN_URL.strip())
        candidates.extend(f"{base_url}{path}" for path in AuthSelectors.LOGIN_PATH_CANDIDATES)
        unique: list[str] = []
        for c in candidates:
            if c and c not in unique:
                unique.append(c)
        return unique

    async def looks_like_login_page(self) -> bool:
        if is_login_url(await self.current_url()):
            return True
        username_selector = await self.find_selector(AuthSelectors.USERNAME_SELECTORS)
        password_selector = await self.find_selector(AuthSelectors.PASSWORD_SELECTORS)
        submit_selector = await self.find_selector(AuthSelectors.SUBMIT_SELECTORS)
        return bool(username_selector and password_selector and submit_selector)

    async def looks_like_error_page(self) -> bool:
        title = await self.as_clean_text(await self.page.title())
        if "خطا" in title or "یافت نشد" in title or "error" in title.lower():
            return True
        current_url = (await self.current_url()).strip().lower()
        if any(f in current_url for f in ("/error", "/exception", "/fault")):
            return True
        not_found_markers = (
            "text=خطا در سامانه",
            "text=متاسفانه در هنگام پردازش درخواست شما خطایی رخ داده است",
            "text=صفحه مورد نظر شما یافت نشد",
            "text=درخواست مجاز نمی باشد",
            "text=ورود مجدد به سامانه",
        )
        for marker in not_found_markers:
            try:
                await self.smart_locator.locate(self.page, [marker], timeout=500)
                return True
            except Exception:
                continue
        try:
            body_text = await self.as_clean_text(await self.page.text_content("body"))
        except Exception:
            body_text = ""
        lowered_body = body_text.lower()
        return any(
            marker in lowered_body
            for marker in (
                "خطا در سامانه",
                "متاسفانه در هنگام پردازش درخواست شما خطایی رخ داده است",
                "ورود مجدد به سامانه",
                "بازگشت به خانه",
            )
        )

    async def extract_login_error(self) -> str | None:
        for selector in AuthSelectors.LOGIN_ERROR_SELECTORS:
            try:
                element = await self.smart_locator.locate(self.page, [selector], timeout=600)
                text = await self.as_clean_text(await element.text_content())
                if text:
                    return text
            except Exception:
                continue
        return None

    async def wait_for_loading_overlays_to_disappear(self, timeout_ms: int = 15000) -> None:
        """Wait for Iranian government style 'لطفا صبر کنید' or other loading masks to disappear."""
        js_check = """
        () => {
            const selectors = [
                ".loading", ".spinner", ".k-loading-mask", ".k-loading-image", ".k-loading-color",
                "#loading", "#loading-box", ".loading-overlay", ".loading-mask", "div.modal-backdrop",
                ".blockUI", ".blockMsg", ".blockPage"
            ];
            for (const sel of selectors) {
                try {
                    const els = document.querySelectorAll(sel);
                    for (const el of els) {
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        if (style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0) {
                            return true;
                        }
                    }
                } catch (e) {}
            }
            try {
                const xpathResult = document.evaluate(
                    "//div[contains(., 'لطفا صبر کنید') or contains(., 'در حال بارگذاری')]",
                    document,
                    null,
                    XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
                    null
                );
                for (let i = 0; i < xpathResult.snapshotLength; i++) {
                    const el = xpathResult.snapshotItem(i);
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    if (style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0) {
                        return true;
                    }
                }
            } catch (e) {}
            return false;
        }
        """
        js_remove_overlays = """
        () => {
            const selectors = [
                ".loading", ".spinner", ".k-loading-mask", ".k-loading-image", ".k-loading-color",
                "#loading", "#loading-box", ".loading-overlay", ".loading-mask", "div.modal-backdrop",
                ".blockUI", ".blockMsg", ".blockPage"
            ];
            let removed = 0;
            for (const sel of selectors) {
                try {
                    const els = document.querySelectorAll(sel);
                    for (const el of els) {
                        try {
                            el.style.display = 'none';
                            el.style.visibility = 'hidden';
                            el.remove();
                            removed++;
                        } catch (e) {}
                    }
                } catch (e) {}
            }
            return removed;
        }
        """
        deadline = asyncio.get_running_loop().time() + (timeout_ms / 1000)
        removal_attempted = False
        while asyncio.get_running_loop().time() < deadline:
            try:
                found_any = await self.page.evaluate(js_check)
            except Exception:
                found_any = False

            if not found_any:
                return

            # If we've been waiting for more than 50% of the timeout, try to remove overlays
            remaining_time_ms = (deadline - asyncio.get_running_loop().time()) * 1000
            if not removal_attempted and remaining_time_ms < (timeout_ms * 0.5):
                try:
                    removed_count = await self.page.evaluate(js_remove_overlays)
                    if removed_count > 0:
                        logger.warning(
                            "auth_loading_overlay_force_removed",
                            extra={"extra_fields": {"removed_count": removed_count, "action": "removed_via_js"}},
                        )
                except Exception as exc:
                    logger.debug(
                        "auth_loading_overlay_js_cleanup_failed",
                        extra={"extra_fields": {"error": str(exc)}},
                    )
                removal_attempted = True

            await asyncio.sleep(0.08)

        logger.warning(
            "auth_loading_overlay_timeout",
            extra={"extra_fields": {"timeout_ms": timeout_ms, "action": "continuing_despite_overlay"}},
        )

    # ------------------------------------------------------------------
    # Login result polling & post-login steps
    # ------------------------------------------------------------------

    async def wait_for_login_result(self, timeout_ms: int = 35000) -> bool:
        """Wait for login to complete by monitoring page state changes.

        Detection strategies (in order of reliability):
        1. Logout button visible → logged in
        2. URL changed away from login URL → redirect succeeded
        3. Authenticated URL pattern → logged in
        4. Waybill or authenticated page markers found → logged in
        5. Login error message appeared → failed
        Falls back to final state check after timeout.
        """
        deadline = asyncio.get_running_loop().time() + (timeout_ms / 1000)
        poll_interval = 0.08

        while asyncio.get_running_loop().time() < deadline:
            # Strategy 1: Logout button (most reliable signal)
            if await self.find_selector(AuthSelectors.LOGOUT_SELECTORS, visible=True, timeout=400):
                return True

            current_url = await self.current_url()

            # Strategy 2: URL navigated away from login page — wait for it to settle
            if current_url and not is_login_url(current_url):
                if is_authenticated_url(current_url):
                    return True
                # Give the page a moment to finish loading after redirect
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=3000)
                except Exception as exc:
                    logger.debug(
                        "auth_navigator_post_login_wait_timeout",
                        extra={"extra_fields": {"error": str(exc)}},
                    )
                # Re-check URL after load
                current_url = await self.current_url()
                if current_url and not is_login_url(current_url):
                    return True

            # Strategy 3: Waybill/authenticated page markers
            if await self.find_selector(AuthSelectors.WAYBILL_FORM_MARKERS, timeout=300):
                return True
            if await self.find_selector(AuthSelectors.AUTHENTICATED_PAGE_MARKERS, timeout=300):
                return True

            # Strategy 4: Explicit login error in the page
            login_error = await self.extract_login_error()
            if login_error:
                return False

            await asyncio.sleep(poll_interval)

        # Timeout reached — final authoritative state check
        final_url = await self.current_url()
        if final_url and not is_login_url(final_url):
            return True
        return not await self.looks_like_login_page()

    async def handle_post_login(self) -> bool:
        try:
            if await self.find_selector(("#ExceptRulesModalReal",), visible=True, timeout=1200):
                checkbox = await self.smart_locator.locate(self.page, ["#ruleExcepted"], timeout=1800)
                await checkbox.check()
                submit_rules = await self.smart_locator.locate(self.page, ["#submitRules"], timeout=1800)
                await submit_rules.click()
                deadline = asyncio.get_running_loop().time() + 12
                while asyncio.get_running_loop().time() < deadline:
                    if not is_login_url(await self.current_url()):
                        return True
                    await asyncio.sleep(0.06)
                return False
        except Exception as _error:
            return False
        return True

    # ------------------------------------------------------------------
    # Multi-factor authentication
    # ------------------------------------------------------------------

    async def handle_mfa(self) -> bool:
        mfa_selectors = (
            "#mfa-code-input",
            "input[name='MfaCode']",
            "input[placeholder*='کد تأیید']",
            "input[placeholder*='code']",
            "text=کد تأیید",
            "text=two-factor",
            "text=two factor",
        )
        mfa_input = await self.find_selector(mfa_selectors, visible=True, timeout=2000)
        if not mfa_input:
            return True
        logger.info("mfa_input_detected")
        mfa_value = getattr(utcms_config, "UTCMS_MFA_CODE", "")
        if not mfa_value:
            logger.warning("mfa_code_not_configured")
            return False
        try:
            await self.page.fill(mfa_input, mfa_value)
            submit_candidates = (
                "#mfa-submit",
                "button[type='submit']",
                "button:has-text('تأیید')",
                "button:has-text('Verify')",
            )
            submit_btn = await self.find_selector(submit_candidates, visible=True, timeout=3000)
            if submit_btn:
                await self.page.click(submit_btn)
            logger.info("mfa_code_submitted")
            await asyncio.sleep(1)
            return True
        except Exception as _exc:
            logger.warning("mfa_submit_failed", exc_info=True)
            return False

    # ------------------------------------------------------------------
    # Navigation to the login page
    # ------------------------------------------------------------------

    async def navigate_to_login(self, login_url: str | None = None) -> bool:
        candidate_urls = self.candidate_login_urls(login_url)
        for candidate_url in candidate_urls:
            try:
                await self.goto_with_retry(candidate_url, wait_until="domcontentloaded")
                try:
                    await self.page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    await asyncio.sleep(0.3)
            except Exception:
                continue
            u_sel = await self.find_selector(AuthSelectors.USERNAME_SELECTORS, visible=True, timeout=8000)
            p_sel = await self.find_selector(AuthSelectors.PASSWORD_SELECTORS, visible=True, timeout=8000)
            s_sel = await self.find_selector(AuthSelectors.SUBMIT_SELECTORS, visible=True, timeout=8000)
            if u_sel and p_sel and s_sel:
                return True
        return False

    # ------------------------------------------------------------------
    # Checkbox / iframe captcha detection
    # ------------------------------------------------------------------

    async def detect_and_solve_checkbox_captcha(self) -> bool:
        logger.info("checking_for_checkbox_captcha")

        try:
            turnstile_iframe = await self.page.query_selector('iframe[src*="challenges.cloudflare.com"]')
            if turnstile_iframe:
                logger.info("detected_cloudflare_turnstile")
                box = await turnstile_iframe.bounding_box()
                if box:
                    click_x = box["x"] + 30 + random.uniform(-3, 3)
                    click_y = box["y"] + box["height"] / 2 + random.uniform(-3, 3)
                    await self.page.mouse.click(click_x, click_y)
                    await asyncio.sleep(random.uniform(2.0, 4.0))
                    logger.info("clicked_cloudflare_turnstile_checkbox")
                    return True
        except Exception as e:
            logger.warning(f"error_handling_cloudflare_turnstile: {e}")

        try:
            recaptcha_iframe = await self.page.query_selector(
                'iframe[src*="recaptcha"], iframe[src*="google.com/recaptcha"]'
            )
            if recaptcha_iframe:
                logger.info("detected_google_recaptcha")
                frame = self.page.frame_locator('iframe[src*="recaptcha"], iframe[src*="google.com/recaptcha"]')
                checkbox = frame.locator("#recaptcha-anchor, .recaptcha-checkbox")
                if await checkbox.count() > 0:
                    await checkbox.click()
                    await asyncio.sleep(random.uniform(2.0, 4.0))
                    logger.info("clicked_google_recaptcha_checkbox")
                    return True
        except Exception as e:
            logger.warning(f"error_handling_google_recaptcha: {e}")

        try:
            hcaptcha_iframe = await self.page.query_selector('iframe[src*="hcaptcha"]')
            if hcaptcha_iframe:
                logger.info("detected_hcaptcha")
                frame = self.page.frame_locator('iframe[src*="hcaptcha"]')
                checkbox = frame.locator("#checkbox, #anchor")
                if await checkbox.count() > 0:
                    await checkbox.click()
                    await asyncio.sleep(random.uniform(2.0, 4.0))
                    logger.info("clicked_hcaptcha_checkbox")
                    return True
        except Exception as e:
            logger.warning(f"error_handling_hcaptcha: {e}")

        try:
            js_info = await self.page.evaluate(
                """() => {
                const robotTexts = ["من ربات نیستم", "ربات نیستم", "من ربات‌نیستم", "ربات‌نیستم"];
                const elements = Array.from(document.querySelectorAll('label, span, div, p, a, button, input'));
                let target = null;
                for (const el of elements) {
                    const text = (el.innerText || el.textContent || '').trim();
                    if (robotTexts.some(rt => text.includes(rt))) {
                        target = el;
                        break;
                    }
                }
                if (!target) return null;
                if (target.tagName.toLowerCase() === 'label' && target.htmlFor) {
                    return { selector: `#${CSS.escape(target.htmlFor)}`, clickText: false };
                }
                if (target.tagName.toLowerCase() === 'input' && target.type === 'checkbox') {
                    return { selector: 'input[type="checkbox"]', clickText: false };
                }
                const inside = target.querySelector('input[type="checkbox"]');
                if (inside) {
                    if (inside.id) return { selector: `#${CSS.escape(inside.id)}`, clickText: false };
                }
                let parent = target.parentElement;
                let depth = 0;
                while (parent && depth < 3) {
                    const near = parent.querySelector('input[type="checkbox"]');
                    if (near) {
                        if (near.id) return { selector: `#${CSS.escape(near.id)}`, clickText: false };
                    }
                    parent = parent.parentElement;
                    depth++;
                }
                if (target.id) {
                    return { selector: `#${CSS.escape(target.id)}`, clickText: false };
                }
                return { selector: null, clickText: target.innerText || target.textContent || '' };
            }"""
            )
            if js_info:
                logger.info(f"detected_custom_robot_checkbox: {js_info}")
                if js_info.get("selector"):
                    await self.page.click(js_info["selector"])
                    await asyncio.sleep(random.uniform(1.0, 2.5))
                    logger.info(f"clicked_custom_robot_checkbox_by_selector: {js_info['selector']}")
                    return True
                elif js_info.get("clickText"):
                    click_text = js_info["clickText"].strip()
                    locator = self.page.locator(f"text={click_text}").first
                    await locator.click()
                    await asyncio.sleep(random.uniform(1.0, 2.5))
                    logger.info(f"clicked_custom_robot_checkbox_by_text: {click_text}")
                    return True
        except Exception as e:
            logger.warning(f"error_handling_custom_robot_checkbox: {e}")
        return False

    # ------------------------------------------------------------------
    # CAPTCHA page helpers (image fingerprint, refresh, retry decision)
    # ------------------------------------------------------------------

    async def captcha_image_fingerprint(self) -> str:
        for selector in AuthSelectors.CAPTCHA_IMAGE_SELECTORS:
            try:
                value = await self.page.eval_on_selector(
                    selector,
                    """el => {
                        if (!el) return '';
                        const src = el.getAttribute('src') || '';
                        const data = el.getAttribute('data-src') || '';
                        const ts = el.getAttribute('data-timestamp') || '';
                        return `${src}|${data}|${ts}`;
                    }""",
                )
                cleaned = await self.as_clean_text(value)
                if cleaned:
                    return cleaned
            except Exception:
                continue
        return ""

    async def wait_for_captcha_refresh(self, previous_fingerprint: str) -> None:
        timeout_seconds = max(0.2, utcms_config.CAPTCHA_REFRESH_WAIT_SECONDS)
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while asyncio.get_running_loop().time() < deadline:
            current = await self.captcha_image_fingerprint()
            if current and current != previous_fingerprint:
                return
            await asyncio.sleep(0.05)
        await asyncio.sleep(timeout_seconds)

    async def refresh_captcha(self) -> bool:
        previous_fingerprint = await self.captcha_image_fingerprint()
        for selector in AuthSelectors.CAPTCHA_REFRESH_SELECTORS:
            try:
                button = await self.smart_locator.locate(self.page, [selector], timeout=900)
                await button.click()
                await self.wait_for_captcha_refresh(previous_fingerprint)
                return True
            except Exception:
                continue
        for selector in AuthSelectors.CAPTCHA_IMAGE_SELECTORS:
            try:
                image = await self.smart_locator.locate(self.page, [selector], timeout=900)
                await image.click()
                await self.wait_for_captcha_refresh(previous_fingerprint)
                return True
            except Exception:
                continue
        return False

    async def should_retry_captcha_after_submit(self, captcha_selector: str, last_error: str | None) -> bool:
        if is_credential_related_error(last_error):
            return False
        if is_captcha_related_error(last_error):
            return True
        if await self.find_selector(AuthSelectors.LOGOUT_SELECTORS, visible=True, timeout=300):
            return False
        if await self.find_selector(AuthSelectors.WAYBILL_FORM_MARKERS, timeout=300):
            return False
        current_url = await self.current_url()
        if current_url and not is_login_url(current_url):
            return False
        if await self.find_selector((captcha_selector,), timeout=300):
            return True
        generic_exists = await self.find_selector(AuthSelectors.CAPTCHA_SELECTORS, timeout=300)
        return bool(generic_exists)

    # ------------------------------------------------------------------
    # Math captcha hint extraction
    # ------------------------------------------------------------------

    async def extract_math_captcha_hints(self) -> list[str]:
        candidates: list[str] = []
        hint_selectors = (
            "label[for='DNTCaptchaInputText']",
            "label[for='CapToken']",
            "#dntCaptcha",
            ".dntCaptcha",
            "#dntCaptchaText",
            ".dnt-captcha-text",
            "[data-captcha-text]",
            ".captcha-text",
            ".captcha-question",
            ".captcha-label",
            ".captcha",
            ".captcha-container",
            ".dntCaptcha .text-center",
            ".security-code-text",
            "#captchaDiv",
        )
        for selector in hint_selectors:
            try:
                text = await self.page.eval_on_selector(
                    selector, "el => ((el.innerText || el.textContent || '').trim())"
                )
                cleaned = await self.as_clean_text(text)
                if cleaned:
                    candidates.extend(hint_candidates_from_text(cleaned))
            except Exception:
                continue

        try:
            around_input = await self.page.eval_on_selector(
                "input[name='DNTCaptchaInputText'], input[id='DNTCaptchaInputText'], input[name='CapToken'], input[id='CapToken']",
                """el => {
                    if (!el) return '';
                    const containers = [
                        el.closest('.dntCaptcha'), el.closest('.captcha-container'),
                        el.closest('.captcha'), el.closest('.form-group'),
                        el.closest('form'),
                        el.parentElement && el.parentElement.parentElement, el.parentElement
                    ];
                    const parts = [];
                    for (const c of containers) {
                        if (c) { const txt = (c.innerText || c.textContent || '').trim(); if (txt) parts.push(txt); }
                    }
                    return parts.join('\\n');
                }""",
            )
            around_cleaned = await self.as_clean_text(around_input)
            if around_cleaned:
                candidates.extend(hint_candidates_from_text(around_cleaned))
        except Exception:
            logger.warning("auth_operation_failed", exc_info=True)

        try:
            around_input = await self.page.evaluate(
                """() => {
                    const hints = [];
                    const labels = document.querySelectorAll('label');
                    for (const l of labels) {
                        const txt = (l.innerText || l.textContent || '').trim();
                        if (txt && /[+\\-*/×÷]/.test(txt)) hints.push(txt);
                        if (txt && /[۰-۹٠-٩0-9]/.test(txt) && /[+\\-*/×÷بعلاوهمنهایضربتقسیم]/.test(txt)) hints.push(txt);
                    }
                    const spans = document.querySelectorAll('.captcha span, .dntCaptcha span, .form-group span');
                    for (const s of spans) {
                        const txt = (s.innerText || s.textContent || '').trim();
                        if (txt && /[+\\-*/×÷]/.test(txt)) hints.push(txt);
                        if (txt && /[۰-۹٠-٩0-9]/.test(txt)) hints.push(txt);
                    }
                    return hints.join('\\n');
                }""",
            )
            around_cleaned = await self.as_clean_text(around_input)
            if around_cleaned:
                candidates.extend(hint_candidates_from_text(around_cleaned))
        except Exception:
            logger.warning("auth_operation_failed", exc_info=True)

        try:
            body_text = await self.page.evaluate("() => ((document.body && document.body.innerText) || '')")
            cleaned = await self.as_clean_text(body_text)
            if cleaned:
                candidates.extend(hint_candidates_from_text(cleaned[:1500]))
        except Exception:
            logger.warning("auth_operation_failed", exc_info=True)

        unique: list[str] = []
        seen = set()
        for item in candidates:
            key = item.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique

    # ------------------------------------------------------------------
    # Generic input fill with event dispatch
    # ------------------------------------------------------------------

    async def fill_input_like(self, selector: str, value: str) -> bool:
        if not value:
            return False
        try:
            await self.page.fill(selector, value)
            await self.page.eval_on_selector(
                selector,
                "el => { el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); el.dispatchEvent(new Event('keyup', { bubbles: true })); if (window.jQuery) { window.jQuery(el).trigger('input').trigger('change').trigger('keyup'); } }",
            )
            return True
        except Exception:
            logger.warning("auth_operation_failed", exc_info=True)

        try:
            locator = self.page.locator(selector).first
            if await locator.count() == 0:
                return False
            await locator.fill(value)
            await locator.evaluate(
                "el => { el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); el.dispatchEvent(new Event('keyup', { bubbles: true })); if (window.jQuery) { window.jQuery(el).trigger('input').trigger('change').trigger('keyup'); } }"
            )
            return True
        except Exception:
            logger.warning("auth_operation_failed", exc_info=True)

        try:
            updated = await self.page.eval_on_selector(
                selector,
                """(el, rawValue) => {
                    const value = String(rawValue ?? '');
                    if (!el) return false;
                    let prototype = Object.getPrototypeOf(el);
                    let setter = null;
                    while (prototype) {
                        const desc = Object.getOwnPropertyDescriptor(prototype, 'value');
                        if (desc && desc.set) { setter = desc.set; break; }
                        prototype = Object.getPrototypeOf(prototype);
                    }
                    if (setter) { setter.call(el, value); }
                    else { el.value = value; }
                    if (el._valueTracker) { el._valueTracker.setValue(value); }
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new Event('keyup', { bubbles: true }));
                    if (window.jQuery) { window.jQuery(el).trigger('input').trigger('change').trigger('keyup'); }
                    return true;
                }""",
                value,
            )
            return bool(updated)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # CapJS Proof-of-Work captcha solver (page-level invocation)
    # ------------------------------------------------------------------

    async def solve_capjs_captcha(self) -> bool:
        logger.info("CapJS Proof-of-Work captcha widget detected. Initiating automated solution...")
        try:
            try:
                widget_locator = self.page.locator("cap-widget")
                if await widget_locator.count() > 0:
                    await widget_locator.first.click(timeout=3000)
                    logger.info("Clicked on cap-widget.")
            except Exception as e:
                logger.warning(f"Could not click cap-widget: {e}")

            await self.page.evaluate(
                """() => {
                    const widget = document.querySelector('cap-widget');
                    if (widget && typeof widget.solve === 'function') {
                        widget.solve().catch(err => console.error("CapJS solve call error:", err));
                    }
                }"""
            )

            for _attempt in range(300):
                token = await self.page.evaluate(
                    """() => {
                        const widget = document.querySelector('cap-widget');
                        if (!widget) return null;
                        const token = widget.token || (widget.querySelector('input[type="hidden"]') ? widget.querySelector('input[type="hidden"]').value : null);
                        if (token) {
                            const capInput = document.querySelector('#CapToken') || document.querySelector('input[name="CapToken"]');
                            if (capInput && capInput.value !== token) {
                                capInput.value = token;
                                capInput.dispatchEvent(new Event('input', { bubbles: true }));
                                capInput.dispatchEvent(new Event('change', { bubbles: true }));
                            }
                            return token;
                        }
                        return null;
                    }"""
                )
                if token:
                    logger.info("کپچای CapJS با موفقیت در مرورگر حل شد و توکن در فرم ثبت گردید.")
                    return True
                await asyncio.sleep(0.1)
            logger.error("CapJS solving timed out after 30 seconds.")
            return False
        except Exception as e:
            logger.error(f"Error solving CapJS captcha: {e}")
            return False
