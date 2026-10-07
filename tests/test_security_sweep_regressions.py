"""Regression tests for the 2026-10-01 security + reliability sweep fixes.

Covers:
- H1: OTP / solved-captcha secrets must never reach logs (runtime + static tripwires).
- M1: alertmanager webhook is fail-closed (503) in production without a secret.
- M2: /healthz and /readyz bypass fail-closed rate limiting.
- M3: InMemoryRateLimiter namespaces buckets by rule key_prefix.
- L2: national codes are masked in automation logs.
"""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.routes.admin_alerts import alertmanager_webhook
from app.automation.gps_shipping_manager import _mask_national_code
from app.automation.waybill_bot_multitenant import WaybillAutomationBot
from app.core.config import utcms_config
from app.core.rate_limiter import InMemoryRateLimiter, RateLimitConfig
from app.main import _is_rate_limit_exempt_path
from tests.test_mobile_waybill_bot import _FakeMobileClient, _mobile_payload
from tests.test_otp_delivery_contract import delivery_api as delivery_api

REPO_ROOT = Path(__file__).resolve().parent.parent


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# H1: OTP / captcha secrets must not be logged
# ---------------------------------------------------------------------------


async def test_otp_values_never_logged_in_multitenant_bot(delivery_api, monkeypatch, caplog) -> None:
    src = _read("app/automation/waybill_bot_multitenant.py")
    # Historical patterns that leaked the live OTP value into logs.
    assert "with OTP=%s" not in src
    assert '": %s", k, otp_code' not in src
    assert 'answer=%s", issue_cap_token' not in src
    # Exercise the current challenge handoff; no particular informational log
    # wording is required, but neither formatted nor structured logs may leak.
    otp = "74318207"
    captcha = "test-sensitive-issuance-captcha"
    clients = []

    class PrivacyClient(_FakeMobileClient):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            clients.append(self)

        async def insert_document(self, payload, *, allow_live_submit, cap_token=None):
            assert cap_token == captcha
            return await super().insert_document(payload, allow_live_submit=allow_live_submit, cap_token="issue-cap")

    caplog.set_level(logging.DEBUG, logger="app.automation.waybill_bot_multitenant")
    monkeypatch.setenv("WORKER_ID", "2")
    payload = _mobile_payload()
    bot = WaybillAutomationBot(MagicMock(), MagicMock(), proxy_url="http://assigned-squid:3128")
    with (
        patch("app.automation.waybill_bot_multitenant.utcms_config.UTCMS_TRANSPORT", "mobile"),
        patch("app.automation.waybill_bot_multitenant.utcms_config.UTCMS_CAPTCHA_VALUE", "login-cap"),
        patch("app.automation.waybill_bot_multitenant.build_enhanced_waybill_payload", return_value=payload),
        patch("app.automation.waybill_bot_multitenant.validate_live_waybill_payload", return_value=[]),
        patch("app.automation.utcms_mobile_client.UtcmsMobileClient", PrivacyClient),
    ):
        result = await bot.execute_waybill_job(
            username="user",
            password="password",
            payload={**payload, "mobile_issue_cap_token": captcha, "otp_code": otp},
            job_id="job-mobile-privacy",
            client_id=1,
            allow_live_submit=True,
        )
    assert sum(client.insert_calls for client in clients) == 1
    assert result["status"] == "unknown" and result["error_category"] == "otp_required"
    assert await delivery_api[1].xlen("rpa:otp:stream") == 0
    logged = caplog.text + repr([record.__dict__ for record in caplog.records])
    assert otp not in logged
    assert captcha not in logged


def test_otp_value_never_logged_in_enhanced_bot() -> None:
    src = _read("app/automation/waybill_enhanced.py")
    assert '"code": otp_value' not in src
    assert '"length": len(otp_value)' in src


# ---------------------------------------------------------------------------
# M1: alertmanager webhook fail-closed without secret in production
# ---------------------------------------------------------------------------


def _webhook_request(body: bytes = b"") -> Request:
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/admin/alerts/webhook",
        "headers": [],
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope, receive)


