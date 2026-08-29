import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.automation import http_browser_bridge as bridge_module
from app.automation.http_browser_bridge import UtcmsHttpBrowserBridge, ensure_utcms_http_browser_bridge


@pytest.fixture(autouse=True)
def isolated_asset_cache(tmp_path, monkeypatch):
    """Keep the persistent UTCMS asset cache out of the developer's filesystem."""
    monkeypatch.setattr(bridge_module, "_ASSET_CACHE_DIR", tmp_path / "utcms_asset_cache")
    return tmp_path / "utcms_asset_cache"


def test_new_session_binds_the_curl_handle_to_the_session_not_the_thread() -> None:
    """curl_cffi keeps the libcurl handle -- and therefore the connection cache
    -- in thread-local storage by default, so a session driven from a second
    thread silently opens a second TLS connection.  That is what made the
    adopted login session useless to the bridge: it inherited the cookies but
    never the warm connection, and every XHR paid a fresh handshake that UTCMS's
    per-IP throttle rejects."""
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page, proxy_url="http://squid:3128")

    with patch("curl_cffi.requests.Session") as session_cls:
        bridge._new_session()

    kwargs = session_cls.call_args.kwargs
    assert kwargs["use_thread_local_curl"] is False
    assert kwargs["verify"] is True
    assert kwargs["impersonate"] == "chrome120"


@pytest.mark.asyncio
async def test_keepalive_pings_when_only_other_sessions_have_been_busy(monkeypatch) -> None:
    """Measured live 2026-08-28: while Chromium streamed form scripts on the
    asset session, the keepalive read the shared "last transport" timestamp,
    concluded the transport was busy, and never pinged (``pings=0``).  The
    reserved document session meanwhile went idle past UTCMS's ~30s tunnel
    timeout, so Captcha/Generate needed a fresh handshake and was throttled."""
    monkeypatch.setattr(bridge_module, "_KEEPALIVE_INTERVAL_SECONDS", 0.01)
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page)
    bridge._document_session = MagicMock()
    # Asset traffic just happened; the document session has been idle far longer.
    bridge._last_transport_at = time.monotonic()
    bridge._last_document_transport_at = time.monotonic() - 120.0
    # One success then two failures gives the loop a bounded run.
    bridge._call = AsyncMock(side_effect=[MagicMock(status_code=200), RuntimeError("a"), RuntimeError("b")])

    await asyncio.wait_for(bridge._keepalive_loop(), timeout=5.0)

    assert bridge._call.await_count == 3, "keepalive never pinged the idle document session"


@pytest.mark.asyncio
async def test_keepalive_skips_while_the_document_session_itself_is_warm(monkeypatch) -> None:
    monkeypatch.setattr(bridge_module, "_KEEPALIVE_INTERVAL_SECONDS", 0.01)
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page)
    bridge._document_session = MagicMock()
    bridge._call = AsyncMock(return_value=MagicMock(status_code=200))
    # Keep the document session permanently "just used" for the test's duration.
    bridge._last_document_transport_at = time.monotonic() + 3600.0

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(bridge._keepalive_loop(), timeout=0.2)

    bridge._call.assert_not_awaited()


@pytest.mark.asyncio
async def test_landing_page_assets_are_bridged_not_fetched_by_chromium() -> None:
    """Every resource Chromium fetches itself is a new TLS handshake from this
    egress IP.  Measured 2026-08-28: the landing page's native asset load opened
    13 connections in 60ms, UTCMS refused all of them, and the bridge's own warm
    tunnel was gone seconds later -- the run poisoned its own IP."""
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page)
    bridge._authenticated_document_bridge = True  # login done, issuance form NOT open yet
    bridge._form_assets_bridge_enabled = False
    session = MagicMock()
    session.request.return_value = MagicMock(
        status_code=200, content=b"/* real */", headers={"content-type": "application/javascript"}
    )
    bridge._ensure_asset_session = AsyncMock(return_value=session)

    for resource_type, url in (
        ("script", "https://barname.utcms.ir/assets/js/site.js"),
        ("stylesheet", "https://barname.utcms.ir/assets/css/site.css"),
        ("image", "https://barname.utcms.ir/assets/img/logo.png"),
    ):
        request = MagicMock()
        request.url = url
        request.method = "GET"
        request.resource_type = resource_type
        request.post_data_buffer = None
        request.all_headers = AsyncMock(return_value={})
        route = MagicMock(request=request)
        route.continue_ = AsyncMock()
        route.abort = AsyncMock()
        route.fulfill = AsyncMock()

        await bridge._handle_route(route)

        assert not route.continue_.await_count, f"{resource_type} escaped to Chromium's own TLS stack"
        route.fulfill.assert_awaited_once()


