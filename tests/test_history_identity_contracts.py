"""Historical request identity survives profile edits; times remain explicit UTC."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models_multitenant import Client, Driver, DriverPlate, FuelInquiry, WaybillJob
from app.schemas.multitenant import FuelInquiryCreateRequest, FuelInquiryResponse
from app.services.fuel_inquiry_service import fuel_inquiry_service
from app.services.reporting_dates import parse_report_date_bounds
from app.services.user_reporting_service import user_reporting_service

pytestmark = pytest.mark.unit
OLD_PLATE = "12ب345ایران67"
NEW_PLATE = "23ع456ایران78"


def test_fuel_identity_migration_preserves_legacy_unknowns(monkeypatch: pytest.MonkeyPatch) -> None:
    path = Path(__file__).resolve().parents[1] / "alembic/versions/042_fuel_request_identity.py"
    spec = spec_from_file_location("fuel_identity_migration", path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE fuel_inquiries (id INTEGER PRIMARY KEY, status TEXT NOT NULL)"))
            connection.execute(text("INSERT INTO fuel_inquiries VALUES (1, 'success')"))
            monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
            migration.upgrade()
            row = connection.execute(text("SELECT * FROM fuel_inquiries")).mappings().one()
            assert row["status"] == "success"
            assert all(
                row[name] is None
                for name in ("plate_number_snapshot", "driver_name_snapshot", "started_at", "finished_at")
            )
            migration.downgrade()
            assert [column["name"] for column in inspect(connection).get_columns("fuel_inquiries")] == ["id", "status"]
    finally:
        engine.dispose()


@pytest.fixture
async def history_session() -> AsyncIterator[tuple[AsyncSession, Client, Driver, DriverPlate]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)
        async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
            client = Client(
                client_code="history",
                name="History",
                email="history@example.invalid",
                username="history",
                full_name="History",
                hashed_password="test-only",
            )
            session.add(client)
            await session.flush()
            driver = Driver(
                client_id=client.id,
                driver_national_code="0084575948",
                full_name="نام هنگام درخواست",
                utcms_username="unused",
                utcms_password_encrypted="unused",
            )
            session.add(driver)
            await session.flush()
            plate = DriverPlate(client_id=client.id, driver_id=driver.id, plate_number=OLD_PLATE, status="active")
            session.add(plate)
            await session.commit()
            yield session, client, driver, plate
    finally:
        await engine.dispose()


async def test_fuel_request_identity_survives_profile_changes_and_filters_history(history_session) -> None:
    session, client, driver, plate = history_session
    with patch("app.workers.tasks.dispatch_fuel_inquiry_task"):
        created = await fuel_inquiry_service.create_inquiry(
            client, FuelInquiryCreateRequest(driver_id=driver.id, year=1405, month=6), session
        )
    requested_name = driver.full_name
    driver.full_name, plate.plate_number = "نام جدید", NEW_PLATE
    session.add_all([driver, plate])
    await session.commit()
    for result in (
        await fuel_inquiry_service.get_inquiry(client, created.id, session),
        (await fuel_inquiry_service.list_inquiries(client, 1, 10, session)).items[0],
    ):
        assert result.plate_number == OLD_PLATE
        assert result.driver_name == requested_name
        assert result.plate_source == result.driver_name_source == "request_snapshot"
    assert (await fuel_inquiry_service.list_inquiries(client, 1, 10, session, plate_number=OLD_PLATE)).total == 1
    assert (await fuel_inquiry_service.list_inquiries(client, 1, 10, session, plate_number=NEW_PLATE)).total == 0


async def test_legacy_fuel_identity_is_unknown_instead_of_fabricated(history_session) -> None:
    session, client, driver, _plate = history_session
    legacy = FuelInquiry(client_id=client.id, driver_id=driver.id, status="success", year=1405, month=6)
    session.add(legacy)
    await session.commit()
    result = await fuel_inquiry_service.get_inquiry(client, legacy.id, session)
    assert result.plate_number is None
    assert result.plate_source == "legacy_unknown"
    assert result.driver_name_source == "current_driver"
    assert result.started_at is result.finished_at is None


async def test_legacy_pending_inquiry_never_submits_current_plate(history_session) -> None:
    session, client, driver, _plate = history_session
    legacy = FuelInquiry(client_id=client.id, driver_id=driver.id, status="pending")
    session.add(legacy)
    await session.commit()
    with patch("app.services.fuel_inquiry_service.FuelScraper.scrape_fuel_quota", new=AsyncMock()) as scrape:
        await fuel_inquiry_service.run_automation(legacy.id, session)
    await session.refresh(legacy)
    assert legacy.status == "failed"
    assert legacy.finished_at is not None
    scrape.assert_not_awaited()


async def test_worker_uses_request_plate_and_persists_execution_times(history_session) -> None:
    session, client, driver, plate = history_session
    with patch("app.workers.tasks.dispatch_fuel_inquiry_task"):
        created = await fuel_inquiry_service.create_inquiry(
            client, FuelInquiryCreateRequest(driver_id=driver.id), session
        )
    plate.plate_number = NEW_PLATE
    session.add(plate)
    await session.commit()
    scrape = AsyncMock(
        return_value={
            "success": True,
            "quota_data": {"tables": [{"rows": [["100"]]}]},
            "screenshot_url": "data:image/png;base64,test",
        }
    )

    @asynccontextmanager
    async def fake_browser_session(**_kwargs):
        yield "fixture", AsyncMock()

    with (
        patch("app.services.fuel_inquiry_service.managed_browser_session", new=fake_browser_session),
        patch("app.services.fuel_inquiry_service.browser_manager.initialize", new=AsyncMock()),
        patch("app.services.fuel_inquiry_service.browser_manager.new_page", new=AsyncMock(return_value=AsyncMock())),
        patch("app.automation.worker_proxy.get_playwright_proxy", return_value=None),
        patch("app.services.fuel_inquiry_service.FuelScraper.scrape_fuel_quota", new=scrape),
    ):
        await fuel_inquiry_service.run_automation(created.id, session)
    assert scrape.await_args.kwargs["plate_number"] == OLD_PLATE
    stored = await session.get(FuelInquiry, created.id)
    await session.refresh(stored)
    assert stored.status == "success"
    assert stored.created_at <= stored.started_at <= stored.finished_at
    assert stored.quota_data_json["tables"][0]["rows"] == [["100"]]


@pytest.mark.parametrize("aware", [False, True])
def test_fuel_timestamps_are_explicit_utc(aware: bool) -> None:
    stamp = datetime(2026, 10, 6, 10, 30)
    if aware:
        stamp = stamp.replace(tzinfo=timezone(timedelta(hours=3, minutes=30)))
    expected = stamp.astimezone(UTC) if aware else stamp.replace(tzinfo=UTC)
    row = FuelInquiry(id=1, client_id=1, driver_id=1, created_at=stamp, updated_at=stamp)
    serialized = FuelInquiryResponse.model_validate(row).model_dump(mode="json")
    assert datetime.fromisoformat(serialized["created_at"].replace("Z", "+00:00")) == expected
    assert serialized["created_at"].endswith(("Z", "+00:00"))


async def test_individual_histories_filter_driver_and_tehran_request_day(history_session) -> None:
    session, client, driver, plate = history_session
    boundary = datetime(2026, 10, 5, 20, 30)
    for index, stamp in enumerate((boundary - timedelta(microseconds=1), boundary, boundary + timedelta(days=1))):
        session.add(FuelInquiry(client_id=client.id, driver_id=driver.id, status="success", created_at=stamp))
        session.add(
            WaybillJob(
                job_id=f"history-{index}",
                idempotency_key=f"history-{index}",
                client_id=client.id,
                driver_id=driver.id,
                created_at=stamp,
                payload_json={"plate_number": OLD_PLATE},
            )
        )
    session.add(FuelInquiry(client_id=client.id, driver_id=999, status="success", created_at=boundary))
    plate.plate_number = NEW_PLATE
    session.add(plate)
    await session.commit()
    start, end = parse_report_date_bounds("2026-10-06", "2026-10-06")
    fuel = await fuel_inquiry_service.list_inquiries(
        client, 1, 10, session, driver_id=driver.id, date_from=start, date_to=end
    )
    jobs = await user_reporting_service.waybill_history(
        client, session, driver_id=driver.id, date_from="2026-10-06", date_to="2026-10-06"
    )
    assert fuel.total == jobs["total"] == 1
    assert jobs["jobs"][0]["job_id"] == "history-1"
    assert jobs["jobs"][0]["plate_number"] == OLD_PLATE
    assert jobs["jobs"][0]["plate_source"] == "payload_snapshot"
    assert jobs["jobs"][0]["created_at"].endswith(("Z", "+00:00"))


async def test_waybill_search_matches_displayed_historical_name_and_plate(history_session) -> None:
    session, client, driver, plate = history_session
    driver.full_name = "نام جدید"
    plate.status = "inactive"
    session.add(driver)
    session.add(plate)
    session.add(DriverPlate(client_id=client.id, driver_id=driver.id, plate_number=NEW_PLATE, status="active"))
    for job_id, payload in (
        ("frozen-name", {"driver_name": "نام قدیمی", "plate_number": OLD_PLATE}),
        ("legacy-name", {}),
    ):
        session.add(
            WaybillJob(
                job_id=job_id,
                idempotency_key=job_id,
                client_id=client.id,
                driver_id=driver.id,
                payload_json=payload,
            )
        )
    await session.commit()
    old_name = await user_reporting_service.waybill_history(client, session, driver_name="نام قدیمی")
    new_name = await user_reporting_service.waybill_history(client, session, driver_name="نام جدید")
    old_plate = await user_reporting_service.waybill_history(client, session, plate_number=OLD_PLATE)
    assert [row["job_id"] for row in old_name["jobs"]] == ["frozen-name"]
    assert [row["job_id"] for row in new_name["jobs"]] == ["legacy-name"]
    assert [row["job_id"] for row in old_plate["jobs"]] == ["frozen-name"]


def test_legacy_fuel_response_does_not_borrow_another_tenants_driver() -> None:
    inquiry = FuelInquiry(id=1, client_id=1, driver_id=2)
    unrelated_driver = Driver(id=2, client_id=9, driver_national_code="0084575948", full_name="نام خصوصی")
    response = fuel_inquiry_service._historical_response(inquiry, unrelated_driver)
    assert response.driver_name is None
    assert response.driver_name_source == "unknown"
