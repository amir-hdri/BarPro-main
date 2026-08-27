from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.automation import http_browser_bridge as bridge_module
from app.automation.http_browser_bridge import UtcmsHttpBrowserBridge, ensure_utcms_http_browser_bridge


@pytest.fixture(autouse=True)
def isolated_asset_cache(tmp_path, monkeypatch):
    """Keep the persistent UTCMS asset cache out of the developer's filesystem."""
    monkeypatch.setattr(bridge_module, "_ASSET_CACHE_DIR", tmp_path / "utcms_asset_cache")
    return tmp_path / "utcms_asset_cache"


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

    await bridge._fulfill_utcms(route, request)

    forwarded_headers = session.request.call_args.kwargs["headers"]
    assert forwarded_headers["Cookie"] == "Barname=session-token"


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
async def test_form_asset_failure_is_stubbed_without_retry() -> None:
    """A stalled optional asset must not block the parser or retry the transport."""
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page, proxy_url="http://127.0.0.1:3128")
    bridge._authenticated_document_bridge = True
    bridge._form_assets_bridge_enabled = True
    session = MagicMock()
    session.request.side_effect = RuntimeError("tls reset")
    bridge._document_session = session
    bridge._document_session_warmed = True
    bridge._new_session = MagicMock(return_value=session)

    request = MagicMock()
    request.url = "https://barname.utcms.ir/assets/vendor/libs/swiper/swiper.js"
    request.method = "GET"
    request.resource_type = "script"
    request.post_data_buffer = None
    request.all_headers = AsyncMock(return_value={})
    route = MagicMock(request=request)
    route.continue_ = AsyncMock()
    route.abort = AsyncMock()
    route.fulfill = AsyncMock()

    await bridge._handle_route(route)

    assert session.request.call_count == 1
    route.continue_.assert_not_awaited()
    route.fulfill.assert_awaited_once_with(
        status=200,
        headers={"content-type": "application/javascript"},
        body=b"",
    )


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
async def test_script_prefetch_warms_critical_form_files_first() -> None:
    """Critical files must be secured before optional vendor bundles."""
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page)
    bridge._session = MagicMock()
    html = (
        b"<html><head>"
        b"<script src='/assets/js/analytics.js'></script>"
        b"<script src='/assets/plugins/jquery/jquery.js'></script>"
        b"<script src='/assets/plugins/jqury-ui/jquery-ui.js'></script>"
        b"<script src='/assets/jspage/Barname/hagigihogugi.js?v=1'></script>"
        b"<script src='https://cdn.example.com/other.js'></script>"
        b"</head></html>"
    )
    session = MagicMock()
    session.request.return_value = MagicMock(
        status_code=200,
        content=b"//js",
        headers={"Content-Type": "text/javascript"},
    )

    await bridge._prefetch_document_scripts(
        session, "https://barname.utcms.ir/barname/Document/HagigiHogugi", html
    )

    fetched = [call.args[1] for call in session.request.call_args_list]
    assert fetched == [
        "https://barname.utcms.ir/assets/plugins/jquery/jquery.js",
        "https://barname.utcms.ir/assets/plugins/jqury-ui/jquery-ui.js",
        "https://barname.utcms.ir/assets/jspage/Barname/hagigihogugi.js?v=1",
        "https://barname.utcms.ir/assets/js/analytics.js",
    ]
    assert set(bridge._prefetched_assets) == {
        "/assets/plugins/jquery/jquery.js",
        "/assets/plugins/jqury-ui/jquery-ui.js",
        "/assets/jspage/barname/hagigihogugi.js?v=1",
        "/assets/js/analytics.js",
    }


@pytest.mark.asyncio
async def test_script_prefetch_stops_optional_files_after_repeated_failures() -> None:
    """A dead connection must not be dragged through the optional tail."""
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page)
    bridge._session = MagicMock()
    html = (
        b"<script src='/assets/plugins/jquery/jquery.js'></script>"
        b"<script src='/assets/js/a.js'></script>"
        b"<script src='/assets/js/b.js'></script>"
        b"<script src='/assets/js/c.js'></script>"
        b"<script src='/assets/js/d.js'></script>"
    )
    session = MagicMock()
    session.request.side_effect = RuntimeError("connection reset")

    await bridge._prefetch_document_scripts(
        session, "https://barname.utcms.ir/barname/Document/HagigiHogugi", html
    )

    fetched = [call.args[1] for call in session.request.call_args_list]
    assert fetched == [
        "https://barname.utcms.ir/assets/plugins/jquery/jquery.js",
        "https://barname.utcms.ir/assets/js/a.js",
        "https://barname.utcms.ir/assets/js/b.js",
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
    session.request.side_effect = [
        RuntimeError("connection reset"),
        MagicMock(status_code=200, content=b"//js", headers={"Content-Type": "text/javascript"}),
    ]

    await bridge._prefetch_document_scripts(
        session, "https://barname.utcms.ir/barname/Document/HagigiHogugi", html
    )

    assert set(bridge._prefetched_assets) == {"/assets/jspage/barname/hagigihogugi.js"}
