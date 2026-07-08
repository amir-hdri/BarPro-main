"""E2E smoke test for self-healing auth + waybill flows.

This test intentionally uses a local in-memory HTML page (no Next.js frontend)
to validate that SmartLocator fallbacks and CaptchaInterceptor are triggered.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
from typing import Any

import pytest
from playwright.async_api import async_playwright

from app.automation.auth import UTCMSAuthenticator
from app.automation.waybill_enhanced import EnhancedWaybillManager
from app.bot.captcha.interceptor import CaptchaInterceptor
from app.core.config import utcms_config

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_e2e_self_healing_bot_flow(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """Run auth + waybill smoke flow with mocked captcha solver and BullMQ payload."""
    caplog.set_level(logging.INFO)

    # 1) Mock BullMQ-like payload for one waybill task
    mocked_job_payload: dict[str, Any] = {
        "job_id": "job_e2e_001",
        "client_id": 1,
        "driver_id": 101,
        "correlation_id": "corr_e2e_001",
        "username": "09121234567",
        "password": "secret",
        "waybill": {
            "sender": {"name": "Sender A"},
            "receiver": {"name": "Receiver B"},
        },
    }

    trace_events: list[dict[str, Any]] = []

    async def fake_request_solver(self: CaptchaInterceptor, image_base64: str) -> str:
        trace_events.append({"event": "captcha_solver_called", "image_size": len(image_base64)})
        return "12345"

    monkeypatch.setattr(CaptchaInterceptor, "_request_solver", fake_request_solver, raising=True)

    original_captcha_value = utcms_config.UTCMS_CAPTCHA_VALUE
    utcms_config.UTCMS_CAPTCHA_VALUE = "12345"

    login_html = """
    <html>
      <body>
        <form onsubmit="event.preventDefault(); document.body.innerHTML='Logged in'; window.history.pushState({}, '', '/dashboard'); return false;">
        <form onsubmit="event.preventDefault(); document.body.innerHTML += \'<div id=\\'login_success\\'></div>\'; return false;">
          <input name="username" type="text" />
          <input id="password" type="password" />
          <img id="dntCaptchaImg" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==" style="width:120px;height:40px;" />
          <input name="DNTCaptchaInputText" type="text" />
          <button id="login-btn" type="submit">Login</button>
        </form>
      </body>
    </html>
    """.strip()

    waybill_html = """
    <html>
      <body>
        <input name="txtSenderFirstName" type="text" />
        <button id="btnGoLVL2" type="button">Next</button>
        <img id="waybillCaptcha" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==" style="width:110px;height:35px;" />
        <input name="DNTCaptchaInputText" type="text" />
      </body>
    </html>
    """.strip()

    encoded_login = "data:text/html," + urllib.parse.quote(login_html)

    try:
        async with async_playwright() as pw:
            system_chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            browser = None
            launch_attempts = [
                {"headless": True, "executable_path": system_chrome_path},
                {"headless": False, "executable_path": system_chrome_path},
                {"headless": True, "channel": "chromium"},
                {"headless": False, "channel": "chromium"},
                {"headless": True},
            ]
            last_launch_error: Exception | None = None
            launch_errors: list[str] = []
            for launch_kwargs in launch_attempts:
                if launch_kwargs.get("executable_path") and not os.path.exists(system_chrome_path):
                    continue
                try:
                    browser = await pw.chromium.launch(**launch_kwargs)
                    break
                except Exception as exc:  # pragma: no cover - depends on local browser install
                    last_launch_error = exc
                    launch_errors.append(f"{launch_kwargs}: {exc}")

            if browser is None:
                summary = " | ".join(launch_errors[-3:]) if launch_errors else str(last_launch_error)
                pytest.skip(f"Chromium not available for E2E smoke test: {summary}")

            context = await browser.new_context()
            page = await context.new_page()

            # 2) Run auth flow (SmartLocator + CaptchaInterceptor)
            auth = UTCMSAuthenticator(page, context)

            original_locate = auth.smart_locator.locate

            async def traced_auth_locate(page_obj, selectors, timeout=10_000):
                trace_events.append({"event": "auth_locate", "selectors": list(selectors), "timeout": timeout})
                return await original_locate(page_obj, selectors, timeout)

            monkeypatch.setattr(auth.smart_locator, "locate", traced_auth_locate, raising=False)

            async def always_true(*_args, **_kwargs):
                return True

            monkeypatch.setattr(auth, "_wait_for_login_result", always_true, raising=True)
            monkeypatch.setattr(auth, "_complete_post_login_steps", always_true, raising=True)
            monkeypatch.setattr(auth, "_is_logged_in", always_true, raising=True)

            ok = await auth.login(
                mocked_job_payload["username"],
                mocked_job_payload["password"],
                login_url=encoded_login,
            )
            assert ok is True
            assert auth.last_state == "success"

            # 3) Run waybill_enhanced core interactions with SmartLocator traces
            await page.set_content(waybill_html)
            manager = EnhancedWaybillManager(page, context)

            original_waybill_locate = manager.smart_locator.locate

            async def traced_waybill_locate(page_obj, selectors, timeout=10_000):
                trace_events.append({"event": "waybill_locate", "selectors": list(selectors), "timeout": timeout})
                return await original_waybill_locate(page_obj, selectors, timeout)

            monkeypatch.setattr(manager.smart_locator, "locate", traced_waybill_locate, raising=False)

            await manager._fill_with_fallback(
                ["#missing-sender", "input[name='txtSenderFirstName']"],
                "Ali",
                "sender_name",
                required=True,
            )
            sender_value = await page.eval_on_selector("input[name='txtSenderFirstName']", "el => el.value")
            assert sender_value == "Ali"

            clicked = await manager._click_with_fallback(
                ["#missing-next", "#btnGoLVL2"],
                label="go_lvl2",
                required=True,
            )
            assert clicked is True

            interceptor = CaptchaInterceptor("http://mock-solver.local/solve", smart_locator=manager.smart_locator)
            captcha_result = await interceptor.solve_and_fill(page)
            assert captcha_result.status.value == "solved"
            captcha_value = await page.eval_on_selector("input[name='DNTCaptchaInputText']", "el => el.value")
            assert captcha_value == "12345"

            await context.close()
            await browser.close()

    finally:
        utcms_config.UTCMS_CAPTCHA_VALUE = original_captcha_value

    # 4) Detailed trace output for review
    logger.info("e2e_self_healing_trace", extra={"extra_fields": {"trace_events": trace_events}})
    print("\\n[E2E TRACE]", json.dumps(trace_events, ensure_ascii=False, indent=2))

    # Ensure fallback telemetry from SmartLocator was emitted at least once.
    assert any("smart_locator_selector_fallback_success" in record.message for record in caplog.records)
    # Ensure captcha interceptor/solver path was exercised.
    assert any(event.get("event") == "captcha_solver_called" for event in trace_events)
