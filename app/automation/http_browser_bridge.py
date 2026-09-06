"""Route UTCMS Playwright traffic through curl_cffi's Chrome TLS stack.

UTCMS accepts the Chrome fingerprint produced by curl_cffi but intermittently
drops Chromium's own TLS handshake.  Playwright is still valuable for running
the portal JavaScript and interacting with the form, so this bridge intercepts
only requests to the UTCMS host, performs them with curl_cffi, and fulfils the
Playwright route with the returned response.
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
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
# Images are bridged too, not because they matter visually but because every
# resource Chromium fetches itself is a NEW TLS handshake from this egress IP.
# Measured from Squid's tunnel log on 2026-08-28: while Chromium loaded the
# authenticated landing page natively it opened 13 connections inside 60ms, and
# UTCMS refused every one of them ("TCP_TUNNEL/200 39" at 2ms).  Seven seconds
# later the bridge's own healthy 48s tunnel was gone as well, so the next XHR had
# to handshake and was throttled.  The run was poisoning its own IP from the
# inside -- which is why cooling the IP between runs never helped.
_ASSET_RESOURCE_TYPES = frozenset({"script", "stylesheet", "image"})
# Web fonts are cosmetic, are served from the same slow static surface, and each
# failed request costs seconds of page time.
_DISCARDED_RESOURCE_TYPES = frozenset({"font"})


_SAFE_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD"})
_AUTHENTICATED_LANDING_URL = "https://barname.utcms.ir/Barname/Notification/Notification"
# Two numbers measured from Squid's own tunnel log on 2026-08-28:
#  * tunnels to UTCMS die after a hard ~30s idle (repeated "30004 ms" durations),
#    so the reserved connection cannot survive Chromium's render/fill gaps; and
#  * fresh handshakes spaced ~7s apart are ALL rejected instantly (a run of
#    "TCP_TUNNEL/200 39" entries — 39 bytes is a killed ClientHello), while the
#    tunnels spaced 37s/45s/101s apart in the same log all carried real data.
# Pinging every 20s therefore keeps the connection established (so no handshake
# is needed at all) without ever entering the handshake-rejection window.  An
# earlier 7s ping was actively harmful: it only fired once the connection was
# already dead, turning recovery into a handshake storm that held the throttle
# permanently engaged and killed KalaSearch/Captcha for the rest of the run.
_KEEPALIVE_INTERVAL_SECONDS = 20.0
# Minimum gap between two runtime XHR on the reserved session.  UTCMS's upstream
# refuses a burst (see ``_last_xhr_dispatch_at``); ~20 init calls therefore cost
# a few seconds of pacing, which is far cheaper than the retries the burst used
# to trigger -- each of which also spent a throttled TLS handshake.
_XHR_MIN_SPACING_SECONDS = 0.4
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
_JSON_CACHE_TTL_SECONDS = 8.0


class BridgeTransportTimeout(TimeoutError):
    """Raised when a curl operation outlives the bridge's hard deadline."""


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


# Captcha endpoints whose response body is the challenge itself.  DNTCaptcha is
# the variant UTCMS serves on the issuance form (``#CapType == "1"``); the other
# two spellings cover the ``CaptchaCode``/``window.cap`` branches.
_CAPTCHA_ASSET_MARKERS = (
    "dntcaptchaimage",
    "/captchaimage",
    "captcha/show",
    "getcaptcha",
)


def _is_captcha_asset(url: str) -> bool:
    lowered = url.lower()
    return any(marker in lowered for marker in _CAPTCHA_ASSET_MARKERS)


def _is_behavioural_asset(url: str, resource_type: Any = None) -> bool:
    """Does this asset change what the automation can observe or do?

    Scripts: live diagnosis on 2026-08-28 killed the assumption that
    non-critical scripts are cosmetic.  The issuance template's document-ready
    handler calls ``FormDocumenDetailsRegister`` and instantiates
    ``FormValidation.Framework.Bootstrap``, and neither is defined in the eight
    hand-listed critical files.  Stubbing their defining bundles with an empty
    body made the ready handler throw, and because it throws NOTHING after it
    runs: no cargo autocomplete, no ``fillBoxType``, no
    ``GETUserFleetListTajmi``, no plate/driver change handlers, no cargo modal.

    Stylesheets: on 2026-08-30 an empty CSS stub was traced to a false
    ``otp_challenge_visible`` reading.  ``#submitOtp`` lives in the closed
    ``FormSendOtpCode`` Bootstrap modal, and ``.modal { display: none }`` comes
    from the stubbed stylesheet -- so with CSS empty-bodied, every hidden modal
    has a real box and Playwright reports it visible.  The bot's OTP/CAPTCHA
    gate decisions are visibility decisions, so CSS is behaviour here, not
    decoration.  Only fonts and images are stubbed now.
    Images: almost all of them are decoration, but the final-registration
    CAPTCHA is an image (``/DNTCaptchaImage/Show?data=...``).  An empty stub
    renders it as a broken image, the solver then reads nothing and fills a
    junk value, and UTCMS rejects the save -- so captcha images must go to the
    network like scripts and stylesheets.  Everything else (fonts, logos,
    icons) is still stubbed.
    """
    if isinstance(resource_type, str) and resource_type in {"script", "stylesheet"}:
        return True
    if _is_captcha_asset(url):
        return True
    return urlparse(url).path.lower().endswith((".js", ".css"))


