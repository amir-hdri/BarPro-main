"""Scheduler eligibility & quota enforcement tests (no live UTCMS/portal).

Verifies the scheduler's pre-dispatch guards: tenant ACTIVE status, active
subscription window, dispatchable driver, submit_after, concurrency/daily
quotas, and atomic creation of a missing DriverRuntimeState. All use an
in-memory SQLite DB.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models_multitenant import Client, Driver, TaskStatus, WaybillJob
from app.models_rpa import DispatchIntent, DriverRuntimeState
from app.orchestrator.scheduler_service import SchedulerService


def _utcnow_naive():
    return datetime.now(UTC).replace(tzinfo=None)


async def _make_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    sf = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine, sf


async def _seed(
    sf,
    *,
    client_status="active",
    subscription_end=None,
    subscription_start=None,
    driver_status="active",
    job_status=TaskStatus.PENDING.value,
    submit_after=None,
    max_concurrent=10,
    max_daily=100,
    with_runtime_state=True,
):
    now = _utcnow_naive()
    async with sf() as session:
        client = Client(
            id=1,
            client_code="tenant-s",
            name="Tenant S",
            email="s@example.com",
            hashed_password="hash",
            username="tenant_s",
            full_name="Tenant S Admin",
            status=client_status,
            max_concurrent_tasks=max_concurrent,
            max_daily_tasks=max_daily,
            subscription_start_date=subscription_start,
            subscription_end_date=subscription_end,
        )
        session.add(client)
        driver = Driver(
            id=1,
            client_id=1,
            driver_national_code="1234567890",
            full_name="Driver S",
            phone="09123456789",
            utcms_username="drv",
            utcms_password_encrypted="pwd",
            status=driver_status,
        )
        session.add(driver)
        if with_runtime_state:
            session.add(DriverRuntimeState(client_id=1, driver_id=1, state="active", active_execution_id=None))
        session.add(
            WaybillJob(
                job_id="job-0001",
                idempotency_key="idem-0001",
                client_id=1,
                driver_id=1,
                status=job_status,
                payload_json={},
                priority=5,
                attempt_count=0,
                submit_after=submit_after,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()


async def _run_scheduler(sf):
    scheduler = SchedulerService()
    with patch("app.orchestrator.scheduler_service.async_session_factory", new=sf):
        return await scheduler.run()


async def _assert_not_scheduled(sf):
    async with sf() as session:
        job = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-0001"))).first()
        assert job.status == TaskStatus.PENDING.value
        intents = (await session.exec(select(DispatchIntent).where(DispatchIntent.job_id == "job-0001"))).all()
        assert intents == []
        state = (await session.exec(select(DriverRuntimeState).where(DriverRuntimeState.driver_id == 1))).first()
        if state is not None:
            assert state.active_execution_id is None


@pytest.mark.asyncio
async def test_suspended_tenant_is_not_scheduled():
    engine, sf = await _make_engine()
    await _seed(sf, client_status="suspended")
    assert await _run_scheduler(sf) == 0
    await _assert_not_scheduled(sf)


@pytest.mark.asyncio
async def test_expired_subscription_is_not_scheduled():
    engine, sf = await _make_engine()
    await _seed(sf, subscription_end=_utcnow_naive() - timedelta(days=1))
    assert await _run_scheduler(sf) == 0
    await _assert_not_scheduled(sf)


@pytest.mark.asyncio
async def test_subscription_not_started_is_not_scheduled():
    engine, sf = await _make_engine()
    await _seed(sf, subscription_start=_utcnow_naive() + timedelta(days=1))
    assert await _run_scheduler(sf) == 0
    await _assert_not_scheduled(sf)


@pytest.mark.asyncio
async def test_inactive_driver_is_not_scheduled():
    engine, sf = await _make_engine()
    await _seed(sf, driver_status="inactive")
    assert await _run_scheduler(sf) == 0
    await _assert_not_scheduled(sf)


@pytest.mark.asyncio
async def test_submit_after_future_is_not_scheduled():
    engine, sf = await _make_engine()
    await _seed(sf, submit_after=_utcnow_naive() + timedelta(hours=1))
    assert await _run_scheduler(sf) == 0
    await _assert_not_scheduled(sf)


@pytest.mark.asyncio
async def test_tenant_concurrent_quota_is_enforced():
    engine, sf = await _make_engine()
    await _seed(sf, max_concurrent=0)
    assert await _run_scheduler(sf) == 0
    await _assert_not_scheduled(sf)


@pytest.mark.asyncio
async def test_tenant_daily_quota_is_enforced():
    engine, sf = await _make_engine()
    await _seed(sf, max_daily=0)
    assert await _run_scheduler(sf) == 0
    await _assert_not_scheduled(sf)


@pytest.mark.asyncio
async def test_eligible_job_is_scheduled():
    engine, sf = await _make_engine()
    await _seed(sf)
    assert await _run_scheduler(sf) == 1
    async with sf() as session:
        job = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-0001"))).first()
        assert job.status == TaskStatus.QUEUED.value
        intent = (await session.exec(select(DispatchIntent).where(DispatchIntent.job_id == "job-0001"))).first()
        assert intent is not None
        state = (await session.exec(select(DriverRuntimeState).where(DriverRuntimeState.driver_id == 1))).first()
        assert state.active_execution_id == intent.intent_id


@pytest.mark.asyncio
async def test_missing_runtime_state_is_created_atomically():
    engine, sf = await _make_engine()
    await _seed(sf, with_runtime_state=False)
    assert await _run_scheduler(sf) == 1
    async with sf() as session:
        state = (await session.exec(select(DriverRuntimeState).where(DriverRuntimeState.driver_id == 1))).first()
        assert state is not None
        assert state.active_execution_id is not None
