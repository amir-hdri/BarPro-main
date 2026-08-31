"""UTCMS HTTP-only login via curl_cffi (bypass WAF TLS fingerprinting).

This module performs a fully HTTP-level login to UTCMS without launching
Playwright. The goal is to bypass the WAF that flags Chromium's TLS
fingerprint (JA3/JA4). ``curl_cffi`` emulates the exact ``ClientHello``
of a real Chrome browser so the WAF treats the request as a genuine
desktop Chrome session.

Hybrid flow (called from ``UTCMSAuthenticator.login``):
  1. ``authenticate()``  →  HTTP POST to /Barname/Account/Login
                              ↳ returns the ASP.NET auth cookie(s)
  2. The cookies are then injected into the Playwright BrowserContext
     via ``inject_cookies_into_context()`` so the rest of the RPA flow
     (waybill submission, navigation, etc.) continues to use the real
     Chromium browser with a valid session.

The CAPTCHA is solved by the **same local ML models** that the
Playwright flow uses (``app.automation.captcha.get_captcha_provider``).
The captcha image is downloaded as bytes (over the same HTTP session)
and passed as base64 to the provider — no behavioural change.
"""

from __future__ import annotations

import asyncio
import base64
import functools
import hashlib
import logging
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC
from typing import Any
from urllib.parse import urljoin, urlparse

from app.core.config import utcms_config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public data classes
# ---------------------------------------------------------------------------


@dataclass
class HttpLoginResult:
    """Outcome of an ``UtcmsHttpLogin.authenticate()`` call.

    Attributes:
        success: True if we obtained a valid auth cookie from UTCMS.
        cookies: A list of ``{"name": ..., "value": ..., "domain": ...,
            "path": ...}`` dicts suitable for ``context.add_cookies()``.
        error: Human-readable error message (Persian) when ``success``
            is False; ``None`` on success.
        final_url: The URL the server redirected to after a successful
            login (or the original URL if no redirect happened). Useful
            for diagnostic logging.
        status_code: HTTP status of the POST response.
    """

    success: bool
    cookies: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    final_url: str | None = None
    status_code: int | None = None


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

# ASP.NET Core antiforgery token. UTCMS renders it as:
#   <input name="RequestVerificationToken" ...>   (no leading "__")
# while the classic ASP.NET MVC convention uses "__RequestVerificationToken".
# Accept both spellings (regexes are case-insensitive).
_ANTIFORGERY_RE = re.compile(
    r'<input[^>]+name=["\']_*RequestVerificationToken["\'][^>]+value=["\']([^"\']+)["\']',
    re.IGNORECASE,
)

# DNT captcha: <input name="DNTCaptchaToken" value="..."> (hidden server token)
_DNT_CAPTCHA_TOKEN_RE = re.compile(
    r'<input[^>]+name=["\']DNTCaptchaToken["\'][^>]+value=["\']([^"\']+)["\']',
    re.IGNORECASE,
)

# DNT captcha text: <input name="DNTCaptchaText" value="..."> (hidden per-image token)
_DNT_CAPTCHA_TEXT_RE = re.compile(
    r'<input[^>]+name=["\']DNTCaptchaText["\'][^>]+value=["\']([^"\']+)["\']',
    re.IGNORECASE,
)

# CapType hidden field (1 = standard DNT math captcha on the login page).
_CAP_TYPE_RE = re.compile(
    r'<input[^>]+name=["\']CapType["\'][^>]+value=["\']([^"\']+)["\']',
    re.IGNORECASE,
)

# The login <form> declares its AJAX endpoint:
#   <form ... data-ajax="true" data-ajax-url="/Barname/Account/OldLogin" ...>
_FORM_AJAX_URL_RE = re.compile(
    r'<form[^>]+data-ajax-url=["\']([^"\']+)["\']',
    re.IGNORECASE,
)

# Captcha image: <img ... id="dntCaptchaImg" src="..." > OR <img src="...captcha...">
_CAPTCHA_IMG_RE = re.compile(
    r'<img[^>]+(?:id=["\'][^"\']*captcha[^"\']*["\']|src=["\'][^"\']*captcha[^"\']*["\'])'
    r'[^>]*src=["\']([^"\']+)["\']',
    re.IGNORECASE,
)

# Generic captcha <img ... src="..."> as a last resort — we filter by URL keyword.
_CAPTCHA_IMG_FALLBACK_RE = re.compile(
    r'<img[^>]+src=["\']([^"\']*captcha[^"\']*)["\']',
    re.IGNORECASE,
)

# Inline captcha <svg>/<canvas>/... are not handled by HTTP mode (UTCMS login
# page uses an <img> for the math captcha, not a JS widget).


# Login error markers (Persian). UTCMS shows these in <div class="text-danger">.
_LOGIN_ERROR_PATTERNS: tuple[str, ...] = (
    "کد ملی یا رمز عبور اشتباه است",
    "رمز عبور اشتباه است",
    "نام کاربری یا رمز عبور",
    "کاربری با این مشخصات یافت نشد",
    "عبارت امنیتی اشتباه است",
    "کد امنیتی اشتباه است",
    "captcha is not valid",
    "captcha invalid",
    "verification code is invalid",
    "login failed",
    "invalid username or password",
)


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------


