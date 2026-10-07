"""Audit regressions: fair shipping fallback and Tehran reporting contracts."""

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes import admin_reporting, shipping_gps, user_reporting
from app.automation import gps_shipping_manager as gps
from app.models_multitenant import Client, WaybillJob
from app.services import admin_reporting_service, user_reporting_service

pytestmark = pytest.mark.unit


def test_missing_shipping_eta_explains_manual_review_without_invented_wait() -> None:
    wait = gps.shipping_wait_reason(gps.ShippingState(job_id="legacy", status="in_transit"))
    assert wait is not None
    detail = shipping_gps._wait_detail(wait)
    assert "بررسی" in detail
    assert "دقیقه" not in detail


class ShippingScanRedis:
    def __init__(self, states: list[gps.ShippingState]) -> None:
        self.values = {f"utcms:shipping:job:{state.job_id}": json.dumps(state.to_dict()) for state in states}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: Any, **kwargs: Any) -> None:
        self.values[key] = str(value)

    async def scan(self, **kwargs: Any) -> tuple[int, list[str]]:
        return 0, [key for key in self.values if key.startswith("utcms:shipping:job:")]


class ShippingScanSession:
    """Mock transport only: honor the real compiled SQL limit and keyset bound."""

    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self.rows = rows
        self.batch_sizes: list[int] = []
        self.queries: list[str] = []

    async def __aenter__(self) -> "ShippingScanSession":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def exec(self, query: Any) -> SimpleNamespace:
        compiled = query.compile(dialect=postgresql.dialect())
        self.queries.append(str(compiled))
        after_id = compiled.params.get("id_1", 0)
        rows = [row for row in self.rows if row.id > after_id][: query._limit_clause.value]
        self.batch_sizes.append(len(rows))
        return SimpleNamespace(all=lambda: rows)


@pytest.mark.parametrize("redis_available", [False, True])
@pytest.mark.parametrize("prefix_kind", ["future", "missing_eta", "redis_delivered"])
async def test_db_shipping_scan_progresses_past_non_due_prefix(
    monkeypatch: pytest.MonkeyPatch, prefix_kind: str, redis_available: bool
) -> None:
    now = datetime(2026, 10, 6, 9, tzinfo=UTC)
    rows = []
    redis_states = []
    for index in range(101):
        eta = (now - timedelta(hours=1)).isoformat()
        if index < 100 and prefix_kind == "future":
            eta = (now + timedelta(days=1)).isoformat()
        elif index < 100 and prefix_kind == "missing_eta":
            eta = ""
        state = gps.ShippingState(job_id=f"audit-shipping-{index}", status="in_transit", estimated_end_at=eta)
        rows.append(
            SimpleNamespace(id=index + 1, job_id=state.job_id, result_json={"_shipping_state": state.to_dict()})
        )
        if index < 100 and prefix_kind == "redis_delivered":
            redis_states.append(gps.ShippingState(job_id=state.job_id, status="delivered", estimated_end_at=eta))
    redis = ShippingScanRedis(redis_states) if redis_available else None
    session = ShippingScanSession(rows)
    monkeypatch.setattr(gps, "_due_scan_db_after_id", 0, raising=False)
    monkeypatch.setattr(gps, "_get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr("app.core.database.async_session_factory", lambda: session)

    observed = []
    for _ in range(3):
        if redis_available:
            # Another scheduler process must continue the shared advisory cursor.
            monkeypatch.setattr(gps, "_due_scan_db_after_id", 0, raising=False)
        observed.extend(state.job_id for state in await gps.get_due_in_transit_jobs(now))

    assert "audit-shipping-100" in observed
    assert max(session.batch_sizes) <= gps.DUE_SCAN_DB_LIMIT
    assert all("ORDER BY waybill_jobs.id" in query for query in session.queries)
    if redis_available and prefix_kind == "redis_delivered":
        assert observed == ["audit-shipping-100"]
    if prefix_kind in {"future", "missing_eta"}:
        assert observed == ["audit-shipping-100"]

    # Reaching the tail wraps around; a trip skipped earlier can become due.
    rows[0].result_json["_shipping_state"]["estimated_end_at"] = (now - timedelta(seconds=1)).isoformat()
    next_tick = await gps.get_due_in_transit_jobs(now)
    if prefix_kind != "redis_delivered" or not redis_available:
        assert "audit-shipping-0" in [state.job_id for state in next_tick]


@pytest.fixture
async def reporting_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add(
            Client(
                id=1,
                client_code="audit",
                name="Audit",
                email="audit@example.invalid",
                hashed_password="x",
                username="audit",
                full_name="Audit",
            )
        )
        await session.commit()
    yield factory
    await engine.dispose()


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/admin/reports/clients/summary",
        "/api/v1/admin/reports/drivers/report",
        "/api/v1/admin/reports/failure-analysis",
        "/api/v1/admin/reports/clients/1/detail",
        "/api/v1/user/reports/waybills",
        "/api/v1/user/reports/errors",
    ],
)
@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"date_from": "invalid-date"}, 422),
        ({"date_to": "2026-02-30"}, 422),
        ({"date_from": "2026-1-2"}, 422),
        ({"date_from": "0001-01-01"}, 422),
        ({"date_from": ""}, 422),
        ({"date_from": "2026-10-06", "date_to": "2026-10-05"}, 400),
    ],
)
async def test_reporting_rejects_invalid_date_filters(
    reporting_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    params: dict[str, str],
    expected: int,
) -> None:
    application = FastAPI()
    application.include_router(admin_reporting.router)
    application.include_router(user_reporting.router)
    application.dependency_overrides[admin_reporting.get_current_admin] = lambda: {"role": "master_admin"}
    async with reporting_factory() as session:
        tenant = await session.get(Client, 1)
        application.dependency_overrides[user_reporting.get_current_client] = lambda: tenant
        application.dependency_overrides[admin_reporting.get_session] = lambda: session
        monkeypatch.setattr(admin_reporting_service, "async_session_factory", reporting_factory)
        async with AsyncClient(
            transport=ASGITransport(app=application, raise_app_exceptions=False), base_url="http://test"
        ) as client:
            response = await client.get(path, params=params)
    assert response.status_code == expected, response.text


