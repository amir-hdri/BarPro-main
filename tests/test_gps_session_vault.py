import asyncio
from types import SimpleNamespace

import pytest

from app.automation import gps_shipping_manager as manager
from app.automation.utcms_mobile_client import UtcmsMobileApiError


@pytest.mark.asyncio
async def test_get_or_login_client_reauthenticates_after_forced_invalidation(monkeypatch):
    calls: list[str] = []

    class FakeClient:
        def __init__(self, *, token=None, proxy_url=None):
            self.token = token

        @staticmethod
        def cap_token_from_solution(value):
            return value[1]

        async def auto_solve_captcha(self, form_id):
            calls.append("captcha")
            return "", "fresh-cap"

        async def login(self, national_code, password, cap_token):
            calls.append("login")
            self.token = "fresh-token"
            return SimpleNamespace(token="fresh-token", refresh_token=None, expires_at=None)

    monkeypatch.setattr("app.automation.utcms_mobile_client.UtcmsMobileClient", FakeClient)
    monkeypatch.setattr(manager, "_get_redis", lambda: asyncio.sleep(0, result=None))
    monkeypatch.setattr(manager, "get_cached_token", lambda _: asyncio.sleep(0, result=None))
    monkeypatch.setattr(manager, "get_cached_refresh_token", lambda _: asyncio.sleep(0, result=None))
    monkeypatch.setattr(manager, "cache_token", lambda *args, **kwargs: asyncio.sleep(0))

    client = await manager.get_or_login_client("001", "password", force_reauth=True)

    assert client.token == "fresh-token"
    assert calls == ["captcha", "login"]


@pytest.mark.asyncio
async def test_get_or_login_client_serializes_concurrent_login(monkeypatch):
    calls = 0

    class FakeRedis:
        def __init__(self):
            self.values = {}

        async def get(self, key):
            return self.values.get(key)

        async def set(self, key, value, **kwargs):
            if kwargs.get("nx") and key in self.values:
                return False
            self.values[key] = value
            return True

        async def delete(self, *keys):
            for key in keys:
                self.values.pop(key, None)

        async def eval(self, _script, _count, key, token):
            if self.values.get(key) == token:
                self.values.pop(key, None)
                return 1
            return 0

    redis = FakeRedis()

    class FakeClient:
        def __init__(self, *, token=None, proxy_url=None):
            self.token = token

        @staticmethod
        def cap_token_from_solution(value):
            return value[1]

        async def auto_solve_captcha(self, form_id):
            return "", "cap"

        async def login(self, national_code, password, cap_token):
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.01)
            self.token = "shared-token"
            return SimpleNamespace(token=self.token, refresh_token=None, expires_at=None)

    monkeypatch.setattr("app.automation.utcms_mobile_client.UtcmsMobileClient", FakeClient)
    monkeypatch.setattr(manager, "_get_redis", lambda: asyncio.sleep(0, result=redis))

    clients = await asyncio.gather(
        manager.get_or_login_client("002", "password"),
        manager.get_or_login_client("002", "password"),
    )

    assert calls == 1
    assert [client.token for client in clients] == ["shared-token", "shared-token"]


def test_mobile_authentication_error_is_strictly_classified():
    class Error:
        status_code = 401
        result_code = None

    class OtherError:
        status_code = 500
        result_code = 200

    assert manager.is_mobile_authentication_error(Error()) is True
    assert manager.is_mobile_authentication_error(OtherError()) is False


def _vault_fakes(monkeypatch, fake_client_cls):
    monkeypatch.setattr("app.automation.utcms_mobile_client.UtcmsMobileClient", fake_client_cls)
    monkeypatch.setattr(manager, "_get_redis", lambda: asyncio.sleep(0, result=None))
    monkeypatch.setattr(manager, "get_cached_token", lambda _: asyncio.sleep(0, result=None))
    monkeypatch.setattr(manager, "get_cached_refresh_token", lambda _: asyncio.sleep(0, result=None))
    monkeypatch.setattr(manager, "cache_token", lambda *args, **kwargs: asyncio.sleep(0))


@pytest.mark.asyncio
async def test_get_or_login_client_retries_transient_non_json_failure(monkeypatch):
    """First login attempt hits a transient non-JSON blip (as seen live) —
    the client must retry once and succeed, not fail the whole attempt."""
    calls: list[str] = []
    attempts = {"n": 0}

    class FakeClient:
        def __init__(self, *, token=None, proxy_url=None):
            self.token = token

        @staticmethod
        def cap_token_from_solution(value):
            return value[1]

        async def auto_solve_captcha(self, form_id):
            calls.append("captcha")
            return "", "fresh-cap"

        async def login(self, national_code, password, cap_token):
            calls.append("login")
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise UtcmsMobileApiError("UTCMS mobile API returned non-JSON response", status_code=502)
            self.token = "second-token"
            return SimpleNamespace(token="second-token", refresh_token=None, expires_at=None)

    _vault_fakes(monkeypatch, FakeClient)
    monkeypatch.setattr(manager, "LOGIN_RETRY_DELAY_SECONDS", 0.0)

    client = await manager.get_or_login_client("003", "password", force_reauth=True)

    assert client.token == "second-token"
    assert calls == ["captcha", "login", "captcha", "login"]


