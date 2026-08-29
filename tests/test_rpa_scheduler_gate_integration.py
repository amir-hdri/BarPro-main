"""Integration tests for RPASchedulerService and UTCMSSubmissionGate."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import utcms_config
from app.models.waybill_batch import WaybillBatch
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
            submit_after=datetime.now(UTC).replace(tzinfo=None),
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
            refreshed_job = (
                await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job_sched_release_1"))
            ).first()
            assert refreshed_job.status == TaskStatus.QUEUED.value

    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("predecessor_status", "expected_job_ids"),
    [
        (TaskStatus.PENDING.value, ["chain_leg_0"]),
        (TaskStatus.RUNNING.value, []),
        (TaskStatus.UNKNOWN.value, []),
        (TaskStatus.FAILED.value, []),
        (TaskStatus.CANCELLED.value, []),
    ],
)
async def test_route_chain_never_dispatches_downstream_before_predecessor_success(
    predecessor_status, expected_job_ids
):
    """A chain queues only the first leg until its predecessor is reconciled SUCCESS."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    with (
        patch("app.core.redis_client.redis_manager.get", new=AsyncMock(return_value=None)),
        patch("app.services.rpa_scheduler_service.async_session_factory", async_session),
        patch.object(utcms_submission_gate, "is_submission_allowed", new=AsyncMock(return_value=True)),
    ):
        async with async_session() as session:
            client = Client(
                client_code=f"CLI-CHAIN-{predecessor_status}",
                name="Tenant Chain",
                email=f"chain-{predecessor_status}@example.com",
                username=f"chain-{predecessor_status}",
                full_name="Tenant Chain",
                hashed_password="hash",
            )
            session.add(client)
            await session.commit()
            await session.refresh(client)

            driver = Driver(
                client_id=client.id,
                driver_national_code="1234567890",
                full_name="Driver Chain",
                utcms_username="driver-chain",
                utcms_password_encrypted="enc_pwd",
                runtime_status=DriverStatus.READY.value,
            )
            session.add(driver)
            await session.commit()
            await session.refresh(driver)

            batch = WaybillBatch(
                client_id=client.id,
                driver_id=driver.id,
                route_template_ids=[1, 2],
                target_count=2,
                route_chain=True,
                interval_minutes=40,
            )
            session.add(batch)
            await session.flush()
            now = datetime.now(UTC).replace(tzinfo=None)
            predecessor = WaybillJob(
                job_id="chain_leg_0",
                idempotency_key=f"chain-idem-0-{predecessor_status}",
                client_id=client.id,
                driver_id=driver.id,
                batch_id=batch.id,
                sequence_index=0,
                status=predecessor_status,
                payload_json={"origin": {"city": "ماهشهر"}, "destination": {"city": "اهواز"}},
                distance_km=100,
                duration_min=60,
                submit_after=now,
                updated_at=now,
            )
            successor = WaybillJob(
                job_id="chain_leg_1",
                idempotency_key=f"chain-idem-1-{predecessor_status}",
                client_id=client.id,
                driver_id=driver.id,
                batch_id=batch.id,
                sequence_index=1,
                status=TaskStatus.PENDING.value,
                payload_json={"origin": {"city": "اهواز"}, "destination": {"city": "تهران"}},
                distance_km=200,
                duration_min=120,
                submit_after=now,
                updated_at=now,
            )
            session.add_all([predecessor, successor])
            await session.commit()

        await rpa_runtime.store_session(
            client.id,
            driver.id,
            SessionBundle(
                cookies=[{"name": "sessionid", "value": "chain"}],
                user_agent="ua",
                issued_at=now.isoformat(),
                expires_at=(now + timedelta(hours=1)).isoformat(),
                session_version=1,
            ),
        )
        plan = await rpa_scheduler_service.plan_due_jobs()
        assert [decision.job_id for decision in plan] == expected_job_ids

        async with async_session() as session:
            refreshed_successor = (
                await session.exec(select(WaybillJob).where(WaybillJob.job_id == "chain_leg_1"))
            ).one()
            assert refreshed_successor.status == TaskStatus.PENDING.value

    await engine.dispose()


