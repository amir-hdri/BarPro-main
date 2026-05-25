import pytest
from httpx import AsyncClient
from sqlmodel import Session
from app.main import app
from app.models_multitenant import Client, ClientStatus
from app.auth_multitenant import create_access_token
from datetime import timedelta

@pytest.mark.asyncio
async def test_driver_limit(db_session: Session):
    # Setup test client with max_drivers = 1
    client = Client(
        client_code="TEST_DRIVER_LIMIT",
        name="Test Limit Client",
        email="limit@test.com",
        hashed_password="hashed_password",
        status=ClientStatus.ACTIVE.value,
        max_drivers=1,
        max_plates=1
    )
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)

    # Generate token
    token = create_access_token(
        data={"sub": client.email, "role": "client", "client_id": client.id},
        expires_delta=timedelta(hours=1)
    )
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(app=app, base_url="http://test") as ac:
        # 1. Add first driver - should succeed
        driver_data_1 = {
            "driver_national_code": "0123456789",
            "full_name": "Driver 1",
            "utcms_username": "driver1_utcms",
            "utcms_password": "password123"
        }
        resp = await ac.post("/api/v1/multitenant/drivers", json=driver_data_1, headers=headers)
        assert resp.status_code == 201

        # 2. Add second driver - should fail with 400
        driver_data_2 = {
            "driver_national_code": "9876543210",
            "full_name": "Driver 2",
            "utcms_username": "driver2_utcms",
            "utcms_password": "password123"
        }
        resp2 = await ac.post("/api/v1/multitenant/drivers", json=driver_data_2, headers=headers)
        assert resp2.status_code == 400
        assert "Driver limit reached" in resp2.json()["detail"]