@pytest.mark.asyncio
async def test_get_or_login_client_does_not_retry_authoritative_rejection(monkeypatch):
    """Portal business rejection (result_code set, e.g. code 1) is final —
    retrying would burn budget and risk lockout."""
    calls: list[str] = []

    class FakeClient:
        def __init__(self, *, token=None, proxy_url=None):
            self.token = token

        @staticmethod
        def cap_token_from_solution(value):
            return value[1]

        async def auto_solve_captcha(self, form_id):
            calls.append("captcha")
            return "", "fresh-cap"

        async def login(self, national_code, password, cap_token):
            calls.append("login")
            raise UtcmsMobileApiError("UTCMS mobile login failed: خطا در سامانه (code: 1)", result_code=1)

    _vault_fakes(monkeypatch, FakeClient)

    with pytest.raises(UtcmsMobileApiError):
        await manager.get_or_login_client("004", "password", force_reauth=True)

    assert calls == ["captcha", "login"]


def test_transient_login_error_classifier():
    assert manager._is_transient_login_error(UtcmsMobileApiError("transport failed")) is True
    assert manager._is_transient_login_error(UtcmsMobileApiError("non-JSON response")) is True
    assert manager._is_transient_login_error(UtcmsMobileApiError("rejected", status_code=429)) is True
    assert manager._is_transient_login_error(UtcmsMobileApiError("rejected", status_code=503)) is True
    assert manager._is_transient_login_error(UtcmsMobileApiError("denied", status_code=401)) is False
    assert manager._is_transient_login_error(UtcmsMobileApiError("blocked", status_code=444)) is False
    assert manager._is_transient_login_error(UtcmsMobileApiError("nope", result_code=1)) is False
    assert manager._is_transient_login_error(ValueError("boom")) is False


@pytest.mark.asyncio
async def test_get_or_login_client_invalidates_broken_refresh_token(monkeypatch):
    """When client.refresh fails (transport/non-JSON error), it immediately
    invalidates the cached session so doomed refresh attempts are not repeated."""
    calls: list[str] = []
    invalidated_codes: list[str] = []

    class FakeClient:
        def __init__(self, *, token=None, proxy_url=None):
            self.token = token

        @staticmethod
        def cap_token_from_solution(value):
            return value[1]

        async def refresh(self, refresh_token):
            calls.append("refresh")
            raise UtcmsMobileApiError("UTCMS mobile API returned non-JSON response", status_code=502)

        async def auto_solve_captcha(self, form_id):
            calls.append("captcha")
            return "", "fresh-cap"

        async def login(self, national_code, password, cap_token):
            calls.append("login")
            self.token = "new-token-after-refresh-fail"
            return SimpleNamespace(token=self.token, refresh_token="new-refresh-token", expires_at=None)

    _vault_fakes(monkeypatch, FakeClient)
    monkeypatch.setattr(manager, "get_cached_refresh_token", lambda _: asyncio.sleep(0, result="broken-refresh"))

    orig_invalidate = manager.invalidate_cached_session

    async def mock_invalidate(nc):
        invalidated_codes.append(nc)
        await orig_invalidate(nc)

    monkeypatch.setattr(manager, "invalidate_cached_session", mock_invalidate)

    client = await manager.get_or_login_client("005", "password")

    assert client.token == "new-token-after-refresh-fail"
    assert "005" in invalidated_codes
    assert calls == ["refresh", "captcha", "login"]


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_pwd", ["", "dummy", "   ", "  dummy  ", None])
async def test_get_or_login_client_rejects_dummy_or_empty_password_before_login(monkeypatch, invalid_pwd):
    """Ensure password is valid and non-empty (raise ValueError if password in ('dummy', ''))
    before attempting login, preventing wasted CAPTCHA solves and UTCMS lockout."""
    calls: list[str] = []

    class FakeClient:
        def __init__(self, *, token=None, proxy_url=None):
            self.token = token

        async def auto_solve_captcha(self, form_id):
            calls.append("captcha")
            return "", "cap"

        async def login(self, national_code, password, cap_token):
            calls.append("login")
            return SimpleNamespace(token="token", refresh_token=None, expires_at=None)

    _vault_fakes(monkeypatch, FakeClient)

    with pytest.raises(ValueError, match="رمز عبور"):
        await manager.get_or_login_client("006", invalid_pwd)

    # Neither captcha solving nor login must be attempted
    assert calls == []


@pytest.mark.asyncio
async def test_get_or_login_client_allows_dummy_pwd_if_cached_token_exists(monkeypatch):
    """If a valid bearer token is already cached in Redis, get_or_login_client reuses it
    and does not raise ValueError because no login is attempted."""
    monkeypatch.setattr(manager, "_get_redis", lambda: asyncio.sleep(0, result=None))
    monkeypatch.setattr(manager, "get_cached_token", lambda _: asyncio.sleep(0, result="already-cached-token"))

    client = await manager.get_or_login_client("007", "dummy")
    assert client.token == "already-cached-token"