@pytest.mark.asyncio
async def test_non_utcms_request_continues_without_proxying() -> None:
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page)
    route = MagicMock()
    route.continue_ = AsyncMock()
    route.abort = AsyncMock()
    route.request.url = "https://example.com/app.js"

    await bridge._handle_route(route)

    route.continue_.assert_awaited_once()
    route.abort.assert_not_awaited()


@pytest.mark.asyncio
async def test_utcms_static_assets_continue_through_chromium() -> None:
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page)
    route = MagicMock()
    route.continue_ = AsyncMock()
    route.abort = AsyncMock()
    route.request.url = "https://barname.utcms.ir/assets/js/main.js"
    route.request.resource_type = "script"

    await bridge._handle_route(route)

    route.continue_.assert_awaited_once()
    route.abort.assert_not_awaited()


@pytest.mark.asyncio
async def test_utcms_documents_continue_through_chromium_before_http_authentication() -> None:
    """Playwright-only login fallback keeps its native document navigation."""
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page)
    route = MagicMock()
    route.continue_ = AsyncMock()
    route.abort = AsyncMock()
    route.request.url = "https://barname.utcms.ir/Barname/Notification/Notification"
    route.request.resource_type = "document"

    await bridge._handle_route(route)

    route.continue_.assert_awaited_once()
    route.abort.assert_not_awaited()


@pytest.mark.asyncio
async def test_utcms_authenticated_documents_use_dedicated_login_session() -> None:
    """Menu documents must not share the landing page's XHR session."""
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page, proxy_url="http://127.0.0.1:3128")
    bridge._authenticated_document_bridge = True
    response = MagicMock(status_code=200, content=b"<form id='txtSenderFirstName'></form>", headers={})
    warmup_response = MagicMock(status_code=200, content=b"<html>landing</html>", headers={})
    document_session = MagicMock()
    document_session.request.side_effect = [warmup_response, response]
    xhr_session = MagicMock()
    bridge._document_session = document_session
    bridge._session = xhr_session

    request = MagicMock()
    request.url = "https://barname.utcms.ir/Barname/Document/HagigiHogugi"
    request.method = "GET"
    request.resource_type = "document"
    request.post_data_buffer = None
    request.all_headers = AsyncMock(
        return_value={
            "Cookie": "Barname=session-token",
            "Referer": "https://barname.utcms.ir/Barname/Notification/Notification",
        }
    )
    route = MagicMock(request=request)
    route.continue_ = AsyncMock()
    route.abort = AsyncMock()
    route.fulfill = AsyncMock()

    await bridge._handle_route(route)

    route.continue_.assert_not_awaited()
    route.abort.assert_not_awaited()
    route.fulfill.assert_awaited_once()
    assert document_session.request.call_count == 2
    assert document_session.request.call_args_list[0].args[1].endswith("/Barname/Notification/Notification")
    assert document_session.request.call_args_list[1].args[1].endswith("/Barname/Document/HagigiHogugi")
    xhr_session.request.assert_not_called()


@pytest.mark.asyncio
async def test_utcms_authenticated_landing_document_stays_native() -> None:
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page, proxy_url="http://127.0.0.1:3128")
    bridge._authenticated_document_bridge = True
    bridge._document_session = MagicMock()
    route = MagicMock()
    route.continue_ = AsyncMock()
    route.abort = AsyncMock()
    route.request.url = "https://barname.utcms.ir/Barname/Notification/Notification"
    route.request.method = "GET"
    route.request.resource_type = "document"

    await bridge._handle_route(route)

    route.continue_.assert_awaited_once()
    route.abort.assert_not_awaited()
    bridge._document_session.request.assert_not_called()


