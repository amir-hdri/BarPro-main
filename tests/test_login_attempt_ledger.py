"""P0-1: per-account UTCMS login attempt ledger + cooldown.

Live incident (2026-09-30): repeated failed logins against driver account
``5720047670`` (ad-hoc History checks with misread CAPTCHAs, 4 job attempts,
keepalive re-auth) pushed the account into a UTCMS-side lockout
(``resultCode=1 خطا در سامانه``) while a sibling account on the same egress
still returned ``resultCode=200``. Nothing capped per-account attempts.

Contract under test:
1. Fresh identities are allowed; burned attempts accumulate in a window.
2. At threshold, further logins are refused LOCALLY (no UTCMS traffic) until
   the cooldown expires; success clears the ledger.
3. Transport/infra failures never count (they are the egress layer's domain).
4. Redis outage fails open (a cache outage must not lock every account).
5. ``AccountCooldownError`` classifies as retryable ``AUTH_FAILURE`` so the
   worker backs off without burning attempts.
6. Mobile (``get_or_login_client``) and web (``UtcmsHttpLogin.authenticate``)
   both consult the ledger before spending an attempt and record burned ones.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.automation.login_attempt_ledger import (
    AccountCooldownError,
    check_login_allowed,
    record_login_failure,
    record_login_success,
)
from app.core.config import utcms_config
from app.core.error_taxonomy import ErrorCategory, classify_exception


class FakeRedis:
    """Minimal async Redis with TTL for ledger tests."""

    def __init__(self):
        self._data: dict[str, tuple[str, float | None]] = {}

    async def get(self, key):
        item = self._data.get(key)
        if item is None:
            return None
        value, exp = item
        if exp is not None and time.monotonic() >= exp:
            del self._data[key]
            return None
        return value

    async def set(self, key, value, ex=None, nx=False):
        if nx and await self.get(key) is not None:
            return None
        exp = time.monotonic() + ex if ex else None
        self._data[key] = (str(value), exp)
        return True

    async def incr(self, key):
        current = await self.get(key)
        value = int(current) + 1 if current is not None else 1
        _, exp = self._data.get(key, ("1", None))
        self._data[key] = (str(value), exp)
        return value

    async def expire(self, key, seconds):
        if key in self._data:
            value, _ = self._data[key]
            self._data[key] = (value, time.monotonic() + seconds)
            return True
        return False

    async def delete(self, *keys):
        removed = 0
        for key in keys:
            if key in self._data:
                del self._data[key]
                removed += 1
        return removed


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def ledger_env(fake_redis):
    with (
        patch("app.automation.login_attempt_ledger._get_redis", new=AsyncMock(return_value=fake_redis)),
        patch.object(utcms_config, "LOGIN_FAILURE_WINDOW_SECONDS", 60, create=True),
        patch.object(utcms_config, "LOGIN_FAILURE_THRESHOLD", 3, create=True),
        patch.object(utcms_config, "LOGIN_COOLDOWN_SECONDS", 60, create=True),
    ):
        yield fake_redis


@pytest.mark.asyncio
async def test_fresh_identity_allowed(ledger_env):
    allowed, reason = await check_login_allowed("5720047670")
    assert allowed is True
    assert reason is None


@pytest.mark.asyncio
async def test_threshold_failures_trigger_cooldown(ledger_env):
    for _ in range(3):
        await record_login_failure("5720047670", kind="mobile")
    allowed, reason = await check_login_allowed("5720047670")
    assert allowed is False
    assert reason is not None and "cooldown" in reason.lower()


@pytest.mark.asyncio
async def test_below_threshold_still_allowed(ledger_env):
    for _ in range(2):
        await record_login_failure("5720047670", kind="mobile")
    allowed, _ = await check_login_allowed("5720047670")
    assert allowed is True


@pytest.mark.asyncio
async def test_success_clears_failures(ledger_env):
    for _ in range(2):
        await record_login_failure("5720047670", kind="mobile")
    await record_login_success("5720047670")
    for _ in range(2):
        await record_login_failure("5720047670", kind="mobile")
    allowed, _ = await check_login_allowed("5720047670")
    assert allowed is True


@pytest.mark.asyncio
async def test_redis_unavailable_fails_open():
    with patch("app.automation.login_attempt_ledger._get_redis", new=AsyncMock(return_value=None)):
        allowed, _ = await check_login_allowed("5720047670")
        assert allowed is True
        await record_login_failure("5720047670", kind="mobile")
        await record_login_success("5720047670")


def test_cooldown_error_classifies_retryable_auth_failure():
    category, retryable = classify_exception(AccountCooldownError("5720047670", "test"))
    assert category == ErrorCategory.AUTH_FAILURE
    assert retryable is True


@pytest.mark.asyncio
async def test_mobile_login_skipped_during_cooldown(ledger_env):
    from app.automation import gps_shipping_manager as gsm

    for _ in range(3):
        await record_login_failure("5720047670", kind="mobile")
    solve = AsyncMock(side_effect=AssertionError("login must not be attempted during cooldown"))
    with (
        patch.object(gsm, "_get_redis", new=AsyncMock(return_value=ledger_env)),
        patch.object(gsm, "_acquire_auth_lock", new=AsyncMock(return_value="tok")),
        patch.object(gsm, "_release_auth_lock", new=AsyncMock()),
        patch.object(gsm, "_solve_and_login_with_retry", new=solve),
    ):
        with pytest.raises(AccountCooldownError):
            await gsm.get_or_login_client("5720047670", "secret", proxy_url=None)
    solve.assert_not_awaited()


@pytest.mark.asyncio
async def test_mobile_records_burned_attempt(ledger_env, fake_redis):
    from app.automation import gps_shipping_manager as gsm
    from app.automation.utcms_mobile_client import UtcmsMobileApiError

    solve = AsyncMock(side_effect=UtcmsMobileApiError("خطا در سامانه", result_code=1))
    with (
        patch.object(gsm, "_get_redis", new=AsyncMock(return_value=fake_redis)),
        patch.object(gsm, "_acquire_auth_lock", new=AsyncMock(return_value="tok")),
        patch.object(gsm, "_release_auth_lock", new=AsyncMock()),
        patch.object(gsm, "_solve_and_login_with_retry", new=solve),
    ):
        with pytest.raises(UtcmsMobileApiError):
            await gsm.get_or_login_client("5720047670", "secret", proxy_url=None)
    assert await fake_redis.get("utcms:login:failures:5720047670") == "1"


@pytest.mark.asyncio
async def test_mobile_ignores_transport_failure(ledger_env, fake_redis):
    from app.automation import gps_shipping_manager as gsm
    from app.automation.utcms_mobile_client import UtcmsMobileApiError

    solve = AsyncMock(side_effect=UtcmsMobileApiError("transport failed", result_code=None))
    with (
        patch.object(gsm, "_get_redis", new=AsyncMock(return_value=fake_redis)),
        patch.object(gsm, "_acquire_auth_lock", new=AsyncMock(return_value="tok")),
        patch.object(gsm, "_release_auth_lock", new=AsyncMock()),
        patch.object(gsm, "_solve_and_login_with_retry", new=solve),
    ):
        with pytest.raises(UtcmsMobileApiError):
            await gsm.get_or_login_client("5720047670", "secret", proxy_url=None)
    assert await fake_redis.get("utcms:login:failures:5720047670") is None


@pytest.mark.asyncio
async def test_http_login_skipped_during_cooldown(ledger_env):
    from app.automation.utcms_http_login import UtcmsHttpLogin

    for _ in range(3):
        await record_login_failure("5720047670", kind="web")
    login = UtcmsHttpLogin()
    try:
        with patch.object(login, "_attempt_single_session", new=AsyncMock()) as attempt:
            result = await login.authenticate("5720047670", "secret")
        assert result.success is False
        assert "cooldown" in (result.error or "").lower()
        assert "captcha" not in (result.error or "").lower()
        attempt.assert_not_awaited()
    finally:
        await login.close()


@pytest.mark.asyncio
async def test_http_login_records_captcha_failure(ledger_env, fake_redis):
    from app.automation.utcms_http_login import HttpLoginResult, UtcmsHttpLogin

    async def _captcha_miss(_u, _p):
        return HttpLoginResult(success=False, error="لطفا کد امنیتی صحیح را وارد نمایید", status_code=200)

    login = UtcmsHttpLogin()
    try:
        with patch.object(login, "_attempt_single_session", side_effect=_captcha_miss):
            result = await login.authenticate("5720047670", "secret")
        assert result.success is False
        assert await fake_redis.get("utcms:login:failures:5720047670") == "1"
    finally:
        await login.close()


@pytest.mark.asyncio
async def test_http_login_ignores_rate_limit(ledger_env, fake_redis, monkeypatch):
    from app.automation.utcms_http_login import HttpLoginResult, UtcmsHttpLogin

    async def _rate_limited(_u, _p):
        return HttpLoginResult(success=False, error="429", status_code=429)

    login = UtcmsHttpLogin()
    try:
        monkeypatch.setattr("app.automation.utcms_http_login.asyncio.sleep", AsyncMock())
        with patch.object(login, "_attempt_single_session", side_effect=_rate_limited):
            result = await asyncio.wait_for(login.authenticate("5720047670", "secret"), timeout=30)
        assert result.success is False
        assert await fake_redis.get("utcms:login:failures:5720047670") is None
    finally:
        await login.close()
