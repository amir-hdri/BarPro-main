"""Tests for the central driver execution-slot release helper and its wiring.

These verify the P0 invariant: a job that fails in a *pre-execution* phase
(proxy unavailable/unhealthy, worker draining, celery unavailable, invalid
claim) must never be left holding a ``DriverRuntimeState.active_execution_id``
slot, or it would be permanently invisible to the scheduler.

All tests run against an in-memory SQLite DB — no live UTCMS/portal calls.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.automation.worker_proxy import ProxyUnavailableError
from app.models_multitenant import Client, Driver, TaskStatus, WaybillJob
from app.models_rpa import DispatchIntent, DriverRuntimeState, Execution
from app.orchestrator.driver_slot import release_driver_execution_slot
from app.workers.waybill_worker import _claim_and_execute

_created_engines = []

COMPLETE_PAYLOAD = {
    "sender": {"name": "علی فلاح", "phone": "09121234567"},
    "receiver": {"name": "احمد مومنی", "phone": "09129876543"},
    "origin": {"province": "هرمزگان", "city": "میناب", "address": "بلوار خلیج فارس"},
    "destination": {"province": "هرمزگان", "city": "میناب", "address": "طالوار"},
    "cargo": {"type": "مصالح", "packaging": "فله", "weight": "15", "value": "35000000"},
    "vehicle": {"driver_national_code": "0084575948", "plate": "79ع989ایران84"},
}


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
    session_factory = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine, session_factory


async def _seed(
    session_factory,
    *,
    intent_status="claimed",
    job_status=TaskStatus.CLAIMED.value,
    payload=None,
):
    """Create a tenant, driver, runtime state holding a slot, a claimed job and intent."""
    intent_id = "intent-0001"
    async with session_factory() as session:
        client = Client(
            id=1,
            client_code="tenant-s",
            name="Tenant S",
            email="s@example.com",
            hashed_password="hash",
            username="tenant_s",
            full_name="Tenant S Admin",
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
            status=TaskStatus.RUNNING.value if False else "active",
        )
        session.add(driver)
        runtime_state = DriverRuntimeState(
            client_id=1,
            driver_id=1,
            state="submitting",
            active_execution_id=intent_id,
        )
        session.add(runtime_state)
        job = WaybillJob(
            job_id="job-0001",
            idempotency_key="idem-0001",
            client_id=1,
            driver_id=1,
            status=job_status,
            payload_json=COMPLETE_PAYLOAD if payload is None else payload,
            priority=5,
            attempt_count=1,
        )
        session.add(job)
        intent = DispatchIntent(
            intent_id=intent_id,
            client_id=1,
            job_id="job-0001",
            attempt_no=1,
            operation="submit",
            fencing_token=1,
            status=intent_status,
        )
        session.add(intent)
        await session.commit()
    return intent_id


# --------------------------------------------------------------------------- #
# Helper unit tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_slot_release_requires_matching_intent_id():
    engine, sf = await _make_engine()
    intent_id = await _seed(sf)
    async with sf() as session:
        # Wrong expected intent: must NOT clear, must return False.
        released = await release_driver_execution_slot(session, driver_id=1, expected_intent_id="intent-OTHER")
        assert released is False
        state = (await session.exec(select(DriverRuntimeState).where(DriverRuntimeState.driver_id == 1))).first()
        assert state.active_execution_id == intent_id
        await session.commit()

    async with sf() as session:
        # Correct expected intent: clears and returns True.
        released = await release_driver_execution_slot(session, driver_id=1, expected_intent_id=intent_id)
        assert released is True
        state = (await session.exec(select(DriverRuntimeState).where(DriverRuntimeState.driver_id == 1))).first()
        assert state.active_execution_id is None
        await session.commit()

    async with sf() as session:
        # Idempotent: releasing an already-empty slot is a no-op returning True.
        released = await release_driver_execution_slot(session, driver_id=1, expected_intent_id=intent_id)
        assert released is True


@pytest.mark.asyncio
async def test_slot_is_not_released_if_execution_is_running():
    engine, sf = await _make_engine()
    intent_id = await _seed(sf)
    async with sf() as session:
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

    async with sf() as session:
        released = await release_driver_execution_slot(session, driver_id=1, expected_intent_id=intent_id)
        assert released is False
        state = (await session.exec(select(DriverRuntimeState).where(DriverRuntimeState.driver_id == 1))).first()
        # A live execution means a worker owns the pipeline — slot must stay.
        assert state.active_execution_id == intent_id
        await session.commit()


@pytest.mark.asyncio
async def test_slot_release_no_runtime_state_is_noop():
    engine, sf = await _make_engine()
    async with sf() as session:
        released = await release_driver_execution_slot(session, driver_id=999)
        assert released is True


# --------------------------------------------------------------------------- #
# Worker pre-execution failure paths must release the slot
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_invalid_payload_needs_review_without_proxy_or_execution():
    engine, sf = await _make_engine()
    intent_id = await _seed(sf, payload={})
    task = MagicMock()
    proxy_lookup = MagicMock()

    with (
        patch("app.workers.waybill_worker.async_session_factory", new=sf),
        patch("app.automation.worker_proxy.is_worker_draining", new=AsyncMock()) as draining_check,
        patch("app.automation.worker_proxy.get_worker_proxy_url", new=proxy_lookup),
    ):
        result = await _claim_and_execute(task, intent_id)

    assert result["status"] == TaskStatus.NEEDS_REVIEW.value
    assert result["error_category"] == "payload_validation_failed"
    draining_check.assert_not_awaited()
    proxy_lookup.assert_not_called()

    async with sf() as session:
        job = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-0001"))).first()
        intent = (await session.exec(select(DispatchIntent).where(DispatchIntent.intent_id == intent_id))).first()
        state = (await session.exec(select(DriverRuntimeState).where(DriverRuntimeState.driver_id == 1))).first()
        executions = (await session.exec(select(Execution))).all()
        assert job.status == TaskStatus.NEEDS_REVIEW.value
        assert job.error_category == "payload_validation_failed"
        assert job.terminal_reason == "payload_validation_failed"
        assert intent.status == "failed"
        assert state.active_execution_id is None
        assert executions == []


@pytest.mark.asyncio
async def test_worker_draining_releases_driver_slot():
    engine, sf = await _make_engine()
    intent_id = await _seed(sf)
    task = MagicMock()
    with (
        patch("app.workers.waybill_worker.async_session_factory", new=sf),
        patch("app.automation.worker_proxy.is_worker_draining", new=AsyncMock(return_value=True)),
        patch("app.automation.worker_proxy.drain_worker_consumers", new=MagicMock()),
    ):
        with pytest.raises(ConnectionError):
            await _claim_and_execute(task, intent_id)

    async with sf() as session:
        job = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-0001"))).first()
        assert job.status == TaskStatus.WAITING_RETRY.value
        state = (await session.exec(select(DriverRuntimeState).where(DriverRuntimeState.driver_id == 1))).first()
        assert state.active_execution_id is None


@pytest.mark.asyncio
async def test_proxy_unavailable_releases_driver_slot():
    engine, sf = await _make_engine()
    intent_id = await _seed(sf)
    task = MagicMock()

    def _raise_proxy():
        raise ProxyUnavailableError("no proxy reachable")

    with (
        patch("app.workers.waybill_worker.async_session_factory", new=sf),
        patch("app.automation.worker_proxy.is_worker_draining", new=AsyncMock(return_value=False)),
        patch("app.automation.worker_proxy.get_worker_proxy_url", side_effect=_raise_proxy),
    ):
        with pytest.raises(ConnectionError):
            await _claim_and_execute(task, intent_id)

    async with sf() as session:
        job = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-0001"))).first()
        assert job.status == TaskStatus.WAITING_RETRY.value
        state = (await session.exec(select(DriverRuntimeState).where(DriverRuntimeState.driver_id == 1))).first()
        assert state.active_execution_id is None


@pytest.mark.asyncio
async def test_proxy_unhealthy_releases_driver_slot():
    engine, sf = await _make_engine()
    intent_id = await _seed(sf)
    task = MagicMock()
    with (
        patch("app.workers.waybill_worker.async_session_factory", new=sf),
        patch("app.automation.worker_proxy.is_worker_draining", new=AsyncMock(return_value=False)),
        patch("app.automation.worker_proxy.get_worker_proxy_url", return_value="http://proxy:8080"),
        patch("app.automation.worker_proxy.check_proxy_health", new=AsyncMock(return_value=False)),
        patch("app.automation.worker_proxy.increment_worker_failures", new=AsyncMock(return_value=1)),
        patch("app.automation.worker_proxy.transition_worker_to_draining", new=AsyncMock()),
        patch("app.automation.worker_proxy.drain_worker_consumers", new=MagicMock()),
    ):
        with pytest.raises(ConnectionError):
            await _claim_and_execute(task, intent_id)

    async with sf() as session:
        job = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-0001"))).first()
        assert job.status == TaskStatus.WAITING_RETRY.value
        state = (await session.exec(select(DriverRuntimeState).where(DriverRuntimeState.driver_id == 1))).first()
        assert state.active_execution_id is None


# --------------------------------------------------------------------------- #
# Dispatcher celery-unavailable path must release the slot
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_celery_unavailable_releases_driver_slot():
    from app.orchestrator.dispatcher_service import DispatcherService

    engine, sf = await _make_engine()
    await _seed(sf, intent_status="pending", job_status=TaskStatus.QUEUED.value)
    dispatcher = DispatcherService()
    with (
        patch("app.orchestrator.dispatcher_service.async_session_factory", new=sf),
        patch("app.orchestrator.dispatcher_service.celery_app", new=None),
    ):
        await dispatcher.run()

    async with sf() as session:
        job = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-0001"))).first()
        # Dispatcher reverts an undeliverable job to WAITING_RETRY.
        assert job.status == TaskStatus.WAITING_RETRY.value
        state = (await session.exec(select(DriverRuntimeState).where(DriverRuntimeState.driver_id == 1))).first()
        assert state.active_execution_id is None
