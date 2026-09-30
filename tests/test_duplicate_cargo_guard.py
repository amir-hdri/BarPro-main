import pytest
from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models_multitenant import Client, Driver, DriverPlate, WaybillJob
from app.schemas.multitenant import WaybillJobCreateRequest
from app.services.waybill_job_service import WaybillJobService


@pytest.fixture
async def async_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session = AsyncSession(engine, expire_on_commit=False)
    yield session
    await session.close()
    await engine.dispose()


@pytest.fixture
async def setup_client_and_driver(async_db: AsyncSession):
    client = Client(
        id=1,
        client_code="CLI001",
        name="Test Company",
        email="test@example.com",
        username="test_client",
        full_name="Test Company LLC",
        hashed_password="hashed_pw_dummy",
    )
    async_db.add(client)
    await async_db.flush()

    driver = Driver(
        id=1,
        client_id=client.id,
        driver_national_code="0084575948",
        full_name="علی رضایی",
        phone="09123456789",
        status="active",
        utcms_username="0084575948",
        utcms_password_encrypted="encrypted_pw",
    )
    async_db.add(driver)
    await async_db.flush()

    plate = DriverPlate(
        id=1,
        client_id=client.id,
        driver_id=driver.id,
        plate_number="27ع799ایران32",
        vehicle_type="کامیون",
        status="active",
    )
    async_db.add(plate)
    await async_db.commit()

    return client, driver, plate


from app.schemas.multitenant import WaybillJobCreateRequest, WaybillPayload


def make_payload():
    return WaybillPayload(
        driver_national_code="0084575948",
        origin="کاشمر",
        destination="کاشمر",
        cargo_type="سیمان",
        cargo_packaging="فله",
        cargo_weight=15000.0,
        cargo_value="50000000",
        vehicle_type="کامیون",
        plate_number="27ع799ایران32",
        driver_phone="09123456789",
        sender_phone="09121111111",
        receiver_phone="09122222222",
        metadata_json={
            "sender": {"name": "شرکت مبدا", "national_code": "4929889601"},
            "receiver": {"name": "شرکت مقصد", "national_code": "0321410408"},
            "origin": {"province": "خراسان رضوی", "city": "کاشمر", "address": "خیابان منتظری ۲۵"},
            "destination": {"province": "خراسان رضوی", "city": "کاشمر", "address": "بلوار معلم"},
            "cargo": {"type": "سیمان", "packaging": "فله", "weight": 15000, "value": "50000000"},
            "vehicle": {"driver_national_code": "0084575948", "plate": "27ع799ایران32", "type": "کامیون"},
        },
    )


@pytest.mark.asyncio
async def test_create_job_rejects_busy_in_transit_driver(async_db: AsyncSession, setup_client_and_driver):
    client, driver, plate = setup_client_and_driver

    # Existing active in_transit job
    existing_job = WaybillJob(
        job_id="job_active_1",
        idempotency_key="idemp_1",
        client_id=client.id,
        driver_id=driver.id,
        status="in_transit",
        payload_json=make_payload().model_dump(),
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )
    async_db.add(existing_job)
    await async_db.commit()

    req = WaybillJobCreateRequest(
        driver_national_code=driver.driver_national_code,
        payload=make_payload(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await WaybillJobService.create_job(client, req, async_db)

    assert exc_info.value.status_code == 409
    assert "فعال" in exc_info.value.detail or "در حال حمل" in exc_info.value.detail


@pytest.mark.asyncio
async def test_create_job_rejects_duplicate_cargo_within_24h(async_db: AsyncSession, setup_client_and_driver):
    client, driver, plate = setup_client_and_driver

    from app.workers.waybill_worker import generate_submission_fingerprint
    from app.automation.multitenant_payload_adapter import build_enhanced_waybill_payload

    payload = make_payload()
    enhanced = build_enhanced_waybill_payload(payload.model_dump())
    fp = generate_submission_fingerprint(enhanced)

    # Existing recent job with identical cargo fingerprint created 2 hours ago
    existing_job = WaybillJob(
        job_id="job_recent_1",
        idempotency_key="idemp_2",
        client_id=client.id,
        driver_id=driver.id,
        status="success",
        submission_fingerprint=fp,
        payload_json=payload.model_dump(),
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2),
    )
    async_db.add(existing_job)
    await async_db.commit()

    req = WaybillJobCreateRequest(
        driver_national_code=driver.driver_national_code,
        payload=payload,
    )

    with pytest.raises(HTTPException) as exc_info:
        await WaybillJobService.create_job(client, req, async_db)

    assert exc_info.value.status_code == 409
    assert "تکراری" in exc_info.value.detail or "مشابه" in exc_info.value.detail or "۲۴ ساعت" in exc_info.value.detail


@pytest.mark.asyncio
async def test_create_job_succeeds_when_different_cargo_or_not_busy(async_db: AsyncSession, setup_client_and_driver):
    client, driver, plate = setup_client_and_driver

    # Previous job was cancelled (not busy)
    existing_job = WaybillJob(
        job_id="job_old_cancelled",
        idempotency_key="idemp_old",
        client_id=client.id,
        driver_id=driver.id,
        status="cancelled",
        payload_json=make_payload().model_dump(),
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=10),
    )
    async_db.add(existing_job)
    await async_db.commit()

    req = WaybillJobCreateRequest(
        driver_national_code=driver.driver_national_code,
        payload=make_payload(),
    )

    mock_created_job = WaybillJob(
        id=999,
        job_id="job_new_created",
        idempotency_key="idemp_new",
        client_id=client.id,
        driver_id=driver.id,
        status="pending",
        payload_json=make_payload().model_dump(),
    )

    with patch("app.services.waybill_job_service.rpa_scheduler_service.create_job", new_callable=AsyncMock, return_value=mock_created_job):
        resp = await WaybillJobService.create_job(client, req, async_db)

    assert resp.job_id == "job_new_created"
    assert resp.status == "pending"