def _asset_stub_content_type(url: str) -> str:
    return "text/css; charset=utf-8" if urlparse(url).path.lower().endswith(".css") else "application/javascript"



class UtcmsHttpBrowserBridge:
    """A page-scoped, serialized curl_cffi transport for UTCMS requests."""

    def __init__(self, page: Any, *, proxy_url: str | None = None, timeout: float = 45.0) -> None:
        self.page = page
        self.proxy_url = (proxy_url or get_worker_proxy_url() or "").strip() or None
        self.timeout = timeout
        self._lock = asyncio.Lock()
        # curl_cffi/libcurl handles are not safe to use across threads.  A busy
        # worker event loop spreads asyncio.to_thread() calls over the default
        # multi-thread pool, so the same session gets driven from alternating
        # threads and UTCMS tears the TLS connection down ("Connection closed
        # abruptly").  Pin every curl operation for this bridge to ONE thread.
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="utcms-bridge"
        )
        self._executor_generation = 0
        self._session: Any = None
        self._document_session: Any = None
        # Static /assets traffic gets its OWN disposable session.  UTCMS's
        # static surface answers scripts with connection teardowns, and when
        # those fetches shared the reserved login session the teardown killed
        # the very keep-alive the runtime XHR depend on: the next KalaSearch /
        # Captcha / fillStates had to open a fresh handshake, which UTCMS's edge
        # rejects when several arrive at once.  A pure-transport probe on the
        # same egress at the same moment answered 200 for all three XHR on a
        # session that had NOT been used for scripts, which is what isolated
        # asset churn to this session.
        self._asset_session: Any = None
        self._asset_session_warmed = False
        # While Chromium renders the form and the operator-visible fill runs, the
        # reserved session sits idle long enough for UTCMS to drop the keep-alive.
        # The next runtime XHR then needs a brand-new TLS handshake, and UTCMS's
        # edge rejects new handshakes from a warm egress IP ("SSL_connect:
        # Connection closed abruptly") — proven concurrently on 2026-08-28, when a
        # second process on the same container could not even complete login while
        # these XHR were failing.  A low-frequency keep-alive ping holds the
        # established connection open so KalaSearch/Captcha/fillStates reuse it
        # instead of gambling on a fresh handshake.
        self._keepalive_task: asyncio.Task[None] | None = None
        self._last_transport_at = 0.0
        # Idleness has to be tracked PER SESSION.  A single global timestamp was
        # bumped by asset and XHR traffic on the *other* two sessions, so while
        # Chromium streamed scripts the keepalive kept concluding "the transport
        # is busy" and skipped its ping -- and the reserved document session,
        # which is the one whose connection the runtime XHR inherit, sat idle
        # past UTCMS's ~30s tunnel timeout and died.  Measured 2026-08-28: the
        # loop reported ``pings=0 consecutive_failures=2`` for exactly this
        # reason, then Captcha/Generate needed a fresh (throttled) handshake.
        self._last_document_transport_at = 0.0
        # The issuance form's initialiser fires ~20 XHR within ~2.5s (fillBoxType,
        # FillProvinces, fillgrid*, GetCostSettings, GetFleetDriverList, ...).
        # Measured on 2026-08-28: in that burst UTCMS answers 408
        # "سرور در حال حاضر قادر به پاسخگویی نمی باشد" / 500
        # "ارتباط با سرویس‌ها برقرار نیست" / bare 400, while the very same
        # requests answer 200 when issued alone on the same session.  The burst
        # itself is the trigger, so runtime XHR are spaced out.
        self._last_xhr_dispatch_at = 0.0
        self._cookie_divergence_logged = False
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
        self._json_cache: dict[str, tuple[float, Any]] = {}

    async def install(self) -> None:
        await self.page.route("**/*", self._handle_route)

    async def _call(self, func: Any, /, *args: Any, **kwargs: Any) -> Any:
        """Run a curl_cffi session operation on this bridge's pinned thread."""
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(
            self._executor, functools.partial(func, *args, **kwargs)
        )
        try:
            # curl_cffi normally honours its own timeout, but a stuck libcurl
            # call used to hold the serialized bridge lock until the whole job
            # deadline.  A shield keeps the underlying future from being
            # cancelled while the worker thread unwinds; the executor is
            # rotated so later requests are not queued behind that call.
            deadline = max(0.25, float(self.timeout))
            return await asyncio.wait_for(asyncio.shield(future), timeout=deadline)
        except asyncio.TimeoutError as exc:
            self._rotate_executor()
            logger.error(
                "http_browser_bridge_transport_timeout timeout=%ss executor_generation=%s",
                max(0.25, float(self.timeout)),
                self._executor_generation,
            )
            raise BridgeTransportTimeout(f"curl operation exceeded {max(0.25, float(self.timeout)):.1f}s") from exc

    def _rotate_executor(self) -> None:
        """Detach a wedged curl thread so the page can continue with a fresh one."""
        old_executor = self._executor
        self._executor_generation += 1
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix=f"utcms-bridge-{self._executor_generation}",
        )
        old_executor.shutdown(wait=False, cancel_futures=True)

    async def close(self) -> None:
        await self._stop_keepalive()
        sessions = [self._session, self._document_session, self._asset_session]
        self._session = None
        self._document_session = None
        self._asset_session = None
        self._asset_session_warmed = False
        self._document_session_warmed = False
        self._prefetched_documents.clear()
        self._prefetched_assets.clear()
        self._json_cache.clear()
        self._preserve_authenticated_session = False
        self._form_assets_bridge_enabled = False
        closed: set[int] = set()
        for session in sessions:
            if session is None or id(session) in closed:
                continue
            closed.add(id(session))
            try:
                await self._call(session.close)
            except Exception:
                logger.debug("http_browser_bridge_close_failed", exc_info=True)
        self._executor.shutdown(wait=False)

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

    async def fetch_json(self, url: str, params: dict[str, Any] | None = None, *, referer: str = "") -> Any | None:
        """GET a UTCMS JSON endpoint on the reserved authenticated session.

        The form's own jQuery AJAX is not a reliable way to reach these lookups:
        jQuery UI only initialises its autocomplete when the optional scripts the
        route handler stubs are present, and when the page-side call fails all the
        caller sees is an empty ``error`` callback.  Run 4 (2026-08-28) lost the
        cargo stage exactly that way -- three retryable statuses on
        ``KalaSearch`` -- while the identical request answered 200 on a direct
        authenticated session.  Callers that need a catalogue lookup (cargo,
        cities) should ask here first and treat the page as a rendering surface
        only.  Read-only by construction: GET, no redirects followed.
        """
        cache_key = self._request_cache_key(url, params)
        cached_json = self._json_cache.get(cache_key)
        if cached_json is not None:
            expires_at, value = cached_json
            if expires_at > time.monotonic():
                return value
            self._json_cache.pop(cache_key, None)

        async with self._lock:
            session = self._document_session or self._session
            if session is None:
                session = self._session = self._new_session()
            headers = {
                "accept": "application/json, text/javascript, */*; q=0.01",
                "accept-encoding": "identity",
                "x-requested-with": "XMLHttpRequest",
            }
            if referer:
                headers["referer"] = referer
            try:
                response = await self._call(
                    session.get,
                    url,
                    params=dict(params or {}),
                    headers=headers,
                    allow_redirects=False,
                    timeout=self.timeout,
                )
            except Exception:
                logger.warning("http_browser_bridge_fetch_json_failed url=%s", url[:120], exc_info=True)
                return None
            self._last_transport_at = time.monotonic()
            if session is self._document_session:
                self._last_document_transport_at = self._last_transport_at
            if int(response.status_code) != 200:
                logger.warning(
                    "http_browser_bridge_fetch_json_status url=%s status=%s",
                    url[:120],
                    int(response.status_code),
                )
                return None
            try:
                parsed = json.loads(response.text)
            except Exception:
                logger.warning("http_browser_bridge_fetch_json_unparsable url=%s", url[:120])
                return None
            # UTCMS sometimes returns a JSON *string* containing the JSON payload.
            if isinstance(parsed, str):
                try:
                    parsed = json.loads(parsed)
                except Exception:
                    return None
            self._json_cache[cache_key] = (time.monotonic() + _JSON_CACHE_TTL_SECONDS, parsed)
            return parsed

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
                await self._call(old.close)
            except Exception:
                logger.debug("http_browser_bridge_adopt_close_failed", exc_info=True)

    def _new_session(self) -> Any:
        from curl_cffi import requests as cc_requests  # type: ignore[import-not-found]

        proxies = {"http": self.proxy_url, "https": self.proxy_url} if self.proxy_url else None
        session = cc_requests.Session(
            impersonate="chrome120",
            proxies=proxies,
            # This session carries the UTCMS username/password and waybill PII.
            # With the Clean IP Pool active the egress is a third-party proxy we
            # do not control, so verify=False would let its operator terminate
            # TLS and read the login in clear text. Measured 2026-08-28: a
            # cert-verified chrome120 session through a free Iranian proxy
            # returns the real login page, so verification is not what was
            # breaking the handshake — the per-IP WAF throttle was.
            verify=True,
            timeout=self.timeout,
            # See the same flag in ``utcms_http_login._build_session``: curl_cffi
            # keeps the libcurl handle -- and therefore the connection cache --
            # in thread-local storage by default.  Every session here is driven
            # from ``self._executor``, but ``close()`` and the adopted login
            # session are not always touched from that same thread, and a
            # per-thread handle silently means a per-thread TLS connection.
            use_thread_local_curl=False,
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
                await self._call(old.close)
            except Exception:
                logger.debug("http_browser_bridge_reset_close_failed", exc_info=True)

    async def _ensure_asset_session(self) -> Any:
        """Return the disposable session used for static /assets fetches.

        It is cookie-seeded and warmed through the authenticated landing page so
        UTCMS treats it as a logged-in client, but it is deliberately NOT the
        reserved login session: script responses that close the connection may
        only ever cost this session its keep-alive, never the one carrying the
        runtime XHR.
        """
        if self._asset_session is None:
            self._asset_session = self._new_session()
            self._asset_session_warmed = False
        if not self._asset_session_warmed:
            try:
                await self._call(
                    self._asset_session.request,
                    "GET",
                    _AUTHENTICATED_LANDING_URL,
                    headers={
                        "Referer": "https://barname.utcms.ir/Barname/Account/OldLogin",
                        "accept-encoding": "identity",
                    },
                    allow_redirects=False,
                    timeout=self.timeout,
                )
            except Exception:
                # A failed warmup is not fatal: static files usually serve
                # without it, and the caller already tolerates asset misses.
                logger.debug("http_browser_bridge_asset_warm_failed", exc_info=True)
            self._asset_session_warmed = True
        return self._asset_session

    def _start_keepalive(self) -> None:
        """Hold the reserved session's connection open for the browser's XHR."""
        if self._keepalive_task is not None and not self._keepalive_task.done():
            return
        self._last_transport_at = time.monotonic()
        self._last_document_transport_at = self._last_transport_at
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())

    async def _stop_keepalive(self) -> None:
        task, self._keepalive_task = self._keepalive_task, None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    async def _keepalive_loop(self) -> None:
        # If the connection is already gone, every ping is a fresh handshake, and
        # a stream of rejected handshakes is what keeps UTCMS's edge hostile.
        # Give up quickly rather than adding pressure.
        consecutive_failures = 0
        pings = 0
        while consecutive_failures < 2:
            await asyncio.sleep(_KEEPALIVE_INTERVAL_SECONDS)
            # Real traffic is itself a keep-alive; only ping into a quiet gap, and
            # never contend for the transport lock with a request in flight.
            # This must look at the DOCUMENT session's own last use: traffic on
            # the asset or XHR sessions says nothing about whether the reserved
            # connection is still warm, and treating it as proof is what let the
            # connection die under a stream of script fetches.
            if time.monotonic() - self._last_document_transport_at < _KEEPALIVE_INTERVAL_SECONDS:
                continue
            if self._lock.locked():
                continue
            async with self._lock:
                # Ping the reserved session itself: it owns the connection the
                # runtime XHR inherit at the swap, and it must not go idle even
                # before the swap happens (Chromium's navigate+render gap alone
                # exceeds UTCMS's ~30s tunnel idle timeout).
                session = self._document_session
                if session is None:
                    continue
                try:
                    await self._call(
                        session.request,
                        "GET",
                        _AUTHENTICATED_LANDING_URL,
                        headers={
                            "Referer": _AUTHENTICATED_LANDING_URL,
                            "accept-encoding": "identity",
                        },
                        allow_redirects=False,
                        timeout=self.timeout,
                    )
                    self._last_transport_at = time.monotonic()
                    self._last_document_transport_at = self._last_transport_at
                    consecutive_failures = 0
                    pings += 1
                except Exception:
                    consecutive_failures += 1
                    logger.debug("http_browser_bridge_keepalive_failed", exc_info=True)
        logger.info(
            "http_browser_bridge_keepalive_stopped pings=%d consecutive_failures=%d",
            pings,
            consecutive_failures,
        )

    async def _rewarm_preserved_session(self) -> None:
        """Re-establish a live keep-alive on the reserved authenticated session.

        Proven live on 2026-08-28: the exact login session performs every
        runtime XHR (GetCostSettings/fillStates/KalaSearch) with HTTP 200 when
        its connection is warm — a pure-transport probe on the same egress at
        the same moment returned 200 for all three even after a 12s idle.  The
        browser path fails instead with ``SSL_connect: Connection closed
        abruptly`` because curl reuses a pooled connection that UTCMS silently
        drops during the browser's form-render/fill gap, and the stale reuse is
        surfaced as a fresh-handshake reset.  Revisiting the Notification
        landing forces a fresh, accepted TLS connection before the XHR is
        retried, reproducing the working sequence.
        """
        session = self._session
        if session is None or session is not self._document_session:
            return
        self._document_session_warmed = False
        try:
            await self._warm_authenticated_document_session(session)
        except Exception:
            logger.debug("http_browser_bridge_preserved_rewarm_failed", exc_info=True)

    async def _warm_authenticated_document_session(self, session: Any) -> None:
        """Reproduce UTCMS's required post-login landing transition.

        UTCMS keeps part of the issuance-navigation state outside the visible
        cookie jar.  The exact curl session that completed login must visit
        Notification once before HagigiHogugi; warming only Chromium does not
        update this session-scoped server state.
        """
        if self._document_session_warmed:
            return
        response = await self._call(
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
        response = await self._call(
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
        await self._prefetch_document_assets(form_url, body)
        # The connection is alive right now.  Chromium's navigate+render gap on
        # its own exceeds UTCMS's ~30s tunnel idle timeout, so start holding the
        # connection open here rather than waiting for the XHR swap — by then it
        # would already be dead and only a (throttled) handshake could recover.
        self._start_keepalive()

    @staticmethod
    def _request_cache_key(url: str, params: dict[str, Any] | None = None) -> str:
        parsed = urlparse(url)
        key = f"{parsed.path.lower()}?{parsed.query}" if parsed.query else parsed.path.lower()
        if params:
            key = f"{key}|{json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)}"
        return key

    async def _prefetch_document_assets(self, form_url: str, body: bytes) -> None:
        """Warm the issuance form's scripts and stylesheets, critical files first.

        Fetches always go on the disposable asset session (see
        ``_ensure_asset_session``), never on a caller-supplied one -- the whole
        point is to keep script traffic off the reserved login session. The
        ``session`` parameter this used to take was silently ignored after that
        change, which made the call site read as if the login session were still
        being used; it is gone rather than left as a lie.

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

        def _add(raw: str) -> None:
            asset_url = urljoin(form_url, raw)
            parsed = urlparse(asset_url)
            if parsed.scheme not in {"http", "https"} or parsed.hostname != _UTCMS_HOST:
                return
            if asset_url not in candidates:
                candidates.append(asset_url)

        for src in re.findall(r'<script[^>]+src=["\']([^"\']+)', html, flags=re.IGNORECASE):
            _add(src)
        # Stylesheets are warmed for a different reason than scripts: the bot's
        # OTP/CAPTCHA decisions are visibility decisions, and Bootstrap's
        # ``.modal { display: none }`` is what keeps a closed modal invisible.
        # They go last because nothing initialises from them.
        stylesheet_start = len(candidates)
        for tag in re.findall(r"<link\b[^>]*>", html, flags=re.IGNORECASE):
            if not re.search(r'rel\s*=\s*["\']?stylesheet', tag, flags=re.IGNORECASE):
                continue
            href = re.search(r'href\s*=\s*["\']([^"\']+)', tag, flags=re.IGNORECASE)
            if href:
                _add(href.group(1))
        scripts = candidates[:stylesheet_start]
        stylesheets = candidates[stylesheet_start:]
        # Critical files first: if the connection dies mid-warmup, the form must
        # still have everything it needs to initialise.  The rest follow in HTML
        # order — they are no longer optional.  Treating them as cosmetic and
        # stubbing them is what left FormDocumenDetailsRegister and
        # FormValidation.Framework.Bootstrap undefined, which aborted the
        # template's document-ready handler and with it every runtime behaviour
        # the automation was reimplementing in Python.
        ordered = [url for url in scripts if _is_critical_form_script(url)]
        ordered += [url for url in scripts if not _is_critical_form_script(url)]
        ordered += stylesheets

        prefetched = 0
        cached = 0
        failures = 0
        # The asset session is created lazily, only when a script actually has to
        # be fetched.  Creating it up-front cost a pointless extra TLS handshake
        # on every run whose cache was already complete, and spare handshakes are
        # exactly what UTCMS's edge punishes.
        asset_session: Any = None
        for asset_url in ordered:
            parsed = urlparse(asset_url)
            cache_key = self._request_cache_key(asset_url)
            critical = _is_critical_form_script(asset_url)
            is_stylesheet = parsed.path.lower().endswith(".css")
            if await asyncio.to_thread(_read_asset_cache, cache_key) is not None:
                cached += 1
                continue
            # A dead connection is not worth dragging through the whole tail of
            # optional vendor bundles; the route handler stubs whatever is left.
            if failures >= 3 and not critical:
                continue
            # Critical scripts get a couple of retries with a short backoff:
            # a single WAF handshake reset must not leave the form missing its
            # validators.  A brief pace between fetches keeps the burst of new
            # requests off the reserved connection gentle enough to avoid the
            # throttle in the first place.
            response = None
            fetch_error: Exception | None = None
            attempts = 3 if critical else 1
            for attempt in range(attempts):
                try:
                    if asset_session is None:
                        # Scripts never ride the reserved login session: UTCMS's
                        # static surface closes connections, and that teardown
                        # would strand the runtime XHR on a dead keep-alive.
                        asset_session = await self._ensure_asset_session()
                    response = await self._call(
                        asset_session.request,
                        "GET",
                        asset_url,
                        headers={
                            "Referer": form_url,
                            "Sec-Fetch-Dest": "style" if is_stylesheet else "script",
                            "Sec-Fetch-Mode": "no-cors",
                            "Sec-Fetch-Site": "same-origin",
                            "accept-encoding": "identity",
                        },
                        allow_redirects=False,
                        timeout=self.timeout,
                    )
                    fetch_error = None
                    break
                except Exception as exc:  # noqa: BLE001 - retried below
                    fetch_error = exc
                    response = None
                    if attempt + 1 < attempts:
                        await asyncio.sleep(0.6 * (attempt + 1))
            if fetch_error is not None or response is None:
                failures += 1
                logger.warning(
                    "http_browser_bridge_script_prefetch_error path=%s critical=%s",
                    parsed.path,
                    critical,
                    exc_info=fetch_error,
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
            # Gentle pace so the reserved connection serves scripts one at a
            # time instead of triggering a burst of parallel-looking handshakes.
            await asyncio.sleep(0.15)
        logger.info(
            "http_browser_bridge_form_assets_warmed fetched=%d already_cached=%d failed=%d candidates=%d stylesheets=%d",
            prefetched,
            cached,
            failures,
            len(ordered),
            len(stylesheets),
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
        # Static resources are bridged for the WHOLE authenticated session, not
        # just the issuance page.  Gating this on the issuance document meant the
        # landing page's assets were fetched by Chromium itself, and that burst
        # of refused handshakes is what made the egress IP hostile before the
        # form was even open (see _ASSET_RESOURCE_TYPES).
        is_asset = request.resource_type in _ASSET_RESOURCE_TYPES and self._authenticated_document_bridge
        if request.resource_type in _DISCARDED_RESOURCE_TYPES and self._authenticated_document_bridge:
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

    def _log_cookie_divergence(self, browser_cookie: str) -> None:
        """Report, once, which cookie NAMES the page and the session disagree on.

        Values are never logged -- only the names, and only the first time, so a
        token mismatch is visible without putting a session token in a log file.
        """
        if self._cookie_divergence_logged:
            return
        session = self._document_session or self._session
        jar = getattr(session, "cookies", None)
        if jar is None:
            return
        differing: list[str] = []
        missing: list[str] = []
        for chunk in browser_cookie.split(";"):
            name, _, value = chunk.strip().partition("=")
            if not name:
                continue
            try:
                mine = jar.get(name)
            except Exception:
                mine = None
            if mine is None:
                missing.append(name)
            elif str(mine) != value:
                differing.append(name)
        self._cookie_divergence_logged = True
        logger.info(
            "http_browser_bridge_cookie_header_dropped differing=%s absent_from_jar=%s",
            differing,
            missing,
        )

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
        browser_cookie = ""
        if not asset and not document:
            # Document navigation keeps the page's Cookie header: dropping it once
            # made warm authenticated navigation look cold and UTCMS answered with
            # its 408 shell (see test_utcms_bridge_forwards_browser_auth_cookie).
            # Runtime XHR are the opposite case.  The bridge session IS the
            # authentication -- its jar comes straight from the HTTP login, which
            # returns TWO ApplicationToken cookies, and Playwright can only keep
            # one per (name, domain, path).  Whatever the page echoes back can
            # therefore override the jar with the other token on exactly the
            # requests whose backend validates it.  Measured 2026-08-28:
            # fillBoxType and FillProvinces answered 408 "سرور ... قادر به
            # پاسخگویی نمی باشد" and ShowNotification 500 "ارتباط با سرویس‌ها
            # برقرار نیست" from the page, while a bare probe on the same session
            # answered 200.
            for key in [k for k in headers if k.lower() == "cookie"]:
                browser_cookie = headers.pop(key)
        if browser_cookie:
            self._log_cookie_divergence(browser_cookie)
        # curl_cffi transparently decompresses responses. Asking for identity
        # avoids forwarding a stale Content-Encoding header to Chromium.
        headers["accept-encoding"] = "identity"
        body = request.post_data_buffer

        is_safe_method = request.method.upper() in _SAFE_IDEMPOTENT_METHODS
        # Assets get a single attempt: retries hold the page's parser hostage and
        # the on-disk cache is what makes the form deterministic instead.
        max_attempts = 1 if asset or not is_safe_method else 3

        if asset and not _is_captcha_asset(request.url):
            # Served outside the transport lock so static files never queue
            # behind the form's document/XHR traffic.  Captcha images skip the
            # cache entirely: every challenge is single-use.
            asset_cache_key = self._request_cache_key(request.url)
            cached_asset = self._prefetched_assets.pop(asset_cache_key, None)
            if cached_asset is None:
                cached_asset = await asyncio.to_thread(_read_asset_cache, asset_cache_key)
            if cached_asset is not None:
                status, cached_headers, cached_body = cached_asset
                await route.fulfill(status=status, headers=cached_headers, body=cached_body)
                return
            # Fonts and images are answered from the stub: the issuance page
            # pulls dozens of them, routing that flood through curl forces
            # fresh TLS handshakes that UTCMS's static surface resets, and
            # neither can change form behaviour or visibility.
            #
            # Scripts and stylesheets are NOT stubbed.  Empty-bodying the
            # "optional" scripts is what broke the form: the template's ready
            # handler calls FormDocumenDetailsRegister and constructs
            # FormValidation.Framework.Bootstrap, both defined outside the
            # hand-listed critical files, so the handler threw and every
            # runtime behaviour that depends on it silently vanished.  Empty
            # CSS was just as harmful in the other direction: without
            # ``.modal { display: none }`` every closed modal -- including the
            # OTP modal that owns #submitOtp -- reads as visible, so the bot
            # mis-detected an OTP challenge that was never shown.  A cache miss
            # therefore goes to the network on the disposable asset session, and
            # only a real fetch failure leaves it empty.
            if not _is_behavioural_asset(request.url, getattr(request, "resource_type", None)):
                await route.fulfill(
                    status=200,
                    headers={"content-type": _asset_stub_content_type(request.url)},
                    body=b"",
                )
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
                        # From here the browser owns the pace, and its gaps are
                        # long enough to lose the connection.  Hold it open.
                        self._start_keepalive()
                        logger.info(
                            "http_browser_bridge_xhr_promoted_to_auth_session doc_session=%s xhr_session=%s",
                            id(self._document_session),
                            id(self._session),
                        )
                        if stale_xhr_session is not None:
                            try:
                                await self._call(stale_xhr_session.close)
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
                    # Static scripts run on the disposable asset session so a
                    # connection teardown from UTCMS's static surface cannot
                    # invalidate the keep-alive the runtime XHR ride on.
                    session = await self._ensure_asset_session()
                else:
                    if self._session is None:
                        self._session = self._new_session()
                    session = self._session
                    # Pace the form's init burst: back-to-back XHR are what UTCMS
                    # answers with 408/500/400 instead of data.
                    gap = time.monotonic() - self._last_xhr_dispatch_at
                    if gap < _XHR_MIN_SPACING_SECONDS:
                        await asyncio.sleep(_XHR_MIN_SPACING_SECONDS - gap)
                    self._last_xhr_dispatch_at = time.monotonic()
                    logger.info(
                        "http_browser_bridge_xhr_dispatch url=%s method=%s req_bytes=%s ct=%s session=%s is_auth=%s preserve=%s",
                        request.url[:80],
                        request.method,
                        len(body or b""),
                        headers.get("content-type", ""),
                        id(session),
                        session is self._document_session,
                        self._preserve_authenticated_session,
                    )
                    if "updateregister" in request.url.lower():
                        logger.info(
                            "http_browser_bridge_submit_payload url=%s body=%s",
                            request.url,
                            (body or b"").decode("utf-8", errors="ignore")[:3000],
                        )
                try:
                    response = await self._call(
                        session.request,
                        request.method,
                        request.url,
                        headers=headers,
                        data=body,
                        allow_redirects=False,
                        timeout=self.timeout,
                    )
                    if "updateregister" in request.url.lower():
                        logger.info(
                            "http_browser_bridge_submit_response url=%s status=%s body=%s",
                            request.url,
                            response.status_code,
                            (response.text or "")[:1000],
                        )
                    self._last_transport_at = time.monotonic()
                    # Only the reserved document session's own traffic proves the
                    # connection the runtime XHR will inherit is still warm.
                    if session is self._document_session:
                        self._last_document_transport_at = self._last_transport_at
                    if not is_safe_method or response.status_code not in (408, 429, 500, 502, 503, 504):
                        break
                    # A retryable status on a runtime XHR is invisible from the
                    # page side -- jQuery only sees its ``error`` callback, so the
                    # form reports "not found" and the real cause never reaches a
                    # log.  Run 4 (2026-08-28) burned all three attempts on
                    # KalaSearch this way while the very same request answered 200
                    # on a direct authenticated session, so the status itself is
                    # the diagnostic that matters here.
                    logger.warning(
                        "http_browser_bridge_xhr_retryable_status url=%s status=%s attempt=%s/%s",
                        request.url[:120],
                        int(response.status_code),
                        attempt,
                        max_attempts,
                    )
                    # A session that completed HTTP login carries server-side
                    # state not reproducible from cookies alone. Keep it for
                    # transient retries; closing it here turns one TLS hiccup
                    # into a guaranteed unauthenticated/408 follow-up.
                    if not document and not asset:
                        if self._preserve_authenticated_session:
                            await self._rewarm_preserved_session()
                        else:
                            await self._reset_session()
                    if attempt < max_attempts:
                        await asyncio.sleep(float(attempt))
                except Exception as exc:
                    last_error = exc
                    if not is_safe_method:
                        break
                    # Space the retry BEFORE touching the transport again.  Each
                    # recovery attempt costs a fresh TLS handshake, and UTCMS's
                    # edge rejects handshakes that arrive back-to-back — retrying
                    # instantly turned one dropped keep-alive into a burst that
                    # failed every remaining XHR of the form.
                    if attempt < max_attempts:
                        await asyncio.sleep(1.5 * attempt)
                    if not document and not asset:
                        # The reserved auth session works for every runtime XHR
                        # when its connection is live (proven pure-transport);
                        # a reset here is a dropped keep-alive, so re-establish
                        # the connection instead of discarding the session.
                        if self._preserve_authenticated_session:
                            await self._rewarm_preserved_session()
                        else:
                            await self._reset_session()

            if response is None:
                raise RuntimeError(f"UTCMS bridge transport failed: {last_error}")

            response_headers = {
                str(k): str(v) for k, v in response.headers.items() if str(k).lower() not in _RESPONSE_DROP_HEADERS
            }
            if not asset and int(response.status_code) >= 400:
                # Classified, never echoed: an error body can carry an
                # antiforgery token or a re-login form, so only its shape is
                # logged -- enough to tell "UTCMS rejected this" from "our
                # session lost its authentication".
                body_text = ""
                try:
                    body_text = (response.text or "")[:4000]
                except Exception:
                    body_text = ""
                # A short text/plain error body is a server-generated message
                # (Kestrel/ASP.NET), not user data, and it is the only thing that
                # distinguishes "UTCMS rejected the request shape" from "the
                # request never arrived intact".  HTML bodies stay unlogged: those
                # are the ones that can carry an antiforgery token or a form.
                content_type = response_headers.get("content-type", "")
                detail = ""
                if content_type.startswith("text/plain") and len(body_text) <= 300 and "<" not in body_text:
                    detail = body_text.replace("\n", " | ")
                logger.warning(
                    "http_browser_bridge_response_error url=%s method=%s req_bytes=%s status=%s "
                    "type=%s bytes=%s looks_like_login=%s detail=%s",
                    request.url[:120],
                    request.method,
                    len(body or b""),
                    int(response.status_code),
                    content_type,
                    len(response.content or b""),
                    any(marker in body_text for marker in ("Account/Login", 'name="Username"', "ورود به سامانه")),
                    detail,
                )
            if asset and not _is_captcha_asset(request.url):
                # Every asset this run manages to download makes the next run
                # faster and less dependent on UTCMS's static surface.  Captcha
                # images are excluded: each one is a single-use challenge bound
                # to a server-side token, so a cached copy would be replayed
                # against a different token on every later run.
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


async def ensure_utcms_http_browser_bridge(
    page: Any, *, proxy_url: str | None = None
) -> UtcmsHttpBrowserBridge | None:
    """Install one bridge per page when HTTP-login mode is enabled."""
    if not getattr(utcms_config, "UTCMS_HTTP_LOGIN_ENABLED", True):
        return None
    existing = getattr(page, "_barpro_http_browser_bridge", None)
    if existing is not None:
        return existing
    bridge = UtcmsHttpBrowserBridge(page, proxy_url=proxy_url)
    await bridge.install()
    page._barpro_http_browser_bridge = bridge
    return bridge


def get_utcms_http_browser_bridge(page: Any) -> UtcmsHttpBrowserBridge | None:
    """Return the bridge already installed on a page, without creating one.

    Callers inside the form (cargo and city lookups) need the authenticated
    transport but must never *install* a bridge mid-run: a bridge created after
    the form is open has no adopted login session and would route the page's
    traffic through an unauthenticated curl session.
    """
    return getattr(page, "_barpro_http_browser_bridge", None)


__all__ = [
    "UtcmsHttpBrowserBridge",
    "ensure_utcms_http_browser_bridge",
    "get_utcms_http_browser_bridge",
]