class UtcmsHttpLogin:
    """HTTP-level UTCMS login using curl_cffi's Chrome TLS fingerprint.

    The class is **stateful** in the sense that it owns a single
    ``curl_cffi.requests.Session`` for the lifetime of one login
    attempt. After ``authenticate()`` returns, the caller can use
    ``inject_cookies_into_context()`` to migrate the obtained cookies
    into a Playwright ``BrowserContext``.
    """

    # Chrome impersonation profile. We use 120 (stable, mid-2024) because
    # the rest of the project already advertises a similar Chrome version
    # in its User-Agent and the WAF sees a consistent fingerprint.
    DEFAULT_IMPERSONATE = "chrome120"

    # Request timeout for the whole handshake (TLS + page load).
    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        *,
        login_url: str | None = None,
        proxy_url: str | None = None,
        impersonate: str = DEFAULT_IMPERSONATE,
        timeout: float = DEFAULT_TIMEOUT,
        user_agent: str | None = None,
    ) -> None:
        raw_login_url = (login_url or utcms_config.LOGIN_URL).strip()
        if "/barname/account/login" in raw_login_url.lower():
            raw_login_url = raw_login_url.replace("/Barname/Account/Login", "/Account/Login").replace("/barname/account/login", "/Account/Login")
        self._login_url = raw_login_url
        if proxy_url is None:
            # Use the worker's configured proxy by default.
            try:
                from app.automation.worker_proxy import get_worker_proxy_url

                proxy_url = get_worker_proxy_url()
            except Exception:
                proxy_url = ""
        self._proxy_url = (proxy_url or "").strip() or None
        self._impersonate = impersonate
        self._timeout = timeout
        self._user_agent = user_agent or self._build_user_agent()
        # Lazy import so the rest of the project can start without
        # curl_cffi installed (the dependency is only required at the
        # worker runtime, not at API startup).
        self._session: Any = None  # curl_cffi.requests.Session
        self._authenticated_session: Any = None
        # libcurl handles must not be driven from alternating threads.  Pin all
        # curl operations for this login to a single worker thread so the shared
        # asyncio pool can't scatter the handshake across threads (which UTCMS
        # answers with an intermittent TLS reset on the login GET).
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="utcms-login"
        )
        self._antiforgery: str | None = None
        self._captcha_token: str | None = None
        self._captcha_text: str | None = None
        self._cap_type: str | None = None
        self._captcha_image_bytes: bytes | None = None
        self._captcha_image_url: str | None = None

    async def _call(self, func: Any, /, *args: Any, **kwargs: Any) -> Any:
        """Run a curl_cffi session operation on this login's pinned thread."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor, functools.partial(func, *args, **kwargs)
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    # Backoff (seconds) applied after the WAF answers HTTP 429 (rate limit).
    # Stability probe showed 4-5 rapid logins trigger a short 429 window that
    # clears after ~30s; we wait a little longer so the retry has a real chance.
    RATE_LIMIT_BACKOFF_SECONDS = 25.0

    # Upstream/proxy hiccups that say nothing about our credentials. Observed in
    # production: a single HTTP 503 on the POST to /Barname/Account/OldLogin
    # aborted the whole HTTP path and pushed the flow onto the WAF-blocked
    # Playwright fallback, which burns ~3 minutes per attempt and blows the
    # Celery task budget. Retrying with a fresh session is far cheaper.
    TRANSIENT_STATUS_CODES = (408, 500, 502, 503, 504)
    TRANSIENT_BACKOFF_SECONDS = 6.0
    TRANSIENT_MAX_RETRIES = 3
    # A TLS handshake reset ("Connection closed abruptly") on the login GET is
    # the WAF throttling *new* handshakes from this egress IP after a burst of
    # logins.  The throttle window lasts minutes, so a fixed short backoff just
    # keeps the IP hot and never escapes it.  Retry the transport-level failure
    # more times with exponential backoff + jitter so the wait can straddle the
    # cool-down window instead of hammering inside it.
    TRANSPORT_MAX_RETRIES = 5
    TRANSPORT_BACKOFF_BASE = 8.0
    TRANSPORT_BACKOFF_CAP = 90.0

    async def authenticate(self, username: str, password: str) -> HttpLoginResult:
        """Run the full HTTP login flow with transparent retries.

        One attempt = GET login page → solve captcha → POST credentials.
        Retries:
          * wrong captcha (کد امنیتی/عبارت امنیتی) → fresh page render so a
            brand new captcha + tokens are used (up to CAPTCHA_AUTO_MAX_ATTEMPTS).
          * HTTP 429 (WAF rate limit) → sleep RATE_LIMIT_BACKOFF_SECONDS, then
            retry with a brand new curl_cffi session (up to 3 times).
          * HTTP 408/5xx (upstream or proxy hiccup) → sleep
            TRANSIENT_BACKOFF_SECONDS, then retry with a brand new session
            (up to TRANSIENT_MAX_RETRIES times).

        Each retry class keeps its own budget, so a transient 503 never eats
        into the (paid) captcha-solve allowance and vice versa.

        Returns:
            HttpLoginResult with success=True and the auth cookies on success.
        """
        from curl_cffi import requests as cc_requests  # type: ignore[import-not-found]

        if not username or not password:
            return HttpLoginResult(success=False, error="نام کاربری یا رمز عبور خالی است")

        _digit_map = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        username = str(username).translate(_digit_map).strip()
        password = str(password).translate(_digit_map).strip()

        captcha_attempts_left = max(4, getattr(utcms_config, "CAPTCHA_AUTO_MAX_ATTEMPTS", 4))
        last_result: HttpLoginResult | None = None
        self._authenticated_session = None
        rate_limit_retries_left = 3
        transient_retries_left = self.TRANSIENT_MAX_RETRIES
        transport_retries_left = self.TRANSPORT_MAX_RETRIES
        attempt = 0

        while captcha_attempts_left > 0:
            attempt += 1
            captcha_attempts_left -= 1
            self._session = self._build_session(cc_requests)
            try:
                result = await self._attempt_single_session(username, password)
                if result.success:
                    # Keep the exact curl session that completed login. UTCMS
                    # binds the authenticated menu/form flow to more than the
                    # four visible cookies; rebuilding a fresh session from
                    # those cookies can redirect back to Login. Transfer
                    # ownership to the browser bridge instead of closing it
                    # in the finally block below.
                    self._authenticated_session = self._session
                    self._session = None
            finally:
                try:
                    if self._session is not None:
                        await self._call(self._session.close)
                except Exception:
                    logger.debug("utcms_http_login_session_close_failed", exc_info=True)
                self._session = None

            last_result = result
            if result.success:
                return result

            error = result.error or ""
            if result.status_code == 429 and rate_limit_retries_left > 0:
                rate_limit_retries_left -= 1
                captcha_attempts_left += 1  # a rate limit is not a captcha miss
                logger.warning(
                    "utcms_http_login_rate_limited_backoff",
                    extra={"extra_fields": {"backoff": self.RATE_LIMIT_BACKOFF_SECONDS}},
                )
                await asyncio.sleep(self.RATE_LIMIT_BACKOFF_SECONDS)
                continue
            if result.status_code in self.TRANSIENT_STATUS_CODES and transient_retries_left > 0:
                transient_retries_left -= 1
                captcha_attempts_left += 1  # an upstream 5xx is not a captcha miss
                logger.warning(
                    "utcms_http_login_transient_status_retry",
                    extra={
                        "extra_fields": {
                            "status": result.status_code,
                            "attempt": attempt,
                            "backoff": self.TRANSIENT_BACKOFF_SECONDS,
                            "retries_left": transient_retries_left,
                            "error": error[:160],
                        }
                    },
                )
                await asyncio.sleep(self.TRANSIENT_BACKOFF_SECONDS)
                continue
            if result.status_code is None and transport_retries_left > 0:
                from app.core.network import is_retryable_network_error

                if is_retryable_network_error(error):
                    consumed = self.TRANSPORT_MAX_RETRIES - transport_retries_left
                    transport_retries_left -= 1
                    captcha_attempts_left += 1  # TLS/connect reset is not a captcha miss
                    backoff = min(
                        self.TRANSPORT_BACKOFF_CAP,
                        self.TRANSPORT_BACKOFF_BASE * (2 ** consumed),
                    )
                    backoff *= 1.0 + random.uniform(-0.2, 0.2)  # de-synchronise workers
                    logger.warning(
                        "utcms_http_login_transport_retry",
                        extra={
                            "extra_fields": {
                                "attempt": attempt,
                                "backoff": round(backoff, 1),
                                "retries_left": transport_retries_left,
                                "error": error[:160],
                            }
                        },
                    )
                    await asyncio.sleep(backoff)
                    continue
            if self._is_captcha_error(error):
                logger.info(
                    "utcms_http_login_captcha_retry",
                    extra={"extra_fields": {"attempt": attempt, "error": error}},
                )
                continue
            break

        return last_result or HttpLoginResult(success=False, error="لاگین ناموفق؛ بدون نتیجه")

    def take_authenticated_session(self) -> Any:
        """Transfer the successful curl session to a caller for reuse.

        Ownership moves with it: ``_session`` points at the same object (see
        ``authenticate``), so it is released too. Otherwise a later ``close()``
        on this helper would close the connection the new owner is using --
        which, now that the handle travels with the session, would drop the
        very warm TLS connection the handoff exists to preserve.
        """
        session, self._authenticated_session = self._authenticated_session, None
        if session is not None and self._session is session:
            self._session = None
        return session

    async def close(self) -> None:
        """Close any session still owned by this login helper."""
        sessions = [self._session, self._authenticated_session]
        self._session = None
        self._authenticated_session = None
        for session in sessions:
            if session is None:
                continue
            try:
                await self._call(session.close)
            except Exception:
                logger.debug("utcms_http_login_close_failed", exc_info=True)
        self._executor.shutdown(wait=False)

    async def fetch_authenticated(
        self,
        url: str,
        *,
        username: str,
        password: str,
        max_attempts: int = 3,
        backoff_seconds: float = 10.0,
        allowed_statuses: tuple[int, ...] = (200,),
    ) -> tuple[Any, list[dict[str, Any]]]:
        """GET a UTCMS page using a persistent authenticated session.

        The worker WAF frequently drops connections on specific pages
        (``ERR_CONNECTION_CLOSED`` / HTTP 408 style reliability hints).
        Instead of sharing a stale session, this method transparently
        re-authenticates and rebuilds the curl_cffi session whenever the
        current request fails at the transport level (connection reset),
        the server returns an auth-required/rate-limit status, or the
        page came back unauthenticated (redirected to ``/Login``).

        Returns:
            A tuple ``(response, cookies)`` on success. ``cookies`` are the
            Playwright-ready cookie dicts from the successful login, so the
            caller can also cold-boot a Playwright context from them.
        """
        from curl_cffi import requests as cc_requests  # type: ignore[import-not-found]

        retry_statuses = (429, *self.TRANSIENT_STATUS_CODES)
        last_exc: Exception | None = None
        last_status: int | None = None
        last_unauthenticated = False
        authenticated_cookies: list[dict[str, Any]] = []

        for attempt in range(1, max(1, max_attempts) + 1):
            session = self._session
            if session is None:
                login_res = await self.authenticate(username, password)
                if not login_res.success:
                    raise RuntimeError(f"باز-لاگین UTCMS جهت بازیابی سشن ناموفق: {login_res.error}")
                authenticated_cookies = login_res.cookies
                # Reuse the exact session that completed authentication. A
                # fresh curl session populated only with visible cookies can
                # lose UTCMS's server-side session context and bounce to Login.
                session = self.take_authenticated_session()
                if session is None:
                    session = self._build_session(cc_requests)
                    for cookie in authenticated_cookies:
                        try:
                            session.cookies.set(
                                cookie["name"],
                                cookie["value"],
                                domain=cookie.get("domain") or "barname.utcms.ir",
                                path=cookie.get("path") or "/",
                            )
                        except Exception:
                            logger.debug("utcms_http_login_cookie_set_failed", exc_info=True)
                self._session = session

            try:
                resp = await self._call(session.get, url, timeout=self._timeout)
            except Exception as exc:
                last_exc = exc
                # Transport-level reset → the session is burned; drop it so the
                # next iteration logs in with a brand new TLS handshake.
                self._session = None
                if attempt < max_attempts:
                    await asyncio.sleep(min(2.0 * attempt, backoff_seconds))
                    continue
                break

            last_status = resp.status_code
            if resp.status_code in retry_statuses:
                self._session = None
                if attempt < max_attempts:
                    await asyncio.sleep(backoff_seconds)
                    continue
                break

            # The session can expire silently: UTCMS then answers with a
            # redirect to (or a 200 render of) /Account/Login instead of the
            # requested page. ``allowed_statuses`` used to be accepted and then
            # ignored, so those responses were handed back to the caller as if
            # the fetch had succeeded. Treat them as a burned session and retry.
            last_unauthenticated = self._looks_unauthenticated(resp)
            if resp.status_code not in allowed_statuses or last_unauthenticated:
                logger.warning(
                    "utcms_http_login_fetch_unauthenticated",
                    extra={
                        "extra_fields": {
                            "url": url,
                            "attempt": attempt,
                            "unauthenticated": last_unauthenticated,
                            **self._response_diagnostics(resp),
                        }
                    },
                )
                self._session = None
                if attempt < max_attempts:
                    await asyncio.sleep(backoff_seconds)
                    continue
                break

            return resp, authenticated_cookies

        if last_exc is not None:
            raise RuntimeError(f"دریافت صفحه {url} ناموفق پس از {max_attempts} تلاش: {last_exc}") from last_exc
        if last_unauthenticated:
            raise RuntimeError(
                f"دریافت صفحه {url} ناموفق پس از {max_attempts} تلاش (پاسخ سامانه صفحه ورود بود؛ سشن معتبر نشد)"
            )
        raise RuntimeError(f"دریافت صفحه {url} ناموفق پس از {max_attempts} تلاش (آخرین وضعیت HTTP {last_status})")

    @staticmethod
    def _looks_unauthenticated(resp: Any) -> bool:
        """True when a response is really the UTCMS login page in disguise.

        Checks both the ``Location`` header (302 → /Account/Login) and the
        response's final URL, so an expired cookie is detected whether the
        portal redirects or renders the login form directly.
        """
        location = ""
        try:
            headers = resp.headers
            location = headers.get("Location") or headers.get("location") or ""
        except Exception:
            location = ""
        for candidate in (str(location or ""), str(getattr(resp, "url", "") or "")):
            if UtcmsHttpLogin._is_login_redirect_target(candidate):
                return True
        return False

    @staticmethod
    def _is_login_redirect_target(location: str) -> bool:
        """True when a redirect Location points at the login page.

        Bug-class fix: classify on the parsed PATH, not the raw string —
        ``/Dashboard?next=/login-help`` must not read as a login redirect.
        Handles both absolute URLs and bare paths (typical Location values).
        """
        if not location:
            return False
        from urllib.parse import urlparse

        try:
            path = urlparse(str(location).strip()).path.lower()
        except Exception:
            path = str(location).lower()
        return "/account/login" in path or path.rstrip("/").endswith("/login")

    @staticmethod
    def _is_captcha_error(error: str | None) -> bool:
        if not error:
            return False
        lowered = error.lower()
        return any(marker in lowered for marker in ("کد امنیتی", "عبارت امنیتی", "captcha", "کد تصویر"))

    async def _attempt_single_session(self, username: str, password: str) -> HttpLoginResult:
        """One full GET → solve → POST round inside a single curl_cffi session."""
        # 1) GET login page
        logger.info(
            "utcms_http_login_get_start",
            extra={"extra_fields": {"login_url": self._login_url, "proxy": self._proxy_url}},
        )
        try:
            get_resp = await self._call(self._session.get, self._login_url, timeout=self._timeout)
        except Exception as exc:
            logger.warning(
                "utcms_http_login_get_failed",
                extra={"extra_fields": {"error": str(exc)[:200]}},
            )
            return HttpLoginResult(
                success=False,
                error=f"دریافت صفحه لاگین ناموفق: {exc}",
                status_code=None,
            )

        if get_resp.status_code != 200:
            logger.warning(
                "utcms_http_login_get_bad_status",
                extra={"extra_fields": self._response_diagnostics(get_resp)},
            )
            return HttpLoginResult(
                success=False,
                error=f"وضعیت HTTP نامعتبر برای صفحه لاگین: {get_resp.status_code}",
                status_code=get_resp.status_code,
                final_url=str(get_resp.url),
            )

        html = get_resp.text

        # 2) Extract tokens
        self._antiforgery = self._extract_antiforgery(html)
        self._captcha_token = self._extract_dnt_captcha_token(html)
        self._captcha_text = self._extract_dnt_captcha_text(html)
        self._cap_type = self._extract_cap_type(html)
        ajax_url = self._extract_form_ajax_url(html)
        captcha_img_url = self._extract_captcha_image_url(html, base_url=str(get_resp.url))

        if not self._antiforgery:
            logger.warning(
                "utcms_http_login_no_antiforgery",
                extra={"extra_fields": {"html_len": len(html)}},
            )
            return HttpLoginResult(
                success=False,
                error="توکن ضد جعل (RequestVerificationToken) در صفحه یافت نشد. ساختار صفحه تغییر کرده؟",
                status_code=200,
                final_url=str(get_resp.url),
            )
        if not captcha_img_url:
            logger.warning(
                "utcms_http_login_no_captcha_image",
                extra={"extra_fields": {"html_excerpt": html[:500]}},
            )
            return HttpLoginResult(
                success=False,
                error="تصویر کپچا در صفحه یافت نشد.",
                status_code=200,
                final_url=str(get_resp.url),
            )

        # 3) Download captcha image
        try:
            self._captcha_image_url = captcha_img_url
            img_resp = await self._call(self._session.get, captcha_img_url, timeout=self._timeout)
            if img_resp.status_code != 200 or len(img_resp.content) < 16:
                return HttpLoginResult(
                    success=False,
                    error=f"دریافت تصویر کپچا ناموفق (HTTP {img_resp.status_code})",
                )
            self._captcha_image_bytes = img_resp.content
            logger.info(
                "utcms_login_captcha_signature",
                extra={
                    "extra_fields": {
                        "cap_type": self._cap_type or "1",
                        "image_path": urlparse(captcha_img_url).path,
                        "content_type": img_resp.headers.get("content-type", ""),
                        "image_bytes": len(self._captcha_image_bytes),
                        # A short digest detects a repeated image without
                        # logging the CAPTCHA itself or its solved value.
                        "image_digest": hashlib.sha256(self._captcha_image_bytes).hexdigest()[:12],
                    }
                },
            )
        except Exception as exc:
            logger.warning(
                "utcms_http_login_captcha_download_failed",
                extra={"extra_fields": {"url": captcha_img_url, "error": str(exc)[:200]}},
            )
            return HttpLoginResult(
                success=False,
                error=f"دانلود تصویر کپچا ناموفق: {exc}",
            )

        # 4) Solve captcha via local ML provider
        captcha_value = await self._solve_captcha()
        if not captcha_value:
            return HttpLoginResult(
                success=False,
                error="حل کپچا ناموفق بود. کیفیت تصویر یا مدل CNN را بررسی کنید.",
            )

        # 5) POST the login form. UTCMS's form uses jQuery Unobtrusive
        # AJAX (data-ajax-url="/Barname/Account/OldLogin"), so we must
        # post to that endpoint — NOT to the URL that served the GET.
        post_url = self._resolve_post_url(str(get_resp.url), ajax_url)
        payload = {
            "UserName": username,
            "NationalCode": username,
            "Password": password,
            "DNTCaptchaInputText": captcha_value,
            "DNTCaptchaToken": self._captcha_token or "",
            "DNTCaptchaText": self._captcha_text or "",
            "CapType": self._cap_type or "1",
            "RequestVerificationToken": self._antiforgery,
            "ruleExcepted": "true",
        }
        origin = f"{urlparse(str(get_resp.url)).scheme}://{urlparse(str(get_resp.url)).netloc}"
        post_headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": str(get_resp.url),
            "Origin": origin,
        }
        logger.info(
            "utcms_http_login_post_start",
            extra={
                "extra_fields": {
                    "post_url": post_url,
                    "captcha_len": len(captcha_value),
                    "has_antiforgery": bool(self._antiforgery),
                }
            },
        )
        try:
            post_resp = await self._call(
                self._session.post,
                post_url,
                data=payload,
                headers=post_headers,
                timeout=self._timeout,
                allow_redirects=False,  # we'll inspect the redirect manually
            )
        except Exception as exc:
            logger.warning(
                "utcms_http_login_post_failed",
                extra={"extra_fields": {"error": str(exc)[:200]}},
            )
            return HttpLoginResult(
                success=False,
                error=f"ارسال فرم لاگین ناموفق: {exc}",
            )

        return self._evaluate_post_response(post_resp)

    async def inject_cookies_into_context_async(self, result: HttpLoginResult, context: Any) -> bool:
        """Async helper to inject auth cookies into a Playwright context."""
        if not result.success or not result.cookies:
            return False
        try:
            cookies = self._normalise_cookies_for_playwright(result.cookies)
            await context.add_cookies(cookies)
            return True
        except Exception as exc:
            logger.warning(
                "utcms_http_login_inject_async_failed",
                extra={"extra_fields": {"error": str(exc)[:200]}},
            )
            return False

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_session(self, cc_requests: Any) -> Any:
        """Create a curl_cffi Session with Chrome impersonation + proxy."""
        proxies = {"http": self._proxy_url, "https": self._proxy_url} if self._proxy_url else None
        # ``curl_cffi`` accepts ``impersonate`` on Session() and on each call.
        session = cc_requests.Session(
            impersonate=self._impersonate,
            proxies=proxies,
            timeout=self._timeout,
            # curl_cffi defaults to a THREAD-LOCAL libcurl handle, and the
            # connection cache lives on the handle, not on the Session.  This
            # session is handed to the browser bridge via
            # ``take_authenticated_session()``, which then drives it from its own
            # pinned thread -- so with the default the bridge silently got a
            # brand-new handle and had to open a brand-new TLS connection for
            # every XHR, which UTCMS's per-IP handshake throttle rejects
            # ("SSL_connect: Connection closed abruptly").  Binding the handle to
            # the session instead makes the warm connection survive the handoff.
            # Safe here because every call is serialised onto one thread at a
            # time (this class's ``_call``, then the bridge's), and libcurl only
            # forbids *simultaneous* use of a handle from two threads.
            use_thread_local_curl=False,
        )
        # Mirror a real Chrome User-Agent + headers so WAF sees a
        # consistent fingerprint end-to-end.
        session.headers.update(
            {
                "User-Agent": self._user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,fa;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            }
        )
        return session

    @staticmethod
    def _build_user_agent() -> str:
        """Build a Chrome 120 user-agent string."""
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

    @staticmethod
    def _extract_antiforgery(html: str) -> str | None:
        m = _ANTIFORGERY_RE.search(html)
        if m:
            return m.group(1)
        # Fallback: <input ... value="..." name="RequestVerificationToken">
        m2 = re.search(
            r'<input[^>]+value=["\']([^"\']+)["\'][^>]+name=["\']_*RequestVerificationToken["\']',
            html,
            re.IGNORECASE,
        )
        return m2.group(1) if m2 else None

    @staticmethod
    def _extract_dnt_captcha_token(html: str) -> str | None:
        m = _DNT_CAPTCHA_TOKEN_RE.search(html)
        return m.group(1) if m else None

    @staticmethod
    def _extract_dnt_captcha_text(html: str) -> str | None:
        m = _DNT_CAPTCHA_TEXT_RE.search(html)
        return m.group(1) if m else None

    @staticmethod
    def _extract_cap_type(html: str) -> str | None:
        m = _CAP_TYPE_RE.search(html)
        return m.group(1) if m else None

    @staticmethod
    def _extract_form_ajax_url(html: str) -> str | None:
        m = _FORM_AJAX_URL_RE.search(html)
        return m.group(1) if m else None

    @staticmethod
    def _extract_captcha_image_url(html: str, base_url: str) -> str | None:
        m = _CAPTCHA_IMG_RE.search(html)
        if m:
            return urljoin(base_url, m.group(1))
        m2 = _CAPTCHA_IMG_FALLBACK_RE.search(html)
        if m2:
            return urljoin(base_url, m2.group(1))
        return None

    @staticmethod
    def _resolve_post_url(get_url: str, ajax_url: str | None = None) -> str:
        """Resolve the login form's post endpoint.

        The GET (login page) reveals the form's AJAX target via
        ``data-ajax-url`` (e.g. ``/Barname/Account/OldLogin``). We
        rebase it onto the same origin. If no AJAX url is present, falls
        back to posting to the page that served the GET (classic MVC).
        """
        if ajax_url:
            if ajax_url.lower().startswith(("http://", "https://")):
                return ajax_url
            from urllib.parse import urljoin as _urljoin

            return _urljoin(get_url, ajax_url)
        return get_url

    async def _solve_captcha(self) -> str | None:
        if not self._captcha_image_bytes:
            return None
        try:
            from app.automation.captcha import get_captcha_provider

            provider = get_captcha_provider()
        except Exception as exc:
            logger.warning(
                "utcms_http_login_no_captcha_provider",
                extra={"extra_fields": {"error": str(exc)[:160]}},
            )
            return None
        if provider is None:
            logger.warning("utcms_http_login_no_captcha_provider")
            return None
        b64 = base64.b64encode(self._captcha_image_bytes).decode("ascii")
        try:
            result = await provider.solve_text_captcha(b64)
        except Exception as exc:
            logger.warning(
                "utcms_http_login_solver_exception",
                extra={"extra_fields": {"provider": getattr(provider, "name", "?"), "error": str(exc)[:200]}},
            )
            return None
        if result.solved and result.value:
            logger.info(
                "utcms_http_login_captcha_solved",
                extra={"extra_fields": {"provider": result.provider, "value_len": len(result.value)}},
            )
            return result.value.strip()
        logger.warning(
            "utcms_http_login_captcha_failed",
            extra={"extra_fields": {"provider": result.provider, "error": result.error}},
        )
        return None

    def _evaluate_post_response(self, post_resp: Any) -> HttpLoginResult:
        """Inspect the POST response to determine login success."""
        status = post_resp.status_code
        location = post_resp.headers.get("Location", "") or post_resp.headers.get("location", "")
        set_cookies = self._collect_set_cookies(post_resp)
        final_url = str(post_resp.url)
        if location:
            # urllib.parse for relative redirects
            from urllib.parse import urljoin as _urljoin

            final_url = _urljoin(final_url, location)

        # Success indicators:
        #   1. 302 redirect with Location NOT pointing back to /Login
        #   2. 200 OK JSON body with success=true (AJAX-style login)
        #   3. 200 OK page that no longer contains the login form
        if status in (301, 302, 303, 307, 308) and location:
            # Path-based check: a Location like "/Dashboard?ref=LoginBanner"
            # must NOT be misread as a bounce back to the login page.
            if not self._is_login_redirect_target(location):
                cookies = self._cookies_to_playwright_dicts(set_cookies, final_url)
                if self._has_auth_cookie(cookies):
                    return HttpLoginResult(
                        success=True,
                        cookies=cookies,
                        final_url=final_url,
                        status_code=status,
                    )
                # Even without the obvious .AspNetCore.Cookies cookie, a
                # redirect away from /Login is a strong success signal.
                # Session may be established via a cookie that curl_cffi
                # stored internally, or WAF may strip the header we see.
                return HttpLoginResult(
                    success=True,
                    cookies=cookies,
                    final_url=final_url,
                    status_code=status,
                )

        body = post_resp.text if hasattr(post_resp, "text") else ""

        # JSON-style login response (e.g. {"success": true, "redirect": "/..."})
        json_result = self._evaluate_json_response(post_resp, status, final_url, set_cookies)
        if json_result is not None:
            return json_result

        # 200 OK page that looks like an authenticated dashboard (has a
        # logout link) — treat as success even without a redirect.
        if status == 200 and self._body_looks_authenticated(body):
            cookies = self._cookies_to_playwright_dicts(set_cookies, final_url)
            return HttpLoginResult(
                success=True,
                cookies=cookies,
                final_url=final_url,
                status_code=status,
            )

        # 200 OK on the same page = login failed (or captcha wrong)
        error_msg = self._extract_login_error(body)
        if not error_msg:
            error_msg = self._classify_html_response(body, final_url, status)
        if status not in (200, 301, 302, 303, 307, 308):
            # Unexpected status (e.g. 503 from Squid vs. from UTCMS) — record who
            # answered so the failure can be attributed without a live re-run.
            logger.warning(
                "utcms_http_login_post_bad_status",
                extra={"extra_fields": {**self._response_diagnostics(post_resp), "post_url": final_url}},
            )
        return HttpLoginResult(
            success=False,
            error=error_msg or f"لاگین ناموفق (HTTP {status})",
            status_code=status,
            final_url=final_url,
        )

    def _evaluate_json_response(
        self,
        post_resp: Any,
        status: int,
        final_url: str,
        set_cookies: list[dict[str, Any]],
    ) -> HttpLoginResult | None:
        """Handle AJAX-style login responses (``{"success": true}``)."""
        content_type = ""
        try:
            content_type = (post_resp.headers.get("Content-Type", "") or "").lower()
        except Exception:
            content_type = ""
        if "json" not in content_type:
            return None
        try:
            import json as _json

            payload = _json.loads(post_resp.text or "{}")
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None

        success = bool(payload.get("success"))
        if success:
            cookies = self._cookies_to_playwright_dicts(set_cookies, final_url)
            return HttpLoginResult(
                success=True,
                cookies=cookies,
                final_url=str(payload.get("redirectUrl") or final_url),
                status_code=status,
            )
        message = str(
            payload.get("message") or payload.get("detail") or payload.get("resultMessage") or "لاگین ناموفق بود"
        )
        return HttpLoginResult(success=False, error=message, status_code=status, final_url=final_url)

    @staticmethod
    def _extract_login_error(body: str) -> str | None:
        m = _ERROR_RE.search(body)
        return m.group(1) if m else None

    @staticmethod
    def _body_looks_authenticated(body: str) -> bool:
        """True if a 200-OK response body resembles a logged-in dashboard."""
        lowered = (body or "").lower()
        if any(marker in lowered for marker in ("خروج", "logout", "به سامانه باربران خوش آمدید")):
            return True
        return "logindevice" not in lowered and ('href="/barname"' in lowered or 'href="/waybill"' in lowered)

    @staticmethod
    def _response_diagnostics(resp: Any) -> dict[str, Any]:
        """Pull the headers that reveal *who* produced an error response.

        A 503 from the worker's Squid egress proxy carries ``X-Squid-Error``
        and a ``Via``/``Server: squid`` header, while a 503 from UTCMS/its WAF
        does not. Without these fields a proxy outage and a genuine upstream
        outage look identical in the logs.
        """
        diag: dict[str, Any] = {"status": getattr(resp, "status_code", None)}
        try:
            headers = resp.headers
            for key in ("Server", "Via", "X-Squid-Error", "X-Cache", "Content-Type", "Retry-After"):
                value = headers.get(key) or headers.get(key.lower())
                if value:
                    diag[key.lower().replace("-", "_")] = str(value)[:120]
        except Exception:
            pass
        try:
            body = resp.text or ""
            diag["body_len"] = len(body)
            diag["body_snippet"] = re.sub(r"\s+", " ", body[:400]).strip()
        except Exception:
            pass
        return diag

    @staticmethod
    def _classify_html_response(body: str, final_url: str, status: int) -> str | None:
        # If the response is the same login page again, it's a credentials/captcha error.
        # Path-based check (bug-class fix): ignore query strings such as "?ref=LoginBanner".
        if UtcmsHttpLogin._is_login_redirect_target(final_url):
            if "عبارت امنیتی" in body or "کد امنیتی" in body:
                return "کپچا اشتباه است."
            if "کد ملی یا رمز عبور" in body or "نام کاربری یا رمز عبور" in body:
                return "کد ملی یا رمز عبور اشتباه است."
            return "لاگین ناموفق؛ صفحه به فرم ورود بازگشت."
        return None

    @staticmethod
    def _has_auth_cookie(cookies: list[dict[str, Any]]) -> bool:
        auth_names = (".aspnetcore.cookies", "utcms", "auth", ".auth", "session")
        for c in cookies:
            name = (c.get("name") or "").lower()
            if any(a in name for a in auth_names):
                return True
        return False

    @staticmethod
    def _collect_set_cookies(post_resp: Any) -> list[dict[str, Any]]:
        """Extract Set-Cookie entries from a curl_cffi response.

        ``curl_cffi`` stores cookies in its own dict-like ``Cookies`` jar
        (iteration yields name strings, NOT cookie objects) and the raw
        ``Set-Cookie`` headers remain in ``response.headers``. We prefer
        parsing the raw headers (full fidelity: domain/path/httpOnly/
        sameSite attributes), then fall back to the cookie jar.
        """
        entries: list[dict[str, Any]] = []

        raw_headers: list[str] = []
        try:
            get_list = getattr(post_resp.headers, "get_list", None)
            if get_list is not None:
                raw_headers = list(get_list("set-cookie"))
        except Exception:
            raw_headers = []
        if not raw_headers:
            try:
                raw = post_resp.headers.get("set-cookie")
                if raw:
                    raw_headers = [raw]
            except Exception:
                raw_headers = []

        if raw_headers:
            for raw in raw_headers:
                parsed = UtcmsHttpLogin._parse_set_cookie_header(raw)
                if parsed:
                    entries.append(parsed)

        if entries:
            return entries

        # Fallback: curl_cffi's dict-like jar (name → Cookie-ish value).
        jar = getattr(post_resp, "cookies", None)
        if jar is not None:
            try:
                for name, cookie in getattr(jar, "items", lambda: [])():
                    if not name:
                        continue
                    value = cookie.value if hasattr(cookie, "value") else str(cookie)
                    entries.append(
                        {
                            "name": name,
                            "value": value,
                            "domain": getattr(cookie, "domain", None) or None,
                            "path": getattr(cookie, "path", None) or "/",
                            "expires": getattr(cookie, "expires", None),
                            "secure": bool(getattr(cookie, "secure", False)),
                            "httpOnly": bool(getattr(cookie, "_rest", {}).get("HttpOnly") or False),
                        }
                    )
            except Exception:
                logger.debug("utcms_http_login_jar_walk_failed", exc_info=True)
        return entries

    @staticmethod
    def _parse_set_cookie_header(raw: str) -> dict[str, Any] | None:
        """Parse a single raw ``Set-Cookie`` header string."""
        try:
            from http.cookies import SimpleCookie

            sc = SimpleCookie()
            sc.load(raw or "")
        except Exception:
            return None
        if not sc:
            return None
        morsel = next(iter(sc.values()))
        name, value = morsel.key, morsel.value
        if not name or value is None:
            return None
        entry: dict[str, Any] = {
            "name": name,
            "value": value,
            "domain": morsel.get("domain") or None,
            "path": morsel.get("path") or "/",
        }
        try:
            expires = morsel.get("expires")
            if expires:
                from email.utils import parsedate_to_datetime

                dt = parsedate_to_datetime(expires)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                entry["expires"] = int(dt.timestamp())
        except Exception:
            pass
        if morsel.get("max-age"):
            try:
                entry["expires"] = int(time.time() + int(morsel["max-age"]))
            except Exception:
                pass
        if morsel.get("httponly"):
            entry["httpOnly"] = True
        if morsel.get("secure"):
            entry["secure"] = True
        same_site = (morsel.get("samesite") or "").title()
        if same_site in ("Strict", "Lax", "None"):
            entry["sameSite"] = same_site
        return entry

    @staticmethod
    def _cookies_to_playwright_dicts(cookies: list[dict[str, Any]], final_url: str) -> list[dict[str, Any]]:
        """Convert internal cookie dicts to Playwright's expected format.

        Playwright's ``BrowserContext.add_cookies`` accepts:
            {"name": str, "value": str, "domain": str, "path": str,
             "expires": int, "httpOnly": bool, "secure": bool,
             "sameSite": "Strict"|"Lax"|"None"}

        We derive ``domain`` from ``final_url`` when missing, and
        convert the expires timestamp to epoch seconds.
        """
        parsed = urlparse(final_url)
        host = parsed.hostname or ""
        out: list[dict[str, Any]] = []
        for c in cookies:
            name = c.get("name")
            value = c.get("value")
            if not name or value is None:
                continue
            entry: dict[str, Any] = {
                "name": name,
                "value": value,
                "domain": c.get("domain") or host,
                "path": c.get("path") or "/",
            }
            expires = c.get("expires")
            if isinstance(expires, (int, float)) and expires > 0:
                entry["expires"] = int(expires)
            if c.get("httpOnly"):
                entry["httpOnly"] = True
            if c.get("secure"):
                entry["secure"] = True
            # Playwright's sameSite is required to be one of three strict
            # values; curl_cffi's jar rarely populates it. Default to "Lax"
            # which is the most common browser default.
            entry.setdefault("sameSite", "Lax")
            out.append(entry)
        return out

    @staticmethod
    def _normalise_cookies_for_playwright(cookies: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter out cookies with empty names or values."""
        return [c for c in cookies if c.get("name") and c.get("value") not in (None, "")]


def cookies_to_playwright(cookies: list[dict[str, Any]], final_url: str) -> list[dict[str, Any]]:
    """Module-level helper to normalise cookies for Playwright (sync API).

    Exposed so callers (e.g. unit tests) can convert the cookies from a
    ``HttpLoginResult`` without instantiating ``UtcmsHttpLogin``.
    """
    return UtcmsHttpLogin._cookies_to_playwright_dicts(cookies, final_url)


__all__ = ["UtcmsHttpLogin", "HttpLoginResult", "cookies_to_playwright"]


# ---------------------------------------------------------------------------
# Convenience: extract an inline login error from a UTCMS error page.
# ---------------------------------------------------------------------------

_ERROR_RE = re.compile(
    r"(" + "|".join(re.escape(p) for p in _LOGIN_ERROR_PATTERNS) + r")",
    re.IGNORECASE,
)
