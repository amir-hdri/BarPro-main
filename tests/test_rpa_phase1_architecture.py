from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from app.core.business_time import business_date_str
from app.models_multitenant import Client, Driver, TaskSource, TaskStatus, WaybillJob
from app.models_rpa import DriverRuntimeState
from app.rpa.contracts import SessionBundle
from app.services.rpa_auth_service import rpa_auth_service
from app.services.rpa_dispatch_service import rpa_dispatch_service
from app.services.rpa_runtime_service import rpa_runtime
from app.services.rpa_scheduler_service import rpa_scheduler_service
from app.services.rpa_submit_service import build_job_idempotency_key, classify_submit_response


@pytest.mark.asyncio
async def test_phase1_scheduler_routes_job_to_auth_then_submit():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    from sqlmodel.ext.asyncio.session import AsyncSession

    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session() as session:
        client = Client(
            client_code="tenant-a",
            name="Tenant A",
            email="a@example.com",
            hashed_password="hash",
            username="tenant_a",
            full_name="Tenant A Admin",
        )
        session.add(client)
        await session.commit()
        await session.refresh(client)
        driver = Driver(
            client_id=client.id,
            driver_national_code="1234567890",
            full_name="Driver One",
            utcms_username="driver1",
            utcms_password_encrypted="enc",
        )
        session.add(driver)
        await session.commit()
        await session.refresh(driver)

    payload = {"driver_national_code": "1234567890", "origin": "تهران", "destination": "قم"}
    with (
        patch("app.services.rpa_scheduler_service.async_session_factory", new=async_session),
        patch("app.services.rpa_runtime_service.redis_manager.get", new=AsyncMock(return_value=None)),
        patch("app.services.rpa_scheduler_service.utcms_submission_gate.is_submission_allowed", new=AsyncMock(return_value=True)),
    ):
        rpa_runtime._memory.clear()
        first = await rpa_scheduler_service.create_job(
            client_id=client.id,
            driver=driver,
            payload=payload,
            source=TaskSource.MANUAL,
            max_retries=3,
            priority=7,
            correlation_id="corr-1",
            idempotency_key="idem-1",
        )
        reused = await rpa_scheduler_service.create_job(
            client_id=client.id,
            driver=driver,
            payload=payload,
            source=TaskSource.MANUAL,
            max_retries=3,
            priority=7,
            correlation_id="corr-1",
            idempotency_key="idem-1",
        )
        assert first.job_id == reused.job_id

        auth_plan = await rpa_scheduler_service.plan_due_jobs()
        assert len(auth_plan) == 1
        assert auth_plan[0].queue_name == "rpa_auth"

        await rpa_runtime.store_session(
            client.id,
            driver.id,
            SessionBundle(
                cookies=[{"name": "sessionid", "value": "abc"}],
                user_agent="ua",
                issued_at=datetime.now(UTC).replace(tzinfo=None).isoformat(),
                expires_at=datetime.now(UTC).replace(tzinfo=None).isoformat(),
                session_version=1,
            ),
        )
        async with async_session() as db_session:
            statement = select(WaybillJob).where(WaybillJob.client_id == client.id)
            job = (await db_session.exec(statement)).first()
            job.status = TaskStatus.QUEUED.value
            job.submit_after = None
            db_session.add(job)
            await db_session.commit()

        submit_plan = await rpa_scheduler_service.plan_due_jobs()
        assert len(submit_plan) == 1
        assert submit_plan[0].queue_name == "rpa_submit"

    await engine.dispose()