@pytest.mark.asyncio
async def test_install_is_idempotent_per_page() -> None:
    page = MagicMock()
    page.route = AsyncMock()
    page._barpro_http_browser_bridge = None

    with patch("app.automation.http_browser_bridge.utcms_config.UTCMS_HTTP_LOGIN_ENABLED", True):
        first = await ensure_utcms_http_browser_bridge(page)
        second = await ensure_utcms_http_browser_bridge(page)

    assert first is second
    page.route.assert_awaited_once()


@pytest.mark.asyncio
async def test_utcms_response_is_fulfilled_and_encoding_headers_are_removed() -> None:
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page, proxy_url="http://127.0.0.1:3128")
    response = MagicMock()
    response.status_code = 200
    response.content = b"<html>ok</html>"
    response.headers = {"Content-Type": "text/html", "Content-Encoding": "gzip", "Content-Length": "99"}
    session = MagicMock()
    session.request.return_value = response
    bridge._session = session

    request = MagicMock()
    request.url = "https://barname.utcms.ir/Barname/Notification/Notification"
    request.method = "GET"
    request.resource_type = "document"
    request.post_data_buffer = None
    request.all_headers = AsyncMock(return_value={"Cookie": "Barname=x", "Accept-Encoding": "gzip"})
    route = MagicMock()
    route.request = request
    route.fulfill = AsyncMock()

    await bridge._fulfill_utcms(route, request)

    kwargs = route.fulfill.await_args.kwargs
    assert kwargs["status"] == 200
    assert kwargs["body"] == b"<html>ok</html>"
    assert "Content-Encoding" not in kwargs["headers"]
    assert "Content-Length" not in kwargs["headers"]


@pytest.mark.asyncio
async def test_utcms_bridge_forwards_browser_auth_cookie() -> None:
    """A reused Playwright session must stay authenticated in curl_cffi.

    The bridge used to drop Cookie before forwarding the navigation request.
    That made warm authenticated menu navigation look like a cold unauthenticated
    request and UTCMS returned the 39-byte stale/408 shell.
    """
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page, proxy_url="http://127.0.0.1:3128")
    response = MagicMock(status_code=200, content=b"<html>ok</html>", headers={"Content-Type": "text/html"})
    session = MagicMock()
    session.request.return_value = response
    bridge._session = session
    # Navigation runs on the reserved document session, and this is the request
    # kind that must keep the page's Cookie header (runtime XHR must not -- see
    # test_runtime_xhr_drops_the_pages_cookie_header).
    bridge._document_session = session
    bridge._document_session_warmed = True

    request = MagicMock()
    request.url = "https://barname.utcms.ir/Barname/Notification/Notification"
    request.method = "GET"
    request.resource_type = "document"
    request.post_data_buffer = None
    request.all_headers = AsyncMock(
        return_value={"Cookie": "Barname=session-token", "Referer": "https://barname.utcms.ir/Barname/Notification/Notification"}
    )
    route = MagicMock(request=request)
    route.fulfill = AsyncMock()

    await bridge._fulfill_utcms(route, request, document=True)

    forwarded_headers = session.request.call_args.kwargs["headers"]
    assert forwarded_headers["Cookie"] == "Barname=session-token"


@pytest.mark.asyncio
async def test_runtime_xhr_drops_the_pages_cookie_header() -> None:
    """A runtime XHR is authenticated by the session's jar, not by the page's copy.

    The HTTP login returns TWO ApplicationToken cookies and Playwright keeps only
    one per (name, domain, path), so the page's Cookie header can override the
    jar with the other token -- which is what made fillBoxType/FillProvinces
    answer 408 and ShowNotification 500 while a bare probe on the same session
    answered 200.  Document navigation still forwards it
    (test_utcms_bridge_forwards_browser_auth_cookie).
    """
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page)
    session = MagicMock()
    session.request.return_value = MagicMock(
        status_code=200, content=b"{}", headers={"Content-Type": "application/json"}
    )
    bridge._session = session

    request = MagicMock()
    request.url = "https://barname.utcms.ir/Barname/Document/fillBoxType"
    request.method = "GET"
    request.resource_type = "xhr"
    request.post_data_buffer = None
    request.all_headers = AsyncMock(return_value={"Cookie": "ApplicationToken=stale", "Accept": "*/*"})
    route = MagicMock(request=request)
    route.fulfill = AsyncMock()

    await bridge._fulfill_utcms(route, request)

    forwarded_headers = session.request.call_args.kwargs["headers"]
    assert not [key for key in forwarded_headers if key.lower() == "cookie"]
    assert forwarded_headers["Accept"] == "*/*"


