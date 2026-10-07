"""Tests for history date filters (waybill jobs + fuel inquiries).

The history page lets operators observe how many registrations each driver
and plate had on an intended day via ``date_from``/``date_to`` (YYYY-MM-DD,
Tehran calendar days). These tests pin the corrected behavior:

  - ``date_to`` includes the *entire* selected day (previously
    ``created_at <= <midnight>`` silently excluded everything registered on
    that day, so filtering a single day returned nothing).
  - Day bounds are interpreted in the Tehran timezone while ``created_at`` is
    stored as naive UTC (previously the first ~3.5h of each Tehran day were
    attributed to the previous day).
  - Invalid date strings are rejected with HTTP 400, not a 500.
"""

from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.multitenant import _parse_history_date_bounds, list_waybill_jobs
from app.core.jalali import tehran_day_bounds_utc
from app.models_multitenant import Client, Driver, FuelInquiry, WaybillJob
from app.schemas.multitenant import TaskFilterRequest
from app.services import admin_reporting_service as admin_reporting_module
from app.services.admin_reporting_service import admin_reporting_service
from app.services.fuel_inquiry_service import fuel_inquiry_service
from app.services.user_reporting_service import user_reporting_service
from app.services.waybill_job_service import WaybillJobService

# Tehran day 2026-10-02 == naive UTC [2026-10-01 20:30, 2026-10-02 20:30)
DAY = "2026-10-02"
DAY_START_UTC = datetime(2026, 10, 1, 20, 30)
DAY_END_UTC = datetime(2026, 10, 2, 20, 30)


def test_tehran_day_bounds_utc():
    start, end = tehran_day_bounds_utc(2026, 10, 2)
    assert start == DAY_START_UTC
    assert end == DAY_END_UTC


def test_parse_history_date_bounds_single_day():
    dt_from, dt_to = _parse_history_date_bounds(DAY, DAY)
    assert dt_from == DAY_START_UTC
    assert dt_to == DAY_END_UTC


def test_parse_history_date_bounds_none():
    assert _parse_history_date_bounds(None, None) == (None, None)
    dt_from, dt_to = _parse_history_date_bounds(DAY, None)
    assert dt_from == DAY_START_UTC and dt_to is None


def test_parse_history_date_bounds_rejects_invalid():
    with pytest.raises(HTTPException) as exc:
        _parse_history_date_bounds("not-a-date", None)
    assert exc.value.status_code == 400


def test_tehran_day_bounds_utc_month_and_year_boundaries():
    """The Tehran shift must cross month/year boundaries, not just day ones."""
    # 1 Jan 2026 Tehran starts on 31 Dec 2025 at 20:30 UTC (year + month roll).
    assert tehran_day_bounds_utc(2026, 1, 1) == (datetime(2025, 12, 31, 20, 30), datetime(2026, 1, 1, 20, 30))
    # 1 Mar 2026 Tehran starts on 28 Feb (2026 is not a Gregorian leap year).
    assert tehran_day_bounds_utc(2026, 3, 1) == (datetime(2026, 2, 28, 20, 30), datetime(2026, 3, 1, 20, 30))
    # 1 Mar 2024 Tehran starts on 29 Feb (2024 IS a leap year).
    assert tehran_day_bounds_utc(2024, 3, 1) == (datetime(2024, 2, 29, 20, 30), datetime(2024, 3, 1, 20, 30))
    # 31 Dec 2026 Tehran ends inside 31 Dec UTC, so the exclusive bound does
    # not spill into the next year.
    assert tehran_day_bounds_utc(2026, 12, 31) == (datetime(2026, 12, 30, 20, 30), datetime(2026, 12, 31, 20, 30))


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("20261002", id="compact-basic-iso"),
        pytest.param("2026-W40-5", id="iso-week-date"),
        pytest.param("2026-10-02T00:00:00", id="full-datetime"),
        pytest.param("2026-10-02T00:00:00+09:00", id="tz-aware-datetime"),
        pytest.param("2026-10-02 00:00:00", id="space-separated-datetime"),
        pytest.param("2026-13-02", id="impossible-month"),
        pytest.param("", id="empty-is-falsy-but-explicit"),
    ],
)
def test_parse_history_date_bounds_is_strict_about_the_documented_format(value):
    """Finding 8: ``fromisoformat`` accepted compact/ISO-week/datetime forms and
    silently DISCARDED any timezone offset (``.year/.month/.day``), so inputs
    outside the documented ``YYYY-MM-DD`` contract were reinterpreted instead
    of rejected."""
    if value == "":
        # Falsy values still mean "no filter", which must stay a no-op.
        assert _parse_history_date_bounds(value, None) == (None, None)
        return
    with pytest.raises(HTTPException) as exc:
        _parse_history_date_bounds(value, None)
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        _parse_history_date_bounds(None, value)
    assert exc.value.status_code == 400


