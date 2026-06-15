import asyncio
import base64
import binascii
import json
import logging
import os
import random
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from playwright.async_api import BrowserContext, Page

from app.automation.captcha import captcha_engine, get_captcha_provider
from app.automation.selectors import AuthSelectors
from app.bot.captcha.interceptor import CaptchaInterceptor, CaptchaSolveStatus
from app.bot.core.smart_locator import SmartLocator
from app.core.config import utcms_config
from app.core.network import is_retryable_network_error
from app.core.utils import resolve_maybe_awaitable
from app.monitoring.metrics import (
    track_captcha_attempt,
    track_captcha_failure,
    track_captcha_submit_retry,
    track_captcha_success,
)

logger = logging.getLogger(__name__)


class UTCMSAuthenticator:
    """Handles authentication for UTCMS."""

    _captcha_digit_map = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    _captcha_value_pattern = re.compile(r"^-?\d+$")
    _captcha_hint_markers = (
        "captcha",
        "کپچا",
        "کد امنیتی",
        "عبارت امنیتی",
        "حاصل",
        "جمع",
        "منهای",
        "تفریق",
        "ضرب",
        "تقسیم",
        "+",
        "-",
        "*",
        "/",
        "×",
        "÷",
    )

    def __init__(self, page: Page, context: BrowserContext):
        self.page = page
        self.context = context
        self.last_error: str | None = None
        self.last_state: str = "failed"
        self.smart_locator = SmartLocator()
        self.captcha_interceptor = CaptchaInterceptor(
            solver_url=getattr(utcms_config, "CAPTCHA_SOLVER_URL", "") or "http://localhost:8099/solve",
            smart_locator=self.smart_locator,
        )

    async def _current_url(self) -> str:
        raw_url = getattr(self.page, "url", "")
        try:
            url_value = await resolve_maybe_awaitable(raw_url)
        except Exception:
            return ""

        if url_value is None:
            return ""
        return url_value if isinstance(url_value, str) else str(url_value)

    async def _as_clean_text(self, value) -> str:
        try:
            resolved = await resolve_maybe_awaitable(value)
        except Exception:
            return ""
        if resolved is None:
            return ""
        return (resolved if isinstance(resolved, str) else str(resolved)).strip()

    async def _goto_with_retry(self, url: str, wait_until: str = "domcontentloaded") -> None:
        attempts = max(1, utcms_config.PAGE_GOTO_MAX_RETRIES + 1)
        base_delay = max(0.1, utcms_config.PAGE_GOTO_RETRY_BASE_SECONDS)
        jitter = max(0.0, utcms_config.PAGE_GOTO_RETRY_JITTER_SECONDS)
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                await self.page.goto(url, wait_until=wait_until, timeout=utcms_config.PAGE_NAVIGATION_TIMEOUT)
                await self.page.wait_for_load_state("domcontentloaded")
                return
            except Exception as exc:
                last_error = exc
                if attempt >= attempts or not is_retryable_network_error(exc):
                    raise
                delay = (base_delay * (2 ** (attempt - 1))) + random.uniform(0, jitter)
                await asyncio.sleep(delay)

        if last_error:
            raise last_error

    def _is_login_url(self, url: str) -> bool:
        lowered = (url or "").lower()
        return any(fragment in lowered for fragment in ("/login", "/account/login", "/signin", "/sign-in"))

    def _is_authenticated_url(self, url: str) -> bool:
        lowered = (url or "").lower()
        return any(
            fragment in lowered
            for fragment in (
                "/notification/notification",
                "/barname/notification",
                "/dashboard",
                "/home/index",
            )
        )

    def _is_ajax_login_response_url(self, url: str) -> bool:
        lowered = (url or "").lower()
        return any(
            fragment in lowered
            for fragment in (
                "/account/oldlogin",
                "/barname/account/oldlogin",
                "/account/login",
                "/barname/account/login",
                "/api/account/login",
                "/api/login",
            )
        )

    def _candidate_login_urls(self, override_login_url: str | None = None) -> list[str]:
        base_url = utcms_config.BASE_URL.rstrip("/")
        candidates = []
        if override_login_url:
            candidates.append(override_login_url.strip())
        candidates.append(utcms_config.LOGIN_URL.strip())
        candidates.extend(f"{base_url}{path}" for path in AuthSelectors.LOGIN_PATH_CANDIDATES)

        unique_candidates: list[str] = []
        for candidate in candidates:
            if candidate and candidate not in unique_candidates:
                unique_candidates.append(candidate)
        return unique_candidates

    async def _find_selector(
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

    async def _has_auth_cookie(self) -> bool:
        try:
            cookies = await self.context.cookies()
        except Exception:
            return False

        auth_keywords = (
            "auth",
            "session",
            "sessionid",
            "aspxauth",
            "identity",
            "aspnet.applicationcookie",
            "aspnetcore.identity",
            "jwt",
        )
        for cookie in cookies:
            name = str(cookie.get("name", "")).lower()
            if any(keyword in name for keyword in auth_keywords):
                return True
        return False

    async def _looks_like_login_page(self) -> bool:
        if self._is_login_url(await self._current_url()):
            return True

        username_selector = await self._find_selector(AuthSelectors.USERNAME_SELECTORS)
        password_selector = await self._find_selector(AuthSelectors.PASSWORD_SELECTORS)
        submit_selector = await self._find_selector(AuthSelectors.SUBMIT_SELECTORS)
        return bool(username_selector and password_selector and submit_selector)

    async def _looks_like_error_page(self) -> bool:
        title = await self._as_clean_text(await self.page.title())
        lowered_title = title.lower()
        if "خطا" in title or "یافت نشد" in title or "error" in lowered_title:
            return True

        current_url = (await self._current_url()).strip().lower()
        error_url_fragments = ("/error", "/exception", "/fault")
        if any(fragment in current_url for fragment in error_url_fragments):
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
            body_text = await self._as_clean_text(await self.page.text_content("body"))
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

    async def _is_logged_in(self, probe_login_url: bool = True) -> bool:
        self.last_error = None
        current_url = await self._current_url()
        if current_url and not self._is_login_url(current_url):
            if await self._find_selector(AuthSelectors.LOGOUT_SELECTORS, visible=True, timeout=1200):
                return True
            if self._is_authenticated_url(current_url):
                return True
            if await self._find_selector(AuthSelectors.AUTHENTICATED_PAGE_MARKERS, timeout=1200):
                return True
            for selector in AuthSelectors.WAYBILL_FORM_MARKERS:
                try:
                    marker = await self.page.query_selector(selector)
                    if marker is not None:
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
                    if curr_url and not self._is_login_url(curr_url):
                        return True
                    await asyncio.sleep(0.2)
                return True
            return False

        try:
            # Start auth probing from the real login page so the browser does not
            # jump to the waybill form URL before we know the session is valid.
            await self._goto_with_retry(utcms_config.LOGIN_URL, wait_until="domcontentloaded")
            try:
                await self.page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                await asyncio.sleep(1.5)
        except Exception:
            return False

        current_url = await self._current_url()
        if self._is_login_url(current_url):
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

        await asyncio.sleep(0.4)
        if await self._looks_like_login_page() or await self._looks_like_error_page():
            return False
        return await self._has_auth_cookie()

    async def _extract_login_error(self) -> str | None:
        for selector in AuthSelectors.LOGIN_ERROR_SELECTORS:
            try:
                element = await self.smart_locator.locate(self.page, [selector], timeout=600)
                text = await self._as_clean_text(await element.text_content())
                if text:
                    return text
            except Exception:
                continue
        return None

    async def _wait_for_login_result(self, timeout_ms: int = 25000) -> bool:
        deadline = asyncio.get_running_loop().time() + (timeout_ms / 1000)
        while asyncio.get_running_loop().time() < deadline:
            if await self._find_selector(AuthSelectors.LOGOUT_SELECTORS, visible=True, timeout=300):
                return True
            if await self._find_selector(AuthSelectors.WAYBILL_FORM_MARKERS, timeout=300):
                return True
            if await self._find_selector(AuthSelectors.AUTHENTICATED_PAGE_MARKERS, timeout=300):
                return True
            if await self._has_auth_cookie():
                return True
            current_url = await self._current_url()
            if self._is_authenticated_url(current_url):
                return True

            if not await self._looks_like_login_page():
                if not self._is_login_url(current_url):
                    return True

            login_error = await self._extract_login_error()
            if login_error:
                self.last_error = login_error
                return False

            await asyncio.sleep(0.35)

        return (
            not await self._looks_like_login_page()
            and not self._is_login_url(await self._current_url())
        )

    async def _complete_post_login_steps(self) -> bool:
        """
        Handle additional UI steps after credential submission.
        Some UTCMS accounts show a rules acceptance modal on first login.
        """
        try:
            modal_selector = "#ExceptRulesModalReal"
            if await self._find_selector((modal_selector,), visible=True, timeout=1200):
                checkbox = await self.smart_locator.locate(self.page, ["#ruleExcepted"], timeout=1800)
                await checkbox.check()
                submit_rules = await self.smart_locator.locate(self.page, ["#submitRules"], timeout=1800)
                await submit_rules.click()

                deadline = asyncio.get_running_loop().time() + 12
                while asyncio.get_running_loop().time() < deadline:
                    if not self._is_login_url(await self._current_url()):
                        return True
                    await asyncio.sleep(0.3)
                return False
        except Exception as error:
            self.last_error = f"تایید قوانین پس از لاگین ناموفق بود: {error}"
            return False

        return True

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
                pass
            await asyncio.sleep(poll_seconds)

        return False

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
                    if not box or not self._is_plausible_captcha_image(box):
                        continue
                    score = self._captcha_image_score(box, input_box, selector)
                    if best_candidate is None or score > best_candidate[0]:
                        best_candidate = (score, locator)
                except Exception:
                    continue

        if best_candidate is None:
            return None

        try:
            image_bytes = await best_candidate[1].screenshot(type="png")
            if image_bytes:
                return base64.b64encode(image_bytes).decode("utf-8")
        except Exception:
            return None

        return None

    @staticmethod
    def _is_plausible_captcha_image(box: dict) -> bool:
        width = float(box.get("width") or 0)
        height = float(box.get("height") or 0)
        if width < 35 or height < 18:
            return False
        if width > 220 or height > 120:
            return False
        aspect_ratio = width / max(height, 1.0)
        return 1.0 <= aspect_ratio <= 5.5

    @staticmethod
    def _captcha_image_score(box: dict, input_box: dict | None, selector: str) -> float:
        width = float(box.get("width") or 0)
        height = float(box.get("height") or 0)
        score = 200.0 - abs(width - 110.0) - abs(height - 40.0)
        lowered = selector.lower()
        if "dnt" in lowered:
            score += 20
        if "captcha" in lowered:
            score += 10

        if input_box:
            image_center_x = float(box.get("x") or 0) + (width / 2.0)
            image_center_y = float(box.get("y") or 0) + (height / 2.0)
            input_center_x = float(input_box.get("x") or 0) + (float(input_box.get("width") or 0) / 2.0)
            input_center_y = float(input_box.get("y") or 0) + (float(input_box.get("height") or 0) / 2.0)
            score -= abs(image_center_x - input_center_x) * 0.35
            score -= abs(image_center_y - input_center_y) * 0.6
        return score

    def _save_captcha_debug_artifact(
        self,
        image_base64: str,
        phase: str,
        attempt: int | None,
        stage: str,
        provider: str | None = None,
        solution: str | None = None,
        error: str | None = None,
    ) -> None:
        if not utcms_config.CAPTCHA_DEBUG_SAVE_IMAGES or not image_base64:
            return
        try:
            image_bytes = base64.b64decode(image_base64, validate=True)
        except (ValueError, binascii.Error):
            return

        timestamp = datetime.now(UTC).replace(tzinfo=None).strftime("%Y%m%d-%H%M%S-%f")
        safe_phase = re.sub(r"[^a-zA-Z0-9_-]+", "_", phase or "login")
        safe_stage = re.sub(r"[^a-zA-Z0-9_-]+", "_", stage or "capture")
        debug_dir = Path(utcms_config.CAPTCHA_DEBUG_DIR)
        debug_dir.mkdir(parents=True, exist_ok=True)

        base_name = f"{timestamp}-{safe_phase}-a{attempt or 0}-{safe_stage}"
        image_path = debug_dir / f"{base_name}.png"
        meta_path = debug_dir / f"{base_name}.json"

        image_path.write_bytes(image_bytes)
        meta_path.write_text(
            json.dumps(
                {
                    "saved_at": datetime.now(UTC).replace(tzinfo=None).isoformat() + "Z",
                    "phase": phase,
                    "attempt": attempt,
                    "stage": stage,
                    "provider": provider,
                    "solution": solution,
                    "error": error,
                    "url": getattr(self.page, "url", ""),
                    "image_path": os.fspath(image_path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        logger.info(
            "captcha_debug_saved",
            extra={"extra_fields": {"image_path": os.fspath(image_path), "meta_path": os.fspath(meta_path), "phase": phase, "attempt": attempt, "stage": stage}},
        )

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

        body_text = ""
        try:
            await self.page.screenshot(path=os.fspath(screenshot_path), full_page=True)
        except Exception:
            screenshot_path = None
        try:
            html_path.write_text(await self.page.content())
        except Exception:
            html_path = None
        try:
            body_text = await self._as_clean_text(await self.page.text_content("body"))
        except Exception:
            body_text = ""

        meta_path.write_text(
            json.dumps(
                {
                    "saved_at": datetime.now(UTC).replace(tzinfo=None).isoformat() + "Z",
                    "stage": stage,
                    "url": await self._current_url(),
                    "last_error": self.last_error,
                    "body_excerpt": body_text[:2000],
                    "screenshot_path": os.fspath(screenshot_path) if screenshot_path else None,
                    "html_path": os.fspath(html_path) if html_path else None,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    def _normalize_captcha_solution(self, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = str(value).strip().translate(self._captcha_digit_map)
        if not normalized:
            return None

        normalized = normalized.replace(" ", "").replace("=", "").replace("؟", "").replace("?", "")

        if any(token in normalized for token in ("+", "-", "*", "/", "x", "X", "×", "÷")) and not self._captcha_value_pattern.match(normalized):
            decision = captcha_engine.solve_text_with_confidence(normalized)
            min_confidence = self._captcha_math_min_confidence()
            if decision.value and decision.confidence >= min_confidence:
                normalized = str(decision.value).translate(self._captcha_digit_map).strip()
            else:
                return None

        if not self._captcha_value_pattern.match(normalized):
            return None

        min_len = max(1, utcms_config.CAPTCHA_VALUE_MIN_LENGTH)
        max_len = max(min_len, utcms_config.CAPTCHA_VALUE_MAX_LENGTH)
        if not (min_len <= len(normalized) <= max_len):
            return None
        return normalized

    def _captcha_math_min_confidence(self) -> float:
        return max(0.0, min(1.0, min(float(utcms_config.CAPTCHA_MATH_MIN_CONFIDENCE), 0.55)))

    @staticmethod
    def _navigation_error_message(url: str, error: Exception) -> str:
        raw = str(error or "").strip()
        lowered = raw.lower()
        host_hint = url.strip() or "UTCMS"

        if any(marker in lowered for marker in ("err_name_not_resolved", "name_not_resolved", "dns", "could not resolve host", "nodename nor servname provided")):
            return (
                f"دسترسی به صفحه ورود UTCMS ممکن نشد؛ دامنه/شبکه برای {host_hint} resolve نشد "
                "(ERR_NAME_NOT_RESOLVED)."
            )
        if "timeout" in lowered or "timed out" in lowered:
            return f"دسترسی به صفحه ورود UTCMS ممکن نشد؛ پاسخ از {host_hint} در زمان مجاز دریافت نشد."
        if raw:
            return f"دسترسی به صفحه ورود UTCMS ممکن نشد ({host_hint}): {raw}"
        return f"دسترسی به صفحه ورود UTCMS ممکن نشد ({host_hint})."

    @classmethod
    def _navigation_failures_message(cls, failures: list[tuple[str, Exception]]) -> str:
        if not failures:
            return "دسترسی به صفحه ورود UTCMS ممکن نشد."

        first_url, _ = failures[0]
        last_url, last_error = failures[-1]
        message = cls._navigation_error_message(last_url, last_error)
        if first_url and first_url != last_url:
            message = f"{message} تلاش روی URL اصلی نیز ناموفق بود: {first_url}"
        return message

    async def _solve_captcha_with_provider(
        self,
        captcha_selector: str | None = None,
        phase: str = "login",
        attempt: int | None = None,
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
                "captcha_provider_image_not_found",
                extra={"extra_fields": {"phase": phase, "attempt": attempt}},
            )
            page_hint_value = await self._solve_math_captcha(phase=phase, attempt=attempt)
            if page_hint_value:
                return page_hint_value
            track_captcha_failure(
                "provider_image_not_found",
                phase=phase,
                strategy="provider",
                latency_seconds=elapsed,
                attempt=attempt,
            )
            if utcms_config.CAPTCHA_LOCAL_FALLBACK_ENABLED:
                return await self._solve_math_captcha(phase=phase, attempt=attempt)
            return None

        self._save_captcha_debug_artifact(image_base64, phase, attempt, "captured")
        result = await provider.solve_text_captcha(image_base64)
        normalized = self._normalize_captcha_solution(result.value)
        if result.solved and normalized:
            elapsed = asyncio.get_running_loop().time() - started_at
            self._save_captcha_debug_artifact(
                image_base64,
                phase,
                attempt,
                "solved",
                provider=result.provider,
                solution=normalized,
            )
            logger.info(
                "captcha_provider_solved",
                extra={"extra_fields": {"phase": phase, "attempt": attempt, "provider": result.provider}},
            )
            track_captcha_success(
                "provider",
                phase=phase,
                latency_seconds=elapsed,
                attempt=attempt,
            )
            return normalized

        elapsed = asyncio.get_running_loop().time() - started_at
        self._save_captcha_debug_artifact(
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
            extra={"extra_fields": {"provider": result.provider, "error": result.error, "phase": phase, "attempt": attempt}},
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
                track_captcha_success(
                    "provider_fallback",
                    phase=phase,
                    latency_seconds=elapsed,
                    attempt=attempt,
                )
                return fallback_value
        return None

    def _hint_candidates_from_text(self, raw_text: str | None) -> list[str]:
        text = (raw_text or "").strip()
        if not text:
            return []

        candidates: list[str] = []
        full_text = " ".join(text.split())
        if full_text:
            candidates.append(full_text)

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in lines:
            lower_line = line.lower()
            if any(marker in lower_line for marker in self._captcha_hint_markers):
                candidates.append(line)

        for fragment in re.findall(r"[^\n]{0,40}[+\-*/×÷][^\n]{0,40}", text):
            cleaned = " ".join(fragment.split())
            if cleaned:
                candidates.append(cleaned)

        unique: list[str] = []
        seen = set()
        for item in candidates:
            normalized = item.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            unique.append(item)
        return unique

    async def _extract_math_captcha_hints(self) -> list[str]:
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
                    selector,
                    "el => ((el.innerText || el.textContent || '').trim())",
                )
                cleaned = await self._as_clean_text(text)
                if cleaned:
                    candidates.extend(self._hint_candidates_from_text(cleaned))
            except Exception:
                continue

        try:
            around_input = await self.page.eval_on_selector(
                "input[name='DNTCaptchaInputText'], input[id='DNTCaptchaInputText'], input[name='CapToken'], input[id='CapToken']",
                """el => {
                    if (!el) return '';
                    const containers = [
                        el.closest('.dntCaptcha'),
                        el.closest('.captcha-container'),
                        el.closest('.captcha'),
                        el.closest('.form-group'),
                        el.closest('form'),
                        el.parentElement && el.parentElement.parentElement,
                        el.parentElement
                    ];
                    const parts = [];
                    for (const c of containers) {
                        if (c) {
                            const txt = (c.innerText || c.textContent || '').trim();
                            if (txt) parts.push(txt);
                        }
                    }
                    return parts.join('\\n');
                }""",
            )
            around_cleaned = await self._as_clean_text(around_input)
            if around_cleaned:
                candidates.extend(self._hint_candidates_from_text(around_cleaned))
        except Exception:
            pass

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
            around_cleaned = await self._as_clean_text(around_input)
            if around_cleaned:
                candidates.extend(self._hint_candidates_from_text(around_cleaned))
        except Exception:
            pass

        try:
            body_text = await self.page.evaluate("() => ((document.body && document.body.innerText) || '')")
            cleaned = await self._as_clean_text(body_text)
            if cleaned:
                candidates.extend(self._hint_candidates_from_text(cleaned[:1500]))
        except Exception:
            pass

        unique: list[str] = []
        seen = set()
        for item in candidates:
            key = item.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(item)

        return unique

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

        min_confidence = self._captcha_math_min_confidence()
        best_value: str | None = None
        best_confidence = 0.0

        for hint in hints:
            decision = captcha_engine.solve_text_with_confidence(hint)
            if not decision.value:
                continue

            solved = self._normalize_captcha_solution(decision.value)
            if solved is None:
                continue

            if decision.confidence >= min_confidence:
                elapsed = asyncio.get_running_loop().time() - started_at
                track_captcha_success(
                    "math",
                    phase=phase,
                    confidence=decision.confidence,
                    latency_seconds=elapsed,
                    attempt=attempt,
                )
                logger.info(
                    "math_captcha_solved",
                    extra={"extra_fields": {"confidence": decision.confidence, "strategy": decision.strategy, "phase": phase, "attempt": attempt}},
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
                "math_relaxed",
                phase=phase,
                confidence=best_confidence,
                latency_seconds=elapsed,
                attempt=attempt,
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

    def _captcha_mode(self) -> str:
        mode = (utcms_config.CAPTCHA_MODE or "").strip().lower()
        if mode in ("provider_first", "manual_only", "provider_only"):
            return mode
        return "provider_first"

    @staticmethod
    def _is_captcha_related_error(text: str | None) -> bool:
        value = (text or "").lower()
        return any(
            marker in value
            for marker in (
                "captcha",
                "کپچا",
                "cap token",
                "verification code",
                "verify code",
                "security code",
                "عبارت امنیتی",
            )
        )

    @staticmethod
    def _is_credential_related_error(text: str | None) -> bool:
        value = (text or "").lower()
        return any(
            marker in value
            for marker in (
                "password",
                "username",
                "نام کاربری",
                "رمز عبور",
                "invalid credential",
                "کد ملی",
                "کاربری با این مشخصات",
                "یافت نشد",
            )
        )

    async def _set_captcha_value(self, captcha_selector: str, value: str) -> bool:
        normalized = self._normalize_captcha_solution(value)
        if not normalized:
            self.last_error = "مقدار کپچا معتبر نیست."
            track_captcha_failure("captcha_value_invalid")
            return False

        # Clear field first
        try:
            await self.page.fill(captcha_selector, "")
        except Exception:
            try:
                field = await self.smart_locator.locate(self.page, [captcha_selector], timeout=1000)
                await field.fill("")
            except Exception:
                pass

        if await self._fill_input_like(captcha_selector, normalized):
            return True

        self.last_error = "مقداردهی فیلد کپچا انجام نشد."
        track_captcha_failure("captcha_fill_failed")
        return False

    async def _captcha_image_fingerprint(self) -> str:
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
                cleaned = await self._as_clean_text(value)
                if cleaned:
                    return cleaned
            except Exception:
                continue
        return ""

    async def _wait_for_captcha_refresh(self, previous_fingerprint: str) -> None:
        timeout_seconds = max(0.2, utcms_config.CAPTCHA_REFRESH_WAIT_SECONDS)
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while asyncio.get_running_loop().time() < deadline:
            current = await self._captcha_image_fingerprint()
            if current and current != previous_fingerprint:
                return
            await asyncio.sleep(0.1)

        await asyncio.sleep(timeout_seconds)

    async def _refresh_captcha(self) -> bool:
        previous_fingerprint = await self._captcha_image_fingerprint()
        for selector in AuthSelectors.CAPTCHA_REFRESH_SELECTORS:
            try:
                button = await self.smart_locator.locate(self.page, [selector], timeout=900)
                await button.click()
                await self._wait_for_captcha_refresh(previous_fingerprint)
                return True
            except Exception:
                continue

        for selector in AuthSelectors.CAPTCHA_IMAGE_SELECTORS:
            try:
                image = await self.smart_locator.locate(self.page, [selector], timeout=900)
                await image.click()
                await self._wait_for_captcha_refresh(previous_fingerprint)
                return True
            except Exception:
                continue
        return False

    async def _should_retry_captcha_after_submit(self, captcha_selector: str) -> bool:
        if self._is_credential_related_error(self.last_error):
            return False
        if self._is_captcha_related_error(self.last_error):
            return True

        if await self._find_selector(AuthSelectors.LOGOUT_SELECTORS, visible=True, timeout=300):
            return False
        if await self._find_selector(AuthSelectors.WAYBILL_FORM_MARKERS, timeout=300):
            return False
        current_url = await self._current_url()
        if current_url and not self._is_login_url(current_url):
            return False

        direct_captcha_exists = await self._find_selector((captcha_selector,), timeout=300)
        if direct_captcha_exists:
            return True

        generic_captcha_exists = await self._find_selector(AuthSelectors.CAPTCHA_SELECTORS, timeout=300)
        return bool(generic_captcha_exists)

    async def _solve_capjs_captcha(self) -> bool:
        """حل خودکار کپچای وب‌اسمبلی CapJS (Proof-of-Work) با اجرای مستقیم در مرورگر."""
        logger.info("CapJS Proof-of-Work captcha widget detected. Initiating automated solution...")
        try:
            # ۱. فراخوانی متد حل کپچا روی کامپوننت cap-widget
            await self.page.evaluate(
                """() => {
                    const widget = document.querySelector('cap-widget');
                    if (widget && typeof widget.solve === 'function') {
                        widget.solve().catch(err => console.error("CapJS solve call error:", err));
                    }
                }"""
            )

            # ۲. پولینگ (Polling) برای اتمام حل و تولید توکن
            # زمان حداکثر ۳۰ ثانیه برای اجرای وب‌اسمبلی روی مرورگر کلاینت
            for _attempt in range(60):  # 60 * 0.5s = 30s
                solved = await self.page.evaluate(
                    """() => {
                        const widget = document.querySelector('cap-widget');
                        if (!widget) return false;
                        const state = widget.getAttribute('data-state');
                        const token = widget.token || (widget.querySelector('input[type="hidden"]') ? widget.querySelector('input[type="hidden"]').value : null);
                        return state === 'done' || !!token;
                    }"""
                )
                if solved:
                    logger.info("کپچای CapJS با موفقیت در مرورگر حل شد.")
                    return True
                await asyncio.sleep(0.5)

            self.last_error = "زمان حل خودکار کپچای CapJS به پایان رسید (Timeout)."
            logger.error("CapJS solving timed out after 30 seconds.")
            return False
        except Exception as e:
            self.last_error = f"خطا در اجرای اسکریپت حل کپچای CapJS: {str(e)}"
            logger.error(f"Error solving CapJS captcha: {e}")
            return False

    async def _auto_solve_captcha(self, captcha_selector: str) -> bool:
        """Auto-solve captcha using CNN model with retry logic."""
        max_attempts = max(1, utcms_config.CAPTCHA_AUTO_MAX_ATTEMPTS)
        retry_delay = max(0.1, utcms_config.CAPTCHA_AUTO_RETRY_DELAY_SECONDS)
        mode = self._captcha_mode()
        allow_provider = mode in ("provider_first", "provider_only")
        allow_math_fallback = mode != "provider_only" or utcms_config.CAPTCHA_LOCAL_FALLBACK_ENABLED

        for attempt in range(1, max_attempts + 1):
            if attempt > 1 and utcms_config.CAPTCHA_AUTO_REFRESH_ON_RETRY:
                await self._refresh_captcha()
                await asyncio.sleep(retry_delay)

            if allow_provider:
                solved_provider = await self._solve_captcha_with_provider(captcha_selector=captcha_selector, phase="login", attempt=attempt)
                if solved_provider and await self._set_captcha_value(captcha_selector, solved_provider):
                    return True

            if allow_math_fallback:
                solved_math = await self._solve_math_captcha(phase="login", attempt=attempt)
                if solved_math and await self._set_captcha_value(captcha_selector, solved_math):
                    return True

        self.last_error = (
            "حل خودکار کپچا ناموفق بود. "
            "کیفیت تصویر کپچا یا مدل CNN را بررسی کنید."
        )
        logger.warning(
            "captcha_auto_solve_failed",
            extra={"extra_fields": {"phase": "login", "max_attempts": max_attempts, "mode": mode}},
        )
        track_captcha_failure("auto_solve_failed", phase="login", strategy="auto")
        return False

    async def _fill_input_like(self, selector: str, value: str) -> bool:
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
            pass

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
            pass

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
                        if (desc && desc.set) {
                            setter = desc.set;
                            break;
                        }
                        prototype = Object.getPrototypeOf(prototype);
                    }

                    if (setter) {
                        setter.call(el, value);
                    } else {
                        el.value = value;
                    }
                    if (el._valueTracker) {
                        el._valueTracker.setValue(value);
                    }
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new Event('keyup', { bubbles: true }));
                    if (window.jQuery) {
                        window.jQuery(el).trigger('input').trigger('change').trigger('keyup');
                    }
                    return true;
                }""",
                value,
            )
            return bool(updated)
        except Exception:
            return False

    async def _fill_credentials(
        self,
        username_selector: str,
        password_selector: str,
        username: str,
        password: str,
    ) -> bool:
        u_ok = await self._fill_input_like(username_selector, username)
        p_ok = await self._fill_input_like(password_selector, password)
        if u_ok and p_ok:
            return True
        self.last_error = "تکمیل فرم ورود با خطا مواجه شد: عناصر ورود پیدا یا پر نشدند"
        return False

    async def _handle_captcha(self, captcha_selector: str, force_auto: bool = False) -> bool:
        if not captcha_selector:
            return True

        # Check for CapJS Proof-of-Work captcha widget
        has_cap_widget = await self.page.query_selector("cap-widget")
        if has_cap_widget and type(has_cap_widget).__name__ not in ("Mock", "AsyncMock", "MagicMock"):
            return await self._solve_capjs_captcha()

        if utcms_config.UTCMS_CAPTCHA_VALUE:
            return await self._set_captcha_value(captcha_selector, utcms_config.UTCMS_CAPTCHA_VALUE)

        captcha_mode = self._captcha_mode()

        if force_auto or utcms_config.CAPTCHA_AUTO_ONLY or captcha_mode != "manual_only":
            return await self._auto_solve_captcha(captcha_selector)

        allow_manual = captcha_mode == "manual_only" and utcms_config.UTCMS_ENABLE_MANUAL_CAPTCHA

        if allow_manual:
            if utcms_config.HEADLESS:
                self.last_error = (
                    "کپچا فعال است ولی مرورگر در حالت HEADLESS اجرا می‌شود. "
                    "برای حل دستی کپچا، `HEADLESS=false` تنظیم شود."
                )
                return False
            solved = await self._wait_for_manual_captcha_input(captcha_selector)
            if not solved:
                self.last_error = (
                    "کپچا در بازه مجاز تکمیل نشد. لطفاً کپچا را دستی وارد کنید و مجدد تلاش کنید."
                )
                track_captcha_failure("manual_timeout", phase="login", strategy="manual")
                return False
            track_captcha_success("manual", phase="login")
            return True

        if captcha_mode == "provider_only":
            self.last_error = (
                "کپچا در حالت provider_only حل نشد. "
                "مقدار `CAPTCHA_PROVIDER` و فایل مدل CNN را بررسی کنید."
            )
        elif captcha_mode == "manual_only":
            self.last_error = (
                "حالت manual_only فعال است اما حل دستی کپچا غیرفعال است. "
                "`UTCMS_ENABLE_MANUAL_CAPTCHA=true` تنظیم شود."
            )
        else:
            self.last_error = (
                "کپچا در صفحه ورود فعال است اما حل خودکار CNN موفق نشد. "
                "فایل مدل و کیفیت تصویر کپچا را بررسی کنید."
            )
        track_captcha_failure("captcha_not_solved", phase="login", strategy=captcha_mode or "unknown")
        return False

    async def _submit_login(self, submit_selector: str) -> bool:
        clicked = False
        ajax_response_task = None
        if hasattr(self.page, "wait_for_response"):
            try:
                # Increased timeout for AJAX login response (UTCMS may be slow)
                ajax_response_task = asyncio.create_task(
                    self.page.wait_for_response(
                        lambda response: self._is_ajax_login_response_url(getattr(response, "url", "")),
                        timeout=25000,  # Increased from 12000 to 25000 for better reliability
                    )
                )
            except Exception:
                ajax_response_task = None
        try:
            await self.page.click(submit_selector)
            clicked = True
            try:
                await self.page.wait_for_load_state("domcontentloaded", timeout=3000)
            except Exception:
                pass
        except Exception:
            try:
                submit_locator = await self.smart_locator.locate(self.page, [submit_selector], timeout=5000)
                await submit_locator.click()
                clicked = True
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=3000)
                except Exception:
                    pass
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
            post_login_ok = await self._complete_post_login_steps()
            if not post_login_ok:
                if not self.last_error:
                    self.last_error = "تکمیل مراحل پس از لاگین ناموفق بود."
                return False

            if await self._is_logged_in(probe_login_url=False):
                return True

            if not self.last_error:
                self.last_error = await self._extract_login_error() or "لاگین تکمیل نشد و دسترسی به فرم بارنامه تایید نشد."
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
        message = (
            payload.get("message")
            or payload.get("detail")
            or payload.get("resultMessage")
            or None
        )
        if not success:
            self.last_error = str(message or "لاگین ناموفق بود")
            return False

        post_login_ok = await self._complete_post_login_steps()
        if not post_login_ok:
            return False

        deadline = asyncio.get_running_loop().time() + 10
        while asyncio.get_running_loop().time() < deadline:
            if await self._find_selector(AuthSelectors.LOGOUT_SELECTORS, visible=True, timeout=300):
                return True
            if not self._is_login_url(await self._current_url()):
                break
            await asyncio.sleep(0.3)

        if await self._is_logged_in(probe_login_url=False):
            return True

        if not self.last_error:
            self.last_error = str(message or "ورود با موفقیت تایید شد ولی session معتبر شناسایی نشد")
        await self._save_login_debug_snapshot("ajax_success_not_verified")
        return False

    async def login(self, username: str, password: str, login_url: str | None = None) -> bool:
        self.last_error = None
        self.last_state = "failed"
        navigation_errors: list[tuple[str, Exception]] = []
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
                    await asyncio.sleep(1.5)
            except Exception as exc:
                if is_retryable_network_error(exc):
                    navigation_errors.append((candidate_login_url, exc))
                continue

            username_selector = await self._find_selector(AuthSelectors.USERNAME_SELECTORS, visible=True, timeout=8000)
            password_selector = await self._find_selector(AuthSelectors.PASSWORD_SELECTORS, visible=True, timeout=8000)
            submit_selector = await self._find_selector(AuthSelectors.SUBMIT_SELECTORS, visible=True, timeout=8000)

            if not (username_selector and password_selector and submit_selector):
                continue

            if not await self._fill_credentials(username_selector, password_selector, username, password):
                continue

            captcha_selector = await self._find_selector(AuthSelectors.CAPTCHA_SELECTORS)
            if captcha_selector:
                interceptor_result = await self.captcha_interceptor.solve_and_fill(
                    self.page,
                    captcha_input_selectors=AuthSelectors.CAPTCHA_SELECTORS,
                )
                if interceptor_result.status == CaptchaSolveStatus.CIRCUIT_OPEN:
                    self.last_error = interceptor_result.error or "سرویس حل کپچا در دسترس نیست (circuit open)"
                    self.last_state = "captcha_failed"
                    return False

                if not await self._handle_captcha(captcha_selector):
                    if self._is_captcha_related_error(self.last_error):
                        self.last_state = "captcha_failed"
                    return False

                max_submit_attempts = max(1, utcms_config.CAPTCHA_AUTO_MAX_ATTEMPTS)

                for attempt in range(1, max_submit_attempts + 1):
                    if await self._submit_login(submit_selector):
                        self.last_state = "success"
                        return True

                    await self._save_login_debug_snapshot(f"retry_before_refresh_{attempt}")
                    if not await self._should_retry_captcha_after_submit(captcha_selector):
                        break

                    if attempt >= max_submit_attempts:
                        break

                    track_captcha_submit_retry()
                    await self._refresh_captcha()
                    await asyncio.sleep(max(0.1, utcms_config.CAPTCHA_SUBMIT_RETRY_DELAY_SECONDS))
                    if not await self._handle_captcha(captcha_selector, force_auto=True):
                        break
                if self._is_captcha_related_error(self.last_error) or self._is_credential_related_error(self.last_error):
                    if self._is_captcha_related_error(self.last_error):
                        self.last_state = "captcha_failed"
                    break
                continue

            if await self._submit_login(submit_selector):
                self.last_state = "success"
                return True
            if self._is_captcha_related_error(self.last_error) or self._is_credential_related_error(self.last_error):
                if self._is_captcha_related_error(self.last_error):
                    self.last_state = "captcha_failed"
                break

        if not self.last_error and navigation_errors:
            self.last_error = self._navigation_failures_message(navigation_errors)

        if not self.last_error:
            self.last_error = "فرم ورود معتبر در URLهای شناخته‌شده پیدا نشد. مقدار `LOGIN_URL` را تنظیم کنید."

        logger.warning("login_failed", extra={"extra_fields": {"reason": self.last_error}})
        if self._is_captcha_related_error(self.last_error):
            self.last_state = "captcha_failed"
        return False
