"""Tests for the ClaimReaper — the safety net that recovers jobs stuck in CLAIMED.

Covers the HIGH-severity coverage gap: previously 0 test files referenced
app/orchestrator/claim_reaper.py.
"""
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models_multitenant import Client, Driver, TaskStatus, WaybillJob
from app.models_rpa import DispatchIntent, Execution
from app.orchestrator.claim_reaper import ClaimReaper


@pytest.fixture
async def async_db():
    # StaticPool: a single shared connection, required for SQLite :memory:
    # (a pooled second connection would see a fresh, empty database).
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    session = AsyncSession(engine, expire_on_commit=False)
    session.add(
        Client(
            id=1,
            client_code="test_client",
            name="Test Client",
            username="testclient",
            full_name="Test Client",
            email="test@client.com",
hashed_password="<redacted>",
        )
    )
    session.add(
        Driver(
            id=1,
            client_id=1,
            driver_national_code="1234567890",
            full_name="Test Driver",
            utcms_username="test_driver",
            utcms_password_encrypted="enc_pass",
encrypted_password="<redacted>",
        )
    )
    await session.commit()
    yield session
    await session.close()
    await engine.dispose()


class _SessionCM:
    """Async context manager wrapper so run() doesn't close the test session."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        return False


def _claimed_job(job_id: str, updated_at: datetime) -> WaybillJob:
    return WaybillJob(
        job_id=job_id,
        idempotency_key=f"idemp_{job_id}",
        client_id=1,
        driver_id=1,
        payload_json={"origin_city_id": 1, "destination_city_id": 2},
        status=TaskStatus.CLAIMED.value,
        mutation_status="dispatched",
        updated_at=updated_at,
    )


async def _run_reaper(session):
    reaper = ClaimReaper()
    with (
        patch(
            "app.orchestrator.claim_reaper.async_session_factory",
            return_value=_SessionCM(session),
        ),
        patch(
            "app.orchestrator.claim_reaper.release_driver_execution_slot",
            new_callable=AsyncMock,
        ),
        patch("app.services.night_submission_policy.is_in_night_window", return_value=False),
    ):
        return await reaper.run()


@pytest.mark.asyncio
async def test_reaps_stale_claimed_job_without_execution(async_db: AsyncSession):
    stale = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=10)
    async_db.add(_claimed_job("job_stale", stale))
    await async_db.commit()

    reclaimed = await _run_reaper(async_db)

    assert reclaimed == 1
    job = await async_db.get(WaybillJob, 1)
    await async_db.refresh(job)
    assert job.status == TaskStatus.WAITING_RETRY.value


@pytest.mark.asyncio
async def test_skips_claimed_job_with_active_execution(async_db: AsyncSession):
    stale = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=10)
    async_db.add(_claimed_job("job_live", stale))
    async_db.add(
        Execution(
            execution_id="exec_1",
            intent_id="intent_1",
            job_id="job_live",
            operation="submit",
            worker_id="worker_1",
            fencing_token="fencing_token",
            lease_expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=5),
            status="running",
        )
    )
    await async_db.commit()

    reclaimed = await _run_reaper(async_db)

    assert reclaimed == 0
    job = await async_db.get(WaybillJob, 1)
    assert job.status == TaskStatus.CLAIMED.value


@pytest.mark.asyncio
async def test_skips_fresh_claimed_job(async_db: AsyncSession):
    fresh = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1)
    async_db.add(_claimed_job("job_fresh", fresh))
    await async_db.commit()

    reclaimed = await _run_reaper(async_db)

    assert reclaimed == 0
    job = await async_db.get(WaybillJob, 1)
    assert job.status == TaskStatus.CLAIMED.value


@pytest.mark.asyncio
async def test_skips_claimed_job_with_pending_intent(async_db: AsyncSession):
    stale = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=10)
    async_db.add(_claimed_job("job_intent", stale))
    async_db.add(
        DispatchIntent(
            intent_id="intent_p1",
            client_id=1,
            job_id="job_intent",
            operation="submit",
            fencing_token="fencing_token",
            status="pending",
            updated_at=stale,
        )
    )
    await async_db.commit()

    reclaimed = await _run_reaper(async_db)

    assert reclaimed == 0
    job = await async_db.get(WaybillJob, 1)
    assert job.status == TaskStatus.CLAIMED.value
