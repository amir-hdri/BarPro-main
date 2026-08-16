"""Route UTCMS Playwright traffic through curl_cffi's Chrome TLS stack.

UTCMS accepts the Chrome fingerprint produced by curl_cffi but intermittently
drops Chromium's own TLS handshake.  Playwright is still valuable for running
the portal JavaScript and interacting with the form, so this bridge intercepts
only requests to the UTCMS host, performs them with curl_cffi, and fulfils the
Playwright route with the returned response.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlparse

from app.automation.worker_proxy import get_worker_proxy_url
from app.core.config import utcms_config

logger = logging.getLogger(__name__)

_UTCMS_HOST = "barname.utcms.ir"
_REQUEST_DROP_HEADERS = {"connection", "content-length", "host", "proxy-connection"}
_RESPONSE_DROP_HEADERS = {
    "connection",
    "content-encoding",
    "content-length",
    "keep-alive",
    "proxy-connection",
    "transfer-encoding",
}
_BRIDGED_RESOURCE_TYPES = frozenset({"document", "xhr", "fetch"})


_SAFE_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD"})


class UtcmsHttpBrowserBridge:
    """A page-scoped, serialized curl_cffi transport for UTCMS requests."""

    def __init__(self, page: Any, *, proxy_url: str | None = None, timeout: float = 45.0) -> None:
        self.page = page
        self.proxy_url = (proxy_url or get_worker_proxy_url() or "").strip() or None
        self.timeout = timeout
        self._lock = asyncio.Lock()
        self._session: Any = None

    async def install(self) -> None:
        await self.page.route("**/*", self._handle_route)

    async def close(self) -> None:
        session, self._session = self._session, None
        if session is not None:
            try:
                await asyncio.to_thread(session.close)
            except Exception:
                logger.debug("http_browser_bridge_close_failed", exc_info=True)

    async def seed_cookies(self, cookies: list[dict[str, Any]]) -> None:
        """Seed the curl session with cookies obtained by HTTP login."""
        async with self._lock:
            if self._session is None:
                self._session = self._new_session()
            for cookie in cookies:
                name = str(cookie.get("name") or "").strip()
                if not name:
                    continue
                try:
                    self._session.cookies.set(
                        name,
                        str(cookie.get("value") or ""),
                        domain=cookie.get("domain") or _UTCMS_HOST,
                        path=cookie.get("path") or "/",
                    )
                except Exception:
                    logger.debug("http_browser_bridge_seed_cookie_failed", exc_info=True)

    def _new_session(self) -> Any:
        from curl_cffi import requests as cc_requests  # type: ignore[import-not-found]

        proxies = {"http": self.proxy_url, "https": self.proxy_url} if self.proxy_url else None
        return cc_requests.Session(
            impersonate="chrome120",
            proxies=proxies,
            verify=False,
            timeout=self.timeout,
        )

    async def _reset_session(self) -> None:
        old, self._session = self._session, None
        if old is not None:
            try:
                await asyncio.to_thread(old.close)
            except Exception:
                logger.debug("http_browser_bridge_reset_close_failed", exc_info=True)

    async def _handle_route(self, route: Any) -> None:
        request = route.request
        parsed = urlparse(request.url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname != _UTCMS_HOST:
            await route.continue_()
            return

        # Chromium's own request stack is the most reliable way to fetch the
        # portal's static JS/CSS/font assets through Squid.  The curl-cffi
        # bridge exists only for the WAF-sensitive HTML/data requests; routing
        # every asset through a serialized curl session caused dozens of TLS
        # resets and turned a normal page load into a 480-second timeout.
        if request.resource_type not in _BRIDGED_RESOURCE_TYPES:
            await route.continue_()
            return

        is_safe_method = request.method.upper() in _SAFE_IDEMPOTENT_METHODS
        try:
            await self._fulfill_utcms(route, request)
        except Exception as exc:
            logger.warning(
                "http_browser_bridge_request_failed url=%s method=%s type=%s error=%s",
                request.url,
                request.method,
                request.resource_type,
                str(exc)[:240],
                extra={
                    "extra_fields": {
                        "url": request.url,
                        "method": request.method,
                        "resource_type": request.resource_type,
                        "error": str(exc)[:240],
                    }
                },
            )
            # Only safe/idempotent requests (GET, HEAD) may fall back to Chromium's native stack.
            # For mutating methods (POST, PUT, DELETE, PATCH), fallback is forbidden to prevent duplicate submit!
            if is_safe_method:
                try:
                    await route.continue_()
                except Exception:
                    await route.abort("connectionfailed")
            else:
                try:
                    await route.abort("failed")
                except Exception:
                    pass

    async def _fulfill_utcms(self, route: Any, request: Any) -> None:
        headers = dict(await request.all_headers())
        headers = {k: v for k, v in headers.items() if k.lower() not in _REQUEST_DROP_HEADERS}
        # curl_cffi transparently decompresses responses. Asking for identity
        # avoids forwarding a stale Content-Encoding header to Chromium.
        headers["accept-encoding"] = "identity"
        body = request.post_data_buffer

        is_safe_method = request.method.upper() in _SAFE_IDEMPOTENT_METHODS
        max_attempts = 3 if is_safe_method else 1

        async with self._lock:
            response = None
            last_error: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                if self._session is None:
                    self._session = self._new_session()
                try:
                    response = await asyncio.to_thread(
                        self._session.request,
                        request.method,
                        request.url,
                        headers=headers,
                        data=body,
                        allow_redirects=False,
                        timeout=self.timeout,
                    )
                    if not is_safe_method or response.status_code not in (408, 429, 500, 502, 503, 504):
                        break
                    await self._reset_session()
                    if attempt < max_attempts:
                        await asyncio.sleep(float(attempt))
                except Exception as exc:
                    last_error = exc
                    await self._reset_session()
                    if not is_safe_method:
                        break
                    if attempt < max_attempts:
                        await asyncio.sleep(float(attempt))

            if response is None:
                raise RuntimeError(f"UTCMS bridge transport failed: {last_error}")

            response_headers = {
                str(k): str(v) for k, v in response.headers.items() if str(k).lower() not in _RESPONSE_DROP_HEADERS
            }
            await route.fulfill(
                status=int(response.status_code),
                headers=response_headers,
                body=bytes(response.content or b""),
            )


async def ensure_utcms_http_browser_bridge(page: Any) -> UtcmsHttpBrowserBridge | None:
    """Install one bridge per page when HTTP-login mode is enabled."""
    if not getattr(utcms_config, "UTCMS_HTTP_LOGIN_ENABLED", True):
        return None
    existing = getattr(page, "_barpro_http_browser_bridge", None)
    if existing is not None:
        return existing
    bridge = UtcmsHttpBrowserBridge(page)
    await bridge.install()
    page._barpro_http_browser_bridge = bridge
    return bridge


__all__ = ["UtcmsHttpBrowserBridge", "ensure_utcms_http_browser_bridge"]