@pytest.mark.asyncio
async def test_phase1_scheduler_respects_daily_attempt_cap():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    from sqlmodel.ext.asyncio.session import AsyncSession

    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session() as session:
        client = Client(
            client_code="tenant-b",
            name="Tenant B",
            email="b@example.com",
            hashed_password="hash",
            username="tenant_b",
            full_name="Tenant B Admin",
        )
        session.add(client)
        await session.commit()
        await session.refresh(client)
        driver = Driver(
            client_id=client.id,
            driver_national_code="2234567890",
            full_name="Driver Two",
            utcms_username="driver2",
            utcms_password_encrypted="enc",
        )
        session.add(driver)
        await session.commit()
        await session.refresh(driver)

    with (
        patch("app.services.rpa_scheduler_service.async_session_factory", new=async_session),
        patch("app.services.rpa_runtime_service.redis_manager.get", new=AsyncMock(return_value=None)),
        patch("app.core.config.utcms_config.DRIVER_DAILY_ATTEMPT_CAP", 2),
    ):
        rpa_runtime._memory.clear()
        await rpa_scheduler_service.create_job(
            client.id, driver, {"x": 1}, TaskSource.MANUAL, 1, idempotency_key="idem-a"
        )
        await rpa_runtime.increment_attempt(client.id, driver.id)
        await rpa_runtime.increment_attempt(client.id, driver.id)
        decisions = await rpa_scheduler_service.plan_due_jobs()
        assert decisions == []
        async with async_session() as session:
            runtime = (await session.exec(select(DriverRuntimeState))).first()
            job = (await session.exec(select(WaybillJob))).first()
            assert runtime.state == "daily_attempt_limit_reached"
            assert job.status == TaskStatus.DAILY_LIMIT_REACHED.value

    await engine.dispose()


@pytest.mark.asyncio
async def test_phase1_scheduler_does_not_stick_job_during_tenant_cooldown():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    from sqlmodel.ext.asyncio.session import AsyncSession

    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session() as session:
        client = Client(
            client_code="tenant-c",
            name="Tenant C",
            email="c@example.com",
            hashed_password="hash",
            username="tenant_c",
            full_name="Tenant C Admin",
        )
        session.add(client)
        await session.commit()
        await session.refresh(client)
        driver = Driver(
            client_id=client.id,
            driver_national_code="3234567890",
            full_name="Driver Three",
            utcms_username="driver3",
            utcms_password_encrypted="enc",
        )
        session.add(driver)
        await session.commit()
        await session.refresh(driver)

    with (
        patch("app.services.rpa_scheduler_service.async_session_factory", new=async_session),
        patch("app.services.rpa_runtime_service.redis_manager.get", new=AsyncMock(return_value=None)),
    ):
        rpa_runtime._memory.clear()
        await rpa_scheduler_service.create_job(
            client.id, driver, {"x": 1}, TaskSource.MANUAL, 1, idempotency_key="idem-c"
        )
        await rpa_runtime.apply_cooldown("tenant", str(client.id), 300)

        decisions = await rpa_scheduler_service.plan_due_jobs()
        assert decisions == []

        async with async_session() as session:
            job = (await session.exec(select(WaybillJob))).first()
            assert job.status == TaskStatus.PENDING.value

    await engine.dispose()