@pytest.mark.asyncio
async def test_route_chain_waits_from_reconciled_completion_and_respects_open_gate():
    """A late predecessor pushes the next leg forward; a closed site gate still wins."""
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
                client_code="CLI-CHAIN-LATE",
                name="Tenant Chain Late",
                email="chain-late@example.com",
                username="chain-late",
                full_name="Tenant Chain Late",
                hashed_password="hash",
            )
            driver = Driver(
                client_id=1,
                driver_national_code="1234567890",
                full_name="Driver Chain Late",
                utcms_username="driver-chain-late",
                utcms_password_encrypted="enc_pwd",
                runtime_status=DriverStatus.READY.value,
            )
            session.add(client)
            await session.flush()
            driver.client_id = client.id
            session.add(driver)
            await session.flush()
            batch = WaybillBatch(
                client_id=client.id,
                driver_id=driver.id,
                route_template_ids=[1, 2],
                target_count=2,
                route_chain=True,
                interval_minutes=40,
            )
            session.add(batch)
            await session.flush()
            now = datetime.now(UTC).replace(tzinfo=None)
            completed_at = now - timedelta(minutes=10)
            predecessor = WaybillJob(
                job_id="chain-late-0",
                idempotency_key="chain-late-idem-0",
                client_id=client.id,
                driver_id=driver.id,
                batch_id=batch.id,
                sequence_index=0,
                status=TaskStatus.SUCCESS.value,
                payload_json={"origin": {"city": "ماهشهر"}, "destination": {"city": "اهواز"}},
                distance_km=100,
                duration_min=60,
                reconciled_at=completed_at,
                updated_at=completed_at,
            )
            successor = WaybillJob(
                job_id="chain-late-1",
                idempotency_key="chain-late-idem-1",
                client_id=client.id,
                driver_id=driver.id,
                batch_id=batch.id,
                sequence_index=1,
                status=TaskStatus.PENDING.value,
                payload_json={"origin": {"city": "اهواز"}, "destination": {"city": "تهران"}},
                submit_after=now - timedelta(hours=2),
                updated_at=now,
            )
            session.add_all([predecessor, successor])
            await session.commit()
            await session.refresh(successor)

        await rpa_runtime.store_session(
            client.id,
            driver.id,
            SessionBundle(
                cookies=[{"name": "sessionid", "value": "chain-late"}],
                user_agent="ua",
                issued_at=now.isoformat(),
                expires_at=(now + timedelta(hours=1)).isoformat(),
                session_version=1,
            ),
        )

        with patch.object(utcms_submission_gate, "is_submission_allowed", new=AsyncMock(return_value=True)):
            plan = await rpa_scheduler_service.plan_due_jobs()
            assert plan == []
        async with async_session() as session:
            refreshed = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "chain-late-1"))).one()
            assert refreshed.status == TaskStatus.PENDING.value
            assert refreshed.submit_after >= completed_at + timedelta(minutes=100)
            # Simulate both the calculated release time and an old completion;
            # this isolates the UTCMS gate from the travel-time guard below.
            predecessor_row = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "chain-late-0"))).one()
            predecessor_row.reconciled_at = now - timedelta(hours=3)
            predecessor_row.updated_at = predecessor_row.reconciled_at
            refreshed.submit_after = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
            session.add(predecessor_row)
            session.add(refreshed)
            await session.commit()

        with patch.object(utcms_submission_gate, "is_submission_allowed", new=AsyncMock(return_value=False)):
            plan = await rpa_scheduler_service.plan_due_jobs()
            assert plan == []
        async with async_session() as session:
            refreshed = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "chain-late-1"))).one()
            assert refreshed.status == TaskStatus.WAITING_SUBMISSION_WINDOW.value

    await engine.dispose()