@pytest.mark.asyncio
async def test_runtime_xhr_are_paced_apart() -> None:
    """The form's init burst is what UTCMS refuses, so XHR are spaced out.

    Measured 2026-08-28: ~20 initialiser XHR within 2.5s drew 408
    ("سرور در حال حاضر قادر به پاسخگویی نمی باشد"), 500 and bare-400 answers,
    while the same requests answered 200 when issued alone on the same session.
    """
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page)
    bridge._authenticated_document_bridge = True
    session = MagicMock()
    session.request.return_value = SimpleNamespace(
        status_code=200, content=b"{}", headers={"content-type": "application/json"}
    )
    bridge._session = session

    slept: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        slept.append(delay)

    def _make_route() -> MagicMock:
        request = MagicMock()
        request.url = "https://barname.utcms.ir/Barname/Document/FillProvinces"
        request.method = "GET"
        request.resource_type = "xhr"
        request.post_data_buffer = None
        request.all_headers = AsyncMock(return_value={})
        route = MagicMock(request=request)
        route.fulfill = AsyncMock()
        return route

    with patch("app.automation.http_browser_bridge.asyncio.sleep", new=_fake_sleep):
        await bridge._fulfill_utcms(_make_route(), _make_route().request)
        await bridge._fulfill_utcms(_make_route(), _make_route().request)

    # The second dispatch had to wait; the first one did not have to wait long
    # enough to matter (the clock starts at 0.0, i.e. "long ago").
    assert len(slept) == 1
    assert 0 < slept[0] <= bridge_module._XHR_MIN_SPACING_SECONDS


@pytest.mark.asyncio
async def test_seed_cookies_populates_bridge_session() -> None:
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page)
    await bridge.seed_cookies([{"name": "Barname", "value": "session", "domain": "barname.utcms.ir"}])
    assert bridge._session is not None
    assert "Barname" in bridge._session.cookies
    assert bridge._authenticated_document_bridge is True


@pytest.mark.asyncio
async def test_adopt_authenticated_session_reuses_exact_session() -> None:
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page)
    old = MagicMock()
    bridge._session = old
    authenticated = MagicMock()

    with patch.object(bridge, "_prefetch_issuance_document", new=AsyncMock()) as prefetch:
        await bridge.adopt_authenticated_session(
            authenticated,
            [{"name": "Barname", "value": "session", "domain": "barname.utcms.ir"}],
        )

    assert bridge._document_session is authenticated
    assert bridge._session is not authenticated
    assert bridge._authenticated_document_bridge is True
    assert bridge._preserve_authenticated_session is False
    prefetch.assert_awaited_once_with(authenticated)
    old.close.assert_called_once()


@pytest.mark.asyncio
async def test_prefetched_issuance_document_is_fulfilled_without_second_network_call() -> None:
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page)
    bridge._authenticated_document_bridge = True
    bridge._document_session = MagicMock()
    path = "/barname/document/hagigihogugi"
    bridge._prefetched_documents[path] = (200, {"Content-Type": "text/html"}, b"txtSenderFirstName")

    request = MagicMock()
    request.url = "https://barname.utcms.ir/barname/Document/HagigiHogugi"
    request.method = "GET"
    request.resource_type = "document"
    request.post_data_buffer = None
    request.all_headers = AsyncMock(return_value={})
    route = MagicMock(request=request)
    route.continue_ = AsyncMock()
    route.abort = AsyncMock()
    route.fulfill = AsyncMock()

    await bridge._handle_route(route)

    route.fulfill.assert_awaited_once_with(
        status=200,
        headers={"Content-Type": "text/html"},
        body=b"txtSenderFirstName",
    )
    bridge._document_session.request.assert_not_called()


