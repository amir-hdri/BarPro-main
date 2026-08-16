import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

import app.models_rpa  # noqa: F401
import app.models_multitenant  # noqa: F401
from app.core.submission_identity import (
    compute_canonical_job_idempotency_key,
    compute_canonical_payload_digest,
    extract_canonical_commercial_payload,
    extract_reconciliation_identity,
)
from app.models_multitenant import Driver, DriverStatus, TaskSource, WaybillJob
from app.queue.queue_manager import WaybillQueueManager
from app.schemas.waybill import WaybillMapRequest
from app.services.rpa_scheduler_service import RPASchedulerService
from app.services.task_service import WaybillTaskService


def test_build_idempotency_key_handles_none_provided_without_unbound_error() -> None:
    service = WaybillTaskService()
    payload = {
        "origin": {"province": "تهران", "city": "تهران", "address": "خیابان آزادی"},
        "destination": {"province": "البرز", "city": "کرج", "address": "بلوار جمهوری"},
        "vehicle": {"plate": "12A345-67"},
        "cargo": {"cargo_type": "آهن", "weight": 10},
    }

    # Should not raise UnboundLocalError when provided is None
    key_auto = service.build_idempotency_key(payload, provided=None)
    assert key_auto.startswith("auto-")

    # Should use provided key when provided
    key_user = service.build_idempotency_key(payload, provided="custom-key-123")
    assert key_user == "custom-key-123"


def test_idempotency_ignores_volatile_fields_and_is_deterministic() -> None:
    service = WaybillTaskService()
    base_payload = {
        "origin": {"province": "تهران", "city": "تهران", "address": "خیابان آزادی"},
        "destination": {"province": "البرز", "city": "کرج", "address": "بلوار جمهوری"},
        "vehicle": {"plate": "12A345-67"},
        "cargo": {"cargo_type": "آهن", "weight": 10},
    }

    payload_1 = {
        **base_payload,
        "correlation_id": "corr-random-1111",
        "session_id": "sess-random-aaaa",
        "batch_id": "batch-1",
        "timestamp": 1700000001,
    }

    payload_2 = {
        **base_payload,
        "correlation_id": "corr-random-2222",
        "session_id": "sess-random-bbbb",
        "batch_id": "batch-2",
        "timestamp": 1700000999,
    }

    key_1 = service.build_idempotency_key(payload_1, provided=None)
    key_2 = service.build_idempotency_key(payload_2, provided=None)

    # Identical commercial payload must produce the exact same auto key regardless of volatile metadata
    assert key_1 == key_2


def test_extract_reconciliation_identity_supports_vehicle_plate() -> None:
    # 1. vehicle.plate
    payload_plate = {
        "vehicle": {"plate": "12-ج-345-67"},
        "origin": {"city": "تهران"},
    }
    identity_1 = extract_reconciliation_identity(payload_plate)
    assert identity_1.plate_number == "12-ج-345-67"

    # 2. vehicle.plate_number
    payload_plate_number = {
        "vehicle": {"plate_number": "12-ج-345-67"},
        "origin": {"city": "تهران"},
    }
    identity_2 = extract_reconciliation_identity(payload_plate_number)
    assert identity_2.plate_number == "12-ج-345-67"

    # 3. Different plates produce different idempotency keys
    payload_other_plate = {
        "vehicle": {"plate": "99-ب-888-77"},
        "origin": {"city": "تهران"},
    }
    key_1 = compute_canonical_job_idempotency_key(client_id=1, driver_id=10, payload=payload_plate)
    key_other = compute_canonical_job_idempotency_key(client_id=1, driver_id=10, payload=payload_other_plate)
    assert key_1 != key_other


@pytest.mark.asyncio
async def test_queue_manager_reused_job_returns_existing_state() -> None:
    qm = WaybillQueueManager()
    request_data = {
        "session_id": "queue-test",
        "sender": {"name": "علی محمدی", "phone": "09121111111", "address": "خیابان آزادی", "national_code": "1234567890"},
        "receiver": {"name": "رضا کرمی", "phone": "09122222222", "address": "بلوار جمهوری"},
        "origin": {"province": "تهران", "city": "تهران", "address": "خیابان آزادی"},
        "destination": {"province": "البرز", "city": "کرج", "address": "بلوار جمهوری"},
        "cargo": {"type": "مصالح", "packaging": "فله", "weight": 1000, "value": 1000000},
        "vehicle": {"driver_national_code": "1234567890", "plate": "79ع989ایران84"},
        "financial": {},
    }
    request = WaybillMapRequest.model_validate(request_data)

    mock_existing_task = {
        "task_id": "job_existing_123",
        "idempotency_key": "auto-abc123",
        "status": "pending",
        "correlation_id": "corr_original_999",
        "celery_task_id": "celery_task_abc",
    }

    with patch("app.services.task_service.task_service.create_or_get_task", return_value=(mock_existing_task, True)):
        response = await qm.enqueue_waybill(request, client_id=1, driver_id=5, idempotency_key=None)

        assert response.reused is True
        assert response.task_id == "job_existing_123"
        assert response.idempotency_key == "auto-abc123"
        assert response.correlation_id == "corr_original_999"


@pytest.mark.asyncio
async def test_rpa_scheduler_create_job_concurrent_deduplication() -> None:
    from sqlalchemy.pool import StaticPool
    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    test_session_factory = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    scheduler = RPASchedulerService()

    from app.models_multitenant import Client, ClientStatus

    client = Client(
        id=1,
        client_code="CLIENT01",
        name="شرکت باربری آزمایشی",
        email="test@example.com",
        hashed_password="hash",
        username="client_test",
        full_name="شرکت آزمایشی",
        status=ClientStatus.ACTIVE.value,
    )

    driver = Driver(
        id=1,
        client_id=1,
        driver_national_code="0012345678",
        full_name="علی محمدی",
        phone="09121111111",
        status=DriverStatus.ACTIVE.value,
        utcms_username="test_user",
        utcms_password_encrypted="enc_pass",
    )

    from app.models_rpa import DriverRuntimeState, DriverRuntimeStateValue

    runtime_state = DriverRuntimeState(
        client_id=1,
        driver_id=1,
        state=DriverRuntimeStateValue.READY.value,
    )

    async with test_session_factory() as session:
        session.add(client)
        session.add(driver)
        session.add(runtime_state)
        await session.commit()

    payload = {
        "origin": {"province": "تهران", "city": "تهران", "address": "خیابان آزادی"},
        "destination": {"province": "البرز", "city": "کرج", "address": "بلوار جمهوری"},
        "vehicle": {"plate": "12A345-67"},
        "cargo": {"cargo_type": "آهن", "weight": 10},
    }

    with patch("app.services.rpa_scheduler_service.async_session_factory", test_session_factory):
        # 1. Sequential duplicate submission must return existing job
        first_job = await scheduler.create_job(
            client_id=1,
            driver=driver,
            payload=payload,
            source=TaskSource.MANUAL,
            max_retries=3,
        )
        second_job = await scheduler.create_job(
            client_id=1,
            driver=driver,
            payload=payload,
            source=TaskSource.MANUAL,
            max_retries=3,
        )
        assert first_job.job_id == second_job.job_id
        assert first_job.idempotency_key == second_job.idempotency_key

    await test_engine.dispose()
