"""Route UTCMS Playwright traffic through curl_cffi's Chrome TLS stack.

UTCMS accepts the Chrome fingerprint produced by curl_cffi but intermittently
drops Chromium's own TLS handshake.  Playwright is still valuable for running
the portal JavaScript and interacting with the form, so this bridge intercepts
only requests to the UTCMS host, performs them with curl_cffi, and fulfils the
Playwright route with the returned response.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from app.automation.worker_proxy import get_worker_proxy_url
from app.core.config import utcms_config

logger = logging.getLogger(__name__)

_UTCMS_HOST = "barname.utcms.ir"
_REQUEST_DROP_HEADERS = {
    "connection",
    "content-length",
    "host",
    "proxy-connection",
    "user-agent",
    "sec-ch-ua",
    "sec-ch-ua-mobile",
    "sec-ch-ua-platform",
    "sec-ch-ua-model",
    "sec-ch-ua-arch",
    "sec-ch-ua-bitness",
    "sec-ch-ua-full-version",
    "sec-ch-ua-full-version-list",
}
_RESPONSE_DROP_HEADERS = {
    "connection",
    "content-encoding",
    "content-length",
    "keep-alive",
    "proxy-connection",
    "transfer-encoding",
}
_BRIDGED_RESOURCE_TYPES = frozenset({"document", "xhr", "fetch"})
_ASSET_RESOURCE_TYPES = frozenset({"script", "stylesheet"})
# Web fonts are cosmetic, are served from the same slow static surface, and each
# failed request costs seconds of page time.  They are dropped on the issuance
# page only; images are never dropped because CAPTCHA images are images.
_DISCARDED_RESOURCE_TYPES = frozenset({"font"})


_SAFE_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD"})
_AUTHENTICATED_LANDING_URL = "https://barname.utcms.ir/Barname/Notification/Notification"
_ISSUANCE_DOCUMENT_MARKERS = (
    "/document/hagigihogugi",
    "/document/create",
    "/waybill/create",
    "/transportation/waybill",
)
# Scripts the issuance form must have in order to initialise.  Verified live on
# 2026-08-27: fetched sequentially on the authenticated login session they all
# return HTTP 200, while Chromium's own TLS handshake resets them.
_CRITICAL_FORM_SCRIPT_MARKERS = (
    "jquery/jquery.js",
    "jqury-ui/jquery-ui.js",
    "jquery-ui/jquery-ui.js",
    "jquery.validate.js",
    "formvalidation.popular",
    "formhelper.js",
    "hagigihogugitemplate.js",
    "hagigihogugi.js",
)

# UTCMS static assets are versioned through a ``?v=<hash>`` query, so a response
# body is valid for as long as that URL is referenced.  Caching them on disk
# makes the issuance form independent of UTCMS's unreliable static surface:
# every asset a previous run managed to download is served locally, so the HTML
# parser never blocks on a synchronous <script> that will not arrive.
_ASSET_CACHE_DIR = Path(os.environ.get("UTCMS_ASSET_CACHE_DIR", "/tmp/utcms_asset_cache"))
_ASSET_CACHE_MAX_BYTES = 8 * 1024 * 1024


def _asset_cache_files(cache_key: str) -> tuple[Path, Path]:
    digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
    return _ASSET_CACHE_DIR / f"{digest}.meta", _ASSET_CACHE_DIR / f"{digest}.body"


def _read_asset_cache(cache_key: str) -> tuple[int, dict[str, str], bytes] | None:
    meta_path, body_path = _asset_cache_files(cache_key)
    try:
        if not meta_path.is_file() or not body_path.is_file():
            return None
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        body = body_path.read_bytes()
    except Exception:
        logger.warning("http_browser_bridge_asset_cache_read_failed key=%s", cache_key, exc_info=True)
        return None
    status = int(meta.get("status") or 0)
    headers = {str(k): str(v) for k, v in (meta.get("headers") or {}).items()}
    if status != 200 or not body:
        return None
    return status, headers, body


def _write_asset_cache(cache_key: str, status: int, headers: dict[str, str], body: bytes) -> None:
    if int(status) != 200 or not body or len(body) > _ASSET_CACHE_MAX_BYTES:
        return
    meta_path, body_path = _asset_cache_files(cache_key)
    try:
        _ASSET_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp_body = body_path.with_suffix(".body.tmp")
        tmp_meta = meta_path.with_suffix(".meta.tmp")
        tmp_body.write_bytes(body)
        tmp_meta.write_text(
            json.dumps({"status": int(status), "headers": headers, "url_key": cache_key}, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp_body.replace(body_path)
        tmp_meta.replace(meta_path)
    except Exception:
        logger.warning("http_browser_bridge_asset_cache_write_failed key=%s", cache_key, exc_info=True)


def _is_critical_form_script(url: str) -> bool:
    lowered = url.lower()
    return any(marker in lowered for marker in _CRITICAL_FORM_SCRIPT_MARKERS)


def _asset_stub_content_type(url: str) -> str:
    return "text/css; charset=utf-8" if urlparse(url).path.lower().endswith(".css") else "application/javascript"



class UtcmsHttpBrowserBridge:
    """A page-scoped, serialized curl_cffi transport for UTCMS requests."""

    def __init__(self, page: Any, *, proxy_url: str | None = None, timeout: float = 45.0) -> None:
        self.page = page
        self.proxy_url = (proxy_url or get_worker_proxy_url() or "").strip() or None
        self.timeout = timeout
        self._lock = asyncio.Lock()
        self._session: Any = None
        self._document_session: Any = None
        self._document_session_warmed = False
        self._prefetched_documents: dict[str, tuple[int, dict[str, str], bytes]] = {}
        self._prefetched_assets: dict[str, tuple[int, dict[str, str], bytes]] = {}
        self._seeded_cookies: list[dict[str, Any]] = []
        self._preserve_authenticated_session = False
        self._form_assets_bridge_enabled = False
        # Top-level documents are kept on Chromium until the HTTP login path
        # has supplied an authenticated curl session.  UTCMS accepts the
        # waybill form only when the request follows the authenticated menu
        # flow; after cookie seeding, curl_cffi preserves that session and the
        # browser request's Referer while avoiding Chromium TLS resets.
        self._authenticated_document_bridge = False

    async def install(self) -> None:
        await self.page.route("**/*", self._handle_route)

    async def close(self) -> None:
        sessions = [self._session, self._document_session]
        self._session = None
        self._document_session = None
        self._document_session_warmed = False
        self._prefetched_documents.clear()
        self._prefetched_assets.clear()
        self._preserve_authenticated_session = False
        self._form_assets_bridge_enabled = False
        closed: set[int] = set()
        for session in sessions:
            if session is None or id(session) in closed:
                continue
            closed.add(id(session))
            try:
                await asyncio.to_thread(session.close)
            except Exception:
                logger.debug("http_browser_bridge_close_failed", exc_info=True)

    async def seed_cookies(self, cookies: list[dict[str, Any]]) -> None:
        """Seed the curl session with cookies obtained by HTTP login."""
        async with self._lock:
            self._seeded_cookies = [dict(c) for c in cookies if isinstance(c, dict)]
            self._authenticated_document_bridge = bool(self._seeded_cookies)
            self._preserve_authenticated_session = False
            if self._session is None:
                self._session = self._new_session()
            else:
                for cookie in self._seeded_cookies:
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

    async def adopt_authenticated_session(self, session: Any, cookies: list[dict[str, Any]] | None = None) -> None:
        """Adopt the exact curl session that completed HTTP login.

        UTCMS may bind the authenticated menu flow to server-side session
        state that is not reproducible from the visible cookie jar alone.
        Keeping this session avoids a redirect back to Login before the menu
        can open the waybill form.
        """
        if session is None:
            if cookies:
                await self.seed_cookies(cookies)
            return
        async with self._lock:
            old_request_session = self._session
            old_document_session = self._document_session
            self._document_session = session
            self._document_session_warmed = False
            self._prefetched_documents.clear()
            self._prefetched_assets.clear()
            self._form_assets_bridge_enabled = False
            self._seeded_cookies = [dict(c) for c in (cookies or []) if isinstance(c, dict)]
            # Keep XHR/fetch traffic off the exact session that completed the
            # login.  Live UTCMS testing showed that mixing Notification AJAX
            # requests with the next top-level HagigiHogugi navigation burns
            # the shared TLS connection; the same login session succeeds when
            # it performs only landing -> form documents.
            self._session = self._new_session()
            self._authenticated_document_bridge = True
            self._preserve_authenticated_session = False
            await self._prefetch_issuance_document(session)
        for old in (old_request_session, old_document_session):
            if old is None or old is session or old is self._session:
                continue
            try:
                await asyncio.to_thread(old.close)
            except Exception:
                logger.debug("http_browser_bridge_adopt_close_failed", exc_info=True)

    def _new_session(self) -> Any:
        from curl_cffi import requests as cc_requests  # type: ignore[import-not-found]

        proxies = {"http": self.proxy_url, "https": self.proxy_url} if self.proxy_url else None
        session = cc_requests.Session(
            impersonate="chrome120",
            proxies=proxies,
            verify=False,
            timeout=self.timeout,
        )
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,fa;q=0.8",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            }
        )
        if self._seeded_cookies:
            for cookie in self._seeded_cookies:
                name = str(cookie.get("name") or "").strip()
                if not name:
                    continue
                try:
                    session.cookies.set(
                        name,
                        str(cookie.get("value") or ""),
                        domain=cookie.get("domain") or _UTCMS_HOST,
                        path=cookie.get("path") or "/",
                    )
                except Exception:
                    logger.debug("http_browser_bridge_seed_cookie_failed", exc_info=True)
        return session

    async def _reset_session(self) -> None:
        old, self._session = self._session, None
        if old is not None:
            try:
                await asyncio.to_thread(old.close)
            except Exception:
                logger.debug("http_browser_bridge_reset_close_failed", exc_info=True)

    async def _warm_authenticated_document_session(self, session: Any) -> None:
        """Reproduce UTCMS's required post-login landing transition.

        UTCMS keeps part of the issuance-navigation state outside the visible
        cookie jar.  The exact curl session that completed login must visit
        Notification once before HagigiHogugi; warming only Chromium does not
        update this session-scoped server state.
        """
        if self._document_session_warmed:
            return
        response = await asyncio.to_thread(
            session.request,
            "GET",
            _AUTHENTICATED_LANDING_URL,
            headers={
                "Referer": "https://barname.utcms.ir/Barname/Account/OldLogin",
                "accept-encoding": "identity",
            },
            allow_redirects=False,
            timeout=self.timeout,
        )
        if int(response.status_code) != 200:
            raise RuntimeError(f"UTCMS authenticated landing warmup failed: HTTP {response.status_code}")
        self._document_session_warmed = True

    async def _prefetch_issuance_document(self, session: Any) -> None:
        """Fetch the form before Chromium starts concurrent landing traffic."""
        await self._warm_authenticated_document_session(session)
        form_url = "https://barname.utcms.ir/barname/Document/HagigiHogugi"
        response = await asyncio.to_thread(
            session.request,
            "GET",
            form_url,
            headers={
                "Referer": _AUTHENTICATED_LANDING_URL,
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
                "accept-encoding": "identity",
            },
            allow_redirects=False,
            timeout=self.timeout,
        )
        body = bytes(response.content or b"")
        if int(response.status_code) != 200 or not any(
            marker in body for marker in (b"txtSenderFirstName", b"txtReceiverFirstName", b"btnGoLVL2")
        ):
            raise RuntimeError(
                f"UTCMS issuance prefetch failed: HTTP {response.status_code}, body_len={len(body)}"
            )
        response_headers = {
            str(k): str(v) for k, v in response.headers.items() if str(k).lower() not in _RESPONSE_DROP_HEADERS
        }
        # The form GET may rotate ASP.NET/session cookies.  XHR/fetch use a
        # separate transport session, so copy the resulting jar before the
        # form JavaScript starts its dependent API calls.
        source_jar = getattr(session, "cookies", None)
        target_jar = getattr(self._session, "cookies", None)
        if source_jar is not None and target_jar is not None:
            try:
                for name, cookie in source_jar.items():
                    value = cookie.value if hasattr(cookie, "value") else str(cookie)
                    target_jar.set(name, value, domain=_UTCMS_HOST, path="/")
            except Exception:
                logger.debug("http_browser_bridge_cookie_sync_failed", exc_info=True)
        self._prefetched_documents[urlparse(form_url).path.lower()] = (
            int(response.status_code),
            response_headers,
            body,
        )
        await self._prefetch_document_scripts(session, form_url, body)

    @staticmethod
    def _request_cache_key(url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.path.lower()}?{parsed.query}" if parsed.query else parsed.path.lower()

    async def _prefetch_document_scripts(self, session: Any, form_url: str, body: bytes) -> None:
        """Warm the issuance form's scripts, critical files first.

        UTCMS's static surface is slow and frequently resets connections, and
        every synchronous ``<script src>`` that does not arrive blocks the HTML
        parser — which is why the form used to stall long before reaching
        ``jquery-ui``/``hagigihogugi*.js`` and stayed DOM-complete but dead.

        Scripts are therefore fetched in HTML order with the critical files
        first and stored in the on-disk cache, which survives across jobs
        because every URL is versioned.  Anything already cached is skipped, and
        a failure is logged and skipped rather than aborting the document: the
        JavaScript-liveness gate is what blocks unsafe progress.
        """
        html = body.decode("utf-8", errors="ignore")
        candidates: list[str] = []
        for src in re.findall(r'<script[^>]+src=["\']([^"\']+)', html, flags=re.IGNORECASE):
            script_url = urljoin(form_url, src)
            parsed = urlparse(script_url)
            if parsed.scheme not in {"http", "https"} or parsed.hostname != _UTCMS_HOST:
                continue
            if script_url not in candidates:
                candidates.append(script_url)
        # Critical files first: if the connection dies mid-warmup, the form must
        # still have everything it needs to initialise.
        ordered = [url for url in candidates if _is_critical_form_script(url)]
        ordered += [url for url in candidates if not _is_critical_form_script(url)]

        prefetched = 0
        cached = 0
        failures = 0
        for script_url in ordered:
            parsed = urlparse(script_url)
            cache_key = self._request_cache_key(script_url)
            critical = _is_critical_form_script(script_url)
            if await asyncio.to_thread(_read_asset_cache, cache_key) is not None:
                cached += 1
                continue
            # A dead connection is not worth dragging through the whole tail of
            # optional vendor bundles; the route handler stubs whatever is left.
            if failures >= 3 and not critical:
                continue
            try:
                response = await asyncio.to_thread(
                    session.request,
                    "GET",
                    script_url,
                    headers={
                        "Referer": form_url,
                        "Sec-Fetch-Dest": "script",
                        "Sec-Fetch-Mode": "no-cors",
                        "Sec-Fetch-Site": "same-origin",
                        "accept-encoding": "identity",
                    },
                    allow_redirects=False,
                    timeout=self.timeout,
                )
            except Exception:
                failures += 1
                logger.warning(
                    "http_browser_bridge_script_prefetch_error path=%s critical=%s",
                    parsed.path,
                    critical,
                    exc_info=True,
                )
                continue
            body_bytes = bytes(response.content or b"")
            if int(response.status_code) != 200 or not body_bytes:
                failures += 1
                logger.warning(
                    "http_browser_bridge_script_prefetch_rejected path=%s status=%s body_len=%d",
                    parsed.path,
                    response.status_code,
                    len(body_bytes),
                )
                continue
            headers = {
                str(k): str(v)
                for k, v in response.headers.items()
                if str(k).lower() not in _RESPONSE_DROP_HEADERS
            }
            self._prefetched_assets[cache_key] = (int(response.status_code), headers, body_bytes)
            await asyncio.to_thread(
                _write_asset_cache, cache_key, int(response.status_code), headers, body_bytes
            )
            prefetched += 1
        logger.info(
            "http_browser_bridge_form_scripts_warmed fetched=%d already_cached=%d failed=%d candidates=%d",
            prefetched,
            cached,
            failures,
            len(ordered),
        )

    async def _handle_route(self, route: Any) -> None:
        request = route.request
        parsed = urlparse(request.url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname != _UTCMS_HOST:
            await route.continue_()
            return

        # Before HTTP authentication, retain the Playwright-only fallback.
        # Afterwards, documents use the exact curl session that completed the
        # login while XHR/fetch use a separate cookie-seeded session. Chromium
        # itself is intermittently rejected during the issuance-page TLS
        # handshake, but sharing one curl session with landing-page AJAX also
        # burns the following document request.
        if request.resource_type == "document":
            path_lower = parsed.path.lower()
            # Keep the authenticated landing/menu pages native.  Only the
            # issuance document is bridged: Chromium reliably renders the
            # landing page, but its TLS handshake is reset on the form route.
            # This also prevents Notification AJAX traffic from consuming the
            # exact login session reserved for the form document.
            if not self._authenticated_document_bridge or not any(
                marker in path_lower for marker in _ISSUANCE_DOCUMENT_MARKERS
            ):
                await route.continue_()
                return

        # Once the issuance document is fulfilled, route its JavaScript through
        # curl_cffi as well.  Chromium's TLS stack intermittently resets these
        # assets (especially hagigihogugi*.js and jQuery plugins), leaving a
        # visually complete but non-functional form.  Do not bridge landing
        # page assets: the flag is enabled only after the issuance document
        # has been consumed, so Notification remains native.
        is_asset = request.resource_type in _ASSET_RESOURCE_TYPES and self._form_assets_bridge_enabled
        if request.resource_type in _DISCARDED_RESOURCE_TYPES and self._form_assets_bridge_enabled:
            # Fonts never affect issuance correctness, and each stalled request
            # costs seconds on an already slow static surface.
            try:
                await route.abort("blockedbyclient")
            except Exception:
                logger.debug("http_browser_bridge_font_abort_failed", exc_info=True)
            return
        if request.resource_type not in _BRIDGED_RESOURCE_TYPES and not is_asset:
            await route.continue_()
            return

        is_safe_method = request.method.upper() in _SAFE_IDEMPOTENT_METHODS
        try:
            await self._fulfill_utcms(
                route,
                request,
                document=request.resource_type == "document",
                asset=is_asset,
            )
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
            if is_asset and not _is_critical_form_script(request.url):
                # A synchronous <script>/<link> that never arrives blocks the HTML
                # parser, so the rest of the form — including the critical files
                # further down the document — is never even requested.  Optional
                # vendor bundles are therefore answered with an empty body.
                # Critical files are never stubbed: their absence must surface
                # through the JavaScript-liveness gate instead of being hidden.
                try:
                    await route.fulfill(
                        status=200,
                        headers={"content-type": _asset_stub_content_type(request.url)},
                        body=b"",
                    )
                    return
                except Exception:
                    logger.debug("http_browser_bridge_asset_stub_failed", exc_info=True)
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

    async def _fulfill_utcms(
        self,
        route: Any,
        request: Any,
        *,
        document: bool = False,
        asset: bool = False,
    ) -> None:
        headers = dict(await request.all_headers())
        headers = {k: v for k, v in headers.items() if k.lower() not in _REQUEST_DROP_HEADERS}
        # curl_cffi transparently decompresses responses. Asking for identity
        # avoids forwarding a stale Content-Encoding header to Chromium.
        headers["accept-encoding"] = "identity"
        body = request.post_data_buffer

        is_safe_method = request.method.upper() in _SAFE_IDEMPOTENT_METHODS
        # Assets get a single attempt: retries hold the page's parser hostage and
        # the on-disk cache is what makes the form deterministic instead.
        max_attempts = 1 if asset or not is_safe_method else 3

        if asset:
            # Served outside the transport lock so static files never queue
            # behind the form's document/XHR traffic.
            asset_cache_key = self._request_cache_key(request.url)
            cached_asset = self._prefetched_assets.pop(asset_cache_key, None)
            if cached_asset is None:
                cached_asset = await asyncio.to_thread(_read_asset_cache, asset_cache_key)
            if cached_asset is not None:
                status, cached_headers, cached_body = cached_asset
                await route.fulfill(status=status, headers=cached_headers, body=cached_body)
                return

        async with self._lock:
            response = None
            last_error: Exception | None = None
            if document:
                cached = self._prefetched_documents.pop(urlparse(request.url).path.lower(), None)
                if cached is not None:
                    # The form's dependent AJAX calls (cargo, driver, and
                    # location lookups) must continue on the exact session
                    # that performed the authenticated Notification -> form
                    # transition.  A cookie-only session is insufficient:
                    # UTCMS keeps server-side state outside the visible jar.
                    # Notification itself remains native because landing-page
                    # traffic is intentionally kept off this reserved session.
                    if self._document_session is not None and self._session is not self._document_session:
                        stale_xhr_session, self._session = self._session, self._document_session
                        self._preserve_authenticated_session = True
                        if stale_xhr_session is not None:
                            try:
                                await asyncio.to_thread(stale_xhr_session.close)
                            except Exception:
                                logger.debug("http_browser_bridge_xhr_session_close_failed", exc_info=True)
                    self._form_assets_bridge_enabled = True
                    status, cached_headers, cached_body = cached
                    await route.fulfill(status=status, headers=cached_headers, body=cached_body)
                    return
            for attempt in range(1, max_attempts + 1):
                if document:
                    if self._document_session is None:
                        self._document_session = self._new_session()
                        self._document_session_warmed = False
                    session = self._document_session
                    await self._warm_authenticated_document_session(session)
                elif asset:
                    # JavaScript required by the issuance form must use the
                    # same authenticated transport that fetched the HTML.
                    # A fresh curl session gets the same TLS reset as
                    # Chromium and cannot reproduce UTCMS server-side state.
                    if self._document_session is None:
                        self._document_session = self._new_session()
                        self._document_session_warmed = False
                    session = self._document_session
                    await self._warm_authenticated_document_session(session)
                else:
                    if self._session is None:
                        self._session = self._new_session()
                    session = self._session
                try:
                    response = await asyncio.to_thread(
                        session.request,
                        request.method,
                        request.url,
                        headers=headers,
                        data=body,
                        allow_redirects=False,
                        timeout=self.timeout,
                    )
                    if not is_safe_method or response.status_code not in (408, 429, 500, 502, 503, 504):
                        break
                    # A session that completed HTTP login carries server-side
                    # state not reproducible from cookies alone. Keep it for
                    # transient retries; closing it here turns one TLS hiccup
                    # into a guaranteed unauthenticated/408 follow-up.
                    if not document and not asset and not self._preserve_authenticated_session:
                        await self._reset_session()
                    if attempt < max_attempts:
                        await asyncio.sleep(float(attempt))
                except Exception as exc:
                    last_error = exc
                    if not document and not asset and not self._preserve_authenticated_session:
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
            if asset:
                # Every asset this run manages to download makes the next run
                # faster and less dependent on UTCMS's static surface.
                await asyncio.to_thread(
                    _write_asset_cache,
                    self._request_cache_key(request.url),
                    int(response.status_code),
                    response_headers,
                    bytes(response.content or b""),
                )
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
