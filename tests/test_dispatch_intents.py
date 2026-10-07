import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import circuit_breaker
from app.models_multitenant import Client, Driver, TaskStatus, WaybillJob
from app.models_rpa import DispatchIntent, DriverRuntimeState
from app.orchestrator.dispatcher_service import DispatcherService
from app.orchestrator.scheduler_service import SchedulerService


@pytest.mark.parametrize(
    "blocking,expected_queues",
    [
        ("none", ["waybill_tasks_2", "waybill_tasks_3", "waybill_tasks_1"]),
        ("selected", ["waybill_tasks_2", "waybill_tasks_1", "waybill_tasks_3"]),
        ("all", ["waybill_tasks_2"]),
    ],
)
async def test_dispatch_batch_selects_each_worker_with_current_block_state(monkeypatch, blocking, expected_queues):
    """Exercise the actual async router once per persisted intent, inside its cache TTL."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        async with session_factory() as session:
            session.add(
                Client(
                    id=1,
                    client_code="routing-tenant",
                    name="Routing tenant",
                    email="routing@example.invalid",
                    username="routing-tenant",
                    full_name="Routing tenant",
                    hashed_password="unused",
                )
            )
            for index in range(3):
                session.add(
                    WaybillJob(
                        job_id=f"routing-job-{index}",
                        idempotency_key=f"routing-job-{index}",
                        client_id=1,
                        status="queued",
                        payload_json={},
                    )
                )
                session.add(
                    DispatchIntent(
                        intent_id=f"routing-intent-{index}",
                        job_id=f"routing-job-{index}",
                        client_id=1,
                        operation="submit",
                        attempt_no=1,
                        fencing_token=1,
                        status="pending",
                    )
                )
            await session.commit()

        blocked = set()
        redis = AsyncMock()
        redis.exists.side_effect = lambda key: int(key.rsplit(":", 1)[1]) in blocked
        redis.incr.side_effect = [1, 2, 3]
        monkeypatch.setattr(circuit_breaker.redis_manager, "get", AsyncMock(return_value=redis))
        monkeypatch.setattr(circuit_breaker, "get_available_ip_indices", lambda: [1, 2, 3])
        monkeypatch.setattr(circuit_breaker, "_get_known_ip_indices", AsyncMock(return_value={1, 2, 3}))
        monkeypatch.setattr(circuit_breaker, "_get_unavailable_ip_indices", AsyncMock(return_value=set()))
        monkeypatch.setattr(circuit_breaker, "_ip_index_cache", 2)
        monkeypatch.setattr(circuit_breaker, "_ip_index_cache_expires", time.monotonic() + 60)

        queues = []

        def send_task(_name, *, args, queue, priority):
            queues.append(queue)
            if len(queues) == 1:
                if blocking == "selected":
                    blocked.add(int(queue.rsplit("_", 1)[1]))
                elif blocking == "all":
                    blocked.update({1, 2, 3})

        with (
            patch("app.orchestrator.dispatcher_service.async_session_factory", session_factory),
            patch("app.orchestrator.dispatcher_service.celery_app") as celery,
        ):
            celery.send_task.side_effect = send_task
            assert await DispatcherService().run() == len(expected_queues)
        assert queues == expected_queues
        assert redis.incr.await_count == len(expected_queues)
        if blocking == "all":
            async with session_factory() as session:
                jobs = (await session.exec(select(WaybillJob))).all()
                assert sorted(job.status for job in jobs) == ["claimed", "waiting_retry", "waiting_retry"]
    finally:
        await engine.dispose()


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
        patch("app.core.circuit_breaker.get_routed_queue_async", side_effect=lambda q, **kwargs: q),
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
        intent_db = (await session.exec(select(DispatchIntent).where(DispatchIntent.job_id == "job-skip-1"))).first()
        assert intent_db is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_reconciliation_audit_intent_dispatched_not_expired_as_unknown_operation():
    """A pending reconciliation_audit intent for a tracking-received job must be
    claimed and routed to the audit worker task — NOT expired as
    unknown_operation. The job keeps its UNKNOWN status (unknown -> claimed
    is not a legal transition); the audit worker drives it."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session() as session:
        session.add(
            Client(
                id=1,
                client_code="tenant-audit",
                name="Tenant Audit",
                email="audit@example.com",
                hashed_password="x",
                username="tenant_audit",
                full_name="Tenant Audit Admin",
            )
        )
        session.add(
            Driver(
                id=1,
                client_id=1,
                driver_national_code="1234567890",
                full_name="Driver Audit",
                phone="09123456789",
                utcms_username="drv",
                utcms_password_encrypted="pwd",
            )
        )
        session.add(DriverRuntimeState(client_id=1, driver_id=1, state="active", active_execution_id=None))

        session.add(
            WaybillJob(
                job_id="job-audit-1",
                idempotency_key="idem-audit-1",
                client_id=1,
                driver_id=1,
                status=TaskStatus.UNKNOWN.value,
                mutation_status="dispatched",
                payload_json={},
                priority=5,
                attempt_count=0,
                result_json={
                    "tracking_code": "UTC-AUDIT-1",
                    "confirmation_status": "tracking_received",
                    "operator_acknowledged": True,
                },
            )
        )
        session.add(
            DispatchIntent(
                intent_id="intent-audit-1",
                client_id=1,
                job_id="job-audit-1",
                attempt_no=1,
                operation="reconciliation_audit",
                fencing_token=7,
                status="pending",
            )
        )
        await session.commit()

    dispatcher = DispatcherService()
    mock_send_task = MagicMock()
    with (
        patch("app.orchestrator.dispatcher_service.async_session_factory", new=async_session),
        patch("app.orchestrator.dispatcher_service.celery_app") as mock_celery,
        patch("app.core.circuit_breaker.get_routed_queue_async", side_effect=lambda q, **kwargs: q),
    ):
        mock_celery.send_task = mock_send_task
        dispatched = await dispatcher.run()
        assert dispatched == 1
        mock_send_task.assert_called_once_with(
            "barpro.waybill.reconcile_audit", args=["intent-audit-1"], queue="reconciliation_tasks", priority=5
        )

    async with async_session() as session:
        intent_db = (
            await session.exec(select(DispatchIntent).where(DispatchIntent.intent_id == "intent-audit-1"))
        ).first()
        assert intent_db is not None
        assert intent_db.status == "claimed", intent_db.status

        job_db = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-audit-1"))).first()
        assert job_db is not None
        # The dispatcher must not force unknown -> claimed; the audit worker
        # drives unknown -> reconciling itself.
        assert job_db.status == TaskStatus.UNKNOWN.value

    await engine.dispose()
