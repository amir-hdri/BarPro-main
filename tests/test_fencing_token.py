import threading
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models_multitenant import Client, TaskStatus, WaybillJob
from app.models_rpa import Execution
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
async def test_fencing_token_mismatch_stops_renewal(async_session):
    async with async_session() as session:
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

        # Fencing token is 1 in database
        execution = Execution(
            execution_id="exec-123",
            intent_id="intent-123",
            job_id="job-1",
            attempt_no=1,
            operation="submit",
            worker_id="w1",
            fencing_token=1,
            lease_expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=10),
            status="running",
        )
        session.add(execution)
        await session.commit()

    # Start renewal with fencing_token = 2 (mismatch!)
    stop_event = threading.Event()
    with patch("app.workers.waybill_worker.async_session_factory", new=async_session):

        def mock_wait(timeout=None):
            time.sleep(0.1)
            return stop_event.is_set()

        with patch.object(stop_event, "wait", side_effect=mock_wait):
            # Run in a separate thread so it doesn't block the test
            t = threading.Thread(target=_renew_lease_sync_loop, args=("exec-123", 2, stop_event), daemon=True)
            t.start()
            t.join(timeout=2)

    # Verify the thread stopped and set stop_event
    assert stop_event.is_set()


@pytest.mark.asyncio
async def test_fencing_token_blocks_parallel_finalize(async_session):
    from app.orchestrator.state_machine import StateTransitionError
    from app.workers.waybill_worker import _assert_still_valid, _finalize_execution

    async with async_session() as session:
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

        # Fencing token is 1 in database
        execution = Execution(
            execution_id="exec-123",
            intent_id="intent-123",
            job_id="job-1",
            attempt_no=1,
            operation="submit",
            worker_id="w1",
            fencing_token=1,
            lease_expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=10),
            status="running",
        )
        session.add(execution)
        await session.commit()

    with patch("app.workers.waybill_worker.async_session_factory", new=async_session):
        # 1. Assert still valid succeeds with correct fencing token and status
        await _assert_still_valid("exec-123", 1)

        # 2. Assert still valid raises StateTransitionError on fencing token mismatch
        with pytest.raises(StateTransitionError):
            await _assert_still_valid("exec-123", 2)

        # 3. Finalize execution with mismatch aborts
        # Let's change database execution status to "orphaned" (like OrphanDetector does)
        async with async_session() as session:
            db_exec = (await session.exec(select(Execution).where(Execution.execution_id == "exec-123"))).first()
            db_exec.status = "orphaned"
            session.add(db_exec)
            await session.commit()

        # Try to finalize the orphaned execution — it should return early without updating status to "completed"
        await _finalize_execution("exec-123", "intent-123", "completed", {"success": True})

        # Verify that execution status remains "orphaned"
        async with async_session() as session:
            db_exec = (await session.exec(select(Execution).where(Execution.execution_id == "exec-123"))).first()
            assert db_exec.status == "orphaned"