@pytest.mark.parametrize("start,end", [("2026-10-05", "2026-10-02"), ("2026-10-03", "2026-10-02")])
def test_parse_history_date_bounds_rejects_reversed_range(start, end):
    """A reversed range used to return an empty page with no hint of why."""
    with pytest.raises(HTTPException) as exc:
        _parse_history_date_bounds(start, end)
    assert exc.value.status_code == 400
    assert "شروع" in exc.value.detail and "پایان" in exc.value.detail
    # An equal (single-day) range is valid, not reversed.
    assert _parse_history_date_bounds(DAY, DAY) == (DAY_START_UTC, DAY_END_UTC)


async def test_waybill_route_rejects_reversed_date_range(session_factory):
    async with session_factory() as session:
        client, _ = await _seed_jobs(session)
        with pytest.raises(HTTPException) as exc:
            await list_waybill_jobs(
                date_from="2026-10-05",
                date_to="2026-10-02",
                page=1,
                user_context={"role": "client", "user": client},
                session=session,
            )
        assert exc.value.status_code == 400


@pytest.fixture
async def session_factory(tmp_path):
    db_file = tmp_path / "history_date_filters.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    await engine.dispose()


_JOB_SEQ = 0


def _job(client_id, driver_id, created_at, status="success"):
    global _JOB_SEQ
    _JOB_SEQ += 1
    return WaybillJob(
        job_id=f"hist-job-{_JOB_SEQ}-{int(created_at.timestamp())}",
        idempotency_key=f"hist-idem-{_JOB_SEQ}",
        client_id=client_id,
        driver_id=driver_id,
        status=status,
        payload_json={"plate_number": "12ع345ایران67"},
        created_at=created_at,
        updated_at=created_at,
    )


async def _seed_jobs(session: AsyncSession):
    client = Client(
        client_code="hist-tenant",
        name="Hist Tenant",
        email="hist@example.com",
        username="hist",
        full_name="Hist Tenant",
        hashed_password="test-hash-not-verified",
    )
    session.add(client)
    await session.flush()
    driver = Driver(
        client_id=client.id,
        driver_national_code="1234567890",
        full_name="راننده تست",
        utcms_username="u",
        utcms_password_encrypted="p",
    )
    session.add(driver)
    await session.flush()

    jobs = [
        # 00:30 Tehran on 2026-10-02 -> inside the selected day
        _job(client.id, driver.id, datetime(2026, 10, 1, 21, 0)),
        # 22:30 Tehran on 2026-10-02 -> inside the selected day
        _job(client.id, driver.id, datetime(2026, 10, 2, 19, 0)),
        # 00:30 Tehran on 2026-10-03 -> next day, must be excluded
        _job(client.id, driver.id, datetime(2026, 10, 2, 21, 0)),
        # 23:30 Tehran on 2026-10-01 -> previous day, must be excluded
        _job(client.id, driver.id, datetime(2026, 10, 1, 20, 0)),
    ]
    session.add_all(jobs)
    await session.commit()
    return client, jobs


async def test_waybill_date_filter_includes_whole_end_day(session_factory):
    """Filtering from=X to=X returns exactly the jobs of Tehran day X."""
    async with session_factory() as session:
        client, jobs = await _seed_jobs(session)
        dt_from, dt_to = _parse_history_date_bounds(DAY, DAY)
        result = await WaybillJobService.list_jobs(
            {"role": "client", "user": client},
            session,
            TaskFilterRequest(date_from=dt_from, date_to=dt_to, page_size=100),
        )
        got = {j.job_id for j in result.tasks}
        assert got == {jobs[0].job_id, jobs[1].job_id}
        assert result.total == 2