@pytest.mark.asyncio
async def test_alert_webhook_production_without_secret_is_503(monkeypatch) -> None:
    """An attacker reaching the backend directly must not bypass auth by
    omitting X-Request-ID when no secret is configured in production."""
    monkeypatch.setattr(utcms_config, "ENVIRONMENT", "production")
    monkeypatch.setattr(utcms_config, "ALERT_WEBHOOK_SECRET", "")
    with pytest.raises(HTTPException) as exc_info:
        await alertmanager_webhook(_webhook_request(), session=None)  # type: ignore[arg-type]
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_alert_webhook_production_with_secret_skips_503(monkeypatch) -> None:
    """Negative control: with a secret configured, the 503 branch is skipped
    and the request proceeds to HMAC validation (403, missing headers)."""
    monkeypatch.setattr(utcms_config, "ENVIRONMENT", "production")
    monkeypatch.setattr(utcms_config, "ALERT_WEBHOOK_SECRET", "test-secret")
    with pytest.raises(HTTPException) as exc_info:
        await alertmanager_webhook(_webhook_request(), session=None)  # type: ignore[arg-type]
    assert exc_info.value.status_code == 403
    assert "signature" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_alert_webhook_nonproduction_without_secret_still_serves_internal(
    monkeypatch,
) -> None:
    """Negative control: outside production the no-secret internal path
    (Alertmanager calling the backend directly) keeps working."""
    monkeypatch.setattr(utcms_config, "ENVIRONMENT", "test")
    monkeypatch.setattr(utcms_config, "ALERT_WEBHOOK_SECRET", "")
    result = await alertmanager_webhook(_webhook_request(b'{"alerts": []}'), session=None)  # type: ignore[arg-type]
    assert result == {"status": "success", "processed_alerts": 0}


# ---------------------------------------------------------------------------
# M2: health probes bypass fail-closed rate limiting
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/healthz", "/readyz"])
def test_health_probe_paths_are_rate_limit_exempt(path: str) -> None:
    assert _is_rate_limit_exempt_path(path) is True


@pytest.mark.parametrize(
    "path",
    ["/api/v1/auth/login", "/api/v1/admin/alerts", "/api/v1/waybill-jobs", "/metrics", "/"],
)
def test_non_probe_paths_are_not_rate_limit_exempt(path: str) -> None:
    assert _is_rate_limit_exempt_path(path) is False


# ---------------------------------------------------------------------------
# M3: in-memory limiter namespaces buckets by rule key_prefix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_memory_limiter_isolates_buckets_by_key_prefix() -> None:
    """The strict auth bucket must not share a counter with the public bucket
    for the same client IP (mirrors the Redis backend's key namespacing)."""
    limiter = InMemoryRateLimiter()
    auth_config = RateLimitConfig(max_requests=1, window_seconds=60, key_prefix="ratelimit:auth")
    public_config = RateLimitConfig(max_requests=1, window_seconds=60, key_prefix="ratelimit:public")

    # Exhaust the auth bucket for this client...
    assert (await limiter.check("10.0.0.1", auth_config)).remaining == 0
    assert (await limiter.check("10.0.0.1", auth_config)).retry_after is not None
    # ...the public bucket for the same client must be unaffected.
    state = await limiter.check("10.0.0.1", public_config)
    assert state.retry_after is None
    assert state.remaining == 0


@pytest.mark.asyncio
async def test_in_memory_limiter_still_shares_bucket_within_rule() -> None:
    """Negative control: the same rule + key still shares one counter."""
    limiter = InMemoryRateLimiter()
    config = RateLimitConfig(max_requests=1, window_seconds=60, key_prefix="ratelimit:auth")
    assert (await limiter.check("10.0.0.2", config)).retry_after is None
    assert (await limiter.check("10.0.0.2", config)).retry_after is not None


# ---------------------------------------------------------------------------
# L2: national codes are masked in logs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1234567890", "********90"),
        (" 123-456-7890 ", "********90"),
        ("12", "***"),
        ("", "***"),
        (None, "***"),
    ],
)
def test_mask_national_code(raw, expected: str) -> None:
    masked = _mask_national_code(raw)
    assert masked == expected
    if raw and len(str(raw).strip()) > 2:
        # The full code must never survive masking.
        assert str(raw).strip() not in masked


def test_national_code_log_sites_use_masker() -> None:
    src = _read("app/automation/gps_shipping_manager.py")
    assert src.count("_mask_national_code(national_code)") == 4
    assert 'national_code=%s", national_code)' not in src
