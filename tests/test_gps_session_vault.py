import asyncio
from types import SimpleNamespace

import pytest

from app.automation import gps_shipping_manager as manager


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
