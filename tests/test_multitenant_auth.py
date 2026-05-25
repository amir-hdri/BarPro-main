from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel


from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth_multitenant import create_access_token, get_current_client
from app.models_multitenant import Client


@pytest.mark.asyncio
async def test_get_current_client_uses_async_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session() as session:
        client = Client(
            client_code="tenant-auth",
            name="Tenant Auth",
            email="tenant-auth@example.com",
            hashed_password="hash",
        )
        session.add(client)
        await session.commit()
        await session.refresh(client)

        with patch("app.auth_multitenant.utcms_config.JWT_SECRET", "test-secret"), patch(
            "app.auth_multitenant.utcms_config.JWT_ALGORITHM", "HS256"
        ):
            token = create_access_token(client.id, client.client_code, client.email)
            credentials = type("Creds", (), {"credentials": token})()
            resolved = await get_current_client(credentials=credentials, session=session)
            assert resolved.id == client.id
            assert resolved.client_code == client.client_code

    await engine.dispose()