async def test_waybill_route_single_day_filter_end_to_end(session_factory):
    """Route-level: date strings from the UI return the whole Tehran day.

    Regression test for the old behavior where ``date_to`` was parsed to
    midnight (``created_at <= <midnight>``), so filtering a single day
    returned nothing at all.
    """
    async with session_factory() as session:
        client, jobs = await _seed_jobs(session)
        result = await list_waybill_jobs(
            date_from=DAY,
            date_to=DAY,
            page=1,
            page_size=100,
            user_context={"role": "client", "user": client},
            session=session,
        )
        assert {j.job_id for j in result.tasks} == {jobs[0].job_id, jobs[1].job_id}
        assert result.total == 2


async def test_waybill_route_rejects_invalid_date(session_factory):
    async with session_factory() as session:
        client, _ = await _seed_jobs(session)
        with pytest.raises(HTTPException) as exc:
            await list_waybill_jobs(
                date_from="not-a-date",
                page=1,
                user_context={"role": "client", "user": client},
                session=session,
            )
        assert exc.value.status_code == 400


async def test_waybill_status_registered_aggregate(session_factory):
    """status='registered' matches the tracking panel's «ثبت» set."""
    async with session_factory() as session:
        client, jobs = await _seed_jobs(session)
        extra = [
            WaybillJob(
                job_id="r-issued",
                client_id=client.id,
                driver_id=1,
                status="issued",
                payload_json={},
                idempotency_key="test-r-issued",
                created_at=datetime(2026, 10, 2, 10, 0),
            ),
            WaybillJob(
                job_id="r-failed",
                client_id=client.id,
                driver_id=1,
                status="failed",
                payload_json={},
                idempotency_key="test-r-failed",
                created_at=datetime(2026, 10, 2, 10, 0),
            ),
        ]
        for job in extra:
            session.add(job)
        await session.commit()

        result = await WaybillJobService.list_jobs(
            {"role": "client", "user": client},
            session,
            TaskFilterRequest(status="registered", page_size=100),
        )
        got = {j.job_id for j in result.tasks}
        # success (seeded) + issued jobs are included...
        assert {j.job_id for j in jobs} <= got
        assert "r-issued" in got
        # ...failed jobs are excluded
        assert "r-failed" not in got
        assert result.total == len(got)
        failed_check = await WaybillJobService.list_jobs(
            {"role": "client", "user": client},
            session,
            TaskFilterRequest(status="failed", page_size=100),
        )
        assert {j.job_id for j in failed_check.tasks} == {"r-failed"}


async def test_waybill_date_filter_open_ranges(session_factory):
    async with session_factory() as session:
        client, jobs = await _seed_jobs(session)

        dt_from, _ = _parse_history_date_bounds(DAY, None)
        result = await WaybillJobService.list_jobs(
            {"role": "client", "user": client},
            session,
            TaskFilterRequest(date_from=dt_from, page_size=100),
        )
        assert {j.job_id for j in result.tasks} == {jobs[0].job_id, jobs[1].job_id, jobs[2].job_id}

        _, dt_to = _parse_history_date_bounds(None, DAY)
        result = await WaybillJobService.list_jobs(
            {"role": "client", "user": client},
            session,
            TaskFilterRequest(date_to=dt_to, page_size=100),
        )
        assert {j.job_id for j in result.tasks} == {jobs[0].job_id, jobs[1].job_id, jobs[3].job_id}


async def test_fuel_inquiry_date_filter_includes_whole_end_day(session_factory):
    async with session_factory() as session:
        client = Client(
            client_code="fuel-hist-tenant",
            name="Fuel Hist",
            email="fuelhist@example.com",
            username="fuelhist",
            full_name="Fuel Hist",
            hashed_password="test-hash-not-verified",
        )
        session.add(client)
        await session.flush()
        driver = Driver(
            client_id=client.id,
            driver_national_code="0987654321",
            full_name="راننده سوخت",
            utcms_username="u2",
            utcms_password_encrypted="p2",
        )
        session.add(driver)
        await session.flush()
        in_day = FuelInquiry(
            client_id=client.id,
            driver_id=driver.id,
            created_at=datetime(2026, 10, 2, 19, 0),  # 22:30 Tehran on 2026-10-02
            updated_at=datetime(2026, 10, 2, 19, 0),
        )
        next_day = FuelInquiry(
            client_id=client.id,
            driver_id=driver.id,
            created_at=datetime(2026, 10, 2, 21, 0),  # 00:30 Tehran on 2026-10-03
            updated_at=datetime(2026, 10, 2, 21, 0),
        )
        session.add_all([in_day, next_day])
        await session.commit()

        dt_from, dt_to = _parse_history_date_bounds(DAY, DAY)
        result = await fuel_inquiry_service.list_inquiries(
            {"role": "client", "user": client},
            1,
            100,
            session,
            date_from=dt_from,
            date_to=dt_to,
        )
        assert {i.id for i in result.items} == {in_day.id}


