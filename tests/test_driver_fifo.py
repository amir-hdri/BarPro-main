import pytest
from datetime import datetime, UTC, timedelta
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from unittest.mock import patch, MagicMock

from app.models_multitenant import WaybillJob, TaskStatus, Client, Driver
from app.models_rpa import DispatchIntent, Execution, DriverRuntimeState
from app.orchestrator.scheduler_service import SchedulerService
from app.orchestrator.dispatcher_service import DispatcherService
from app.orchestrator.orphan_detector import OrphanDetector
from app.workers.waybill_worker import _finalize_execution


@pytest.fixture
async def async_session(tmp_path):
    db_file = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False, future=True)
    session_factory = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield session_factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_driver_fifo_serialization(async_session):
    # Setup test data (1 client, 1 driver, 3 waybill jobs for that driver)
    async with async_session() as session:
        client = Client(
            id=1,
            client_code="t1",
            name="Tenant 1",
            email="t1@example.com",
            hashed_password="hash",
            username="t1",
            full_name="Tenant 1 Admin"
        )
        session.add(client)
        
        driver = Driver(
            id=1,
            client_id=1,
            driver_national_code="1234567890",
            full_name="Driver FIFO",
            phone="09123456789",
            utcms_username="drv",
            utcms_password_encrypted="pwd"
        )
        session.add(driver)
        
        # Driver runtime state (initially idle)
        driver_state = DriverRuntimeState(
            client_id=1,
            driver_id=1,
            state="active",
            active_execution_id=None
        )
        session.add(driver_state)
        
        # Enqueue 3 waybill jobs for the same driver
        job1 = WaybillJob(
            job_id="job-1",
            idempotency_key="id-1",
            client_id=1,
            driver_id=1,
            status=TaskStatus.PENDING.value,
            payload_json={},
            priority=5,
            attempt_count=0,
            created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=10)
        )
        job2 = WaybillJob(
            job_id="job-2",
            idempotency_key="id-2",
            client_id=1,
            driver_id=1,
            status=TaskStatus.PENDING.value,
            payload_json={},
            priority=5,
            attempt_count=0,
            created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=5)
        )
        job3 = WaybillJob(
            job_id="job-3",
            idempotency_key="id-3",
            client_id=1,
            driver_id=1,
            status=TaskStatus.PENDING.value,
            payload_json={},
            priority=5,
            attempt_count=0,
            created_at=datetime.now(UTC).replace(tzinfo=None)
        )
        session.add(job1)
        session.add(job2)
        session.add(job3)
        await session.commit()

    # Step 1: Run Scheduler. Since the driver is free, it should schedule only job1 (oldest by created_at)
    scheduler = SchedulerService()
    with patch("app.orchestrator.scheduler_service.async_session_factory", new=async_session):
        scheduled = await scheduler.run()
        # Even though there are 3 due jobs, only 1 should be scheduled because they belong to the same driver
        assert scheduled == 1

    # Verify database state
    async with async_session() as session:
        j1 = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-1"))).first()
        j2 = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-2"))).first()
        j3 = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-3"))).first()
        
        assert j1.status == TaskStatus.QUEUED.value
        assert j2.status == TaskStatus.PENDING.value
        assert j3.status == TaskStatus.PENDING.value
        
        # Check active execution id slot is set
        d_state = (await session.exec(select(DriverRuntimeState).where(DriverRuntimeState.driver_id == 1))).first()
        assert d_state.active_execution_id is not None
        intent_id1 = d_state.active_execution_id
        
        # Dispatch intent check
        intent1 = (await session.exec(select(DispatchIntent).where(DispatchIntent.intent_id == intent_id1))).first()
        assert intent1 is not None
        assert intent1.job_id == "job-1"

    # Step 2: Running Scheduler again should schedule 0 jobs because the driver slot is occupied
    with patch("app.orchestrator.scheduler_service.async_session_factory", new=async_session):
        scheduled = await scheduler.run()
        assert scheduled == 0

    # Step 3: Complete execution for job1. This should free the slot
    # Simulating creating execution slot and then finalizing it
    async with async_session() as session:
        execution = Execution(
            execution_id="exec-1",
            intent_id=intent_id1,
            job_id="job-1",
            attempt_no=1,
            operation="submit",
            worker_id="w1",
            fencing_token=1,
            lease_expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=90),
            status="running"
        )
        session.add(execution)
        await session.commit()

    with patch("app.workers.waybill_worker.async_session_factory", new=async_session):
        await _finalize_execution("exec-1", intent_id1, "completed", {"status": "success"})

    # Verify slot is freed
    async with async_session() as session:
        d_state = (await session.exec(select(DriverRuntimeState).where(DriverRuntimeState.driver_id == 1))).first()
        assert d_state.active_execution_id is None

    # Step 4: Run Scheduler again. Now the slot is free, so job2 should be scheduled
    with patch("app.orchestrator.scheduler_service.async_session_factory", new=async_session):
        scheduled = await scheduler.run()
        assert scheduled == 1

    async with async_session() as session:
        j2 = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-2"))).first()
        assert j2.status == TaskStatus.QUEUED.value
        
        d_state = (await session.exec(select(DriverRuntimeState).where(DriverRuntimeState.driver_id == 1))).first()
        assert d_state.active_execution_id is not None
        intent_id2 = d_state.active_execution_id

    # Step 5: Simulate job2 execution stalls/orphaned. Expire the lease and run OrphanDetector
    async with async_session() as session:
        # Create execution expired 10s ago
        expired = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=10)
        execution2 = Execution(
            execution_id="exec-2",
            intent_id=intent_id2,
            job_id="job-2",
            attempt_no=1,
            operation="submit",
            worker_id="w1",
            fencing_token=1,
            lease_expires_at=expired,
            status="running"
        )
        session.add(execution2)
        await session.commit()

    detector = OrphanDetector()
    with patch("app.orchestrator.orphan_detector.async_session_factory", new=async_session):
        detected = await detector.run()
        assert detected == 1

    # Verify slot is freed on orphanage
    async with async_session() as session:
        d_state = (await session.exec(select(DriverRuntimeState).where(DriverRuntimeState.driver_id == 1))).first()
        assert d_state.active_execution_id is None
        
        j2 = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-2"))).first()
        assert j2.status == TaskStatus.UNKNOWN.value

    # Step 6: Run Scheduler again. Slot is free, so job3 should be scheduled
    with patch("app.orchestrator.scheduler_service.async_session_factory", new=async_session):
        scheduled = await scheduler.run()
        assert scheduled == 1

    async with async_session() as session:
        j3 = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-3"))).first()
        assert j3.status == TaskStatus.QUEUED.value
