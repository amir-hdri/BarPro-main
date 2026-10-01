"""Cross-tenant isolation tests: resource-exists-but-owned-by-B behavior.

When tenant A requests a resource belonging to tenant B, the API must return
404 (indistinguishable from "does not exist") — never 500, and never a signal
that leaks the resource's existence or owner. Previously TenantIsolationError
had no exception handler and bubbled up as a 500.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth_multitenant import get_current_user_or_admin
from app.core.database import get_session
from app.main import app
from app.models_multitenant import Client, Driver


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
    session.add(
        Client(id=1, client_code="tenant-a", name="Tenant A", username="a",
               full_name="Tenant A", email="a@x.c", hashed_password="x")
    )
    session.add(
        Client(id=2, client_code="tenant-b", name="Tenant B", username="b",
               full_name="Tenant B", email="b@x.c", hashed_password="x")
    )
    session.add(
        Driver(id=1, client_id=2, driver_national_code="1", full_name="B Driver",
               utcms_username="u", utcms_password_encrypted="e", encrypted_password="x")
    )
    await session.commit()
    yield session
    await session.close()
    await engine.dispose()


@pytest.fixture
async def api_client(db_session):
    tenant_a = await db_session.get(Client, 1)
    app.dependency_overrides[get_current_user_or_admin] = lambda: {
        "role": "client",
        "user": tenant_a,
    }
    app.dependency_overrides[get_session] = lambda: db_session
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def test_cross_tenant_driver_returns_404_not_500(api_client):
    """Tenant A GETs tenant B's driver → 404, no existence/oracle leak."""
    response = api_client.get("/api/v1/drivers/1")
    assert response.status_code == 404, (
        f"expected 404 for cross-tenant access, got {response.status_code}: {response.text[:200]}"
    )
    body = response.json()
    assert body.get("error") == "NOT_FOUND"


def test_cross_tenant_driver_does_not_leak_owner(api_client):
    """The 404 body must not name the owning tenant or the real reason."""
    response = api_client.get("/api/v1/drivers/1")
    assert response.status_code == 404
    text = response.text.lower()
    assert "tenant-b" not in text
    assert "client 2" not in text
    assert "isolation" not in text


def test_nonexistent_driver_same_404_shape(api_client):
    """Nonexistent IDs return 404 too — same status, no differential oracle."""
    response = api_client.get("/api/v1/drivers/99999")
    assert response.status_code == 404