@pytest.mark.asyncio
async def test_phase1_scheduler_preview_has_no_side_effects():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    from sqlmodel.ext.asyncio.session import AsyncSession

    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session() as session:
        client = Client(
            client_code="tenant-preview",
            name="Tenant Preview",
            email="preview@example.com",
            hashed_password="hash",
            username="tenant_preview",
            full_name="Tenant Preview Admin",
        )
        session.add(client)
        await session.commit()
        await session.refresh(client)
        driver = Driver(
            client_id=client.id,
            driver_national_code="4234567890",
            full_name="Driver Preview",
            utcms_username="driver-preview",
            utcms_password_encrypted="enc",
        )
        session.add(driver)
        await session.commit()
        await session.refresh(driver)

    with (
        patch("app.services.rpa_scheduler_service.async_session_factory", new=async_session),
        patch("app.services.rpa_runtime_service.redis_manager.get", new=AsyncMock(return_value=None)),
    ):
        rpa_runtime._memory.clear()
        await rpa_scheduler_service.create_job(
            client.id, driver, {"x": 1}, TaskSource.MANUAL, 1, idempotency_key="idem-preview"
        )
        preview = await rpa_scheduler_service.plan_due_jobs(persist=False)
        assert len(preview) == 1
        assert preview[0].queue_name == "rpa_auth"

        async with async_session() as session:
            job = (await session.exec(select(WaybillJob))).first()
            assert job.status == TaskStatus.PENDING.value
            assert job.celery_task_id is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_phase1_dispatch_due_jobs_enqueues_auth_task_and_persists_task_id():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    from sqlmodel.ext.asyncio.session import AsyncSession

    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session() as session:
        client = Client(
            client_code="tenant-dispatch",
            name="Tenant Dispatch",
            email="dispatch@example.com",
            hashed_password="hash",
            username="tenant_dispatch",
            full_name="Tenant Dispatch Admin",
        )
        session.add(client)
        await session.commit()
        await session.refresh(client)
        driver = Driver(
            client_id=client.id,
            driver_national_code="5234567890",
            full_name="Driver Dispatch",
            utcms_username="driver-dispatch",
            utcms_password_encrypted="enc",
        )
        session.add(driver)
        await session.commit()
        await session.refresh(driver)

    fake_result = SimpleNamespace(id="celery-auth-1")
    fake_celery = SimpleNamespace(send_task=lambda *args, **kwargs: fake_result)

    with (
        patch("app.services.rpa_scheduler_service.async_session_factory", new=async_session),
        patch("app.services.rpa_dispatch_service.async_session_factory", new=async_session),
        patch("app.services.rpa_runtime_service.redis_manager.get", new=AsyncMock(return_value=None)),
        patch(
            "app.services.rpa_dispatch_service.celery_app",
            fake_celery,
        ),
        patch(
            "app.core.circuit_breaker.get_routed_queue_async",
            new=AsyncMock(side_effect=lambda x: x),
        ),
    ):
        rpa_runtime._memory.clear()
        await rpa_scheduler_service.create_job(
            client.id, driver, {"x": 1}, TaskSource.MANUAL, 1, idempotency_key="idem-dispatch"
        )
        dispatched = await rpa_dispatch_service.dispatch_phase1_due_jobs()

        assert len(dispatched) == 1
        assert dispatched[0]["queue_name"] == "rpa_auth"
        assert dispatched[0]["status"] == "queued"
        assert dispatched[0]["celery_task_id"] == "celery-auth-1"

        async with async_session() as session:
            job = (await session.exec(select(WaybillJob))).first()
            assert job.status == TaskStatus.WAITING_AUTH.value
            assert job.celery_task_id == "celery-auth-1"

    await engine.dispose()