@pytest.mark.asyncio
async def test_consuming_prefetch_promotes_document_session_for_form_xhr() -> None:
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page)
    bridge._authenticated_document_bridge = True
    document_session = MagicMock()
    xhr_session = MagicMock()
    bridge._document_session = document_session
    bridge._session = xhr_session
    bridge._prefetched_documents["/barname/document/hagigihogugi"] = (
        200,
        {"Content-Type": "text/html"},
        b"txtSenderFirstName",
    )

    request = MagicMock()
    request.url = "https://barname.utcms.ir/Barname/Document/HagigiHogugi"
    request.method = "GET"
    request.resource_type = "document"
    request.post_data_buffer = None
    request.all_headers = AsyncMock(return_value={})
    route = MagicMock(request=request)
    route.continue_ = AsyncMock()
    route.abort = AsyncMock()
    route.fulfill = AsyncMock()

    await bridge._handle_route(route)

    assert bridge._session is document_session
    assert bridge._preserve_authenticated_session is True
    assert bridge._form_assets_bridge_enabled is True
    xhr_session.close.assert_called_once()


@pytest.mark.asyncio
async def test_authenticated_landing_assets_stay_native_until_form_is_consumed() -> None:
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page)
    bridge._authenticated_document_bridge = True
    route = MagicMock()
    route.continue_ = AsyncMock()
    route.abort = AsyncMock()
    route.request.url = "https://barname.utcms.ir/assets/js/main.js"
    route.request.method = "GET"
    route.request.resource_type = "script"

    await bridge._handle_route(route)

    route.continue_.assert_awaited_once()
    route.abort.assert_not_awaited()


@pytest.mark.asyncio
async def test_stylesheet_is_stubbed_without_touching_the_network() -> None:
    """A stalled stylesheet must not block the parser or spend a handshake."""
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page, proxy_url="http://127.0.0.1:3128")
    bridge._authenticated_document_bridge = True
    bridge._form_assets_bridge_enabled = True
    session = MagicMock()
    session.request.side_effect = RuntimeError("tls reset")
    bridge._document_session = session
    bridge._document_session_warmed = True
    bridge._new_session = MagicMock(return_value=session)
    # Asset traffic runs on the disposable asset session, so that is the seam the
    # route handler actually reaches for -- patching _new_session alone let a REAL
    # curl session through to the configured proxy.
    bridge._ensure_asset_session = AsyncMock(return_value=session)

    request = MagicMock()
    request.url = "https://barname.utcms.ir/assets/vendor/css/core.css"
    request.method = "GET"
    request.resource_type = "stylesheet"
    request.post_data_buffer = None
    request.all_headers = AsyncMock(return_value={})
    route = MagicMock(request=request)
    route.continue_ = AsyncMock()
    route.abort = AsyncMock()
    route.fulfill = AsyncMock()

    await bridge._handle_route(route)

    assert session.request.call_count == 0
    route.continue_.assert_not_awaited()
    route.fulfill.assert_awaited_once_with(
        status=200,
        headers={"content-type": "text/css; charset=utf-8"},
        body=b"",
    )


@pytest.mark.asyncio
async def test_non_critical_script_is_fetched_not_stubbed() -> None:
    """No script is cosmetic.

    Stubbing "optional" bundles is what left FormDocumenDetailsRegister and
    FormValidation.Framework.Bootstrap undefined, aborting the issuance form's
    document-ready handler and with it the cargo autocomplete, fillBoxType,
    GETUserFleetListTajmi and both tajmi change handlers.
    """
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page)
    bridge._authenticated_document_bridge = True
    bridge._form_assets_bridge_enabled = True
    session = MagicMock()
    session.request.return_value = SimpleNamespace(
        status_code=200,
        content=b"function FormDocumenDetailsRegister(){}",
        headers={"content-type": "application/javascript"},
    )
    bridge._document_session = session
    bridge._document_session_warmed = True
    bridge._ensure_asset_session = AsyncMock(return_value=session)

    request = MagicMock()
    request.url = "https://barname.utcms.ir/assets/jspage/barname/documentdetails.js"
    request.method = "GET"
    request.resource_type = "script"
    request.post_data_buffer = None
    request.all_headers = AsyncMock(return_value={})
    route = MagicMock(request=request)
    route.continue_ = AsyncMock()
    route.abort = AsyncMock()
    route.fulfill = AsyncMock()

    with (
        patch("app.automation.http_browser_bridge._read_asset_cache", return_value=None),
        patch("app.automation.http_browser_bridge._write_asset_cache"),
    ):
        await bridge._handle_route(route)

    assert session.request.call_count == 1
    fulfilled = route.fulfill.await_args.kwargs
    assert fulfilled["body"] == b"function FormDocumenDetailsRegister(){}"


