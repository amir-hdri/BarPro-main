from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models_multitenant import Client, Driver, TaskStatus, WaybillJob
from app.models_rpa import DispatchIntent, DriverRuntimeState
from app.orchestrator.dispatcher_service import DispatcherService
from app.orchestrator.scheduler_service import SchedulerService


@pytest.mark.asyncio
async def test_scheduler_and_dispatcher_flow():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    # Setup database data
    async with async_session() as session:
        client = Client(
            id=1,
            client_code="tenant-t",
            name="Tenant T",
            email="t@example.com",
            hashed_password="hash",
            username="tenant_t",
            full_name="Tenant T Admin",
        )
        session.add(client)

        driver = Driver(
            id=1,
            client_id=1,
            driver_national_code="1234567890",
            full_name="Driver T",
            phone="09123456789",
            utcms_username="drv",
            utcms_password_encrypted="pwd",
        )
        session.add(driver)

        driver_state = DriverRuntimeState(client_id=1, driver_id=1, state="active", active_execution_id=None)
        session.add(driver_state)

        job = WaybillJob(
            job_id="job-123",
            idempotency_key="idem-123",
            client_id=1,
            driver_id=1,
            status=TaskStatus.PENDING.value,
            payload_json={},
            priority=5,
            attempt_count=0,
        )
        session.add(job)
        await session.commit()

    # Run scheduler
    scheduler = SchedulerService()
    with patch("app.orchestrator.scheduler_service.async_session_factory", new=async_session):
        scheduled = await scheduler.run()
        assert scheduled == 1

    # Verify job status is queued and intent exists
    async with async_session() as session:
        job_db = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-123"))).first()
        assert job_db.status == TaskStatus.QUEUED.value

        intent_db = (await session.exec(select(DispatchIntent).where(DispatchIntent.job_id == "job-123"))).first()
        assert intent_db is not None
        assert intent_db.status == "pending"
        assert intent_db.operation == "submit"
        assert intent_db.attempt_no == 1
        assert intent_db.fencing_token == 1
        intent_id = intent_db.intent_id

    # Run dispatcher
    dispatcher = DispatcherService()
    mock_send_task = MagicMock()
    with (
        patch("app.orchestrator.dispatcher_service.async_session_factory", new=async_session),
        patch("app.orchestrator.dispatcher_service.celery_app") as mock_celery,
        patch("app.core.circuit_breaker.get_routed_queue", side_effect=lambda q: q),
    ):
        mock_celery.send_task = mock_send_task
        dispatched = await dispatcher.run()
        assert dispatched == 1
        mock_send_task.assert_called_once_with(
            "barpro.waybill.execute", args=[intent_id], queue="waybill_tasks", priority=5
        )

    # Verify job status is claimed and intent is claimed
    async with async_session() as session:
        job_db = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-123"))).first()
        assert job_db.status == TaskStatus.CLAIMED.value

        intent_db = (await session.exec(select(DispatchIntent).where(DispatchIntent.job_id == "job-123"))).first()
        assert intent_db.status == "claimed"

    await engine.dispose()
