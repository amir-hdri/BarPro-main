"""Regression tests for the 2026-10-02 tenant-isolation audit, batch C.

C1: retired unscoped global OTP key; scoped job-scoped -> phone-scoped lookup.
    HTTP/Lua intake isolation is covered by test_otp_delivery_contract.py.
C2: legacy POST /waybill/create-with-map auth-state scoping (never global).
C3: driver session-vault client_id threading at call sites.
C4: shipping mutation lock is acquired only AFTER the ownership check.
C5: master_admin driver creation requires an explicit client_id (no silent
    fallback to the first active client).
"""

import json as _json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException as _HTTPException
from fastapi import Request as _Request

from app.api.routes import shipping_gps as sg_mod
from app.api.routes import waybill_map as waybill_map_mod
from app.automation.otp_keys import (
    normalize_phone_for_otp_key,
    otp_job_key,
    otp_lookup_keys,
    otp_phone_key,
)
from app.automation.waybill_enhanced import fetch_scoped_otp
from app.models_multitenant import Client
from app.schemas.multitenant import DriverCreateRequest
from app.services.driver_service import DriverService
from app.services.session_vault import SessionVault

# ── Shared fakes ─────────────────────────────────────────────────────────────


class FakeRedis:
    """Minimal read-only Redis double for the active browser OTP reader."""

    def __init__(self):
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)


def _otp_payload(code: str, received_at: float | None = None) -> str:
    now = received_at if received_at is not None else time.time()
    return _json.dumps(
        {"code": code, "sender": "20007777", "phone": "09120000000", "received_at": now, "expires_at": now + 300}
    )