@pytest.mark.asyncio
async def test_critical_form_script_failure_is_never_stubbed() -> None:
    """A missing critical file must surface, not be hidden behind an empty body."""
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page)
    bridge._authenticated_document_bridge = True
    bridge._form_assets_bridge_enabled = True
    session = MagicMock()
    session.request.side_effect = RuntimeError("tls reset")
    bridge._document_session = session
    bridge._document_session_warmed = True
    # Assets ride the disposable asset session, so that is the one that has to
    # fail here.  Without this the fetch escaped to the real network and the
    # assertion silently depended on UTCMS being unreachable from the test host.
    bridge._ensure_asset_session = AsyncMock(return_value=session)

    request = MagicMock()
    request.url = "https://barname.utcms.ir/assets/js/jqury-ui/jquery-ui.js"
    request.method = "GET"
    request.resource_type = "script"
    request.post_data_buffer = None
    request.all_headers = AsyncMock(return_value={})
    route = MagicMock(request=request)
    route.continue_ = AsyncMock()
    route.abort = AsyncMock()
    route.fulfill = AsyncMock()

    await bridge._handle_route(route)

    route.fulfill.assert_not_awaited()
    route.continue_.assert_awaited_once()


@pytest.mark.asyncio
async def test_successful_form_asset_is_persisted_and_reused_from_disk() -> None:
    """The on-disk cache removes the next run's dependency on UTCMS statics."""
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page)
    bridge._authenticated_document_bridge = True
    bridge._form_assets_bridge_enabled = True
    session = MagicMock()
    session.request.return_value = MagicMock(
        status_code=200,
        content=b"window.formReady=true;",
        headers={"Content-Type": "text/javascript"},
    )
    bridge._document_session = session
    bridge._document_session_warmed = True
    # Scripts are served on the asset session, not the reserved login session.
    bridge._ensure_asset_session = AsyncMock(return_value=session)

    def make_route() -> MagicMock:
        request = MagicMock()
        request.url = "https://barname.utcms.ir/assets/jspage/Barname/hagigihogugi.js?v=1"
        request.method = "GET"
        request.resource_type = "script"
        request.post_data_buffer = None
        request.all_headers = AsyncMock(return_value={})
        route = MagicMock(request=request)
        route.continue_ = AsyncMock()
        route.abort = AsyncMock()
        route.fulfill = AsyncMock()
        return route

    first = make_route()
    await bridge._handle_route(first)
    assert session.request.call_count == 1

    # A brand-new bridge (i.e. the next job) must not touch the network at all.
    fresh = UtcmsHttpBrowserBridge(MagicMock())
    fresh._authenticated_document_bridge = True
    fresh._form_assets_bridge_enabled = True
    fresh._document_session = MagicMock()
    second = make_route()
    await fresh._handle_route(second)

    fresh._document_session.request.assert_not_called()
    second.fulfill.assert_awaited_once_with(
        status=200,
        headers={"Content-Type": "text/javascript"},
        body=b"window.formReady=true;",
    )


@pytest.mark.asyncio
async def test_form_fonts_are_dropped_instead_of_stalling_the_page() -> None:
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page)
    bridge._authenticated_document_bridge = True
    bridge._form_assets_bridge_enabled = True

    request = MagicMock()
    request.url = "https://barname.utcms.ir/assets/vendor/fonts/feather/feather.woff"
    request.method = "GET"
    request.resource_type = "font"
    request.post_data_buffer = None
    request.all_headers = AsyncMock(return_value={})
    route = MagicMock(request=request)
    route.continue_ = AsyncMock()
    route.abort = AsyncMock()
    route.fulfill = AsyncMock()

    await bridge._handle_route(route)

    route.abort.assert_awaited_once_with("blockedbyclient")
    route.continue_.assert_not_awaited()
    route.fulfill.assert_not_awaited()


