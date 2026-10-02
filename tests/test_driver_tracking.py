"""Tests for driver registration tracking: 15-day Jalali periods and plate fields.

Covers:
  - Jalali <-> Gregorian conversion against known reference dates
  - Period boundaries (phase 1: 9-23 Mehr, phase 2: 24 Mehr-8 Aban)
  - Automatic "reset" of کل ثبت when a period ends (window-based counting)
  - ثبت امروز / تعداد هدف ثبت / کل ثبت per plate
  - Tenant isolation of the tracking endpoint data
  - Plate toggles (فعال/غیرفعال، رفت و برگشت، حمل) persistence
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.jalali import (
    get_tracking_period,
    gregorian_to_jalali,
    jalali_to_gregorian,
)
from app.models_multitenant import Client, Driver, DriverPlate, WaybillJob
from app.schemas.multitenant import PlateUpdateRequest
from app.services.driver_tracking_service import DriverTrackingService
from app.services.plate_service import PlateService

PLATE_1 = "12ع345ایران67"
PLATE_2 = "78ب901ایران34"

# Phase 1 (9-23 Mehr 1405) in naive UTC: 2026-09-30 20:30 -> 2026-10-15 20:30
NOW_PHASE_1 = datetime(2026, 10, 2, 8, 0, tzinfo=UTC)  # 10 Mehr, 11:30 Tehran
NOW_PHASE_2 = datetime(2026, 10, 16, 8, 0, tzinfo=UTC)  # 24 Mehr, 11:30 Tehran


@pytest.fixture
async def session_factory(tmp_path):
    db_file = tmp_path / "driver_tracking.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    await engine.dispose()


async def _seed(session: AsyncSession, client_id: int = 1):
    client = Client(
        client_code=f"tenant-{client_id}",
        name=f"Tenant {client_id}",
        email=f"tenant{client_id}@example.com",
        username=f"tenant{client_id}",
        full_name=f"Tenant {client_id}",
        hashed_password="x",
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

    plate = DriverPlate(
        client_id=client.id,
        driver_id=driver.id,
        plate_number=PLATE_1,
        vehicle_type="کامیون",
        target_count=50,
        round_trip=True,
        in_transport=False,
    )
    session.add(plate)
    await session.commit()
    await session.refresh(plate)
    return client, driver, plate


_JOB_SEQ = 0


def _job(client_id, driver_id, created_at, status="success", plate=PLATE_1):
    global _JOB_SEQ
    _JOB_SEQ += 1
    return WaybillJob(
        job_id=f"test-job-{_JOB_SEQ}-{int(created_at.timestamp())}",
        idempotency_key=f"test-idem-{_JOB_SEQ}",
        client_id=client_id,
        driver_id=driver_id,
        status=status,
        payload_json={"plate_number": plate},
        created_at=created_at,
        updated_at=created_at,
    )


# --------------------------------------------------------------------------
# Pure calendar tests
# --------------------------------------------------------------------------


def test_jalali_known_reference_dates():
    assert gregorian_to_jalali(2026, 10, 2) == (1405, 7, 10)
    assert gregorian_to_jalali(2026, 3, 21) == (1405, 1, 1)
    assert gregorian_to_jalali(2025, 3, 21) == (1404, 1, 1)
    assert jalali_to_gregorian(1405, 7, 10) == (2026, 10, 2)
    assert jalali_to_gregorian(1405, 1, 1) == (2026, 3, 21)


def test_jalali_roundtrip():
    for y in (1399, 1403, 1404, 1405, 1410):
        for m in (1, 6, 7, 8, 10, 12):
            for d in (1, 15, 28):
                g = jalali_to_gregorian(y, m, d)
                assert gregorian_to_jalali(*g) == (y, m, d)


def test_tracking_period_phase_1():
    period = get_tracking_period(NOW_PHASE_1)
    assert period["phase"] == 1
    assert period["start_jalali"] == (1405, 7, 9)
    assert period["end_jalali"] == (1405, 7, 24)  # exclusive bound
    assert period["label"] == "دوره ۱ (۹ مهر تا ۲۳ مهر)"
    assert period["start_at"] == datetime(2026, 9, 30, 20, 30)
    assert period["end_at"] == datetime(2026, 10, 15, 20, 30)


def test_tracking_period_phase_2_boundary():
    period = get_tracking_period(NOW_PHASE_2)
    assert period["phase"] == 2
    assert period["start_jalali"] == (1405, 7, 24)
    assert period["end_jalali"] == (1405, 8, 9)  # exclusive bound
    assert period["label"] == "دوره ۲ (۲۴ مهر تا ۸ آبان)"


# --------------------------------------------------------------------------
# Service tests (SQLite)
# --------------------------------------------------------------------------


async def test_tracking_counts_and_today(session_factory):
    async with session_factory() as session:
        client, driver, plate = await _seed(session)

        # 2 jobs today (Tehran), 1 job yesterday (Tehran), all in phase 1
        session.add(_job(client.id, driver.id, datetime(2026, 10, 2, 5, 0)))  # today
        session.add(_job(client.id, driver.id, datetime(2026, 10, 2, 7, 59)))  # today
        session.add(_job(client.id, driver.id, datetime(2026, 10, 1, 19, 0)))  # yesterday 22:30 Tehran
        await session.commit()

        ctx = {"role": "client", "user": client}
        result = await DriverTrackingService.get_driver_tracking(ctx, session, now=NOW_PHASE_1)

        assert result.period.phase == 1
        assert result.period.label == "دوره ۱ (۹ مهر تا ۲۳ مهر)"
        assert len(result.items) == 1
        item = result.items[0]
        assert item.plate_number == PLATE_1
        assert item.today_count == 2  # ثبت امروز
        assert item.period_total == 3  # کل ثبت
        assert item.target_count == 50  # تعداد هدف ثبت
        assert item.round_trip is True
        assert item.in_transport is False


async def test_period_total_resets_automatically(session_factory):
    """کل ثبت must return to zero when the 15-day period ends, with no reset job."""
    async with session_factory() as session:
        client, driver, plate = await _seed(session)
        session.add(_job(client.id, driver.id, datetime(2026, 10, 10, 5, 0)))
        session.add(_job(client.id, driver.id, datetime(2026, 10, 11, 5, 0)))
        await session.commit()

        ctx = {"role": "client", "user": client}
        in_phase_1 = await DriverTrackingService.get_driver_tracking(ctx, session, now=NOW_PHASE_1)
        assert in_phase_1.items[0].period_total == 2

        # Same DB, evaluated inside phase 2: previous period's jobs no longer count.
        in_phase_2 = await DriverTrackingService.get_driver_tracking(ctx, session, now=NOW_PHASE_2)
        assert in_phase_2.period.phase == 2
        assert in_phase_2.items[0].period_total == 0


async def test_failed_and_cancelled_jobs_not_counted(session_factory):
    async with session_factory() as session:
        client, driver, plate = await _seed(session)
        session.add(_job(client.id, driver.id, datetime(2026, 10, 2, 5, 0), status="success"))
        session.add(_job(client.id, driver.id, datetime(2026, 10, 2, 5, 0), status="failed"))
        session.add(_job(client.id, driver.id, datetime(2026, 10, 2, 5, 0), status="cancelled"))
        session.add(_job(client.id, driver.id, datetime(2026, 10, 2, 5, 0), status="pending"))
        session.add(_job(client.id, driver.id, datetime(2026, 10, 2, 5, 0), status="in_transit"))
        await session.commit()

        ctx = {"role": "client", "user": client}
        result = await DriverTrackingService.get_driver_tracking(ctx, session, now=NOW_PHASE_1)
        assert result.items[0].period_total == 2  # success + in_transit
        assert result.items[0].today_count == 2


async def test_payload_plate_attribution_across_driver_plates(session_factory):
    """Jobs are attributed to the plate named in their payload, not just the driver."""
    async with session_factory() as session:
        client, driver, plate1 = await _seed(session)
        plate2 = DriverPlate(
            client_id=client.id,
            driver_id=driver.id,
            plate_number=PLATE_2,
            vehicle_type="تریلی",
        )
        session.add(plate2)
        await session.flush()

        session.add(_job(client.id, driver.id, datetime(2026, 10, 2, 5, 0), plate=PLATE_1))
        session.add(_job(client.id, driver.id, datetime(2026, 10, 2, 5, 0), plate=PLATE_2))
        session.add(_job(client.id, driver.id, datetime(2026, 10, 2, 5, 0), plate=PLATE_2))
        await session.commit()

        ctx = {"role": "client", "user": client}
        result = await DriverTrackingService.get_driver_tracking(ctx, session, now=NOW_PHASE_1)
        by_plate = {i.plate_number: i for i in result.items}
        assert by_plate[PLATE_1].period_total == 1
        assert by_plate[PLATE_2].period_total == 2


async def test_tenant_isolation(session_factory):
    async with session_factory() as session:
        client_a, driver_a, _ = await _seed(session, client_id=1)
        client_b, driver_b, _ = await _seed(session, client_id=2)

        session.add(_job(client_a.id, driver_a.id, datetime(2026, 10, 2, 5, 0)))
        session.add(_job(client_b.id, driver_b.id, datetime(2026, 10, 2, 5, 0)))
        await session.commit()

        result_a = await DriverTrackingService.get_driver_tracking(
            {"role": "client", "user": client_a}, session, now=NOW_PHASE_1
        )
        result_b = await DriverTrackingService.get_driver_tracking(
            {"role": "client", "user": client_b}, session, now=NOW_PHASE_1
        )
        assert len(result_a.items) == 1
        assert len(result_b.items) == 1
        assert result_a.items[0].period_total == 1
        assert result_b.items[0].period_total == 1

        # master_admin sees both tenants
        result_admin = await DriverTrackingService.get_driver_tracking(
            {"role": "master_admin"}, session, now=NOW_PHASE_1
        )
        assert len(result_admin.items) == 2


async def test_plate_toggles_and_target_update(session_factory):
    async with session_factory() as session:
        client, driver, plate = await _seed(session)
        ctx = {"role": "client", "user": client}

        updated = await PlateService.update_plate(
            ctx,
            plate.id,
            PlateUpdateRequest(target_count=120, round_trip=False, in_transport=True, status="inactive"),
            session,
        )
        assert updated.target_count == 120
        assert updated.round_trip is False
        assert updated.in_transport is True
        assert updated.status == "inactive"

        result = await DriverTrackingService.get_driver_tracking(ctx, session, now=NOW_PHASE_1)
        item = result.items[0]
        assert item.target_count == 120
        assert item.round_trip is False
        assert item.in_transport is True
        assert item.status == "inactive"


def test_tracking_period_exact_boundaries():
    """Pin the exact Tehran-midnight edges of phase 1/2 (regression)."""
    # 8 Mehr 23:59 Tehran -> last period of the previous cycle
    p = get_tracking_period(datetime(2026, 9, 30, 20, 29, tzinfo=UTC))
    assert p["phase"] == 25
    assert p["start_jalali"] == (1405, 7, 4)
    # 9 Mehr 00:00 Tehran -> phase 1 begins
    p = get_tracking_period(datetime(2026, 9, 30, 20, 30, tzinfo=UTC))
    assert p["phase"] == 1
    assert p["label"] == "دوره ۱ (۹ مهر تا ۲۳ مهر)"
    # 23 Mehr 23:59 Tehran -> still phase 1
    p = get_tracking_period(datetime(2026, 10, 15, 20, 29, tzinfo=UTC))
    assert p["phase"] == 1
    # 24 Mehr 00:00 Tehran -> phase 2 begins
    p = get_tracking_period(datetime(2026, 10, 15, 20, 30, tzinfo=UTC))
    assert p["phase"] == 2
    assert p["label"] == "دوره ۲ (۲۴ مهر تا ۸ آبان)"


def test_tracking_period_crosses_jalali_new_year():
    """Cycles continue seamlessly across the Jalali year boundary."""
    p = get_tracking_period(datetime(2026, 3, 21, 8, 0, tzinfo=UTC))  # 1 Farvardin 1405
    assert p["start_jalali"] == (1404, 12, 24)
    assert p["end_jalali"] == (1405, 1, 10)
    assert p["label"] == "دوره ۱۲ (۲۴ اسفند تا ۹ فروردین)"
