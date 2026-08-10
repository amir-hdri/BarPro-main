"""Cancellation / DispatchIntent lifecycle tests (no live UTCMS/portal).

Verifies:
- Soft-cancel of queued / claimed-without-execution jobs cancels their
  pending/claimed intents and releases the driver slot.
- Running jobs with a live Execution return HTTP 409 and are untouched.
- The dispatcher never claims an intent belonging to a cancelled job.
- Terminal jobs carrying child records are archived, never hard-deleted.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models_multitenant import Client, Driver, TaskStatus, WaybillJob, WaybillTaskLog
from app.models_rpa import DispatchIntent, DriverRuntimeState, Execution
from app.orchestrator.dispatcher_service import DispatcherService
from app.services.waybill_job_service import WaybillJobService

_created_engines = []


@pytest.fixture(autouse=True)
async def _dispose_created_engines():
    yield
    while _created_engines:
        await _created_engines.pop().dispose()


def _utcnow_naive():
    return datetime.now(UTC).replace(tzinfo=None)


async def _make_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    _created_engines.append(engine)
    sf = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine, sf


async def _seed(
    sf, *, job_status=TaskStatus.QUEUED.value, intent_status="pending", with_runtime_state=True, live_execution=False
):
    intent_id = "intent-0001"
    async with sf() as session:
        session.add(
            Client(
                id=1,
                client_code="tenant-c",
                name="Tenant C",
                email="c@example.com",
                hashed_password="hash",
                username="tenant_c",
                full_name="Tenant C Admin",
            )
        )
        session.add(
            Driver(
                id=1,
                client_id=1,
                driver_national_code="1234567890",
                full_name="Driver C",
                phone="09123456789",
                utcms_username="drv",
                utcms_password_encrypted="pwd",
                status="active",
            )
        )
        if with_runtime_state:
            session.add(
                DriverRuntimeState(
                    client_id=1,
                    driver_id=1,
                    state="submitting",
                    active_execution_id=intent_id,
                )
            )
        session.add(
            WaybillJob(
                job_id="job-0001",
                idempotency_key="idem-0001",
                client_id=1,
                driver_id=1,
                status=job_status,
                payload_json={},
                priority=5,
                attempt_count=1,
            )
        )
        session.add(
            DispatchIntent(
                intent_id=intent_id,
                client_id=1,
                job_id="job-0001",
                attempt_no=1,
                operation="submit",
                fencing_token=1,
                status=intent_status,
            )
        )
        if live_execution:
            session.add(
                Execution(
                    execution_id="exec-1",
                    intent_id=intent_id,
                    job_id="job-0001",
                    attempt_no=1,
                    operation="submit",
                    worker_id="w1",
                    fencing_token=1,
                    lease_expires_at=_utcnow_naive(),
                    status="running",
                )
            )
        await session.commit()
    return intent_id


async def _get_client(sf):
    async with sf() as session:
        return (await session.exec(select(Client).where(Client.id == 1))).first()


async def _reload(sf):
    async with sf() as session:
        job = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-0001"))).first()
        intent = (await session.exec(select(DispatchIntent).where(DispatchIntent.job_id == "job-0001"))).first()
        state = (await session.exec(select(DriverRuntimeState).where(DriverRuntimeState.driver_id == 1))).first()
        return job, intent, state


@pytest.mark.asyncio
async def test_cancel_queued_job_cancels_pending_intent():
    engine, sf = await _make_engine()
    await _seed(sf, job_status=TaskStatus.QUEUED.value, intent_status="pending")
    client = await _get_client(sf)
    async with sf() as session:
        await WaybillJobService.delete_job(client, "job-0001", session)
    job, intent, state = await _reload(sf)
    assert job.status == TaskStatus.CANCELLED.value
    assert intent.status == "cancelled"
    assert state.active_execution_id is None


@pytest.mark.asyncio
async def test_cancel_claimed_job_without_execution_cancels_claimed_intent():
    engine, sf = await _make_engine()
    await _seed(sf, job_status=TaskStatus.CLAIMED.value, intent_status="claimed")
    client = await _get_client(sf)
    async with sf() as session:
        await WaybillJobService.delete_job(client, "job-0001", session)
    job, intent, state = await _reload(sf)
    assert job.status == TaskStatus.CANCELLED.value
    assert intent.status == "cancelled"
    assert state.active_execution_id is None


@pytest.mark.asyncio
async def test_cancel_running_job_returns_409():
    engine, sf = await _make_engine()
    await _seed(sf, job_status=TaskStatus.RUNNING.value, intent_status="claimed", live_execution=True)
    client = await _get_client(sf)
    with pytest.raises(HTTPException) as excinfo:
        async with sf() as session:
            await WaybillJobService.delete_job(client, "job-0001", session)
    assert excinfo.value.status_code == 409
    # Job / intent / slot must be untouched.
    job, intent, state = await _reload(sf)
    assert job.status == TaskStatus.RUNNING.value
    assert intent.status == "claimed"
    assert state.active_execution_id == "intent-0001"


@pytest.mark.asyncio
async def test_cancel_does_not_free_slot_of_live_execution():
    engine, sf = await _make_engine()
    await _seed(sf, job_status=TaskStatus.IN_PROGRESS.value, intent_status="claimed", live_execution=True)
    client = await _get_client(sf)
    with pytest.raises(HTTPException) as excinfo:
        async with sf() as session:
            await WaybillJobService.delete_job(client, "job-0001", session)
    assert excinfo.value.status_code == 409
    _, _, state = await _reload(sf)
    assert state.active_execution_id == "intent-0001"


@pytest.mark.asyncio
async def test_dispatcher_skips_cancelled_job():
    engine, sf = await _make_engine()
    await _seed(sf, job_status=TaskStatus.CANCELLED.value, intent_status="pending")
    dispatcher = DispatcherService()
    mock_send_task = MagicMock()
    with (
        patch("app.orchestrator.dispatcher_service.async_session_factory", new=sf),
        patch("app.orchestrator.dispatcher_service.celery_app") as mock_celery,
    ):
        mock_celery.send_task = mock_send_task
        await dispatcher.run()
    job, intent, _ = await _reload(sf)
    assert job.status == TaskStatus.CANCELLED.value
    assert intent.status == "cancelled"  # never claimed, never dispatched
    mock_send_task.assert_not_called()


@pytest.mark.asyncio
async def test_terminal_job_with_child_records_is_not_hard_deleted():
    engine, sf = await _make_engine()
    await _seed(sf, job_status=TaskStatus.FAILED.value, intent_status="failed")
    # Add a child task log + attempt so the job is not childless.
    async with sf() as session:
        session.add(
            WaybillTaskLog(
                job_id="job-0001",
                client_id=1,
                step="complete",
                status="success",
                message="done",
            )
        )
        await session.commit()
    client = await _get_client(sf)
    async with sf() as session:
        await WaybillJobService.delete_job(client, "job-0001", session)
    job, _, _ = await _reload(sf)
    # Archived, not deleted.
    assert job is not None
    assert job.status == TaskStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_success_job_with_children_rejected_not_hard_deleted():
    # A SUCCESS job means the waybill was registered — it cannot transition to
    # CANCELLED, and it must not be hard-deleted because it has an audit trail.
    engine, sf = await _make_engine()
    await _seed(sf, job_status=TaskStatus.SUCCESS.value, intent_status="completed")
    async with sf() as session:
        session.add(
            WaybillTaskLog(
                job_id="job-0001",
                client_id=1,
                step="complete",
                status="success",
                message="done",
            )
        )
        await session.commit()
    client = await _get_client(sf)
    with pytest.raises(HTTPException) as excinfo:
        async with sf() as session:
            await WaybillJobService.delete_job(client, "job-0001", session)
    assert excinfo.value.status_code == 409
    job, _, _ = await _reload(sf)
    assert job is not None
    assert job.status == TaskStatus.SUCCESS.value  # untouched, not hard-deleted


@pytest.mark.asyncio
async def test_terminal_job_with_intent_is_archived():
    engine, sf = await _make_engine()
    await _seed(sf, job_status=TaskStatus.FAILED.value, intent_status="failed")
    client = await _get_client(sf)
    async with sf() as session:
        await WaybillJobService.delete_job(client, "job-0001", session)
    job, _, _ = await _reload(sf)
    # The intent row is a child record, so the job is archived, not hard-deleted.
    assert job is not None
    assert job.status == TaskStatus.CANCELLED.value