@pytest.mark.asyncio
async def test_prefetched_form_asset_is_fulfilled_without_network() -> None:
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page)
    bridge._authenticated_document_bridge = True
    bridge._form_assets_bridge_enabled = True
    key = "/assets/jspage/barname/hagigihogugi.js?v=abc"
    bridge._prefetched_assets[key] = (
        200,
        {"Content-Type": "text/javascript"},
        b"window.formReady=true;",
    )
    bridge._document_session = MagicMock()

    request = MagicMock()
    request.url = "https://barname.utcms.ir/assets/jspage/Barname/hagigihogugi.js?v=abc"
    request.method = "GET"
    request.resource_type = "script"
    request.post_data_buffer = None
    request.all_headers = AsyncMock(return_value={})
    route = MagicMock(request=request)
    route.continue_ = AsyncMock()
    route.abort = AsyncMock()
    route.fulfill = AsyncMock()

    await bridge._handle_route(route)

    route.fulfill.assert_awaited_once_with(
        status=200,
        headers={"Content-Type": "text/javascript"},
        body=b"window.formReady=true;",
    )
    bridge._document_session.request.assert_not_called()


@pytest.mark.asyncio
async def test_script_prefetch_warms_every_same_origin_script_critical_first() -> None:
    """Critical files are warmed first, then the rest; off-host scripts never.

    Two properties are asserted together because they are the same decision: no
    same-origin script is optional (stubbing "cosmetic" bundles is what left
    FormDocumenDetailsRegister undefined and aborted the form's ready handler),
    and every fetch goes on the disposable ASSET session, never the reserved
    login session that the runtime XHR depend on.
    """
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page)
    login_session = MagicMock()
    bridge._session = login_session
    bridge._document_session = login_session
    html = (
        b"<html><head>"
        b"<script src='/assets/js/analytics.js'></script>"
        b"<script src='/assets/plugins/jquery/jquery.js'></script>"
        b"<script src='/assets/plugins/jqury-ui/jquery-ui.js'></script>"
        b"<script src='/assets/jspage/Barname/hagigihogugi.js?v=1'></script>"
        b"<script src='https://cdn.example.com/other.js'></script>"
        b"</head></html>"
    )
    asset_session = MagicMock()
    asset_session.request.return_value = MagicMock(
        status_code=200,
        content=b"//js",
        headers={"Content-Type": "text/javascript"},
    )
    bridge._ensure_asset_session = AsyncMock(return_value=asset_session)

    await bridge._prefetch_document_scripts(
        "https://barname.utcms.ir/barname/Document/HagigiHogugi", html
    )

    fetched = [call.args[1] for call in asset_session.request.call_args_list]
    assert fetched == [
        "https://barname.utcms.ir/assets/plugins/jquery/jquery.js",
        "https://barname.utcms.ir/assets/plugins/jqury-ui/jquery-ui.js",
        "https://barname.utcms.ir/assets/jspage/Barname/hagigihogugi.js?v=1",
        "https://barname.utcms.ir/assets/js/analytics.js",
    ]
    # Off-host scripts are never routed through the authenticated egress.
    assert "https://cdn.example.com/other.js" not in fetched
    assert set(bridge._prefetched_assets) == {
        "/assets/plugins/jquery/jquery.js",
        "/assets/plugins/jqury-ui/jquery-ui.js",
        "/assets/jspage/barname/hagigihogugi.js?v=1",
        "/assets/js/analytics.js",
    }
    login_session.request.assert_not_called()


@pytest.mark.asyncio
async def test_script_prefetch_survives_a_dead_asset_connection() -> None:
    """Every critical file is still attempted, and nothing is recorded as cached."""
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page)
    bridge._session = MagicMock()
    html = (
        b"<script src='/assets/plugins/jquery/jquery.js'></script>"
        b"<script src='/assets/plugins/jqury-ui/jquery-ui.js'></script>"
        b"<script src='/assets/js/a.js'></script>"
    )
    asset_session = MagicMock()
    asset_session.request.side_effect = RuntimeError("connection reset")
    bridge._ensure_asset_session = AsyncMock(return_value=asset_session)

    await bridge._prefetch_document_scripts(
        "https://barname.utcms.ir/barname/Document/HagigiHogugi", html
    )

    # Each critical file is retried, so compare the DISTINCT urls in first-seen
    # order: the property under test is "every file was still attempted after the
    # connection died", not the retry count.  Non-critical scripts are attempted
    # too now that none of them are treated as cosmetic; only once the failure
    # count passes the cutoff does the warmup stop dragging the tail along.
    attempted = list(dict.fromkeys(call.args[1] for call in asset_session.request.call_args_list))
    assert attempted == [
        "https://barname.utcms.ir/assets/plugins/jquery/jquery.js",
        "https://barname.utcms.ir/assets/plugins/jqury-ui/jquery-ui.js",
        "https://barname.utcms.ir/assets/js/a.js",
    ]
    assert bridge._prefetched_assets == {}


