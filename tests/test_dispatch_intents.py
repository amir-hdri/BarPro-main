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


@pytest.mark.asyncio
async def test_submit_intent_not_dispatched_when_tracking_code_persisted():
    """A job with a persisted tracking code must never be submit-dispatched.

    Pre-existing pending submit and stale reconciliation intents for a
    tracking-received job are cancelled; no celery task is sent.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session() as session:
        client = Client(
            id=1,
            client_code="tenant-ack",
            name="Tenant Ack",
            email="ack@example.com",
            hashed_password="hash",
            username="tenant_ack",
            full_name="Tenant Ack Admin",
        )
        session.add(client)
        driver = Driver(
            id=1,
            client_id=1,
            driver_national_code="1234567890",
            full_name="Driver Ack",
            phone="09123456789",
            utcms_username="drv",
            utcms_password_encrypted="pwd",
        )
        session.add(driver)
        session.add(DriverRuntimeState(client_id=1, driver_id=1, state="active", active_execution_id=None))

        job = WaybillJob(
            job_id="job-ack-1",
            idempotency_key="idem-ack-1",
            client_id=1,
            driver_id=1,
            status=TaskStatus.QUEUED.value,
            payload_json={},
            priority=5,
            attempt_count=0,
            result_json={
                "tracking_code": "UTC-ACK-9",
                "confirmation_status": "tracking_received",
                "operator_acknowledged": True,
            },
        )
        session.add(job)
        submit_intent = DispatchIntent(
            intent_id="intent-submit-ack",
            client_id=1,
            job_id="job-ack-1",
            attempt_no=1,
            operation="submit",
            fencing_token=1,
            status="pending",
        )
        recon_intent = DispatchIntent(
            intent_id="intent-recon-ack",
            client_id=1,
            job_id="job-ack-1",
            attempt_no=1,
            operation="reconciliation",
            fencing_token=1,
            status="pending",
        )
        session.add(submit_intent)
        session.add(recon_intent)
        await session.commit()

    dispatcher = DispatcherService()
    mock_send_task = MagicMock()
    with (
        patch("app.orchestrator.dispatcher_service.async_session_factory", new=async_session),
        patch("app.orchestrator.dispatcher_service.celery_app") as mock_celery,
    ):
        mock_celery.send_task = mock_send_task
        dispatched = await dispatcher.run()
        assert dispatched == 0
        mock_send_task.assert_not_called()

    async with async_session() as session:
        for intent_id in ("intent-submit-ack", "intent-recon-ack"):
            intent_db = (
                await session.exec(select(DispatchIntent).where(DispatchIntent.intent_id == intent_id))
            ).first()
            assert intent_db is not None
            assert intent_db.status == "cancelled", intent_db.status

    await engine.dispose()


@pytest.mark.asyncio
async def test_scheduler_skips_tracking_acknowledged_job():
    """The scheduler never creates a submit intent for a tracking-received job."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session() as session:
        client = Client(
            id=1,
            client_code="tenant-skip",
            name="Tenant Skip",
            email="skip@example.com",
            hashed_password="hash",
            username="tenant_skip",
            full_name="Tenant Skip Admin",
        )
        session.add(client)
        driver = Driver(
            id=1,
            client_id=1,
            driver_national_code="1234567890",
            full_name="Driver Skip",
            phone="09123456789",
            utcms_username="drv",
            utcms_password_encrypted="pwd",
        )
        session.add(driver)
        session.add(DriverRuntimeState(client_id=1, driver_id=1, state="active", active_execution_id=None))

        job = WaybillJob(
            job_id="job-skip-1",
            idempotency_key="idem-skip-1",
            client_id=1,
            driver_id=1,
            status=TaskStatus.WAITING_RETRY.value,
            payload_json={},
            priority=5,
            attempt_count=0,
            next_retry_at=None,
            submit_after=None,
            result_json={
                "tracking_code": "UTC-SKIP-1",
                "confirmation_status": "tracking_received",
                "operator_acknowledged": True,
            },
        )
        session.add(job)
        await session.commit()

    scheduler = SchedulerService()
    with patch("app.orchestrator.scheduler_service.async_session_factory", new=async_session):
        scheduled = await scheduler.run()
        assert scheduled == 0

    async with async_session() as session:
        job_db = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-skip-1"))).first()
        assert job_db.status == TaskStatus.WAITING_RETRY.value  # untouched
        intent_db = (
            await session.exec(select(DispatchIntent).where(DispatchIntent.job_id == "job-skip-1"))
        ).first()
        assert intent_db is None

    await engine.dispose()
