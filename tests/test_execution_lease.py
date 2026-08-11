import threading
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models_multitenant import Client, TaskStatus, WaybillJob
from app.models_rpa import DispatchIntent, Execution
from app.orchestrator.orphan_detector import OrphanDetector
from app.workers.waybill_worker import _renew_lease_sync_loop


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
async def test_lease_renewal_loop(async_session):
    async with async_session() as session:
        # Create execution row with near expiry
        now = datetime.now(UTC).replace(tzinfo=None)
        expiry = now + timedelta(seconds=10)

        # Add Client and WaybillJob
        client = Client(
            id=1,
            client_code="c1",
            name="C1",
            email="c1@example.com",
            hashed_password="h",
            username="c1",
            full_name="C1",
        )
        session.add(client)
        job = WaybillJob(
            job_id="job-1", idempotency_key="id-1", client_id=1, status=TaskStatus.RUNNING.value, payload_json={}
        )
        session.add(job)

        execution = Execution(
            execution_id="exec-123",
            intent_id="intent-123",
            job_id="job-1",
            attempt_no=1,
            operation="submit",
            worker_id="w1",
            fencing_token=1,
            lease_expires_at=expiry,
            status="running",
        )
        session.add(execution)
        await session.commit()

    # Start renewal loop in a thread
    stop_event = threading.Event()
    with patch("app.workers.waybill_worker.async_session_factory", new=async_session):
        # We patch wait to run exactly once
        call_count = 0

        def mock_wait(timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return False
            return True

        with patch.object(stop_event, "wait", side_effect=mock_wait):
            _renew_lease_sync_loop("exec-123", 1, stop_event)

    # Verify lease was extended
    async with async_session() as session:
        exec_db = (await session.exec(select(Execution).where(Execution.execution_id == "exec-123"))).first()
        assert exec_db.lease_expires_at > expiry


@pytest.mark.asyncio
async def test_orphan_detector(async_session):
    async with async_session() as session:
        # Setup Client, WaybillJob, and expired Execution
        client = Client(
            id=1,
            client_code="c1",
            name="C1",
            email="c1@example.com",
            hashed_password="h",
            username="c1",
            full_name="C1",
        )
        session.add(client)

        job = WaybillJob(
            job_id="job-stale",
            idempotency_key="id-stale",
            client_id=1,
            status=TaskStatus.RUNNING.value,
            payload_json={},
        )
        session.add(job)

        expired = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=10)
        execution = Execution(
            execution_id="exec-stale",
            intent_id="intent-stale",
            job_id="job-stale",
            attempt_no=1,
            operation="submit",
            worker_id="w1",
            fencing_token=1,
            lease_expires_at=expired,
            status="running",
        )
        session.add(execution)
        await session.commit()

    # Run OrphanDetector
    detector = OrphanDetector()
    with patch("app.orchestrator.orphan_detector.async_session_factory", new=async_session):
        detected = await detector.run()
        assert detected == 1

    # Verify execution is orphaned, job status is unknown, and reconciliation intent is created
    async with async_session() as session:
        exec_db = (await session.exec(select(Execution).where(Execution.execution_id == "exec-stale"))).first()
        assert exec_db.status == "orphaned"

        job_db = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-stale"))).first()
        assert job_db.status == TaskStatus.UNKNOWN.value

        reconcile_intent = (
            await session.exec(
                select(DispatchIntent)
                .where(DispatchIntent.job_id == "job-stale")
                .where(DispatchIntent.operation == "reconciliation")
            )
        ).first()
        assert reconcile_intent is not None
        assert reconcile_intent.status == "pending"
