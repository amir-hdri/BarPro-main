from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

import app.models_multitenant  # noqa: F401
import app.models_rpa  # noqa: F401
from app.core.submission_identity import (
    compute_canonical_job_idempotency_key,
    extract_reconciliation_identity,
)
from app.models_multitenant import Driver, DriverStatus, TaskSource
from app.queue.queue_manager import WaybillQueueManager
from app.schemas.waybill import WaybillMapRequest
from app.services.rpa_scheduler_service import RPASchedulerService
from app.services.task_service import WaybillTaskService


def test_build_idempotency_key_scopes_supplied_key_by_tenant() -> None:
    service = WaybillTaskService()
    payload = {
        "origin": {"province": "تهران", "city": "تهران", "address": "خیابان آزادی"},
        "destination": {"province": "البرز", "city": "کرج", "address": "بلوار جمهوری"},
        "vehicle": {"plate": "12A345-67"},
        "cargo": {"cargo_type": "آهن", "weight": 10},
    }

    key_t1 = service.build_idempotency_key(payload, provided="custom-key-123", client_id=1)
    key_t2 = service.build_idempotency_key(payload, provided="custom-key-123", client_id=2)

    # The same raw supplied key must map to different stored keys per tenant
    # (audit finding A1: no cross-tenant key collision is possible).
    assert key_t1 == "tenant:1:custom-key-123"
    assert key_t2 == "tenant:2:custom-key-123"
    assert key_t1 != key_t2


def test_build_idempotency_key_scoping_is_idempotent_for_prefixed_keys() -> None:
    service = WaybillTaskService()
    payload = {"sender": {"name": "x"}}

    key = service.build_idempotency_key(payload, provided="tenant:1:custom-key-123", client_id=1)
    assert key == "tenant:1:custom-key-123"


def test_build_idempotency_key_auto_key_is_deterministic_and_tenant_specific() -> None:
    service = WaybillTaskService()
    payload = {
        "origin": {"province": "تهران", "city": "تهران", "address": "خیابان آزادی"},
        "destination": {"province": "البرز", "city": "کرج", "address": "بلوار جمهوری"},
        "vehicle": {"plate": "12A345-67"},
        "cargo": {"cargo_type": "آهن", "weight": 10},
    }

    key_1a = service.build_idempotency_key(payload, provided=None, client_id=1)
    key_1b = service.build_idempotency_key(payload, provided=None, client_id=1)
    key_2 = service.build_idempotency_key(payload, provided=None, client_id=2)

    # Same tenant + same commercial payload => identical key (idempotent retries still dedup).
    assert key_1a == key_1b
    # Different tenant => different key even for identical payloads.
    assert key_1a != key_2


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

    key_1 = service.build_idempotency_key(payload_1, provided=None, client_id=1)
    key_2 = service.build_idempotency_key(payload_2, provided=None, client_id=1)

    # Identical commercial payload must produce the exact same key regardless of volatile metadata
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
        "sender": {
            "name": "علی محمدی",
            "phone": "09121111111",
            "address": "خیابان آزادی پلاک ۱",
            "national_code": "0084575948",
        },
        "receiver": {"name": "رضا کرمی", "phone": "09122222222", "address": "بلوار جمهوری پلاک ۲"},
        "origin": {"province": "تهران", "city": "تهران", "address": "خیابان آزادی پلاک ۱"},
        "destination": {"province": "البرز", "city": "کرج", "address": "بلوار جمهوری پلاک ۲"},
        "cargo": {"type": "مصالح", "packaging": "فله", "weight": 1000, "value": 1000000},
        "vehicle": {"driver_national_code": "0084575948", "driver_phone": "09123333333", "plate": "79ع989ایران84"},
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


