"""Regression tests for mobile login failure diagnostics (code-1 class).

Covers the 2026-09-23 live probe stop: UTCMS rejected
POST /Account/UserLoginV2 with resultCode=1 ("خطا در سامانه") and the
client discarded the envelope. The client must now keep the sanitized
envelope on the exception and log an actionable summary without ever
leaking credential material.
"""

import json
import logging

import pytest

from app.automation.utcms_mobile_client import (
    UtcmsMobileApiError,
    UtcmsMobileClient,
    require_successful_mutation,
)
from app.core.config import utcms_config


class _LoginRejectedClient:
    """Fake transport returning the exact live failure shape (code 1)."""

    async def post(self, url, **kwargs):
        class FakeResponse:
            status_code = 200

            def json(self):
                return {
                    "resultCode": 1,
                    "resultMessage": "خطا در سامانه",
                    "obj": {"token": "tok-secret", "capToken": "cap-secret"},
                }

        return FakeResponse()


class _LoginStringOkClient:
    async def post(self, url, **kwargs):
        class FakeResponse:
            status_code = 200

            def json(self):
                return {
                    "resultCode": "200",
                    "obj": {"token": "token-1", "refreshToken": "refresh-1"},
                }

        return FakeResponse()


class _BrokenSettingsClient:
    async def post(self, url, **kwargs):
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_login_rejection_keeps_sanitized_envelope_and_logs_summary(caplog):
    client = UtcmsMobileClient(base_url="https://example.invalid/API", http_client=_LoginRejectedClient())
    with caplog.at_level(logging.WARNING, logger="app.automation.utcms_mobile_client"):
        with pytest.raises(UtcmsMobileApiError) as exc_info:
            await client.login("0084575948", "secret-password", "pow-cap")

    err = exc_info.value
    assert err.result_code == 1
    assert "خطا در سامانه" in str(err)

    dumped = json.dumps(err.response_body, ensure_ascii=False)
    assert "tok-secret" not in dumped
    assert "cap-secret" not in dumped
    assert "secret-password" not in dumped

    logged = caplog.text
    assert "mobile_login_rejected" in logged
    assert "tok-secret" not in logged
    assert "cap-secret" not in logged
    assert "secret-password" not in logged


@pytest.mark.asyncio
async def test_login_accepts_string_success_code():
    client = UtcmsMobileClient(base_url="https://example.invalid/API", http_client=_LoginStringOkClient())
    auth = await client.login("0084575948", "secret", "cap")
    assert auth.token == "token-1"


def test_mutation_gate_keeps_server_message_and_sanitized_body():
    response = {
        "resultCode": 401,
        "resultMessage": "توکن نامعتبر است",
        "obj": {"token": "tok-secret", "capToken": "cap-secret"},
    }
    with pytest.raises(UtcmsMobileApiError) as exc_info:
        require_successful_mutation(response, "InsertDocument")

    err = exc_info.value
    assert err.result_code == 401
    assert "توکن نامعتبر است" in str(err)
    dumped = json.dumps(err.response_body, ensure_ascii=False)
    assert "tok-secret" not in dumped
    assert "cap-secret" not in dumped


@pytest.mark.asyncio
async def test_site_key_fallback_logs_warning_without_key_value(caplog):
    client = UtcmsMobileClient(base_url="https://example.invalid/API", http_client=_BrokenSettingsClient())
    with caplog.at_level(logging.WARNING, logger="app.automation.utcms_mobile_client"):
        key = await client.get_cap_site_key()

    assert key == utcms_config.UTCMS_CAPTCHA_POW_SITE_KEY
    assert "cap_site_key_live_fetch_failed" in caplog.text
