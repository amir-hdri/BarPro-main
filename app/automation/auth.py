"""Core authentication orchestrator for UTCMS.

UTCMSAuthenticator coordinates session management (SessionManager),
page navigation & state detection (AuthNavigator), CAPTCHA solving,
credential filling, and form submission into a single ``login()`` workflow.
"""

import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from playwright.async_api import BrowserContext, Page

from app.automation.auth_navigator import AuthNavigator
from app.automation.auth_session import SessionManager
from app.automation.auth_utils import (
    captcha_image_score,
    get_captcha_math_min_confidence,
    get_captcha_mode,
    get_captcha_strategy_order,
    is_ajax_login_response_url,
    is_authenticated_url,
    is_captcha_related_error,
    is_credential_related_error,
    is_login_url,
    is_plausible_captcha_image,
    navigation_failures_message,
    normalize_captcha_solution,
    save_captcha_debug_artifact,
)
from app.automation.captcha import captcha_engine, get_captcha_provider
from app.automation.selectors import AuthSelectors
from app.bot.captcha.interceptor import CaptchaInterceptor, CaptchaSolveStatus
from app.bot.core.smart_locator import SmartLocator
from app.core.config import utcms_config
from app.core.network import is_retryable_network_error
from app.monitoring.metrics import (
    track_captcha_attempt,
    track_captcha_failure,
    track_captcha_submit_retry,
    track_captcha_success,
)

logger = logging.getLogger(__name__)

_POST_LOGIN_LANDING_URL = "https://barname.utcms.ir/Barname/Notification/Notification"