@pytest.mark.asyncio
async def test_two_tenants_same_raw_idempotency_key_each_get_own_task_row() -> None:
    """A1 regression: tenant B submitting the SAME raw idempotency key as
    tenant A must get its OWN task row — never tenant A's job_id, and tenant
    B's payload must not be silently dropped.

    The old global behavior matched on the raw key without a client_id filter,
    so tenant B received ``reused=True`` with tenant A's task_id while B's own
    waybill vanished.
    """
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

    from app.models_multitenant import Client, ClientStatus

    async with test_session_factory() as session:
        for client_id, code in ((1, "TENANT_A"), (2, "TENANT_B")):
            session.add(
                Client(
                    id=client_id,
                    client_code=code,
                    name=f"tenant {code}",
                    email=f"{code}@example.com",
                    hashed_password="hash",
                    username=f"user_{code}",
                    full_name=f"tenant {code}",
                    status=ClientStatus.ACTIVE.value,
                )
            )
        await session.commit()

    payload_a = {
        "origin": {"province": "تهران", "city": "تهران", "address": "خیابان آزادی"},
        "destination": {"province": "البرز", "city": "کرج", "address": "بلوار جمهوری"},
        "vehicle": {"plate": "11A111-11"},
        "cargo": {"cargo_type": "آهن", "weight": 10},
    }
    payload_b = {
        "origin": {"province": "تهران", "city": "تهران", "address": "خیابان انقلاب"},
        "destination": {"province": "قم", "city": "قم", "address": "بلوار الغدیر"},
        "vehicle": {"plate": "22B222-22"},
        "cargo": {"cargo_type": "سیمان", "weight": 20},
    }

    service = WaybillTaskService()
    with patch("app.services.task_service.async_session_factory", test_session_factory):
        # Same raw supplied key, mirrored through the queue path's normalization.
        key_a = service.build_idempotency_key(payload_a, provided="shared-key", client_id=1)
        task_a, reused_a = await service.create_or_get_task(payload=dict(payload_a), idempotency_key=key_a, client_id=1)

        key_b = service.build_idempotency_key(payload_b, provided="shared-key", client_id=2)
        task_b, reused_b = await service.create_or_get_task(payload=dict(payload_b), idempotency_key=key_b, client_id=2)

    # Tenant B must NOT hijack tenant A's task: two distinct rows, no reuse.
    assert reused_a is False
    assert reused_b is False
    assert task_a["task_id"] != task_b["task_id"]
    assert task_a["client_id"] == 1
    assert task_b["client_id"] == 2
    # Keys are tenant-scoped at rest, so the global UNIQUE constraint on
    # idempotency_key can never collide across tenants.
    assert task_a["idempotency_key"] == "tenant:1:shared-key"
    assert task_b["idempotency_key"] == "tenant:2:shared-key"

    with patch("app.services.task_service.async_session_factory", test_session_factory):
        # Tenant B's payload was persisted, not silently dropped.
        stored_b = await service.get_payload(task_b["task_id"])
    assert stored_b is not None
    assert stored_b["vehicle"]["plate"] == "22B222-22"
    assert stored_b["cargo"]["cargo_type"] == "سیمان"

    await test_engine.dispose()


@pytest.mark.asyncio
async def test_same_tenant_same_raw_key_reuses_own_task() -> None:
    """Within one tenant, resubmitting the same raw idempotency key must still
    dedup to that tenant's OWN existing task (idempotent retries keep working)."""
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

    from app.models_multitenant import Client, ClientStatus

    async with test_session_factory() as session:
        session.add(
            Client(
                id=1,
                client_code="TENANT_A",
                name="tenant A",
                email="a@example.com",
                hashed_password="hash",
                username="user_a",
                full_name="tenant A",
                status=ClientStatus.ACTIVE.value,
            )
        )
        await session.commit()

    payload = {
        "origin": {"province": "تهران", "city": "تهران", "address": "خیابان آزادی"},
        "destination": {"province": "البرز", "city": "کرج", "address": "بلوار جمهوری"},
        "vehicle": {"plate": "11A111-11"},
        "cargo": {"cargo_type": "آهن", "weight": 10},
    }

    service = WaybillTaskService()
    with patch("app.services.task_service.async_session_factory", test_session_factory):
        key = service.build_idempotency_key(payload, provided="retry-key", client_id=1)
        first, reused_first = await service.create_or_get_task(payload=dict(payload), idempotency_key=key, client_id=1)
        key_again = service.build_idempotency_key(payload, provided="retry-key", client_id=1)
        second, reused_second = await service.create_or_get_task(
            payload=dict(payload), idempotency_key=key_again, client_id=1
        )

    assert reused_first is False
    assert reused_second is True
    assert second["task_id"] == first["task_id"]
    assert second["client_id"] == 1

    await test_engine.dispose()
