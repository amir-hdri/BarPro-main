from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models_multitenant import Client, Driver, TaskStatus, WaybillJob
from app.models_rpa import DispatchIntent, DriverRuntimeState
from app.workers.waybill_worker import execute_dispatched_intent

COMPLETE_PAYLOAD = {
    "sender": {"name": "علی فلاح"},
    "receiver": {"name": "احمد مومنی"},
    "origin": {"province": "هرمزگان", "city": "میناب", "address": "بلوار خلیج فارس"},
    "destination": {"province": "هرمزگان", "city": "میناب", "address": "طالوار"},
    "cargo": {"type": "مصالح", "packaging": "فله", "weight": "15", "value": "35000000"},
    "vehicle": {"driver_national_code": "0084575948", "plate": "79ع989ایران84"},
}


@pytest.fixture
async def async_session(tmp_path):
    db_file = tmp_path / "test_chaos.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False, future=True)
    session_factory = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield session_factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_redis_unavailable_fail_closed(async_session):
    # Setup database with client, driver, and a claimed job ready to run
    async with async_session() as session:
        client = Client(
            id=1,
            client_code="t1",
            name="Tenant 1",
            email="t1@example.com",
            hashed_password="hash",
            username="t1",
            full_name="Tenant 1 Admin",
        )
        session.add(client)

        driver = Driver(
            id=1,
            client_id=1,
            driver_national_code="0084575948",
            full_name="Chaos Driver",
            phone="09123456789",
            utcms_username="drv",
            utcms_password_encrypted="pwd",
        )
        session.add(driver)

        driver_state = DriverRuntimeState(client_id=1, driver_id=1, state="active", active_execution_id="intent-1")
        session.add(driver_state)

        intent = DispatchIntent(
            intent_id="intent-1",
            client_id=1,
            job_id="job-1",
            attempt_no=1,
            operation="submit",
            fencing_token=1,
            status="claimed",
        )
        session.add(intent)

        job = WaybillJob(
            job_id="job-1",
            idempotency_key="id-1",
            client_id=1,
            driver_id=1,
            status=TaskStatus.CLAIMED.value,
            payload_json=COMPLETE_PAYLOAD,
            priority=5,
            attempt_count=0,
        )
        session.add(job)
        await session.commit()

    # Simulate Redis connection failure in session_vault by mocking redis_manager
    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 0
    mock_redis.get.side_effect = Exception("Redis connection refused")

    with (
        patch("app.workers.waybill_worker.async_session_factory", new=async_session),
        patch("app.core.redis.redis_manager.get", return_value=mock_redis),
        patch("app.workers.waybill_worker.decrypt_driver_password", return_value="pwd"),
        patch("app.workers.waybill_worker.rpa_runtime.acquire_lock", return_value=True),
        patch("app.workers.waybill_worker.rpa_runtime.release_lock"),
        patch("app.automation.worker_proxy.get_worker_proxy_url", return_value="http://mock-proxy:3128"),
    ):

        # Execute the worker task
        result = execute_dispatched_intent.apply(args=("intent-1",)).get()

        assert result["status"] == TaskStatus.WAITING_RETRY.value
        assert result["error_category"] == "session_vault_error"

    # Verify task database state changed to WAITING_RETRY and locks were released
    async with async_session() as session:
        j = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-1"))).first()
        print("JOB STATUS IN DB:", j.status)
        print("JOB LAST ERROR IN DB:", j.last_error)
        print("JOB ERROR CAT IN DB:", j.error_category)
        assert j.status == TaskStatus.WAITING_RETRY.value
        assert "Redis session vault check failed" in j.last_error
        assert j.error_category == "session_vault_error"

        d_state = (await session.exec(select(DriverRuntimeState).where(DriverRuntimeState.driver_id == 1))).first()
        print("DRIVER AUTH LOCK OWNER IN DB:", d_state.auth_lock_owner)
        # Verify db locks ownership were cleared on finalization
        assert d_state.auth_lock_owner is None
