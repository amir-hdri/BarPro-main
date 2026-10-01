"""Idempotency tests for job creation under duplicate delivery.

create_job() must return the existing job when called twice with the same
idempotency key — both for the normal check-then-insert path and for the
concurrent race path where the second INSERT hits the DB unique constraint
(IntegrityError → rollback → re-query → return existing).
"""

from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models_multitenant import Client, Driver, TaskSource, WaybillJob
from app.services.rpa_scheduler_service import rpa_scheduler_service


@pytest.fixture
async def async_db():
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
        Client(id=1, client_code="c1", name="C", username="c1", full_name="C", email="c@c.c", hashed_password="x")
    )
    session.add(
        Driver(
            id=1,
            client_id=1,
            driver_national_code="1",
            full_name="D",
            utcms_username="u",
            utcms_password_encrypted="e",
            encrypted_password="x",
        )
    )
    await session.commit()
    yield session
    await session.close()
    await engine.dispose()


class _SessionCM:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        return False


async def _create(session, key: str) -> WaybillJob:
    driver = await session.get(Driver, 1)
    with (
        patch(
            "app.services.rpa_scheduler_service.async_session_factory",
            return_value=_SessionCM(session),
        ),
        patch("app.workers.celery_app.celery_app", None),
    ):
        # celery_app=None: skip the broker publish at the end of create_job
        # (no Redis in unit tests; the send is best-effort and swallowed anyway).
        return await rpa_scheduler_service.create_job(
            client_id=1,
            driver=driver,
            payload={"origin": {"city": "Tehran"}, "destination": {"city": "Qom"}},
            source=TaskSource.MANUAL,
            max_retries=3,
            idempotency_key=key,
        )


@pytest.mark.asyncio
async def test_duplicate_idempotency_key_returns_existing_job(async_db: AsyncSession):
    job1 = await _create(async_db, "key-dup-1")
    job2 = await _create(async_db, "key-dup-1")

    assert job1.job_id == job2.job_id

    rows = (await async_db.exec(select(WaybillJob))).all()
    assert len(rows) == 1, f"duplicate job created: {[r.job_id for r in rows]}"


@pytest.mark.asyncio
async def test_concurrent_race_recovers_via_integrity_error(async_db: AsyncSession):
    """Real race: initial check misses, but the INSERT hits the DB unique constraint.

    Simulates a concurrent request that commits between our existence check and
    our INSERT. The IntegrityError handler must roll back, re-query, and return
    the winner's job instead of raising.
    """
    from unittest.mock import MagicMock

    engine = async_db.bind
    session_b = AsyncSession(engine, expire_on_commit=False)
    try:
        # The "other" concurrent request wins the race and commits first.
        session_b.add(
            WaybillJob(
                job_id="job_race_winner",
                idempotency_key="tenant:1:key-race-1",  # build_job_idempotency_key scopes supplied keys
                client_id=1,
                driver_id=1,
                payload_json={},
                status="pending",
                mutation_status="dispatched",
            )
        )
        await session_b.commit()

        # Our existence check runs before the winner is visible to us → miss.
        real_exec = async_db.exec
        calls = 0

        async def fake_exec(statement, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                missed = MagicMock()
                missed.first.return_value = None
                return missed
            return await real_exec(statement, *args, **kwargs)

        async_db.exec = fake_exec  # type: ignore[method-assign]

        driver = await async_db.get(Driver, 1)
        with (
            patch(
                "app.services.rpa_scheduler_service.async_session_factory",
                return_value=_SessionCM(async_db),
            ),
            patch("app.workers.celery_app.celery_app", None),
        ):
            job = await rpa_scheduler_service.create_job(
                client_id=1,
                driver=driver,
                payload={"origin": {"city": "Tehran"}, "destination": {"city": "Qom"}},
                source=TaskSource.MANUAL,
                max_retries=3,
                idempotency_key="key-race-1",
            )

        assert calls >= 2, "the recovery re-query never ran — race path not exercised"
        assert job.job_id == "job_race_winner"
        rows = (await async_db.exec(select(WaybillJob))).all()
        assert len(rows) == 1, f"duplicate job created: {[r.job_id for r in rows]}"
    finally:
        await session_b.close()