@pytest.mark.asyncio
async def test_failed_script_prefetch_does_not_abort_the_document() -> None:
    """One reset static file must not fail the whole authenticated handoff."""
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page)
    bridge._session = MagicMock()
    html = (
        b"<script src='/assets/plugins/jquery/jquery.js'></script>"
        b"<script src='/assets/jspage/Barname/hagigihogugi.js'></script>"
    )
    session = MagicMock()

    # Keyed on URL rather than call order: every critical script is retried, so an
    # ordered side_effect list made the first script consume the success intended
    # for the second one. jquery fails all attempts; hagigihogugi always answers.
    def _respond(method: str, url: str, **kwargs: object) -> MagicMock:
        if "jquery" in url:
            raise RuntimeError("connection reset")
        return MagicMock(status_code=200, content=b"//js", headers={"Content-Type": "text/javascript"})

    session.request.side_effect = _respond
    bridge._ensure_asset_session = AsyncMock(return_value=session)

    await bridge._prefetch_document_scripts(
        "https://barname.utcms.ir/barname/Document/HagigiHogugi", html
    )

    assert set(bridge._prefetched_assets) == {"/assets/jspage/barname/hagigihogugi.js"}


@pytest.mark.asyncio
async def test_fetch_json_uses_the_reserved_authenticated_session() -> None:
    """Catalogue lookups must ride the session that completed the login."""
    bridge = UtcmsHttpBrowserBridge(MagicMock())
    document_session = MagicMock()
    bridge._document_session = document_session
    bridge._session = MagicMock()
    bridge._call = AsyncMock(return_value=MagicMock(status_code=200, text='[{"id": 15122, "label": "سیمان"}]'))

    result = await bridge.fetch_json(
        "https://barname.utcms.ir/Barname/Document/KalaSearch",
        {"txtkala": "سیمان"},
        referer="https://barname.utcms.ir/Barname/Document/HagigiHogugi",
    )

    assert result == [{"id": 15122, "label": "سیمان"}]
    assert bridge._call.await_args.args[0] is document_session.get
    headers = bridge._call.await_args.kwargs["headers"]
    assert headers["x-requested-with"] == "XMLHttpRequest"
    assert bridge._call.await_args.kwargs["allow_redirects"] is False
    # A lookup on the document session proves that connection is still warm.
    assert bridge._last_document_transport_at == bridge._last_transport_at


@pytest.mark.asyncio
async def test_fetch_json_unwraps_a_json_encoded_string_payload() -> None:
    bridge = UtcmsHttpBrowserBridge(MagicMock())
    bridge._document_session = MagicMock()
    bridge._call = AsyncMock(return_value=MagicMock(status_code=200, text='"[{\\"id\\": 1}]"'))

    assert await bridge.fetch_json("https://barname.utcms.ir/x") == [{"id": 1}]


@pytest.mark.asyncio
async def test_fetch_json_returns_none_on_an_error_status() -> None:
    """Run 4 (2026-08-28): KalaSearch answered a retryable status three times and
    the page-side jQuery call reported nothing but a bare ``error``, so the cargo
    stage claimed the catalogue lacked an entry it actually had.  A None here lets
    the caller distinguish "lookup failed" from "no such cargo"."""
    bridge = UtcmsHttpBrowserBridge(MagicMock())
    bridge._document_session = MagicMock()
    bridge._call = AsyncMock(return_value=MagicMock(status_code=500, text="error"))

    assert await bridge.fetch_json("https://barname.utcms.ir/x") is None


@pytest.mark.asyncio
async def test_fetch_json_never_raises_on_a_transport_failure() -> None:
    bridge = UtcmsHttpBrowserBridge(MagicMock())
    bridge._document_session = MagicMock()
    bridge._call = AsyncMock(side_effect=RuntimeError("connection reset"))

    assert await bridge.fetch_json("https://barname.utcms.ir/x") is None


def test_get_bridge_never_installs_one() -> None:
    """A bridge created mid-run would have no adopted login session."""
    page = MagicMock()
    page._barpro_http_browser_bridge = None
    assert bridge_module.get_utcms_http_browser_bridge(page) is None
