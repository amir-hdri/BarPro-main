from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.automation.worker_proxy import (
    drain_worker_consumers,
    increment_worker_failures,
    is_worker_draining,
    transition_worker_to_draining,
)
from app.core.config import utcms_config
from app.models_multitenant import WaybillJob
from app.models_rpa import DispatchIntent, WorkerRegistry
from app.workers.waybill_worker import _claim_and_execute, _claim_and_reconcile, get_retry_delay

COMPLETE_PAYLOAD = {
    "sender": {"name": "علی فلاح"},
    "receiver": {"name": "احمد مومنی"},
    "origin": {"province": "هرمزگان", "city": "میناب", "address": "بلوار خلیج فارس"},
    "destination": {"province": "هرمزگان", "city": "میناب", "address": "طالوار"},
    "cargo": {"type": "مصالح", "packaging": "فله", "weight": "15", "value": "35000000"},
    "vehicle": {"driver_national_code": "0084575948", "plate": "79ع989ایران84"},
}


@pytest.fixture
async def async_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield async_session
    await engine.dispose()


@pytest.mark.asyncio
async def test_increment_worker_failures():
    mock_redis = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock(return_value=True)

    with patch("app.core.redis_client.redis_manager.get", return_value=mock_redis):
        val = await increment_worker_failures("test_worker")
        assert val == 1
        mock_redis.incr.assert_called_once_with("worker_retry_attempts:test_worker")
        mock_redis.expire.assert_called_once_with("worker_retry_attempts:test_worker", 60)


@pytest.mark.asyncio
async def test_transition_worker_to_draining(async_db):
    # Setup database record
    async with async_db() as session:
        worker = WorkerRegistry(
            worker_id="test_worker_drain",
            hostname="localhost",
            status="active",
            created_at=datetime.now(UTC).replace(tzinfo=None),
            updated_at=datetime.now(UTC).replace(tzinfo=None),
        )
        session.add(worker)
        await session.commit()

    with patch("app.core.database.async_session_factory", new=async_db):
        # Trigger transition
        await transition_worker_to_draining("test_worker_drain")

    # Verify status updated
    async with async_db() as session:
        stmt = select(WorkerRegistry).where(WorkerRegistry.worker_id == "test_worker_drain")
        res = await session.exec(stmt)
        worker_updated = res.first()
        assert worker_updated.status == "draining"


@pytest.mark.asyncio
async def test_is_worker_draining(async_db):
    async with async_db() as session:
        worker = WorkerRegistry(
            worker_id="test_worker_check",
            hostname="localhost",
            status="draining",
            created_at=datetime.now(UTC).replace(tzinfo=None),
            updated_at=datetime.now(UTC).replace(tzinfo=None),
        )
        session.add(worker)
        await session.commit()

    with patch("app.core.database.async_session_factory", new=async_db):
        assert await is_worker_draining("test_worker_check") is True
        assert await is_worker_draining("non_existent_worker") is False


def test_drain_worker_consumers():
    mock_task = MagicMock()
    mock_task.request.hostname = "test_worker_host"

    drain_worker_consumers(mock_task)

    # Verify cancel_consumer was attempted for at least one waybill/reconcile queue
    mock_task.app.control.cancel_consumer.assert_any_call("waybill_tasks", destination=["test_worker_host"])


def test_get_retry_delay():
    # Transient errors should exponentially backoff starting from 60s
    res_network = {"error_category": "network_error"}
    assert get_retry_delay(res_network, 1) == 60
    assert get_retry_delay(res_network, 2) == 120
    assert get_retry_delay(res_network, 3) == 240
    # Capped at 1800s
    assert get_retry_delay(res_network, 10) == 1800

    # Permanent/non-transient errors should use default delay
    res_auth = {"error_category": "auth_failure"}
    assert get_retry_delay(res_auth, 1) == utcms_config.DRIVER_RETRY_DELAY_SECONDS


