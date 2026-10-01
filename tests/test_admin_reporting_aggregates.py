"""Regression tests for AdminReportingService aggregate queries.

Covers the per-client job aggregates in ``client_summary`` (total / success /
failed counts plus first/last job timestamps). These aggregates were refactored
from one six-column ``select()`` into two narrower queries because sqlmodel's
``select()`` typing overloads accept at most four columns; this test pins the
runtime behavior end-to-end against a real SQLite database.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models_multitenant import Client, Driver, TaskStatus, WaybillJob
from app.services import admin_reporting_service
from app.services.admin_reporting_service import AdminReportingService


@pytest.fixture
async def agg_session_factory(tmp_path):
    db_file = tmp_path / "admin_reporting_agg.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False, future=True)
    factory = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    base = datetime(2026, 9, 1, 12, 0, 0)
    async with factory() as session:
        session.add(
            Client(
                id=1,
                client_code="agg-c1",
                name="Agg C1",
                email="agg-c1@example.com",
                hashed_password="x",
                username="agg-c1",
                full_name="Agg C1",
            )
        )
        session.add(
            Client(
                id=2,
                client_code="agg-c2",
                name="Agg C2",
                email="agg-c2@example.com",
                hashed_password="x",
                username="agg-c2",
                full_name="Agg C2",
            )
        )
        session.add(
            Driver(
                id=1,
                client_id=1,
                full_name="D1",
                driver_national_code="111",
                status="active",
                utcms_username="agg-d1",
                utcms_password_encrypted="x",
            )
        )
        jobs = [
            # client 1: success + failed + pending across three days
            WaybillJob(
                job_id="agg-j1",
                idempotency_key="agg-k1",
                client_id=1,
                driver_id=1,
                status=TaskStatus.SUCCESS.value,
                payload_json={},
                created_at=base,
            ),
            WaybillJob(
                job_id="agg-j2",
                idempotency_key="agg-k2",
                client_id=1,
                driver_id=1,
                status=TaskStatus.FAILED.value,
                payload_json={},
                created_at=base + timedelta(days=1),
            ),
            WaybillJob(
                job_id="agg-j3",
                idempotency_key="agg-k3",
                client_id=1,
                driver_id=1,
                status=TaskStatus.PENDING.value,
                payload_json={},
                created_at=base + timedelta(days=2),
            ),
            # client 2: single failed job
            WaybillJob(
                job_id="agg-j4",
                idempotency_key="agg-k4",
                client_id=2,
                status=TaskStatus.FAILED.value,
                payload_json={},
                created_at=base + timedelta(days=3),
            ),
        ]
        session.add_all(jobs)
        await session.commit()

    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_client_summary_job_aggregates(agg_session_factory, monkeypatch):
    """Per-client counts and first/last timestamps must match the seeded jobs."""
    monkeypatch.setattr(admin_reporting_service, "async_session_factory", agg_session_factory)

    report = await AdminReportingService().client_summary()
    by_id = {row["client_id"]: row for row in report["rows"]}

    c1 = by_id[1]
    assert c1["total_jobs"] == 3
    assert c1["success_jobs"] == 1
    assert c1["failed_jobs"] == 1
    assert c1["first_activity"] == "2026-09-01T12:00:00"
    assert c1["last_activity"] == "2026-09-03T12:00:00"

    c2 = by_id[2]
    assert c2["total_jobs"] == 1
    assert c2["success_jobs"] == 0
    assert c2["failed_jobs"] == 1
    assert c2["first_activity"] == "2026-09-04T12:00:00"
    assert c2["last_activity"] == "2026-09-04T12:00:00"


@pytest.mark.asyncio
async def test_client_summary_aggregates_respect_date_filter(agg_session_factory, monkeypatch):
    """date_from/date_to must apply to both the counts and the timestamps queries."""
    monkeypatch.setattr(admin_reporting_service, "async_session_factory", agg_session_factory)

    report = await AdminReportingService().client_summary(date_from="2026-09-02", date_to="2026-09-02")
    by_id = {row["client_id"]: row for row in report["rows"]}

    c1 = by_id[1]
    # Only the failed job of 2026-09-02 falls inside the window.
    assert c1["total_jobs"] == 1
    assert c1["success_jobs"] == 0
    assert c1["failed_jobs"] == 1
    assert c1["first_activity"] == "2026-09-02T12:00:00"
    assert c1["last_activity"] == "2026-09-02T12:00:00"

    c2 = by_id[2]
    assert c2["total_jobs"] == 0
    assert c2["first_activity"] is None
    assert c2["last_activity"] is None
