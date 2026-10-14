"""Tests for automatic driver activation state machine."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models_multitenant import Client, ClientStatus, Driver, DriverStatus
from app.services.driver_service import DriverService


@pytest.fixture
async def sqlite_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async_session = AsyncSession(engine, expire_on_commit=False)
    try:
        # Create a test client
        client = Client(
            id=1,
            client_code="CLIENT-TEST",
            username="testclient",
            full_name="مدیر تست",
            name="Test Client",
            email="client@test.ir",
            phone="09121111111",
            hashed_password="hashed_test_password",
            status=ClientStatus.ACTIVE.value,
        )
        async_session.add(client)
        await async_session.commit()
        yield async_session
    finally:
        await async_session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_pending_driver_incomplete_remains_pending(sqlite_session: AsyncSession):
    driver = Driver(
        id=1,
        client_id=1,
        driver_national_code="0081234567",
        full_name="علی محمدی",
        phone="09121234567",
        utcms_username="user1",
        utcms_password_encrypted="enc_pass",
        status=DriverStatus.PENDING.value,
        metadata_json={},
    )
    sqlite_session.add(driver)
    await sqlite_session.commit()

    # With no OTP verified and no permissions in Redis/metadata
    with patch("app.core.redis_client.redis_manager.get", new_callable=AsyncMock) as mock_redis:
        mock_redis.return_value = None
        activated = await DriverService.check_and_auto_activate_driver(driver_id=driver.id, session=sqlite_session)
        assert activated is False

    refreshed = (await sqlite_session.exec(select(Driver).where(Driver.id == driver.id))).first()
    assert refreshed is not None
    assert refreshed.status == DriverStatus.PENDING.value


@pytest.mark.asyncio
async def test_pending_driver_completes_activation(sqlite_session: AsyncSession):
    driver = Driver(
        id=2,
        client_id=1,
        driver_national_code="0087654321",
        full_name="رضا حسینی",
        phone="09303653432",
        utcms_username="user2",
        utcms_password_encrypted="enc_pass",
        status=DriverStatus.PENDING.value,
        metadata_json={"otp_verified": True},
    )
    sqlite_session.add(driver)
    await sqlite_session.commit()

    fake_redis_data = '{"permissions": {"receive_sms": true, "location": true}, "last_seen": 1000}'

    class FakeRedis:
        async def get(self, key):
            if "rpa:forwarder:connected:" in key:
                return fake_redis_data
            return None

    with (
        patch("app.core.redis_client.redis_manager.get", new_callable=AsyncMock) as mock_redis,
        patch("app.orchestrator.alert_manager.admin_alert_service.create_alert", new_callable=AsyncMock) as mock_alert,
        patch("app.realtime.events.event_hub.publish", new_callable=AsyncMock) as mock_publish,
    ):
        mock_redis.return_value = FakeRedis()
        activated = await DriverService.check_and_auto_activate_driver(driver_id=driver.id, session=sqlite_session)
        assert activated is True

        # Check alert and event were dispatched
        assert mock_alert.called
        assert mock_publish.called
        call_kwargs = mock_alert.call_args[1]
        assert call_kwargs["category"] == "driver_activation"
        assert "رضا حسینی" in call_kwargs["message"]
        assert "09303653432" in call_kwargs["message"]

    refreshed = (await sqlite_session.exec(select(Driver).where(Driver.id == driver.id))).first()
    assert refreshed is not None
    assert refreshed.status == DriverStatus.ACTIVE.value
    assert refreshed.runtime_status == DriverStatus.READY.value
