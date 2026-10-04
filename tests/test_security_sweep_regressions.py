"""Regression tests for the 2026-10-01 security + reliability sweep fixes.

Covers:
- H1: OTP / solved-captcha secrets must never reach logs (static tripwire).
- M1: alertmanager webhook is fail-closed (503) in production without a secret.
- M2: /healthz and /readyz bypass fail-closed rate limiting.
- M3: InMemoryRateLimiter namespaces buckets by rule key_prefix.
- L2: national codes are masked in automation logs.
"""

from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.routes.admin_alerts import alertmanager_webhook
from app.automation.gps_shipping_manager import _mask_national_code
from app.core.config import utcms_config
from app.core.rate_limiter import InMemoryRateLimiter, RateLimitConfig
from app.main import _is_rate_limit_exempt_path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# H1: OTP / captcha secrets must not be logged (static tripwire)
# ---------------------------------------------------------------------------


def test_otp_values_never_logged_in_multitenant_bot() -> None:
    src = _read("app/automation/waybill_bot_multitenant.py")
    # Historical patterns that leaked the live OTP value into logs.
    assert "with OTP=%s" not in src
    assert '": %s", k, otp_code' not in src
    assert 'answer=%s", issue_cap_token' not in src
    # The surviving log lines mention the event, not the secret.
    assert 'logger.info("Received a current OTP for the mobile document")' in src
    assert 'logger.info("Submitting IssueDocumentByOtp for docId=%s", document_id)' in src


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
