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
    monkeypatch.setattr(manager, "get_cached_token", lambda _nc, **_kw: asyncio.sleep(0, result=None))
    monkeypatch.setattr(manager, "get_cached_refresh_token", lambda _nc, **_kw: asyncio.sleep(0, result=None))
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
    monkeypatch.setattr(manager, "get_cached_token", lambda _nc, **_kw: asyncio.sleep(0, result=None))
    monkeypatch.setattr(manager, "get_cached_refresh_token", lambda _nc, **_kw: asyncio.sleep(0, result=None))
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
    assert manager._is_transient_login_error(UtcmsMobileApiError("کد امنیتی صحیح نمی باشد", result_code=4003)) is True
    assert manager._is_transient_login_error(UtcmsMobileApiError("wrong captcha", result_code="4003")) is True
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
    monkeypatch.setattr(
        manager, "get_cached_refresh_token", lambda _nc, **_kw: asyncio.sleep(0, result="broken-refresh")
    )

    orig_invalidate = manager.invalidate_cached_session

    async def mock_invalidate(nc, **_kw):
        invalidated_codes.append(nc)
        await orig_invalidate(nc, **_kw)

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
    monkeypatch.setattr(manager, "get_cached_token", lambda _nc, **_kw: asyncio.sleep(0, result="already-cached-token"))

    client = await manager.get_or_login_client("007", "dummy")
    assert client.token == "already-cached-token"


# ── C3 (batch C): tenant-scoped vault keys ────────────────────────────────────


class _FakeVaultRedis:
    """Dict-backed async Redis double supporting the vault's key shapes."""

    def __init__(self):
        self.values: dict[str, str] = {}

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
        return len(keys)


@pytest.mark.asyncio
async def test_c3_vault_uses_scoped_key_when_client_id_provided(monkeypatch):
    """cache_token/get_cached_token must use the tenant-scoped key with client_id.

    A different tenant (or no tenant) must NOT read the entry back: scoped
    lookups never fall back to the legacy unscoped key.
    """
    fake = _FakeVaultRedis()
    monkeypatch.setattr(manager, "_get_redis", lambda: asyncio.sleep(0, result=fake))

    await manager.cache_token("0012345678", "tok-tenant-7", client_id=7)

    assert fake.values.get("utcms:driver:token:7:0012345678") == "tok-tenant-7"
    assert await manager.get_cached_token("0012345678", client_id=7) == "tok-tenant-7"
    # Another tenant sharing the national code sees nothing.
    assert await manager.get_cached_token("0012345678", client_id=8) is None
    # The legacy unscoped key was never written and is never consulted.
    assert "utcms:driver:token:0012345678" not in fake.values
    assert await manager.get_cached_token("0012345678") is None


@pytest.mark.asyncio
async def test_c3_get_or_login_client_scopes_vault_to_tenant(monkeypatch):
    """get_or_login_client(client_id=7) must hit the scoped key, not the legacy one."""
    fake = _FakeVaultRedis()
    fake.values["utcms:driver:token:0012345678"] = "tok-legacy-unscoped"
    fake.values["utcms:driver:token:7:0012345678"] = "tok-tenant-7"
    monkeypatch.setattr(manager, "_get_redis", lambda: asyncio.sleep(0, result=fake))

    client = await manager.get_or_login_client("0012345678", "some-password", client_id=7)

    assert client.token == "tok-tenant-7"


@pytest.mark.asyncio
async def test_c3_get_or_login_client_without_client_id_keeps_legacy_key(monkeypatch):
    """Without client_id the legacy unscoped behavior is preserved (explicit opt-out)."""
    fake = _FakeVaultRedis()
    fake.values["utcms:driver:token:0012345678"] = "tok-legacy-unscoped"
    monkeypatch.setattr(manager, "_get_redis", lambda: asyncio.sleep(0, result=fake))

    client = await manager.get_or_login_client("0012345678", "some-password")

    assert client.token == "tok-legacy-unscoped"


@pytest.mark.asyncio
async def test_c3_invalidate_cached_session_is_tenant_scoped(monkeypatch):
    """Invalidation with client_id must not wipe another tenant's session."""
    fake = _FakeVaultRedis()
    fake.values["utcms:driver:token:7:0012345678"] = "tok-7"
    fake.values["utcms:driver:refresh:7:0012345678"] = "ref-7"
    fake.values["utcms:driver:token:8:0012345678"] = "tok-8"
    monkeypatch.setattr(manager, "_get_redis", lambda: asyncio.sleep(0, result=fake))

    await manager.invalidate_cached_session("0012345678", client_id=7)

    assert "utcms:driver:token:7:0012345678" not in fake.values
    assert "utcms:driver:refresh:7:0012345678" not in fake.values
    assert fake.values.get("utcms:driver:token:8:0012345678") == "tok-8"