def _make_request(headers: dict | None = None) -> _Request:
    scope = {
        "type": "http",
        "method": "POST",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return _Request(scope, receive)


def _driver_request(**overrides) -> DriverCreateRequest:
    base = {
        "driver_national_code": "0012345678",
        "full_name": "Test Driver",
        "utcms_username": "testuser",
        "utcms_password": "pass1234",
        "plate_number": "12ع345ایران67",
    }
    base.update(overrides)
    return DriverCreateRequest(**base)


def _mock_session(exec_results: list) -> MagicMock:
    session = MagicMock()
    session.exec = AsyncMock(side_effect=exec_results)
    session.commit = AsyncMock()
    session.add = MagicMock()

    async def _refresh(instance):
        instance.id = 1

    session.refresh = AsyncMock(side_effect=_refresh)
    return session


def _first(value):
    m = MagicMock()
    m.first.return_value = value
    return m


def _one(value):
    m = MagicMock()
    m.one.return_value = value
    return m


def _tenant_client(client_id: int) -> Client:
    return Client(
        id=client_id,
        client_code=f"tenant-{client_id}",
        name=f"Tenant {client_id}",
        email=f"tenant{client_id}@example.com",
        max_drivers=10,
    )


# ── C1: retired global OTP key ───────────────────────────────────────────────


def test_c1_otp_lookup_keys_scoped_order_and_no_global():
    assert otp_lookup_keys("job_1", "09121234567") == [
        "rpa:otp:job:job_1",
        "rpa:otp:phone:09121234567",
    ]
    # Job-only and phone-only contexts still work.
    assert otp_lookup_keys("job_1", None) == ["rpa:otp:job:job_1"]
    assert otp_lookup_keys(None, "+989121234567") == ["rpa:otp:phone:09121234567"]
    # No context -> no keys at all: readers fail closed, never global.
    assert otp_lookup_keys(None, None) == []
    assert otp_lookup_keys("", "") == []
    for keys in (
        otp_lookup_keys("job_1", "09121234567"),
        otp_lookup_keys("job_1", None),
        otp_lookup_keys(None, "09121234567"),
    ):
        assert "rpa:otp:latest" not in keys


def test_c1_phone_normalization_matches_writer():
    # The reader-side key must equal the writer-side key for every input shape.
    assert otp_phone_key("+989121234567") == "rpa:otp:phone:09121234567"
    assert otp_phone_key("۹۸۹۱۲۱۲۳۴۵۶۷") == "rpa:otp:phone:09121234567"
    assert otp_phone_key("") is None
    assert otp_phone_key(None) is None
    assert normalize_phone_for_otp_key("20007777") == "20007777"


@pytest.mark.asyncio
async def test_c1_fetch_scoped_otp_rejects_stale_entry():
    """A stale OTP (older than the 15s window) is never consumed — fail closed."""
    fake = FakeRedis()
    fake.store[otp_job_key("job_old")] = _otp_payload("99999", received_at=time.time() - 3600)
    assert await fetch_scoped_otp(fake, job_id="job_old", driver_phone=None, wait_start=time.time()) is None


@pytest.mark.asyncio
async def test_c1_fetch_scoped_otp_prefers_job_key_over_phone_key():
    fake = FakeRedis()
    fake.store[otp_job_key("job_x")] = _otp_payload("11111")
    fake.store["rpa:otp:phone:09120000001"] = _otp_payload("22222")
    found = await fetch_scoped_otp(fake, job_id="job_x", driver_phone="09120000001", wait_start=time.time())
    assert found is not None
    code, key, _entry = found
    assert code == "11111"
    assert key == "rpa:otp:job:job_x"


@pytest.mark.asyncio
async def test_c1_fetch_scoped_otp_never_reads_global_key():
    """Even if a legacy global key lingers in Redis, the reader ignores it."""
    fake = FakeRedis()
    fake.store["rpa:otp:latest"] = _otp_payload("31337")
    assert await fetch_scoped_otp(fake, job_id=None, driver_phone=None, wait_start=time.time()) is None


# ── C2: legacy /waybill/create-with-map auth-state scoping ───────────────────


def test_c2_legacy_route_scope_api_key_only_is_infra(monkeypatch):
    """API-key-only callers (smoke scripts) share the non-tenant 'infra' scope."""
    monkeypatch.setattr(waybill_map_mod, "_is_api_key_valid", lambda key: True)
    req = _make_request(headers={"X-API-Key": "infra-key"})
    assert waybill_map_mod._resolve_legacy_route_scope(req) == "infra"


def test_c2_legacy_route_scope_client_jwt_is_tenant(monkeypatch):
    monkeypatch.setattr(waybill_map_mod, "_is_api_key_valid", lambda key: False)
    monkeypatch.setattr(waybill_map_mod, "_extract_bearer_token", lambda auth: "tok")
    monkeypatch.setattr(waybill_map_mod, "_decode_jwt", lambda tok: {"role": "client", "sub": "7"})
    req = _make_request(headers={"Authorization": "Bearer tok"})
    assert waybill_map_mod._resolve_legacy_route_scope(req) == "client-7"


def test_c2_legacy_route_scope_master_admin_maps_to_client_1(monkeypatch):
    monkeypatch.setattr(waybill_map_mod, "_is_api_key_valid", lambda key: False)
    monkeypatch.setattr(waybill_map_mod, "_extract_bearer_token", lambda auth: "tok")
    monkeypatch.setattr(waybill_map_mod, "_decode_jwt", lambda tok: {"role": "master_admin"})
    req = _make_request(headers={"Authorization": "Bearer tok"})
    assert waybill_map_mod._resolve_legacy_route_scope(req) == "client-1"


@pytest.mark.asyncio
async def test_c2_legacy_route_forwards_scope_to_service(monkeypatch):
    """The route passes the resolved tenant scope into waybill_service."""
    monkeypatch.setattr(waybill_map_mod, "_is_api_key_valid", lambda key: False)
    monkeypatch.setattr(waybill_map_mod, "_extract_bearer_token", lambda auth: "tok")
    monkeypatch.setattr(waybill_map_mod, "_decode_jwt", lambda tok: {"role": "client", "sub": "7"})
    service = SimpleNamespace(create_waybill_with_map=AsyncMock(return_value={"ok": True}))
    monkeypatch.setattr(waybill_map_mod, "waybill_service", service)

    req = _make_request(headers={"Authorization": "Bearer tok"})
    result = await waybill_map_mod.create_waybill_with_map(request=MagicMock(), raw_request=req)

    assert result == {"ok": True}
    service.create_waybill_with_map.assert_awaited_once()
    _, kwargs = service.create_waybill_with_map.call_args
    assert kwargs["auth_scope"] == "client-7"


def test_c2_auth_state_path_and_redis_key_are_tenant_scoped():
    """Scoping the auth-state path scopes the Redis session-vault key too."""
    vault = SessionVault()
    scoped = vault.auth_state_path_for_account(username="driver1", national_code="001", scope="client-7")
    unscoped = vault.auth_state_path_for_account(username="driver1", national_code="001")
    assert "client-7" in scoped
    assert scoped != unscoped
    assert "client-7" in (vault._redis_key_from_path(scoped) or "")
    assert "client-7" not in (vault._redis_key_from_path(unscoped) or "")


# ── C3: session-vault client_id threading at call sites ──────────────────────


def test_c3_caller_client_id_helper():
    client_ctx = {"role": "client", "user": SimpleNamespace(id=5)}
    assert sg_mod._caller_client_id(client_ctx) == 5
    # master_admin has no tenant: unscoped, never guessed.
    assert sg_mod._caller_client_id({"role": "master_admin"}) is None
    assert sg_mod._caller_client_id({}) is None


@pytest.mark.asyncio
async def test_c3_shipping_login_threads_caller_tenant(monkeypatch):
    vault_client = AsyncMock()
    monkeypatch.setattr(sg_mod, "get_or_login_client", vault_client)
    monkeypatch.setattr("app.auth_multitenant.decrypt_driver_password", lambda enc: "decrypted-pwd")
    driver = SimpleNamespace(driver_national_code="0012345678", utcms_password_encrypted="enc")

    await sg_mod._login_driver_client(
        driver,
        "http://proxy:3128",
        user_context={"role": "client", "user": SimpleNamespace(id=5)},
    )

    vault_client.assert_awaited_once_with(
        national_code="0012345678",
        password="decrypted-pwd",
        proxy_url="http://proxy:3128",
        force_reauth=False,
        client_id=5,
    )


@pytest.mark.asyncio
async def test_c3_shipping_login_admin_keeps_unscoped_vault(monkeypatch):
    vault_client = AsyncMock()
    monkeypatch.setattr(sg_mod, "get_or_login_client", vault_client)
    monkeypatch.setattr("app.auth_multitenant.decrypt_driver_password", lambda enc: "decrypted-pwd")
    driver = SimpleNamespace(driver_national_code="0012345678", utcms_password_encrypted="enc")

    await sg_mod._login_driver_client(driver, None, user_context={"role": "master_admin"}, force_reauth=True)

    _, kwargs = vault_client.call_args
    assert kwargs["client_id"] is None
    assert kwargs["force_reauth"] is True


# ── C4: shipping mutation lock ordering ──────────────────────────────────────


@pytest.mark.asyncio
async def test_c4_other_tenant_cannot_squat_shipping_lock(monkeypatch):
    """Ownership failure (404) -> the mutation (completion-claim) lock is never acquired."""
    monkeypatch.setattr(sg_mod.utcms_config, "ALLOW_LIVE_SUBMIT", True)

    async def fake_ownership(job_id, user_context):
        raise _HTTPException(status_code=404, detail="not found")

    monkeypatch.setattr(sg_mod, "_get_job_and_driver", fake_ownership)
    acquire = AsyncMock(return_value="tok")
    release = AsyncMock()
    monkeypatch.setattr(sg_mod, "_acquire_completion_claim", acquire)
    monkeypatch.setattr(sg_mod, "_release_completion_claim", release)

    handler = AsyncMock(return_value={"ok": True})
    wrapped = sg_mod._shipping_mutation_lock(handler)

    with pytest.raises(_HTTPException) as exc_info:
        await wrapped(SimpleNamespace(job_id="job_x"), {"role": "client"})
    assert exc_info.value.status_code == 404
    acquire.assert_not_awaited()
    release.assert_not_awaited()
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_c4_owner_acquires_lock_only_after_ownership_check(monkeypatch):
    """Happy path: ownership check -> completion-claim acquire -> handler -> release."""
    monkeypatch.setattr(sg_mod.utcms_config, "ALLOW_LIVE_SUBMIT", True)
    order: list[str] = []

    async def fake_ownership(job_id, user_context):
        order.append("ownership")
        return ({}, None)

    async def fake_acquire(job_id):
        order.append("acquire")
        assert job_id == "job_x"
        return "tok"

    async def fake_release(job_id, token):
        order.append("release")
        assert job_id == "job_x"
        assert token == "tok"

    async def fake_handler(req, user_context):
        order.append("handler")
        return {"ok": True}

    monkeypatch.setattr(sg_mod, "_get_job_and_driver", fake_ownership)
    monkeypatch.setattr(sg_mod, "_acquire_completion_claim", fake_acquire)
    monkeypatch.setattr(sg_mod, "_release_completion_claim", fake_release)

    wrapped = sg_mod._shipping_mutation_lock(fake_handler)
    result = await wrapped(SimpleNamespace(job_id="job_x"), {"role": "client"})

    assert result == {"ok": True}
    assert order == ["ownership", "acquire", "handler", "release"]


@pytest.mark.asyncio
async def test_c4_lock_contention_still_rejected_for_owner(monkeypatch):
    """The mutex semantics are unchanged: a second owner call (claim held) gets 409."""
    monkeypatch.setattr(sg_mod.utcms_config, "ALLOW_LIVE_SUBMIT", True)

    async def fake_ownership(job_id, user_context):
        return ({}, None)

    monkeypatch.setattr(sg_mod, "_get_job_and_driver", fake_ownership)
    monkeypatch.setattr(sg_mod, "_acquire_completion_claim", AsyncMock(return_value=None))
    monkeypatch.setattr(sg_mod, "_release_completion_claim", AsyncMock())

    wrapped = sg_mod._shipping_mutation_lock(AsyncMock(return_value={"ok": True}))
    with pytest.raises(_HTTPException) as exc_info:
        await wrapped(SimpleNamespace(job_id="job_x"), {"role": "client"})
    assert exc_info.value.status_code == 409


# ── C5: explicit client_id on admin driver creation ──────────────────────────


@pytest.mark.asyncio
async def test_c5_master_admin_without_client_id_rejected():
    """No silent fallback to the first active client: 400 when client_id is absent."""
    with pytest.raises(_HTTPException) as exc_info:
        await DriverService.create_driver({"role": "master_admin"}, _driver_request(), session=None)
    assert exc_info.value.status_code == 400
    assert "client_id" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_c5_master_admin_with_client_id_assigns_named_tenant():
    """An explicit client_id lands the driver in exactly that tenant's pool."""
    session = _mock_session(
        [
            _first(_tenant_client(7)),  # admin client lookup by id
            _one(0),  # driver count
            _first(None),  # no duplicate national code
            _first(None),  # no existing plate
            _one(0),  # plate count
        ]
    )
    resp = await DriverService.create_driver({"role": "master_admin"}, _driver_request(client_id=7), session)

    added = [c.args[0] for c in session.add.call_args_list]
    assert added, "driver must be added to the session"
    assert added[0].client_id == 7
    assert resp is not None


@pytest.mark.asyncio
async def test_c5_master_admin_unknown_client_id_404():
    session = _mock_session([_first(None)])
    with pytest.raises(_HTTPException) as exc_info:
        await DriverService.create_driver({"role": "master_admin"}, _driver_request(client_id=4242), session)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_c5_client_caller_derives_own_tenant():
    """Client callers without client_id get their own tenant; no cross-tenant write."""
    session = _mock_session([_one(0), _first(None), _first(None), _one(0)])
    await DriverService.create_driver({"role": "client", "user": _tenant_client(3)}, _driver_request(), session)
    added = [c.args[0] for c in session.add.call_args_list]
    assert added[0].client_id == 3


@pytest.mark.asyncio
async def test_c5_client_caller_mismatched_client_id_rejected():
    with pytest.raises(_HTTPException) as exc_info:
        await DriverService.create_driver(
            {"role": "client", "user": _tenant_client(3)},
            _driver_request(client_id=9),
            session=None,
        )
    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# C2-followup: queue inline path threads the tenant auth scope
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_c2_queue_inline_path_scopes_auth_state_to_task_tenant():
    """_execute_inline must pass auth_scope=client-{client_id} (never unscoped)."""
    from unittest.mock import patch as _patch

    from app.queue.queue_manager import WaybillQueueManager
    from app.services.task_service import task_service as _ts
    from app.services.waybill_service import waybill_service as _ws

    captured = {}

    async def fake_create(request, auth_scope=None):
        captured["auth_scope"] = auth_scope
        return {"success": True}

    manager = WaybillQueueManager()
    with (
        _patch.object(_ts, "get_payload", new=AsyncMock(return_value={"a": 1})),
        _patch.object(_ts, "get_task_client_id", new=AsyncMock(return_value=7)),
        _patch.object(_ts, "mark_processing", new=AsyncMock()),
        _patch.object(_ts, "mark_success", new=AsyncMock()),
        _patch.object(_ws, "create_waybill_with_map", new=AsyncMock(side_effect=fake_create)),
        _patch("app.schemas.waybill.WaybillMapRequest.model_validate", return_value=MagicMock()),
    ):
        await manager._execute_inline("job_test123", "key")

    assert captured["auth_scope"] == "client-7"