@pytest.mark.asyncio
async def test_phase1_auth_success_dispatches_submit_for_resume_job():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    from sqlmodel.ext.asyncio.session import AsyncSession

    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session() as session:
        client = Client(
            client_code="tenant-auth-flow",
            name="Tenant Auth Flow",
            email="authflow@example.com",
            hashed_password="hash",
            username="tenant_auth_flow",
            full_name="Tenant Auth Flow Admin",
        )
        session.add(client)
        await session.commit()
        await session.refresh(client)
        driver = Driver(
            client_id=client.id,
            driver_national_code="6234567890",
            full_name="Driver Auth Flow",
            utcms_username="driver-auth-flow",
            utcms_password_encrypted="enc",
        )
        session.add(driver)
        await session.commit()
        await session.refresh(driver)
        job = WaybillJob(
            job_id="job-auth-flow",
            idempotency_key="tenant:1:auth-flow",
            client_id=client.id,
            driver_id=driver.id,
            status=TaskStatus.WAITING_AUTH.value,
            source=TaskSource.MANUAL.value,
            payload_json='{"x": 1}',
            max_retries=1,
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)

    fake_page = AsyncMock()
    fake_page.evaluate = AsyncMock(return_value="ua")
    fake_page.close = AsyncMock()
    fake_context = AsyncMock()
    fake_context.cookies = AsyncMock(return_value=[{"name": "sessionid", "value": "abc"}])

    class FakeAuthenticator:
        def __init__(self, page, context):
            self.last_error = None

        async def login(self, *_args, **_kwargs):
            return True

    async def fake_followup_dispatch(client_id, job_id, page, context, session_bundle):
        from app.models_multitenant import TaskStatus, WaybillJob
        from app.services.rpa_submit_service import SubmitOutcome

        async with async_session() as session:
            job = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == job_id))).first()
            if job:
                job.celery_task_id = "celery-submit-1"
                job.status = TaskStatus.QUEUED.value
                session.add(job)
                await session.commit()

        # Define a mock SubmitResult object with the required properties
        class MockSubmitResult:
            def __init__(self, classification, raw_response, driver_message, business_date):
                self.classification = classification
                self.raw_response = raw_response
                self.driver_message = driver_message
                self.business_date = business_date

        class MockSubmitClassification:
            def __init__(self, outcome, reason_code, next_retry_after_minutes):
                self.outcome = outcome
                self.reason_code = reason_code
                self.next_retry_after_minutes = next_retry_after_minutes

        return MockSubmitResult(
            classification=MockSubmitClassification(
                outcome=SubmitOutcome.SUCCESS, reason_code="portal_success", next_retry_after_minutes=0
            ),
            raw_response="success",
            driver_message="success",
            business_date="2025-01-01",
        )

    with (
        patch("app.services.rpa_auth_service.async_session_factory", new=async_session),
        patch("app.services.rpa_runtime_service.redis_manager.get", new=AsyncMock(return_value=None)),
        patch(
            "app.services.rpa_auth_service.decrypt_driver_password",
            return_value="password",
        ),
        patch("app.services.rpa_auth_service.browser_manager.initialize", new=AsyncMock()),
        patch(
            "app.services.rpa_auth_service.browser_manager.create_context",
            new=AsyncMock(return_value=("session-auth", fake_context)),
        ),
        patch("app.services.rpa_auth_service.browser_manager.new_page", new=AsyncMock(return_value=fake_page)),
        patch(
            "app.services.rpa_auth_service.browser_manager.save_auth_state",
            new=AsyncMock(),
        ),
        patch("app.services.rpa_auth_service.browser_manager.close_context", new=AsyncMock()),
        patch(
            "app.services.rpa_auth_service.UTCMSAuthenticator",
            FakeAuthenticator,
        ),
        patch("app.services.rpa_auth_service.session_vault.ensure_parent_dir"),
        patch(
            "app.services.rpa_auth_service.rpa_submit_service.process_job_live",
            new=AsyncMock(side_effect=fake_followup_dispatch),
        ) as followup_dispatch,
    ):
        rpa_runtime._memory.clear()
        result = await rpa_auth_service.authenticate_driver(
            client_id=client.id,
            driver_id=driver.id,
            reason="auth_required",
            resume_job_id="job-auth-flow",
        )
        assert result.ok is True
        assert followup_dispatch.await_count == 1

        async with async_session() as session:
            job = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-auth-flow"))).first()
            assert job.status == TaskStatus.QUEUED.value
            assert job.celery_task_id is not None

    await engine.dispose()


def test_phase1_supplied_idempotency_key_is_tenant_scoped():
    key_one = build_job_idempotency_key(1, 10, {"x": 1}, supplied="shared-key")
    key_two = build_job_idempotency_key(2, 10, {"x": 1}, supplied="shared-key")

    assert key_one != key_two
    assert len(key_one) <= 100
    assert len(key_two) <= 100


def test_phase1_business_date_uses_tehran_calendar_day():
    utc_time = datetime(2025, 1, 1, 20, 45, tzinfo=UTC)
    assert business_date_str(utc_time) == "2025-01-02"


def test_phase1_submit_classifier_maps_auth_and_duplicate_errors():
    auth = classify_submit_response(403, "Please login again")
    duplicate = classify_submit_response(409, "duplicate request")
    success = classify_submit_response(200, "operation success")
    explicit_fail = classify_submit_response(200, '{"success": false, "message": "Driver not eligible"}')

    assert auth.reason_code == "session_expired"
    assert duplicate.reason_code == "duplicate_registration"
    assert success.reason_code == "portal_success"
    assert explicit_fail.outcome.value == "validation_error"
    assert explicit_fail.reason_code == "portal_validation_error"
    assert explicit_fail.message == "Driver not eligible"
