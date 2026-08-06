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
import logging
import re
from dataclasses import dataclass, field
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

# ASP.NET Core antiforgery token: <input name="__RequestVerificationToken" value="...">
_ANTIFORGERY_RE = re.compile(
    r'<input[^>]+name=["\']__RequestVerificationToken["\'][^>]+value=["\']([^"\']+)["\']',
    re.IGNORECASE,
)

# DNT captcha: <input name="DNTCaptchaInputText" ...> + <input name="DNTCaptchaToken" value="...">
_DNT_CAPTCHA_TOKEN_RE = re.compile(
    r'<input[^>]+name=["\']DNTCaptchaToken["\'][^>]+value=["\']([^"\']+)["\']',
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
        self._login_url = (login_url or utcms_config.LOGIN_URL).strip()
        try:
            from app.automation.worker_proxy import get_worker_proxy_url

            default_proxy = get_worker_proxy_url()
        except Exception:
            default_proxy = None
        self._proxy_url = (proxy_url or default_proxy or "").strip() or None
        self._impersonate = impersonate
        self._timeout = timeout
        self._user_agent = user_agent or self._build_user_agent()
        # Lazy import so the rest of the project can start without
        # curl_cffi installed (the dependency is only required at the
        # worker runtime, not at API startup).
        self._session: Any = None  # curl_cffi.requests.Session
        self._antiforgery: str | None = None
        self._captcha_token: str | None = None
        self._captcha_image_bytes: bytes | None = None
        self._captcha_image_url: str | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def authenticate(self, username: str, password: str) -> HttpLoginResult:
        """Run the full HTTP login flow and return the auth cookies.

        Steps:
          1. Open a curl_cffi session (Chrome TLS fingerprint).
          2. GET the login page → extract antiforgery + captcha token.
          3. GET the captcha image (same session) → solve with local CNN.
          4. POST the login form with credentials + captcha answer.
          5. Validate the response: redirect away from /Login = success.

        Returns:
            ``HttpLoginResult`` with ``success=True`` and the
            session cookies when login succeeded.
        """
        from curl_cffi import requests as cc_requests  # type: ignore[import-not-found]

        if not username or not password:
            return HttpLoginResult(success=False, error="نام کاربری یا رمز عبور خالی است")

        self._session = self._build_session(cc_requests)
        try:
            # 1) GET login page
            logger.info(
                "utcms_http_login_get_start",
                extra={"extra_fields": {"login_url": self._login_url, "proxy": self._proxy_url}},
            )
            try:
                get_resp = await asyncio.to_thread(self._session.get, self._login_url, timeout=self._timeout)
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
                img_resp = await asyncio.to_thread(
                    self._session.get, captcha_img_url, timeout=self._timeout
                )
                if img_resp.status_code != 200 or len(img_resp.content) < 16:
                    return HttpLoginResult(
                        success=False,
                        error=f"دریافت تصویر کپچا ناموفق (HTTP {img_resp.status_code})",
                    )
                self._captcha_image_bytes = img_resp.content
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

            # 5) POST the login form
            post_url = self._resolve_post_url(get_resp.url)
            payload = {
                "NationalCode": username,
                "Password": password,
                "DNTCaptchaInputText": captcha_value,
                "DNTCaptchaToken": self._captcha_token or "",
                "__RequestVerificationToken": self._antiforgery,
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
                post_resp = await asyncio.to_thread(
                    self._session.post,
                    post_url,
                    data=payload,
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

        finally:
            try:
                if self._session is not None:
                    await asyncio.to_thread(self._session.close)
            except Exception:
                logger.debug("utcms_http_login_session_close_failed", exc_info=True)
            self._session = None

    async def inject_cookies_into_context_async(
        self, result: HttpLoginResult, context: Any
    ) -> bool:
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
        # Fallback: <input ... value="..." name="__RequestVerificationToken">
        m2 = re.search(
            r'<input[^>]+value=["\']([^"\']+)["\'][^>]+name=["\']__RequestVerificationToken["\']',
            html,
            re.IGNORECASE,
        )
        return m2.group(1) if m2 else None

    @staticmethod
    def _extract_dnt_captcha_token(html: str) -> str | None:
        m = _DNT_CAPTCHA_TOKEN_RE.search(html)
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
    def _resolve_post_url(get_url: str) -> str:
        """The form posts to the same URL that served the GET."""
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
            lowered_loc = location.lower()
            if "/login" not in lowered_loc and "/account/login" not in lowered_loc:
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
                if cookies:
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
            payload.get("message")
            or payload.get("detail")
            or payload.get("resultMessage")
            or "لاگین ناموفق بود"
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
        return "logindevice" not in lowered and (
            "href=\"/barname\"" in lowered or "href=\"/waybill\"" in lowered
        )

    @staticmethod
    def _classify_html_response(body: str, final_url: str, status: int) -> str | None:
        # If the response is the same login page again, it's a credentials/captcha error.
        if "/login" in final_url.lower():
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

        ``curl_cffi`` exposes ``response.cookies`` (a ``RequestsCookieJar``).
        We also walk ``response.headers`` for raw ``Set-Cookie`` strings
        to preserve the ``domain``/``path`` attributes that Playwright
        needs.
        """
        jar_entries: list[dict[str, Any]] = []
        jar = getattr(post_resp, "cookies", None)
        if jar is not None:
            try:
                for cookie in jar:
                    jar_entries.append(
                        {
                            "name": cookie.name,
                            "value": cookie.value,
                            "domain": cookie.domain,
                            "path": cookie.path or "/",
                            "expires": getattr(cookie, "expires", None),
                            "secure": bool(getattr(cookie, "secure", False)),
                            "httpOnly": bool(getattr(cookie, "_rest", {}).get("HttpOnly") or False),
                        }
                    )
            except Exception:
                logger.debug("utcms_http_login_jar_walk_failed", exc_info=True)
        return jar_entries

    @staticmethod
    def _cookies_to_playwright_dicts(
        cookies: list[dict[str, Any]], final_url: str
    ) -> list[dict[str, Any]]:
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
        """Pass-through normaliser (placeholder for future scrubbing)."""
        return [c for c in cookies if c.get("name") and c.get("value") is not None]


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
