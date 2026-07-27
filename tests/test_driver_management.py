import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth_multitenant import create_access_token
from app.core.database import get_session
from app.main import app
from app.models_multitenant import Client, ClientStatus


@pytest.mark.asyncio
async def test_driver_limit():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session() as session:
        # Setup test client with max_drivers = 1
        client = Client(
            client_code="TEST_DRIVER_LIMIT",
            name="Test Limit Client",
            email="limit@test.com",
            hashed_password="hashed_password",
            status=ClientStatus.ACTIVE.value,
            username="testlimit",
            full_name="Test Limit Client",
            max_drivers=1,
            max_plates=1,
        )
        session.add(client)
        await session.commit()
        await session.refresh(client)

        # Generate token
        token = create_access_token(client.id, client.client_code, client.email)
        headers = {"Authorization": f"Bearer {token}"}

        async def _override_get_session():
            yield session

        app.dependency_overrides[get_session] = _override_get_session

        from fastapi.testclient import TestClient

        with TestClient(app) as ac:
            # 1. Add first driver - should succeed
            driver_data_1 = {
                "driver_national_code": "0123456789",
                "full_name": "Driver 1",
                "phone": "09123456789",
                "utcms_username": "driver1_utcms",
                "utcms_password": "password123",
            }
            resp = ac.post("/api/v1/drivers", json=driver_data_1, headers=headers)
            assert resp.status_code == 201

            # 2. Add second driver - should fail with 400
            driver_data_2 = {
                "driver_national_code": "9876543210",
                "full_name": "Driver 2",
                "phone": "09123456789",
                "utcms_username": "driver2_utcms",
                "utcms_password": "password123",
            }
            resp2 = ac.post("/api/v1/drivers", json=driver_data_2, headers=headers)
            assert resp2.status_code == 400
            assert "Driver limit reached" in resp2.json()["message"]

        # Clean up dependency overrides
        app.dependency_overrides.clear()

    await engine.dispose()
