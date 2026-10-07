"""Transactional ORM and JSONB paths, exercised only against explicit PostgreSQL."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.automation import gps_shipping_manager as shipping
from app.core import database
from app.models_multitenant import Client, Driver, WaybillJob

pytestmark = pytest.mark.integration


def tenant(code: str) -> Client:
    return Client(
        client_code=code,
        name=code,
        email=f"{code}@example.invalid",
        username=code,
        full_name=code,
        hashed_password="test-only",
    )


async def test_session_dependency_commits_success_and_rolls_back_failure(
    postgres_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(database, "async_session_factory", postgres_factory)
    transaction = asynccontextmanager(database.get_session)
    async with transaction() as session:
        committed = tenant("committed")
        session.add(committed)
    with pytest.raises(RuntimeError, match="request failed"):
        async with transaction() as session:
            saved = await session.get(Client, committed.id)
            assert saved is not None
            saved.name = "must-roll-back"
            session.add(saved)
            session.add(tenant("must-not-exist"))
            await session.flush()
            raise RuntimeError("request failed")
    async with postgres_factory() as session:
        rows = (await session.exec(select(Client))).all()
        assert len(rows) == 1
        assert rows[0].name == "committed"


async def test_driver_identity_is_tenant_scoped_and_integrity_failure_rolls_back(
    postgres_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(database, "async_session_factory", postgres_factory)
    transaction = asynccontextmanager(database.get_session)
    async with transaction() as session:
        first, second = tenant("first"), tenant("second")
        session.add_all([first, second])
        await session.flush()
        for client_id in (first.id, second.id):
            session.add(
                Driver(
                    client_id=client_id,
                    driver_national_code="0084575948",
                    full_name="Test driver",
                    utcms_username="unused",
                    utcms_password_encrypted="unused",
                )
            )
    with pytest.raises(IntegrityError):
        async with transaction() as session:
            session.add(
                Driver(
                    client_id=first.id,
                    driver_national_code="0084575948",
                    full_name="Duplicate",
                    utcms_username="unused",
                    utcms_password_encrypted="unused",
                )
            )
            await session.flush()
    async with postgres_factory() as session:
        assert (await session.exec(select(func.count(col(Driver.id))))).one() == 2


async def test_waybill_idempotency_constraint_rejects_duplicate_without_losing_original(
    postgres_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(database, "async_session_factory", postgres_factory)
    transaction = asynccontextmanager(database.get_session)
    async with transaction() as session:
        client = tenant("jobs")
        session.add(client)
        await session.flush()
        session.add(
            WaybillJob(
                job_id="first-job",
                idempotency_key="tenant-scoped-intent",
                client_id=client.id,
                payload_json={"witness": "original"},
            )
        )
    with pytest.raises(IntegrityError):
        async with transaction() as session:
            session.add(
                WaybillJob(
                    job_id="duplicate-job",
                    idempotency_key="tenant-scoped-intent",
                    client_id=client.id,
                    payload_json={"witness": "duplicate"},
                )
            )
            await session.flush()
    async with postgres_factory() as session:
        jobs = (await session.exec(select(WaybillJob))).all()
        assert len(jobs) == 1
        assert jobs[0].job_id == "first-job"
        assert jobs[0].payload_json == {"witness": "original"}


async def test_shipping_fallback_pages_real_postgres_jsonb(
    postgres_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 10, 6, 10, tzinfo=UTC)
    monkeypatch.setattr(database, "async_session_factory", postgres_factory)
    monkeypatch.setattr(shipping, "_get_redis", AsyncMock(return_value=None))
    monkeypatch.setattr(shipping, "_due_scan_db_after_id", 0)
    async with postgres_factory() as session:
        client = tenant("shipping")
        session.add(client)
        await session.flush()
        for index in range(51):
            state = shipping.ShippingState(
                job_id=f"pg-shipping-{index}",
                status="in_transit",
                estimated_end_at=(now + timedelta(days=1) if index < 50 else now - timedelta(hours=1)).isoformat(),
            )
            session.add(
                WaybillJob(
                    job_id=state.job_id,
                    idempotency_key=state.job_id,
                    client_id=client.id,
                    payload_json={},
                    result_json={"_shipping_state": state.to_dict()},
                    status="success",
                )
            )
        await session.commit()
    assert await shipping.get_due_in_transit_jobs(now) == []
    assert [state.job_id for state in await shipping.get_due_in_transit_jobs(now)] == ["pg-shipping-50"]
