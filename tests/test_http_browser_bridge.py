from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.automation.http_browser_bridge import UtcmsHttpBrowserBridge, ensure_utcms_http_browser_bridge


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
async def test_utcms_authenticated_documents_use_seeded_http_session() -> None:
    """Menu navigation must use curl_cffi after HTTP login seeds the session."""
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page, proxy_url="http://127.0.0.1:3128")
    bridge._authenticated_document_bridge = True
    response = MagicMock(status_code=200, content=b"<form id='txtSenderFirstName'></form>", headers={"Content-Type": "text/html"})
    session = MagicMock()
    session.request.return_value = response
    bridge._session = session

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
    forwarded_headers = session.request.call_args.kwargs["headers"]
    assert forwarded_headers["Cookie"] == "Barname=session-token"
    assert forwarded_headers["Referer"] == "https://barname.utcms.ir/Barname/Notification/Notification"


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

    await bridge.adopt_authenticated_session(
        authenticated,
        [{"name": "Barname", "value": "session", "domain": "barname.utcms.ir"}],
    )

    assert bridge._session is authenticated
    assert bridge._authenticated_document_bridge is True
    old.close.assert_called_once()
