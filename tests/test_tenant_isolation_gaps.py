"""Tenant-isolation regression tests for audit GAPs 1-3 (2026-10-01).

GAP-1 (HIGH): GET /api/v1/otp/latest leaked the global OTP to any tenant.
    Fixed: admin-only.
GAP-2 (HIGH): POST /api/v1/otp/submit-manual allowed cross-tenant OTP
    poisoning via req.job_id. Fixed: client must own the job; client
    without job_id is rejected.
GAP-3 (MEDIUM-HIGH): GET /waybill/tasks/{task_id} had no tenant scoping.
    Fixed: clients see only their own job_* IDs; legacy task IDs are
    admin-only.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth_multitenant import get_current_admin, get_current_user_or_admin
from app.core.database import get_session
from app.main import app
from app.models_multitenant import Client, WaybillJob


@pytest.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    session = AsyncSession(engine, expire_on_commit=False)
    for cid, code in ((1, "tenant-a"), (2, "tenant-b")):
        session.add(
            Client(
                id=cid,
                client_code=code,
                name=f"Tenant {code}",
                username=code,
                full_name=f"Tenant {code}",
                email=f"{code}@x.c",
                hashed_password="$2b$12$dummyhashfortestonlyxxxxxxxxxxxxxx",
            )
        )
    # Job owned by tenant B.
    session.add(
        WaybillJob(
            job_id="job_b123",
            client_id=2,
            status="pending",
            payload_json="{}",
            idempotency_key="test-b123",
        )
    )
    # Job owned by tenant A.
    session.add(
        WaybillJob(
            job_id="job_a456",
            client_id=1,
            status="pending",
            payload_json="{}",
            idempotency_key="test-a456",
        )
    )
    await session.commit()
    yield session
    await session.close()
    await engine.dispose()


def _client_for(db_session, role: str, client_id: int | None = None):
    """Build a TestClient with the given auth override."""

    async def _override_user_or_admin():
        if role == "master_admin":
            return {"role": "master_admin", "user": {"username": "admin", "role": "master_admin"}}
        user = await db_session.get(Client, client_id)
        return {"role": "client", "user": user}

    async def _override_admin():
        if role == "master_admin":
            return {"role": "master_admin", "user": {"username": "admin", "role": "master_admin"}}
        raise AssertionError("get_current_admin must not be called for non-admin test")

    # get_current_admin raises 403 for non-admins in real code; emulate it.
    from fastapi import HTTPException

    async def _override_admin_strict():
        if role == "master_admin":
            return {"role": "master_admin", "user": {"username": "admin", "role": "master_admin"}}
        raise HTTPException(status_code=403, detail="Forbidden")

    app.dependency_overrides[get_current_user_or_admin] = _override_user_or_admin
    app.dependency_overrides[get_current_admin] = _override_admin_strict
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def tenant_a_client(db_session):
    yield from _client_for(db_session, "client", client_id=1)


@pytest.fixture
def tenant_b_client(db_session):
    yield from _client_for(db_session, "client", client_id=2)


@pytest.fixture
def admin_client(db_session):
    yield from _client_for(db_session, "master_admin")


@pytest.fixture
def patch_session_factory(db_session, monkeypatch):
    """Route async_session_factory to the in-memory test DB."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _factory():
        yield db_session

    import importlib

    import app.api.routes.otp_forwarder as otp_mod

    task_mod = importlib.import_module("app.services.task_service")

    monkeypatch.setattr(otp_mod, "async_session_factory", _factory)
    monkeypatch.setattr(task_mod, "async_session_factory", _factory)


@pytest.fixture
def mock_redis(monkeypatch):
    """Stub redis_manager.get() so OTP endpoints don't need a live Redis."""
    import app.api.routes.otp_forwarder as otp_mod

    fake = AsyncMock()
    fake.get = AsyncMock(return_value=None)
    fake.set = AsyncMock(return_value=True)
    monkeypatch.setattr(otp_mod.redis_manager, "get", AsyncMock(return_value=fake))
    return fake


# --- GAP-1: GET /otp/latest is admin-only ---


def test_gap1_client_cannot_read_global_otp(tenant_a_client, mock_redis):
    resp = tenant_a_client.get("/api/v1/otp/latest")
    assert resp.status_code == 403, f"expected 403, got {resp.status_code}: {resp.text[:200]}"


def test_gap1_admin_can_read_latest_otp(admin_client, mock_redis):
    resp = admin_client.get("/api/v1/otp/latest")
    # No OTP stored -> "none", not 403. Proves admin passes the gate.
    assert resp.status_code == 200
    assert resp.json()["status"] == "none"


# --- GAP-2: POST /otp/submit-manual verifies job ownership ---


def test_gap2_client_cannot_poison_foreign_job(tenant_a_client, mock_redis, patch_session_factory):
    """Tenant A submits an OTP for tenant B's job -> 404 (not 200)."""
    resp = tenant_a_client.post(
        "/api/v1/otp/submit-manual",
        json={"code": "123456", "job_id": "job_b123"},
    )
    assert resp.status_code == 404, f"expected 404, got {resp.status_code}: {resp.text[:200]}"
    # The poisoned key must not have been written.
    written_keys = [c.args[0] for c in mock_redis.set.await_args_list if c.args and "rpa:otp:job:" in str(c.args[0])]
    assert not any("job_b123" in k for k in written_keys)


def test_gap2_ownership_does_not_bypass_challenge_eligibility(tenant_a_client, mock_redis, patch_session_factory):
    resp = tenant_a_client.post(
        "/api/v1/otp/submit-manual",
        json={"code": "123456", "job_id": "job_a456"},
    )
    assert resp.status_code == 409, f"expected 409, got {resp.status_code}: {resp.text[:200]}"
    mock_redis.set.assert_not_awaited()


def test_gap2_client_without_job_id_rejected(tenant_a_client, mock_redis, patch_session_factory):
    resp = tenant_a_client.post("/api/v1/otp/submit-manual", json={"code": "123456"})
    assert resp.status_code == 403, f"expected 403, got {resp.status_code}: {resp.text[:200]}"


def test_gap2_admin_needs_job_or_recipient_phone(admin_client, mock_redis):
    resp = admin_client.post("/api/v1/otp/submit-manual", json={"code": "123456"})
    assert resp.status_code == 422, f"expected 422, got {resp.status_code}: {resp.text[:200]}"
    mock_redis.set.assert_not_awaited()


# --- GAP-3: GET /waybill/tasks/{task_id} is tenant-scoped ---


def test_gap3_client_cannot_read_foreign_job(tenant_a_client, patch_session_factory):
    """Tenant A reads tenant B's job via legacy route -> 404."""
    resp = tenant_a_client.get("/waybill/tasks/job_b123")
    assert resp.status_code == 404, f"expected 404, got {resp.status_code}: {resp.text[:200]}"


def test_gap3_client_can_read_own_job(tenant_a_client, patch_session_factory):
    resp = tenant_a_client.get("/waybill/tasks/job_a456")
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text[:200]}"


def test_gap3_client_cannot_read_legacy_task_id(tenant_a_client, patch_session_factory):
    """Legacy (non-job_*) task IDs are admin-only -> 404 for clients."""
    resp = tenant_a_client.get("/waybill/tasks/some-legacy-task-id")
    assert resp.status_code == 404, f"expected 404, got {resp.status_code}: {resp.text[:200]}"


def test_gap3_admin_can_read_any_job(admin_client, patch_session_factory):
    resp = admin_client.get("/waybill/tasks/job_b123")
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text[:200]}"
