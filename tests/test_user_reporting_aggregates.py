"""Regression tests for UserReportingService aggregate queries.

The per-driver / per-dashboard aggregates were rewritten from single wide
``select()`` statements into two narrower queries (sqlmodel's ``select()``
stubs accept at most four columns). These tests execute the real service
methods against a temporary SQLite database and verify the aggregate values,
proving the split queries return identical results to the original logic.
"""

from collections.abc import AsyncIterator
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models_multitenant import Client, Driver, TaskStatus, WaybillJob
from app.services.user_reporting_service import UserReportingService

MASTER_CLIENT_KW = {
    "client_code": "AGG-U1",
    "name": "Agg U1",
    "email": "agg-u1@example.com",
    "hashed_password": "x",
    "username": "agg-u1",
    "full_name": "Agg U1",
    "status": "active",
}
MASTER_DRIVER_KW = {
    "full_name": "D1",
    "driver_national_code": "111",
    "status": "active",
    "utcms_username": "agg-u1",
    "utcms_password_encrypted": "x",
}


@pytest_asyncio.fixture
async def session() -> AsyncIterator[async_sessionmaker]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield maker
    await engine.dispose()


def _mk_job(
    session_id: int,
    job_id: str,
    driver_id: int,
    status: str,
    created: datetime,
) -> WaybillJob:
    return WaybillJob(
        id=session_id,
        job_id=job_id,
        idempotency_key=f"key-{job_id}",
        client_id=1,
        driver_id=driver_id,
        status=status,
        payload_json="{}",
        created_at=created,
    )


async def _seed(maker: async_sessionmaker) -> None:
    async with maker() as session:
        session.add(Client(id=1, **MASTER_CLIENT_KW))
        session.add(Driver(id=1, client_id=1, **MASTER_DRIVER_KW))
        session.add(
            Driver(
                id=2,
                client_id=1,
                full_name="D2",
                driver_national_code="222",
                status="active",
                utcms_username="agg-u2",
                utcms_password_encrypted="x",
            )
        )
        session.add_all(
            [
                _mk_job(1, "j1", 1, TaskStatus.SUCCESS.value, datetime(2026, 9, 1, 12)),
                _mk_job(2, "j2", 1, TaskStatus.FAILED.value, datetime(2026, 9, 2, 12)),
                _mk_job(3, "j3", 1, TaskStatus.PENDING.value, datetime(2026, 9, 3, 12)),
                _mk_job(4, "j4", 2, TaskStatus.SUCCESS.value, datetime(2026, 9, 4, 12)),
            ]
        )
        await session.commit()


@pytest.mark.asyncio
async def test_driver_list_with_status_aggregates(session: async_sessionmaker) -> None:
    await _seed(session)
    svc = UserReportingService()
    async with session() as s:
        client = await s.get(Client, 1)
        assert client is not None
        rows = await svc.driver_list_with_status(client, s)
    by_id = {r["driver_id"]: r for r in rows}
    d1 = by_id[1]
    assert d1["total_jobs"] == 3
    assert d1["success_jobs"] == 1
    assert d1["failed_jobs"] == 1
    assert d1["pending_jobs"] == 1
    assert d1["last_job_at"] == "2026-09-03T12:00:00"
    d2 = by_id[2]
    assert d2["total_jobs"] == 1
    assert d2["success_jobs"] == 1
    assert d2["failed_jobs"] == 0
    assert d2["pending_jobs"] == 0
    assert d2["last_job_at"] == "2026-09-04T12:00:00"


@pytest.mark.asyncio
async def test_driver_performance_aggregates(session: async_sessionmaker) -> None:
    await _seed(session)
    svc = UserReportingService()
    async with session() as s:
        client = await s.get(Client, 1)
        assert client is not None
        rows = await svc.driver_performance(client, s)
    by_id = {r["driver_id"]: r for r in rows}
    d1 = by_id[1]
    assert d1["total_jobs"] == 3
    assert d1["success_jobs"] == 1
    assert d1["failed_jobs"] == 1
    assert d1["last_job_at"] == "2026-09-03T12:00:00"
    d2 = by_id[2]
    assert d2["total_jobs"] == 1
    assert d2["last_job_at"] == "2026-09-04T12:00:00"


@pytest.mark.asyncio
async def test_dashboard_stats_aggregates(session: async_sessionmaker) -> None:
    await _seed(session)
    svc = UserReportingService()
    async with session() as s:
        client = await s.get(Client, 1)
        assert client is not None
        stats = await svc.dashboard_stats(client, s)
    assert stats["total_drivers"] == 2
    assert stats["total_jobs"] == 4
    assert stats["success_jobs"] == 2
    assert stats["failed_jobs"] == 1
    assert stats["pending_jobs"] == 1
