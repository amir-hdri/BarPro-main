"""Hermetic browser smoke test for locator fallbacks and CAPTCHA interception."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import aiohttp
import httpx
import pytest
import requests
from curl_cffi import requests as curl_requests
from playwright.async_api import APIRequestContext, Route, async_playwright

from app.automation.auth import UTCMSAuthenticator
from app.automation.waybill_enhanced import EnhancedWaybillManager
from app.bot.captcha.interceptor import CaptchaInterceptor
from app.bot.core.smart_locator import RetryPolicy
from app.core.config import utcms_config

pytestmark = pytest.mark.unit
FIXTURE_URL = "http://barpro-e2e.test/Account/Login"
CAPTCHA_IMAGE = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="


@pytest.fixture
def blocked_http_transports(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Fail on attempted Python HTTP/DNS, including curl's native socket path."""
    attempted: list[str] = []

    def deny(*args: Any, **kwargs: Any) -> Any:
        attempted.append("HTTP or DNS transport attempted")
        raise AssertionError("Hermetic browser smoke test cannot use external HTTP/DNS")

    async def deny_async(*args: Any, **kwargs: Any) -> Any:
        return deny(*args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(requests.Session, "request", deny)
    monkeypatch.setattr(curl_requests.Session, "request", deny)
    monkeypatch.setattr(curl_requests.AsyncSession, "request", deny_async)
    monkeypatch.setattr(httpx.Client, "send", deny)
    monkeypatch.setattr(httpx.AsyncClient, "send", deny_async)
    monkeypatch.setattr(aiohttp.ClientSession, "_request", deny_async)
    for method in ("get", "post", "put", "delete", "patch", "fetch", "head"):
        monkeypatch.setattr(APIRequestContext, method, deny_async)
    return attempted


@pytest.mark.asyncio
async def test_e2e_self_healing_bot_flow(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, blocked_http_transports: list[str]
) -> None:
    caplog.set_level(logging.INFO)
    trace_events: list[str] = []
    browser_requests: list[str] = []
    blocked_browser_requests: list[str] = []

    async def fake_solver(self: CaptchaInterceptor, image_base64: str) -> str:
        assert image_base64
        trace_events.append("captcha_solver_called")
        return "12345"

    monkeypatch.setattr(CaptchaInterceptor, "_request_solver", fake_solver)
    monkeypatch.setattr(utcms_config, "UTCMS_CAPTCHA_VALUE", "12345")
    monkeypatch.setattr(utcms_config, "PAGE_GOTO_MAX_RETRIES", 0)
    monkeypatch.setattr(utcms_config, "PAGE_NAVIGATION_TIMEOUT", 3000)
    monkeypatch.setattr("app.automation.login_attempt_ledger.check_login_allowed", AsyncMock(return_value=(True, None)))

    login_html = f"""<html><body>
      <form onsubmit="event.preventDefault();
        if (this.NationalCode.value === '09121234567' && this.Password.value === 'test-input'
            && this.CapToken.value === '12345') {{
          this.hidden = true;
          const success = document.createElement('div');
          success.id = 'login_success'; success.textContent = 'Logged in';
          document.body.appendChild(success);
        }} return false;">
        <input name="NationalCode" type="text">
        <input name="Password" type="password">
        <img id="dntCaptchaImg" src="{CAPTCHA_IMAGE}" style="width:120px;height:40px">
        <input name="CapToken" type="text">
        <button id="inter" type="submit">Login</button>
      </form>
    </body></html>"""
    waybill_html = f"""<html><body>
      <input name="txtSenderFirstName" type="text">
      <button id="btnGoLVL2" type="button" onclick="this.dataset.clicked='yes'">Next</button>
      <img id="waybillCaptcha" src="{CAPTCHA_IMAGE}" style="width:110px;height:35px">
      <input name="DNTCaptchaInputText" type="text">
    </body></html>"""

    async def route_fixture(route: Route) -> None:
        browser_requests.append(route.request.url)
        if route.request.url == FIXTURE_URL:
            await route.fulfill(status=200, content_type="text/html", body=login_html)
        else:
            blocked_browser_requests.append(route.request.url)
            await route.abort("blockedbyclient")

    def bound_locator(locator: Any) -> None:
        locator.retry_policy = RetryPolicy(max_attempts=1)
        locator.stability_checks = 1
        locator.stability_interval_ms = 50
        original = locator.locate

        async def locate(page: Any, selectors: Any, timeout: int = 10000) -> Any:
            return await original(page, selectors, timeout=min(timeout, 600))

        monkeypatch.setattr(locator, "locate", locate)

    async with asyncio.timeout(40), async_playwright() as playwright:
        system_chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        executable = system_chrome if system_chrome.is_file() else Path(playwright.chromium.executable_path)
        if not executable.is_file():
            if os.getenv("CI") == "true":
                pytest.fail("CI must install Playwright Chromium before running the browser smoke test")
            pytest.skip("Playwright Chromium is not installed")
        browser = await playwright.chromium.launch(
            headless=True,
            executable_path=str(executable),
            timeout=10000,
            args=[
                "--disable-background-networking",
                "--disable-component-update",
                "--host-resolver-rules=MAP * ~NOTFOUND",
            ],
        )
        context = await browser.new_context(service_workers="block")
        try:
            context.set_default_timeout(1500)
            context.set_default_navigation_timeout(3000)
            await context.route("**/*", route_fixture)
            page = await context.new_page()
            auth = UTCMSAuthenticator(page, context)
            bound_locator(auth.smart_locator)
            http_first = AsyncMock(return_value=False)
            monkeypatch.setattr(auth, "_try_http_login_first", http_first)
            monkeypatch.setattr(auth.navigator, "candidate_login_urls", lambda *_args: [FIXTURE_URL])
            auth.captcha_interceptor = CaptchaInterceptor("http://solver.invalid", smart_locator=auth.smart_locator)

            async def verify_fixture_login(*args: Any, **kwargs: Any) -> bool:
                await page.locator("#login_success").wait_for(state="visible", timeout=1500)
                return True

            monkeypatch.setattr(auth, "_wait_for_login_result", verify_fixture_login)
            monkeypatch.setattr(auth, "_complete_post_login_steps", verify_fixture_login)
            monkeypatch.setattr(auth, "_is_logged_in", verify_fixture_login)
            assert await auth.login("09121234567", "test-input", login_url=FIXTURE_URL)
            assert auth.last_state == "success"
            http_first.assert_awaited_once()
            assert await page.locator("#login_success").inner_text() == "Logged in"

            await page.set_content(waybill_html)
            manager = EnhancedWaybillManager(page, context)
            bound_locator(manager.smart_locator)
            await manager._fill_with_fallback(
                ["#missing-sender", "input[name='txtSenderFirstName']"], "Ali", "sender_name"
            )
            assert await page.locator("input[name='txtSenderFirstName']").input_value() == "Ali"
            assert await manager._click_with_fallback(
                ["#missing-next", "#btnGoLVL2"], label="go_lvl2", wait_after_seconds=0
            )
            assert await page.locator("#btnGoLVL2").get_attribute("data-clicked") == "yes"
            interceptor = CaptchaInterceptor("http://solver.invalid", smart_locator=manager.smart_locator)
            result = await interceptor.solve_and_fill(
                page, captcha_input_selectors=["input[name='DNTCaptchaInputText']"]
            )
            assert result.status.value == "solved"
            assert await page.locator("input[name='DNTCaptchaInputText']").input_value() == "12345"
        finally:
            await asyncio.wait_for(context.close(), timeout=5)
            await asyncio.wait_for(browser.close(), timeout=5)

    assert browser_requests == [FIXTURE_URL]
    assert blocked_browser_requests == []
    assert blocked_http_transports == []
    assert trace_events.count("captcha_solver_called") == 2
    assert any("smart_locator_selector_fallback_success" in record.message for record in caplog.records)