@pytest.mark.asyncio
async def test_claim_and_execute_draining(async_db):
    mock_task = MagicMock()
    mock_task.request.hostname = "test_host"

    # Insert mock intent and job
    async with async_db() as session:
        job = WaybillJob(
            job_id="job-1",
            idempotency_key="idemp-1",
            payload_json=COMPLETE_PAYLOAD,
            client_id=1,
            driver_id=1,
            status="claimed",
            priority=5,
            attempt_count=0,
        )
        intent = DispatchIntent(
            intent_id="intent-1",
            client_id=1,
            job_id="job-1",
            attempt_no=1,
            operation="execute",
            fencing_token=100,
            status="claimed",
        )
        session.add(job)
        session.add(intent)
        await session.commit()

    with (
        patch("app.workers.waybill_worker.async_session_factory", new=async_db),
        patch("app.automation.worker_proxy.is_worker_draining", return_value=True),
        patch("app.automation.worker_proxy.drain_worker_consumers") as mock_drain,
    ):

        with pytest.raises(ConnectionError) as exc_info:
            await _claim_and_execute(mock_task, "intent-1")

        assert "currently draining" in str(exc_info.value)
        mock_drain.assert_called_once_with(mock_task)

    # Verify database status updated: intent to failed, job to waiting_retry
    async with async_db() as session:
        res_intent = await session.exec(select(DispatchIntent).where(DispatchIntent.intent_id == "intent-1"))
        assert res_intent.first().status == "failed"

        res_job = await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-1"))
        assert res_job.first().status == "waiting_retry"


@pytest.mark.asyncio
async def test_claim_and_execute_unhealthy_proxy(async_db):
    mock_task = MagicMock()
    mock_task.request.hostname = "test_host"

    # Insert mock intent and job
    async with async_db() as session:
        job = WaybillJob(
            job_id="job-2",
            idempotency_key="idemp-2",
            payload_json=COMPLETE_PAYLOAD,
            client_id=1,
            driver_id=1,
            status="claimed",
            priority=5,
            attempt_count=0,
        )
        intent = DispatchIntent(
            intent_id="intent-2",
            client_id=1,
            job_id="job-2",
            attempt_no=1,
            operation="execute",
            fencing_token=200,
            status="claimed",
        )
        session.add(job)
        session.add(intent)
        await session.commit()

    with (
        patch("app.workers.waybill_worker.async_session_factory", new=async_db),
        patch("app.automation.worker_proxy.is_worker_draining", return_value=False),
        patch("app.automation.worker_proxy.get_worker_proxy_url", return_value="http://1.2.3.4:3128"),
        patch("app.automation.worker_proxy.check_proxy_health", return_value=False),
        patch("app.automation.worker_proxy.increment_worker_failures", return_value=4) as mock_incr,
        patch("app.automation.worker_proxy.transition_worker_to_draining") as mock_drain_db,
        patch("app.automation.worker_proxy.drain_worker_consumers") as mock_drain_consumers,
    ):

        with pytest.raises(ConnectionError) as exc_info:
            await _claim_and_execute(mock_task, "intent-2")

        assert "unhealthy" in str(exc_info.value)
        mock_incr.assert_not_called()
        mock_drain_db.assert_not_called()
        mock_drain_consumers.assert_not_called()

    # Verify database status updated: intent to failed, job to waiting_retry
    async with async_db() as session:
        res_intent = await session.exec(select(DispatchIntent).where(DispatchIntent.intent_id == "intent-2"))
        assert res_intent.first().status == "failed"

        res_job = await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-2"))
        assert res_job.first().status == "waiting_retry"


@pytest.mark.asyncio
async def test_claim_and_reconcile_draining(async_db):
    mock_task = MagicMock()
    mock_task.request.hostname = "test_host"

    # Insert mock intent and job
    async with async_db() as session:
        job = WaybillJob(
            job_id="job-3",
            idempotency_key="idemp-3",
            payload_json={},
            client_id=1,
            driver_id=1,
            status="claimed",
            priority=5,
            attempt_count=0,
        )
        intent = DispatchIntent(
            intent_id="intent-3",
            client_id=1,
            job_id="job-3",
            attempt_no=1,
            operation="reconciliation",
            fencing_token=300,
            status="claimed",
        )
        session.add(job)
        session.add(intent)
        await session.commit()

    with (
        patch("app.workers.waybill_worker.async_session_factory", new=async_db),
        patch("app.automation.worker_proxy.is_worker_draining", return_value=True),
        patch("app.automation.worker_proxy.drain_worker_consumers") as mock_drain,
    ):

        with pytest.raises(ConnectionError) as exc_info:
            await _claim_and_reconcile(mock_task, "intent-3")

        assert "currently draining" in str(exc_info.value)
        mock_drain.assert_called_once_with(mock_task)

    # Verify database status updated: intent to failed, job to unknown (since it is reconciliation)
    async with async_db() as session:
        res_intent = await session.exec(select(DispatchIntent).where(DispatchIntent.intent_id == "intent-3"))
        assert res_intent.first().status == "failed"

        res_job = await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-3"))
        assert res_job.first().status == "unknown"