# ── Reports must agree with /history about where a Tehran day begins/ends ────
#
# Finding 7: /history used tehran_day_bounds_utc while EVERY reporting service
# still did ``fromisoformat(date_to) + timedelta(days=1)`` in naive UTC, so the
# two surfaces disagreed for the first 3.5 hours of every Tehran day (a job
# created 2026-10-02 02:00 Tehran = 2026-10-01 22:30 UTC was counted on 10-02
# in history but 10-01 in reports).


async def test_user_report_history_agrees_with_history_page_on_tehran_day(session_factory):
    async with session_factory() as session:
        client, jobs = await _seed_jobs(session)

        report = await user_reporting_service.waybill_history(
            client, session, date_from=DAY, date_to=DAY, page=1, page_size=100
        )
        reported = {row["job_id"] for row in report["jobs"]}

        dt_from, dt_to = _parse_history_date_bounds(DAY, DAY)
        history = await WaybillJobService.list_jobs(
            {"role": "client", "user": client},
            session,
            TaskFilterRequest(date_from=dt_from, date_to=dt_to, page_size=100),
        )

        # jobs[0] is 00:30 Tehran on the selected day (22:00-ish UTC the day
        # before) and jobs[2] is 00:30 Tehran on the NEXT day: the naive-UTC
        # window got both of those exactly backwards.
        assert reported == {jobs[0].job_id, jobs[1].job_id}
        assert reported == {job.job_id for job in history.tasks}
        assert report["total"] == history.total == 2


async def test_user_error_details_uses_tehran_day_bounds(session_factory):
    async with session_factory() as session:
        client, _ = await _seed_jobs(session)
        early = _job(client.id, 1, datetime(2026, 10, 1, 21, 0), status="failed")  # 00:30 Tehran 10-02
        late = _job(client.id, 1, datetime(2026, 10, 2, 21, 0), status="failed")  # 00:30 Tehran 10-03
        session.add_all([early, late])
        await session.commit()

        rows = await user_reporting_service.error_details(client, session, date_from=DAY, date_to=DAY)
        got = {row["job_id"] for row in rows}
        assert early.job_id in got
        assert late.job_id not in got


async def test_admin_client_detail_uses_tehran_day_bounds(session_factory):
    async with session_factory() as session:
        client, jobs = await _seed_jobs(session)

        detail = await admin_reporting_service.client_detail(client.id, session, date_from=DAY, date_to=DAY)
        # Same two jobs the history page returns for this Tehran day.
        assert detail["total_jobs"] == 2
        assert detail["success_jobs"] == 2
        per_driver = {row["driver_id"]: row for row in detail["driver_breakdown"]}
        assert per_driver[jobs[0].driver_id]["total_jobs"] == 2


async def test_admin_client_detail_still_rejects_malformed_dates(session_factory):
    async with session_factory() as session:
        client, _ = await _seed_jobs(session)
        for kwargs in ({"date_from": "not-a-date"}, {"date_to": "not-a-date"}):
            with pytest.raises(HTTPException) as exc:
                await admin_reporting_service.client_detail(client.id, session, **kwargs)
            assert exc.value.status_code == 422


async def test_admin_failure_analysis_uses_tehran_day_bounds(session_factory, monkeypatch):
    async with session_factory() as session:
        client, _ = await _seed_jobs(session)
        early = _job(client.id, 1, datetime(2026, 10, 1, 21, 0), status="failed")  # 00:30 Tehran 10-02
        late = _job(client.id, 1, datetime(2026, 10, 2, 21, 0), status="failed")  # 00:30 Tehran 10-03
        session.add_all([early, late])
        await session.commit()

    monkeypatch.setattr(admin_reporting_module, "async_session_factory", session_factory)
    report = await admin_reporting_service.failure_analysis(client_id=client.id, date_from=DAY, date_to=DAY)
    assert report["total_failed"] == 1
    assert [row["job_id"] for examples in report["examples"].values() for row in examples] == [early.job_id]
