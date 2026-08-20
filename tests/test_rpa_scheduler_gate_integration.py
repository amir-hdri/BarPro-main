"""Integration tests for RPASchedulerService and UTCMSSubmissionGate."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import utcms_config
from app.models_multitenant import Client, Driver, DriverStatus, TaskSource, TaskStatus, WaybillJob
from app.rpa.contracts import SessionBundle
from app.services.rpa_runtime_service import rpa_runtime
from app.services.rpa_scheduler_service import rpa_scheduler_service
from app.services.utcms_submission_gate import utcms_submission_gate


@pytest.mark.asyncio
async def test_scheduler_holds_jobs_when_gate_closed():
    """Verify that when Gate is closed, scheduler transitions jobs to WAITING_SUBMISSION_WINDOW without burning attempts."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    with (
        patch("app.core.redis_client.redis_manager.get", new=AsyncMock(return_value=None)),
        patch("app.services.rpa_scheduler_service.async_session_factory", async_session),
    ):
        async with async_session() as session:
            client = Client(
                client_code="CLI-001",
                name="Tenant A",
                email="tenant_a@example.com",
                username="tenant_a",
                full_name="Tenant A Admin",
                hashed_password="hash",
                is_active=True,
            )
            session.add(client)
            await session.commit()
            await session.refresh(client)

            driver = Driver(
                client_id=client.id,
                driver_national_code="1234567890",
                full_name="Driver One",
                utcms_username="driver1",
                utcms_password_encrypted="enc_pwd",
                runtime_status=DriverStatus.READY.value,
                is_active=True,
            )
            session.add(driver)
            await session.commit()
            await session.refresh(driver)

        # Create job
        job = await rpa_scheduler_service.create_job(
            client_id=client.id,
            driver=driver,
            payload={"cargo": "iron"},
            source=TaskSource.MANUAL,
            max_retries=3,
            priority=5,
            correlation_id="corr-gate-1",
            idempotency_key="idem-gate-1",
        )

        # Prime active session
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

        # With Gate closed (OTP active)
        with (
            patch("app.core.redis_client.redis_manager.get", new=AsyncMock(return_value=None)),
            patch.object(utcms_submission_gate, "is_submission_allowed", new=AsyncMock(return_value=False)),
        ):
            plan = await rpa_scheduler_service.plan_due_jobs()
            assert len(plan) == 0

        async with async_session() as session:
            refreshed_job = (await session.exec(select(WaybillJob).where(WaybillJob.id == job.id))).first()
            assert refreshed_job.status == TaskStatus.WAITING_SUBMISSION_WINDOW.value
            assert refreshed_job.attempt_count == 0  # no attempt consumed!
            assert refreshed_job.submit_after is not None

    await engine.dispose()


@pytest.mark.asyncio
async def test_scheduler_releases_jobs_when_gate_opens():
    """Verify that when Gate opens (OTP free), jobs in WAITING_SUBMISSION_WINDOW are queued for submit."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    with (
        patch("app.core.redis_client.redis_manager.get", new=AsyncMock(return_value=None)),
        patch("app.services.rpa_scheduler_service.async_session_factory", async_session),
    ):
        async with async_session() as session:
            client = Client(
                client_code="CLI-002",
                name="Tenant B",
                email="tenant_b@example.com",
                username="tenant_b",
                full_name="Tenant B Admin",
                hashed_password="hash",
                is_active=True,
            )
            session.add(client)
            await session.commit()
            await session.refresh(client)

            driver = Driver(
                client_id=client.id,
                driver_national_code="9876543210",
                full_name="Driver Two",
                utcms_username="driver2",
                utcms_password_encrypted="enc_pwd",
                runtime_status=DriverStatus.READY.value,
                is_active=True,
            )
            session.add(driver)
            await session.commit()
            await session.refresh(driver)

            job = WaybillJob(
                job_id="job_sched_release_1",
                idempotency_key="idemp_rel_1",
                client_id=client.id,
                driver_id=driver.id,
                status=TaskStatus.WAITING_SUBMISSION_WINDOW.value,
                priority=5,
                payload_json={"test": "123"},
                attempt_count=0,
                submit_after=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=10),
            )
            session.add(job)
            await session.commit()

        # Prime active session
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

        # With Gate open (OTP free)
        with patch.object(utcms_submission_gate, "is_submission_allowed", new=AsyncMock(return_value=True)):
            plan = await rpa_scheduler_service.plan_due_jobs()
            assert len(plan) == 1
            assert plan[0].queue_name == utcms_config.RPA_SUBMIT_QUEUE
            assert plan[0].job_id == "job_sched_release_1"

        async with async_session() as session:
            refreshed_job = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job_sched_release_1"))).first()
            assert refreshed_job.status == TaskStatus.QUEUED.value

    await engine.dispose()
