from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth_multitenant import get_current_admin
from app.schemas.multitenant import AdminClientUpdateRequest, AdminLoginRequest, ClientRegisterRequest
from app.services.multitenant_service import ClientService


@pytest.mark.asyncio
async def test_master_admin_login_and_token_resolution():
    with patch("app.auth_multitenant.utcms_config.MASTER_ADMIN_USERNAME", "master_bar"), patch(
        "app.auth_multitenant.utcms_config.MASTER_ADMIN_PASSWORD", "master_bar"
    ), patch("app.auth_multitenant.utcms_config.JWT_SECRET", "test-secret"), patch(
        "app.auth_multitenant.utcms_config.JWT_ALGORITHM", "HS256"
    ):
        payload = await ClientService.login_master_admin(
            AdminLoginRequest(username="master_bar", password="master_bar")
        )
        credentials = type("Creds", (), {"credentials": payload["access_token"]})()
        admin = await get_current_admin(credentials=credentials)
        assert admin["username"] == "master_bar"
        assert admin["role"] == "master_admin"


@pytest.mark.asyncio
async def test_master_admin_can_create_update_and_delete_clients():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session() as session:
        created = await ClientService.register_client(
            ClientRegisterRequest(
                client_code="tenant-admin",
                name="Tenant Admin",
                email="tenant-admin@example.com",
                phone="09120000000",
                password="strongpass123",
            ),
            session,
        )
        assert created.client_code == "tenant-admin"

        clients = await ClientService.list_clients(session)
        assert len(clients) == 1
        assert clients[0].email == "tenant-admin@example.com"

        updated = await ClientService.update_client_by_admin(
            clients[0].id,
            AdminClientUpdateRequest(
                name="Tenant Admin Updated",
                email="tenant-admin-updated@example.com",
                max_drivers=25,
                password="newstrongpass123",
            ),
            session,
        )
        assert updated.name == "Tenant Admin Updated"
        assert updated.email == "tenant-admin-updated@example.com"

        await ClientService.delete_client_by_admin(clients[0].id, session)
        remaining = await ClientService.list_clients(session)
        assert remaining == []

    await engine.dispose()


@pytest.mark.asyncio
async def test_master_admin_list_clients_supports_search_filter_and_pagination():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session() as session:
        for client_code, name, email, status in [
            ("tenant-a", "Alpha Logistics", "alpha@example.com", "active"),
            ("tenant-b", "Beta Movers", "beta@example.com", "suspended"),
            ("tenant-c", "Cargo Gamma", "gamma@example.com", "active"),
        ]:
            created = await ClientService.register_client(
                ClientRegisterRequest(
                    client_code=client_code,
                    name=name,
                    email=email,
                    phone="09120000000",
                    password="strongpass123",
                ),
                session,
            )
            if status != "active":
                await ClientService.update_client_by_admin(
                    created.id,
                    AdminClientUpdateRequest(status=status),
                    session,
                )

        filtered = await ClientService.list_clients(session, q="beta", status_filter="suspended", page=1, page_size=10)
        assert len(filtered) == 1
        assert filtered[0].client_code == "tenant-b"

        paged = await ClientService.list_clients(session, page=2, page_size=1)
        assert len(paged) == 1

    await engine.dispose()