@pytest.mark.parametrize("hour", [1, 21])
async def test_dashboard_and_daily_summary_share_tehran_day_boundaries(
    reporting_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch, hour: int
) -> None:
    # 21:00 UTC is already the following day in Tehran.
    now = datetime(2026, 10, 6, hour, tzinfo=UTC)
    today = "2026-10-07" if hour == 21 else "2026-10-06"
    midnight = datetime(2026, 10, 6 if hour == 21 else 5, 20, 30)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return now

    monkeypatch.setattr(user_reporting_service, "datetime", FrozenDateTime)
    async with reporting_factory() as session:
        moments = [
            midnight - timedelta(microseconds=1),
            midnight,
            midnight + timedelta(hours=1),
            midnight + timedelta(days=1),
        ]
        for index, moment in enumerate(moments):
            session.add(
                WaybillJob(
                    job_id=f"report-{index}",
                    idempotency_key=f"report-{index}",
                    client_id=1,
                    payload_json={},
                    status="success" if index != 2 else "failed",
                    created_at=moment,
                )
            )
        session.add(
            WaybillJob(
                job_id="other-tenant",
                idempotency_key="other-tenant",
                client_id=2,
                payload_json={},
                status="success",
                created_at=midnight,
            )
        )
        await session.commit()
        tenant = await session.get(Client, 1)
        assert tenant is not None
        dashboard = await user_reporting_service.user_reporting_service.dashboard_stats(tenant, session)
        daily = await user_reporting_service.user_reporting_service.daily_summary(1, 3, session)

    assert dashboard["today_jobs"] == 2
    assert dashboard["today_success"] == 1
    assert dashboard["today_failed"] == 1
    assert daily["summary"][0] == {"date": today, "total": 2, "success": 1, "failed": 1, "pending": 0}
    assert daily["summary"][1]["total"] == 1
    assert daily["summary"][2]["total"] == 0