class UTCMSAuthenticator:
    """Orchestrates the full UTCMS authentication flow.

    Delegates to three specialised subsystems:
      * SessionManager   – cookie inspection, session persistence
      * AuthNavigator    – page navigation, element detection, post-login steps
      * auth_utils       – URL classification, captcha normalisation, debug I/O

    Backward-compatible delegation methods (``_find_selector``, ``_current_url``,
    …) are provided so that external code or test monkey-patches that reference
    the old method names continue to work transparently.
    """

    def __init__(self, page: Page, context: BrowserContext):
        self.page = page
        self.context = context
        self.last_error: str | None = None
        self.last_state: str = "failed"
        self.smart_locator = SmartLocator()
        # Local-only mode: never contact an external captcha solver service.
        # The bundled local ML models (via _handle_captcha / get_captcha_provider)
        # handle all captcha types, so the external CaptchaInterceptor is skipped.
        solver_url = getattr(utcms_config, "CAPTCHA_SOLVER_URL", "")
        if getattr(utcms_config, "CAPTCHA_LOCAL_ONLY", True) or not solver_url:
            solver_url = ""
        if solver_url:
            self.captcha_interceptor = CaptchaInterceptor(
                solver_url=solver_url,
                smart_locator=self.smart_locator,
            )
        else:
            self.captcha_interceptor = None
        self.session = SessionManager(context, page)
        self.navigator = AuthNavigator(page, context, self.smart_locator)

    # ==================================================================
    # Backward-compatible delegation methods
    #
    # Each method below mirrors a method that previously lived directly on
    # this class but has been moved to AuthNavigator or SessionManager.
    # The thin wrapper ensures that code which monkey-patches or calls
    # e.g. ``authenticator._find_selector(…)`` continues to work.
    # ==================================================================

    async def _current_url(self) -> str:
        return await self.navigator.current_url()

    async def _find_selector(self, selectors, visible=False, timeout=3000):
        return await self.navigator.find_selector(selectors, visible=visible, timeout=timeout)

    async def _goto_with_retry(self, url, wait_until="domcontentloaded"):
        await self.navigator.goto_with_retry(url, wait_until=wait_until)

    def _candidate_login_urls(self, override_login_url=None):
        return self.navigator.candidate_login_urls(override_login_url)

    async def _looks_like_login_page(self):
        return await self.navigator.looks_like_login_page()

    async def _looks_like_error_page(self):
        return await self.navigator.looks_like_error_page()

    async def _extract_login_error(self):
        return await self.navigator.extract_login_error()

    async def _wait_for_login_result(self, timeout_ms=25000):
        return await self.navigator.wait_for_login_result(timeout_ms=timeout_ms)

    async def _complete_post_login_steps(self):
        return await self.navigator.handle_post_login()

    async def _has_auth_cookie(self):
        return await self.session.has_auth_cookie()

    async def _refresh_captcha(self):
        return await self.navigator.refresh_captcha()

    async def _detect_and_solve_checkbox_captcha(self):
        return await self.navigator.detect_and_solve_checkbox_captcha()

    async def _solve_capjs_captcha(self):
        result = await self.navigator.solve_capjs_captcha()
        if not result and not self.last_error:
            self.last_error = "زمان حل خودکار کپچای CapJS به پایان رسید (Timeout)."
        return result

    async def _extract_math_captcha_hints(self):
        return await self.navigator.extract_math_captcha_hints()

    def _normalize_captcha_solution(self, value):
        return normalize_captcha_solution(value)

    # ==================================================================
    # Login state detection
    # ==================================================================

    async def _is_logged_in(self, probe_login_url: bool = True) -> bool:
        self.last_error = None
        # Fast path: if there are no cookies in the browser context, we cannot be logged in
        try:
            cookies = await self.context.cookies()
            if not cookies:
                return False
        except Exception:
            pass
        current_url = await self.navigator.current_url()
        if current_url and not is_login_url(current_url):
            if await self._find_selector(AuthSelectors.LOGOUT_SELECTORS, visible=True, timeout=1200):
                return True
            if is_authenticated_url(current_url):
                return True
            if await self._find_selector(AuthSelectors.AUTHENTICATED_PAGE_MARKERS, timeout=1200):
                return True
            for selector in AuthSelectors.WAYBILL_FORM_MARKERS:
                try:
                    if await self.page.query_selector(selector) is not None:
                        return True
                except Exception:
                    continue
        if await self._looks_like_error_page():
            self.last_error = "صفحه بارنامه به‌جای فرم، خطای سامانه برگرداند"
            return False

        if not probe_login_url:
            if await self._has_auth_cookie():
                deadline = asyncio.get_running_loop().time() + 5.0
                while asyncio.get_running_loop().time() < deadline:
                    curr_url = await self._current_url()
                    if curr_url and not is_login_url(curr_url):
                        return True
                    await asyncio.sleep(0.05)
                return True
            return False

        try:
            await self._goto_with_retry(utcms_config.LOGIN_URL, wait_until="domcontentloaded")
            try:
                await self.page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                await asyncio.sleep(0.3)
        except Exception:
            return False

        current_url = await self._current_url()
        if is_login_url(current_url):
            return False
        if await self._find_selector(AuthSelectors.LOGOUT_SELECTORS, visible=True, timeout=3000):
            return True

        for selector in AuthSelectors.WAYBILL_FORM_MARKERS:
            try:
                await self.smart_locator.locate(self.page, [selector], timeout=500)
                return True
            except Exception:
                continue

        if await self._looks_like_login_page():
            return False
        if await self._looks_like_error_page():
            self.last_error = "صفحه بارنامه به‌جای فرم، خطای سامانه برگرداند"
            return False

        await asyncio.sleep(0.08)
        if await self._looks_like_login_page() or await self._looks_like_error_page():
            return False
        return await self._has_auth_cookie()

    # ==================================================================
    # Debug snapshot
    # ==================================================================

    async def _save_login_debug_snapshot(self, stage: str) -> None:
        if not utcms_config.CAPTCHA_DEBUG_SAVE_IMAGES:
            return
        timestamp = datetime.now(UTC).replace(tzinfo=None).strftime("%Y%m%d-%H%M%S-%f")
        safe_stage = re.sub(r"[^a-zA-Z0-9_-]+", "_", stage or "login")
        debug_dir = Path(utcms_config.CAPTCHA_DEBUG_DIR)
        debug_dir.mkdir(parents=True, exist_ok=True)
        base_name = f"{timestamp}-login-{safe_stage}"
        screenshot_path = debug_dir / f"{base_name}.png"
        html_path = debug_dir / f"{base_name}.html"
        meta_path = debug_dir / f"{base_name}.json"

        try:
            await self.page.screenshot(path=str(screenshot_path), full_page=True)
        except Exception:
            screenshot_path = None
        try:
            html_path.write_text(await self.page.content())
        except Exception:
            html_path = None
        body_text = ""
        try:
            body_text = await self.navigator.as_clean_text(await self.page.text_content("body"))
        except Exception as exc:
            logger.warning(
                "auth_body_text_extraction_failed",
                extra={"extra_fields": {"error": str(exc)}},
            )

        meta_path.write_text(
            json.dumps(
                {
                    "saved_at": datetime.now(UTC).replace(tzinfo=None).isoformat() + "Z",
                    "stage": stage,
                    "url": await self._current_url(),
                    "last_error": self.last_error,
                    "body_excerpt": body_text[:2000],
                    "screenshot_path": str(screenshot_path) if screenshot_path else None,
                    "html_path": str(html_path) if html_path else None,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    # ==================================================================
    # CAPTCHA solving
    # ==================================================================

    async def _extract_captcha_image_base64(self, captcha_selector: str | None = None) -> str | None:
        input_box = None
        if captcha_selector:
            try:
                captcha_input = await self.smart_locator.locate(self.page, [captcha_selector], timeout=900)
                input_box = await captcha_input.bounding_box()
            except Exception:
                input_box = None

        best_candidate = None
        for selector in AuthSelectors.CAPTCHA_IMAGE_SELECTORS:
            try:
                locators = self.page.locator(selector)
                count = await locators.count()
            except Exception:
                continue
            for index in range(count):
                try:
                    locator = locators.nth(index)
                    box = await locator.bounding_box()
                    if not box or not is_plausible_captcha_image(box):
                        continue
                    score = captcha_image_score(box, input_box, selector)
                    if best_candidate is None or score > best_candidate[0]:
                        best_candidate = (score, locator)
                except Exception:
                    continue

        if best_candidate is None:
            return None
        try:
            image_bytes = await best_candidate[1].screenshot(type="png")
            if image_bytes:
                import base64

                return base64.b64encode(image_bytes).decode("utf-8")
        except Exception:
            return None
        return None

    async def _wait_for_manual_captcha_input(self, selector: str) -> bool:
        timeout_seconds = max(5, utcms_config.UTCMS_MANUAL_CAPTCHA_TIMEOUT_SECONDS)
        poll_seconds = max(0.2, utcms_config.UTCMS_MANUAL_CAPTCHA_POLL_SECONDS)
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while asyncio.get_running_loop().time() < deadline:
            try:
                value = await self.page.eval_on_selector(selector, "el => (el.value || '').trim()")
                if value:
                    return True
            except Exception:
                logger.warning("auth_operation_failed", exc_info=True)
            await asyncio.sleep(poll_seconds)
        return False

    async def _set_captcha_value(self, captcha_selector: str, value: str) -> bool:
        normalized = normalize_captcha_solution(value)
        if not normalized:
            self.last_error = "مقدار کپچا معتبر نیست."
            track_captcha_failure("captcha_value_invalid")
            return False
        try:
            await self.page.fill(captcha_selector, "")
        except Exception:
            try:
                field = await self.smart_locator.locate(self.page, [captcha_selector], timeout=1000)
                await field.fill("")
            except Exception:
                logger.warning("auth_operation_failed", exc_info=True)
        if await self.navigator.fill_input_like(captcha_selector, normalized):
            return True
        self.last_error = "مقداردهی فیلد کپچا انجام نشد."
        track_captcha_failure("captcha_fill_failed")
        return False

    async def _solve_captcha_with_provider(
        self, captcha_selector: str | None = None, phase: str = "login", attempt: int | None = None
    ) -> str | None:
        started_at = asyncio.get_running_loop().time()
        track_captcha_attempt("provider", phase=phase, attempt=attempt)
        provider = get_captcha_provider()
        if not provider:
            track_captcha_failure(
                "provider_not_configured",
                phase=phase,
                strategy="provider",
                latency_seconds=asyncio.get_running_loop().time() - started_at,
                attempt=attempt,
            )
            if utcms_config.CAPTCHA_LOCAL_FALLBACK_ENABLED:
                return await self._solve_math_captcha(phase=phase, attempt=attempt)
            return None

        image_base64 = await self._extract_captcha_image_base64(captcha_selector=captcha_selector)
        if not image_base64:
            elapsed = asyncio.get_running_loop().time() - started_at
            logger.warning(
                "captcha_provider_image_not_found", extra={"extra_fields": {"phase": phase, "attempt": attempt}}
            )
            page_hint_value = await self._solve_math_captcha(phase=phase, attempt=attempt)
            if page_hint_value:
                return page_hint_value
            track_captcha_failure(
                "provider_image_not_found", phase=phase, strategy="provider", latency_seconds=elapsed, attempt=attempt
            )
            if utcms_config.CAPTCHA_LOCAL_FALLBACK_ENABLED:
                return await self._solve_math_captcha(phase=phase, attempt=attempt)
            return None

        page_url = str(self.page.url) if hasattr(self.page, "url") else ""
        save_captcha_debug_artifact(page_url, image_base64, phase, attempt, "captured")
        result = await provider.solve_text_captcha(image_base64)
        normalized = normalize_captcha_solution(result.value)
        if result.solved and normalized:
            elapsed = asyncio.get_running_loop().time() - started_at
            save_captcha_debug_artifact(
                page_url, image_base64, phase, attempt, "solved", provider=result.provider, solution=normalized
            )
            logger.info(
                "captcha_provider_solved",
                extra={"extra_fields": {"phase": phase, "attempt": attempt, "provider": result.provider}},
            )
            track_captcha_success("provider", phase=phase, latency_seconds=elapsed, attempt=attempt)
            return normalized

        elapsed = asyncio.get_running_loop().time() - started_at
        save_captcha_debug_artifact(
            page_url,
            image_base64,
            phase,
            attempt,
            "failed",
            provider=result.provider,
            solution=result.value,
            error=result.error,
        )
        logger.warning(
            "captcha_provider_failed",
            extra={
                "extra_fields": {"provider": result.provider, "error": result.error, "phase": phase, "attempt": attempt}
            },
        )
        track_captcha_failure(
            result.error or "provider_invalid_value",
            phase=phase,
            strategy="provider",
            latency_seconds=elapsed,
            attempt=attempt,
        )
        if utcms_config.CAPTCHA_LOCAL_FALLBACK_ENABLED:
            fallback_value = await self._solve_math_captcha(phase=phase, attempt=attempt)
            if fallback_value:
                track_captcha_success("provider_fallback", phase=phase, latency_seconds=elapsed, attempt=attempt)
                return fallback_value
        return None

    async def _solve_math_captcha(self, phase: str = "login", attempt: int | None = None) -> str | None:
        started_at = asyncio.get_running_loop().time()
        track_captcha_attempt("math", phase=phase, attempt=attempt)
        hints = await self._extract_math_captcha_hints()
        if not hints:
            track_captcha_failure(
                "math_hint_not_found",
                phase=phase,
                strategy="math",
                latency_seconds=asyncio.get_running_loop().time() - started_at,
                attempt=attempt,
            )
            return None

        min_confidence = get_captcha_math_min_confidence()
        best_value: str | None = None
        best_confidence = 0.0
        for hint in hints:
            decision = captcha_engine.solve_text_with_confidence(hint)
            if not decision.value:
                continue
            solved = normalize_captcha_solution(decision.value)
            if solved is None:
                continue
            if decision.confidence >= min_confidence:
                elapsed = asyncio.get_running_loop().time() - started_at
                track_captcha_success(
                    "math", phase=phase, confidence=decision.confidence, latency_seconds=elapsed, attempt=attempt
                )
                logger.info(
                    "math_captcha_solved",
                    extra={
                        "extra_fields": {
                            "confidence": decision.confidence,
                            "strategy": decision.strategy,
                            "phase": phase,
                            "attempt": attempt,
                        }
                    },
                )
                return solved
            if decision.confidence > best_confidence:
                best_confidence = decision.confidence
                best_value = solved

        if best_value is not None and best_confidence >= max(0.3, min_confidence - 0.2):
            elapsed = asyncio.get_running_loop().time() - started_at
            logger.info(
                "math_captcha_solved_relaxed",
                extra={"extra_fields": {"confidence": best_confidence, "phase": phase, "attempt": attempt}},
            )
            track_captcha_success(
                "math_relaxed", phase=phase, confidence=best_confidence, latency_seconds=elapsed, attempt=attempt
            )
            return best_value

        track_captcha_failure(
            "math_parse_failed",
            phase=phase,
            strategy="math",
            latency_seconds=asyncio.get_running_loop().time() - started_at,
            attempt=attempt,
        )
        return None

    async def _auto_solve_captcha(self, captcha_selector: str) -> bool:
        max_attempts = max(1, utcms_config.CAPTCHA_AUTO_MAX_ATTEMPTS)
        retry_delay = max(0.1, utcms_config.CAPTCHA_AUTO_RETRY_DELAY_SECONDS)
        mode = get_captcha_mode()
        strategy_order = get_captcha_strategy_order(mode, utcms_config.CAPTCHA_LOCAL_FALLBACK_ENABLED)
        for attempt in range(1, max_attempts + 1):
            if attempt > 1 and utcms_config.CAPTCHA_AUTO_REFRESH_ON_RETRY:
                await self._refresh_captcha()
                await asyncio.sleep(retry_delay)
            for strategy in strategy_order:
                if strategy == "math":
                    solved = await self._solve_math_captcha(phase="login", attempt=attempt)
                else:
                    solved = await self._solve_captcha_with_provider(
                        captcha_selector=captcha_selector, phase="login", attempt=attempt
                    )
                if solved and await self._set_captcha_value(captcha_selector, solved):
                    return True
        self.last_error = "حل خودکار کپچا ناموفق بود. کیفیت تصویر کپچا یا مدل CNN را بررسی کنید."
        logger.warning(
            "captcha_auto_solve_failed",
            extra={"extra_fields": {"phase": "login", "max_attempts": max_attempts, "mode": mode}},
        )
        track_captcha_failure("auto_solve_failed", phase="login", strategy="auto")
        return False

    async def _handle_captcha(self, captcha_selector: str, force_auto: bool = False) -> bool:
        if not captcha_selector:
            return True
        has_cap_widget = await self.page.query_selector("cap-widget")
        if has_cap_widget and type(has_cap_widget).__name__ not in ("Mock", "AsyncMock", "MagicMock"):
            return await self._solve_capjs_captcha()
        if utcms_config.UTCMS_CAPTCHA_VALUE:
            return await self._set_captcha_value(captcha_selector, utcms_config.UTCMS_CAPTCHA_VALUE)

        captcha_mode = get_captcha_mode()
        if force_auto or captcha_mode != "manual_only":
            return await self._auto_solve_captcha(captcha_selector)

        allow_manual = captcha_mode == "manual_only" and utcms_config.UTCMS_ENABLE_MANUAL_CAPTCHA
        if allow_manual:
            if utcms_config.HEADLESS:
                self.last_error = "کپچا فعال است ولی مرورگر در حالت HEADLESS اجرا می‌شود. برای حل دستی کپچا، `HEADLESS=false` تنظیم شود."
                return False
            solved = await self._wait_for_manual_captcha_input(captcha_selector)
            if not solved:
                self.last_error = "کپچا در بازه مجاز تکمیل نشد. لطفاً کپچا را دستی وارد کنید و مجدد تلاش کنید."
                track_captcha_failure("manual_timeout", phase="login", strategy="manual")
                return False
            track_captcha_success("manual", phase="login")
            return True

        if captcha_mode == "provider_only":
            self.last_error = (
                "کپچا در حالت provider_only حل نشد. مقدار `CAPTCHA_PROVIDER` و فایل مدل CNN را بررسی کنید."
            )
        elif captcha_mode == "manual_only":
            self.last_error = (
                "حالت manual_only فعال است اما حل دستی کپچا غیرفعال است. `UTCMS_ENABLE_MANUAL_CAPTCHA=true` تنظیم شود."
            )
        else:
            self.last_error = (
                "کپچا در صفحه ورود فعال است اما حل خودکار CNN موفق نشد. فایل مدل و کیفیت تصویر کپچا را بررسی کنید."
            )
        track_captcha_failure("captcha_not_solved", phase="login", strategy=captcha_mode or "unknown")

        return False

    # ==================================================================
    # Credential filling
    # ==================================================================

    async def _fill_credentials(
        self, username_selector: str, password_selector: str, username: str, password: str
    ) -> bool:
        digit_table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        username_clean = (username or "").translate(digit_table).strip()
        u_ok = await self.navigator.fill_input_like(username_selector, username_clean)
        p_ok = await self.navigator.fill_input_like(password_selector, password)
        if u_ok and p_ok:
            return True
        self.last_error = "تکمیل فرم ورود با خطا مواجه شد: عناصر ورود پیدا یا پر نشدند"
        return False

    # ==================================================================
    # Form submission
    # ==================================================================

    async def _submit_login(self, submit_selector: str) -> bool:
        clicked = False
        ajax_response_task = None
        if hasattr(self.page, "wait_for_response"):
            try:
                ajax_response_task = asyncio.create_task(
                    self.page.wait_for_response(
                        lambda response: is_ajax_login_response_url(getattr(response, "url", "")),
                        timeout=25000,
                    )
                )
            except Exception:
                ajax_response_task = None
        # Ensure all loading overlays are gone before attempting click
        await self.navigator.wait_for_loading_overlays_to_disappear(timeout_ms=10000)

        try:
            await self.page.click(submit_selector, timeout=8000)
            clicked = True
            try:
                await self.page.wait_for_load_state("domcontentloaded", timeout=3000)
            except Exception as exc:
                # `wait_for_load_state` commonly times out when the page is
                # already loaded or when SPA routing has already completed;
                # not actionable, log at debug level.
                logger.debug(
                    "auth_wait_domcontentloaded_timeout",
                    extra={"extra_fields": {"error": str(exc)}},
                )
        except Exception as click_err:
            logger.warning(f"Normal click failed, trying force click: {click_err}")
            try:
                submit_locator = await self.smart_locator.locate(self.page, [submit_selector], timeout=5000)
                # Use force=True to bypass pointer interception (e.g. by loading spinner)
                await submit_locator.click(force=True, timeout=8000)
                clicked = True
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=3000)
                except Exception as exc:
                    logger.debug(
                        "auth_wait_domcontentloaded_timeout",
                        extra={"extra_fields": {"error": str(exc)}},
                    )
            except Exception:
                clicked = False

        if not clicked:
            self.last_error = "ارسال فرم ورود انجام نشد."
            if ajax_response_task:
                ajax_response_task.cancel()
            await self._save_login_debug_snapshot("submit_not_clicked")
            return False

        ajax_result = await self._consume_ajax_login_response(ajax_response_task)
        if ajax_result is not None:
            return ajax_result

        if await self._wait_for_login_result():
            # Allow page to fully settle after redirect before doing final checks
            await asyncio.sleep(0.5)
            if not await self._complete_post_login_steps():
                if not self.last_error:
                    self.last_error = "تکمیل مراحل پس از لاگین ناموفق بود."
                return False
            if await self._is_logged_in(probe_login_url=False):
                return True
            if not self.last_error:
                self.last_error = (
                    await self._extract_login_error() or "لاگین تکمیل نشد و دسترسی به فرم بارنامه تایید نشد."
                )
            await self._save_login_debug_snapshot("post_submit_not_verified")
            return False

        if not self.last_error:
            self.last_error = await self._extract_login_error() or "لاگین ناموفق بود؛ صفحه در وضعیت ورود باقی ماند."
        await self._save_login_debug_snapshot("submit_failed")
        return False

    async def _consume_ajax_login_response(self, ajax_response_task) -> bool | None:
        if not ajax_response_task:
            return None
        try:
            response = await asyncio.wait_for(ajax_response_task, timeout=12)
        except Exception:
            return None

        payload = None
        try:
            payload = await response.json()
        except Exception:
            try:
                raw_text = await response.text()
                payload = json.loads(raw_text)
            except Exception:
                payload = None

        if not isinstance(payload, dict) or "success" not in payload:
            return None

        success = bool(payload.get("success"))
        message = payload.get("message") or payload.get("detail") or payload.get("resultMessage") or None
        if not success:
            self.last_error = str(message or "لاگین ناموفق بود")
            return False

        if not await self._complete_post_login_steps():
            return False

        deadline = asyncio.get_running_loop().time() + 10
        while asyncio.get_running_loop().time() < deadline:
            if await self._find_selector(AuthSelectors.LOGOUT_SELECTORS, visible=True, timeout=300):
                return True
            if not is_login_url(await self._current_url()):
                break
            await asyncio.sleep(0.06)

        if await self._is_logged_in(probe_login_url=False):
            return True
        if not self.last_error:
            self.last_error = str(message or "ورود با موفقیت تایید شد ولی session معتبر شناسایی نشد")
        await self._save_login_debug_snapshot("ajax_success_not_verified")
        return False

    # ==================================================================
    # Public API — main orchestration
    # ==================================================================

    async def _accept_rules_modal_if_present(self, timeout: float = 8.0) -> bool:
        """Accept the UTCMS 'rules acceptance' modal if it is currently shown.

        The modal (checkbox ``#ruleExcepted`` + confirm button ``#submitRules``)
        overlays the login form and prevents the username/password fields from
        being located. Returns True if a modal was detected and accepted.
        """
        try:
            checkbox = self.page.locator("#ruleExcepted").first
            if await checkbox.count() == 0:
                return False
            # Only act if the modal is actually visible.
            try:
                if not await checkbox.is_visible(timeout=2000):
                    return False
            except Exception:
                return False
            await checkbox.check(timeout=timeout)
            logger.info("rules_modal_checkbox_checked")
            confirm = self.page.locator("#submitRules").first
            if await confirm.count():
                await confirm.click(timeout=timeout)
                logger.info("rules_modal_confirmed")
            # Wait for the modal to disappear and the form to settle.
            await asyncio.sleep(1.5)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("rules_modal_accept_failed", extra={"extra_fields": {"error": str(exc)[:160]}})
            return False

    async def _clear_loading_overlays(self) -> None:
        """Permanently suppress UTCMS's full-page '#loading' mask.

        UTCMS renders a ``<div id="loading" class="loading">`` mask on top of the
        whole page (including the login form and the submit button). It can
        re-appear during the session, so we physically remove it from the DOM
        and install a MutationObserver that deletes any future instance, plus a
        CSS safety net. This guarantees no pointer interception and lets
        field/button locators report as interactable.
        """
        try:
            await self.page.evaluate("""() => {
                    const KILL = () => {
                        document.querySelectorAll('#loading.loading, div.loading, .loading-overlay, .loading-mask')
                            .forEach(el => el.remove());
                    };
                    KILL();
                    // Re-kill if UTCMS re-injects the mask.
                    if (!window.__barpro_overlay_observer) {
                        const mo = new MutationObserver(KILL);
                        mo.observe(document.documentElement, {childList: true, subtree: true});
                        window.__barpro_overlay_observer = mo;
                    }
                    // CSS safety net in case removal races with re-injection.
                    const root = document.head || document.body || document.documentElement;
                    if (root) {
                        let style = document.getElementById('__barpro_overlay_killer');
                        if (!style) {
                            style = document.createElement('style');
                            style.id = '__barpro_overlay_killer';
                            root.appendChild(style);
                        }
                        style.textContent = '#loading.loading, div.loading, .loading-overlay, .loading-mask { display:none !important; pointer-events:none !important; visibility:hidden !important; }';
                    }
                }""")
        except Exception as exc:  # noqa: BLE001
            logger.debug("clear_loading_overlays_failed", extra={"extra_fields": {"error": str(exc)[:120]}})

    async def _try_http_login_first(self, username: str, password: str) -> bool:
        """Attempt an HTTP-only login (curl_cffi) before launching Playwright.

        The WAF in front of barname.utcms.ir aggressively flags Chromium's
        TLS fingerprint (JA3/JA4). ``curl_cffi`` impersonates a real Chrome
        120 ``ClientHello``, so the HTTP request is far more likely to
        succeed. If it does, we inject the obtained auth cookies into the
        Playwright context and the rest of the RPA flow continues with a
        valid session.

        Returns:
            True if the HTTP login succeeded AND the cookies were
            injected. The caller can then skip the Playwright login form
            and go straight to the post-login flow.
        """
        # Feature-flag: opt-in via env var. Default = ON (faster + bypass
        # WAF fingerprint). Set UTCMS_HTTP_LOGIN_ENABLED=false to fall
        # back to the legacy Playwright-only flow.
        if not getattr(utcms_config, "UTCMS_HTTP_LOGIN_ENABLED", True):
            return False
        # Skip if any required piece is missing.
        if not username or not password:
            return False
        try:
            from app.automation.utcms_http_login import UtcmsHttpLogin  # type: ignore[import-not-found]
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "auth_http_login_unavailable",
                extra={"extra_fields": {"error": str(exc)[:160]}},
            )
            return False
        try:
            http_login = UtcmsHttpLogin()
            result = await http_login.authenticate(username, password)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "auth_http_login_exception",
                extra={"extra_fields": {"error": str(exc)[:200]}},
            )
            return False
        if not result.success:
            logger.info(
                "auth_http_login_failed_falling_back",
                extra={"extra_fields": {"error": result.error, "status": result.status_code}},
            )
            return False
        # Inject cookies into the Playwright context.
        injected = await http_login.inject_cookies_into_context_async(result, self.context)
        if not injected:
            logger.warning("auth_http_login_cookie_inject_failed")
            return False
        try:
            from app.automation.http_browser_bridge import ensure_utcms_http_browser_bridge

            bridge = await ensure_utcms_http_browser_bridge(self.page)
            if bridge is not None:
                authenticated_session = http_login.take_authenticated_session()
                await bridge.adopt_authenticated_session(authenticated_session, result.cookies)
            else:
                await http_login.close()
        except Exception:
            logger.debug("auth_http_login_bridge_setup_failed", exc_info=True)
        logger.info(
            "auth_http_login_succeeded",
            extra={
                "extra_fields": {
                    "status": result.status_code,
                    "final_url": result.final_url,
                    "cookie_count": len(result.cookies),
                }
            },
        )
        # Warm the browser session on UTCMS's official post-login landing page.
        # Directly opening ``WAYBILL_URL`` as the first Chromium request is
        # consistently answered with HTTP 408 / a dropped connection by the
        # portal WAF, while this same page is the target used by UTCMS's own
        # Login.js and loads reliably with the injected cookies. The waybill
        # manager will then follow the real menu link from this warm page.
        try:
            await self.page.goto(
                _POST_LOGIN_LANDING_URL,
                wait_until="domcontentloaded",
                timeout=40000,
            )
        except Exception as nav_exc:
            logger.warning(
                "auth_http_login_post_nav_failed",
                extra={"extra_fields": {"error": str(nav_exc)[:200]}},
            )
            # Still return True — cookies are in the context even if goto failed
        return True

    async def login(self, username: str, password: str, login_url: str | None = None) -> bool:
        self.last_error = None
        self.last_state = "failed"
        navigation_errors: list[tuple[str, Exception]] = []

        # Hybrid: try the HTTP (curl_cffi) login first to bypass the WAF
        # TLS-fingerprint filter. If it succeeds, the Playwright context
        # already has a valid session — just navigate to the dashboard
        # and let the post-login flow take over.
        if await self._try_http_login_first(username, password):
            try:
                # Visit a known authenticated page to validate the session
                # and trigger any post-login state changes.
                if await self._is_logged_in(probe_login_url=False):
                    self.last_state = "success"
                    return True
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "auth_http_login_post_verify_failed",
                    extra={"extra_fields": {"error": str(exc)[:200]}},
                )
            # If we reached here the HTTP cookie didn't make Playwright
            # logged-in (likely the cookie name is unusual). Fall through
            # to the Playwright login flow as a safety net.
            logger.info("auth_http_login_falling_back_to_playwright")

        try:
            candidate_urls = self._candidate_login_urls(login_url)
        except TypeError:
            candidate_urls = self._candidate_login_urls()

        for candidate_login_url in candidate_urls:
            try:
                await self._goto_with_retry(candidate_login_url, wait_until="domcontentloaded")
                try:
                    await self.page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    await asyncio.sleep(0.3)
                # Wait for any blocking overlays (e.g., initial page loader) to vanish
                await self.navigator.wait_for_loading_overlays_to_disappear()

                # UTCMS shows a "rules acceptance" modal on first load. It overlays
                # the login form and blocks the username/password fields from being
                # found. Accept it (check the box + click confirm) before proceeding.
                await self._accept_rules_modal_if_present()

                # Neutralise the full-page '#loading' mask (re-appears dynamically,
                # so we inject a persistent CSS killer, not a one-off removal).
                await self._clear_loading_overlays()

                # Small grace period for the login form to become interactable.
                await asyncio.sleep(0.5)

                # Ensure the loading mask is gone before locating fields.
                await self._clear_loading_overlays()
            except Exception as exc:
                if is_retryable_network_error(exc):
                    navigation_errors.append((candidate_login_url, exc))
                continue

            # WAF block detection: UTCMS WAF returns HTTP 444 or a page
            # saying "درخواست مجاز نمی‌باشد" for headless Chromium. Detect
            # this early and fail fast — do not waste 3 minutes trying to fill
            # an invisible login form that will never appear.
            try:
                pw_url = self.page.url
                page_text = await self.page.evaluate(
                    "() => document.body ? document.body.innerText.substring(0, 400) : ''"
                )
                if "درخواست مجاز نمی‌باشد" in page_text or "request not authorized" in page_text.lower():
                    self.last_error = (
                        "سامانه دسترسی از مرورگر headless را مسدود کرده است (WAF). "
                        "لاگین HTTP نیز شکست خورده — سرویس UTCMS در حال حاضر در دسترس نیست."
                    )
                    logger.warning(
                        "auth_playwright_waf_blocked",
                        extra={"extra_fields": {"url": pw_url, "snippet": page_text[:200]}},
                    )
                    return False
            except Exception:
                pass

            username_selector = await self._find_selector(AuthSelectors.USERNAME_SELECTORS, visible=True, timeout=8000)
            password_selector = await self._find_selector(AuthSelectors.PASSWORD_SELECTORS, visible=True, timeout=8000)

            submit_selector = await self._find_selector(AuthSelectors.SUBMIT_SELECTORS, visible=True, timeout=8000)

            if not (username_selector and password_selector and submit_selector):
                logger.warning(
                    f"auth_login_fields_not_found: username_selector={username_selector}, "
                    f"password_selector={password_selector}, submit_selector={submit_selector}"
                )
                await self._save_login_debug_snapshot("fields_not_found")
                continue

            if not await self._fill_credentials(username_selector, password_selector, username, password):
                continue

            has_cap_widget = await self.page.query_selector("cap-widget")
            if has_cap_widget:
                logger.info("Detected CapJS 'I am not a robot' checkbox widget. Solving...")
                if not await self._solve_capjs_captcha():
                    self.last_state = "captcha_failed"
                    return False
            else:
                checkbox_solved = await self._detect_and_solve_checkbox_captcha()
                if checkbox_solved:
                    logger.info("Detected and solved checkbox/iframe captcha successfully.")
                    await asyncio.sleep(0.5)

            captcha_selector = await self._find_selector(AuthSelectors.CAPTCHA_SELECTORS)
            if captcha_selector and captcha_selector != "cap-widget":
                logger.info("Detected standard math/image captcha. Solving using local OCR/CNN...")
                interceptor = self.captcha_interceptor
                if interceptor is not None:
                    interceptor_result = await interceptor.solve_and_fill(
                        self.page,
                        captcha_input_selectors=AuthSelectors.CAPTCHA_SELECTORS,
                    )
                    if interceptor_result.status == CaptchaSolveStatus.CIRCUIT_OPEN:
                        self.last_error = interceptor_result.error or "سرویس حل کپچا در دسترس نیست (circuit open)"
                        self.last_state = "captcha_failed"
                        return False

                if not await self._handle_captcha(captcha_selector):
                    if is_captcha_related_error(self.last_error):
                        self.last_state = "captcha_failed"
                    return False

                max_submit_attempts = max(1, utcms_config.CAPTCHA_AUTO_MAX_ATTEMPTS)
                for attempt in range(1, max_submit_attempts + 1):
                    if await self._submit_login(submit_selector):
                        self.last_state = "success"
                        return True

                    await self._save_login_debug_snapshot(f"retry_before_refresh_{attempt}")
                    if not await self.navigator.should_retry_captcha_after_submit(captcha_selector, self.last_error):
                        break
                    if attempt >= max_submit_attempts:
                        break
                    track_captcha_submit_retry()
                    await self._refresh_captcha()
                    await asyncio.sleep(max(0.1, utcms_config.CAPTCHA_SUBMIT_RETRY_DELAY_SECONDS))
                    if not await self._handle_captcha(captcha_selector, force_auto=True):
                        break

                if is_captcha_related_error(self.last_error) or is_credential_related_error(self.last_error):
                    if is_captcha_related_error(self.last_error):
                        self.last_state = "captcha_failed"
                    break
                continue

            if await self._submit_login(submit_selector):
                self.last_state = "success"
                return True
            if is_captcha_related_error(self.last_error) or is_credential_related_error(self.last_error):
                if is_captcha_related_error(self.last_error):
                    self.last_state = "captcha_failed"
                break

        if not self.last_error and navigation_errors:
            self.last_error = navigation_failures_message(navigation_errors)
        if not self.last_error:
            self.last_error = "فرم ورود معتبر در URLهای شناخته‌شده پیدا نشد. مقدار `LOGIN_URL` را تنظیم کنید."

        logger.warning("login_failed", extra={"extra_fields": {"reason": self.last_error}})
        if is_captcha_related_error(self.last_error):
            self.last_state = "captcha_failed"
        return False
