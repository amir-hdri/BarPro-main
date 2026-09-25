"""Unit tests for driver anti-flood inter-waybill cooldown in RPASchedulerService."""

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
async def test_driver_antiflood_cooldown_defers_standalone_job(caplog):
    """Verify that a standalone job is deferred when the driver's previous waybill is in cooldown."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    now = datetime.now(UTC).replace(tzinfo=None)

    with (
        patch("app.core.redis_client.redis_manager.get", new=AsyncMock(return_value=None)),
        patch("app.services.rpa_scheduler_service.async_session_factory", async_session),
        patch.object(utcms_submission_gate, "is_submission_allowed", new=AsyncMock(return_value=True)),
        patch.object(utcms_config, "UTCMS_TRANSPORT", "web"),
    ):
        async with async_session() as session:
            client = Client(
                client_code="CLI-CD-1",
                name="Tenant Cooldown",
                email="cooldown@example.com",
                username="cooldown_user",
                full_name="Cooldown Admin",
                hashed_password="hash",
                is_active=True,
            )
            session.add(client)
            await session.commit()
            await session.refresh(client)

            driver = Driver(
                client_id=client.id,
                driver_national_code="0011223344",
                full_name="Driver Cooldown",
                utcms_username="drv_cooldown",
                utcms_password_encrypted="enc_pwd",
                runtime_status=DriverStatus.READY.value,
                is_active=True,
            )
            session.add(driver)
            await session.commit()
            await session.refresh(driver)

            # Previous successful waybill completed 15 minutes ago with duration 30 min.
            # Cooldown = duration (30m) + 30m = 60m after finished_at.
            # Since only 15m elapsed, 45m cooldown remaining.
            finished_at = now - timedelta(minutes=15)
            last_success = WaybillJob(
                job_id="job-last-success-1",
                idempotency_key="idem-last-success-1",
                client_id=client.id,
                driver_id=driver.id,
                status=TaskStatus.SUCCESS.value,
                duration_min=30.0,
                reconciled_at=finished_at,
                updated_at=finished_at,
                payload_json={"origin": {"city": "تهران"}, "destination": {"city": "قم"}},
            )
            # New standalone job ready now
            new_job = WaybillJob(
                job_id="job-new-standalone-1",
                idempotency_key="idem-new-standalone-1",
                client_id=client.id,
                driver_id=driver.id,
                status=TaskStatus.PENDING.value,
                source=TaskSource.MANUAL.value,
                payload_json={"origin": {"city": "قم"}, "destination": {"city": "کاشان"}},
                submit_after=now - timedelta(minutes=1),
                updated_at=now,
            )
            session.add_all([last_success, new_job])
            await session.commit()

        # Provide active session so job is not blocked by auth
        await rpa_runtime.store_session(
            client.id,
            driver.id,
            SessionBundle(
                cookies=[{"name": "sessionid", "value": "val"}],
                user_agent="ua",
                issued_at=now.isoformat(),
                expires_at=(now + timedelta(hours=1)).isoformat(),
                session_version=1,
            ),
        )

        with caplog.at_level("INFO"):
            plan = await rpa_scheduler_service.plan_due_jobs()

        # Job must be deferred: not planned for submit
        assert len(plan) == 0

        # Check DB: submit_after moved to earliest_safe_time = finished_at + 60m
        expected_earliest_safe = finished_at + timedelta(minutes=60.0)
        async with async_session() as session:
            refreshed = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-new-standalone-1"))).one()
            assert refreshed.submit_after is not None
            assert abs((refreshed.submit_after - expected_earliest_safe).total_seconds()) < 1.0

        # Verify log event
        assert any("driver_in_cooldown_preventing_code_5000" in rec.message for rec in caplog.records)

    await engine.dispose()


@pytest.mark.asyncio
async def test_driver_antiflood_cooldown_releases_after_elapsed():
    """Verify that a standalone job is planned normally when cooldown has already elapsed."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    now = datetime.now(UTC).replace(tzinfo=None)

    with (
        patch("app.core.redis_client.redis_manager.get", new=AsyncMock(return_value=None)),
        patch("app.services.rpa_scheduler_service.async_session_factory", async_session),
        patch.object(utcms_submission_gate, "is_submission_allowed", new=AsyncMock(return_value=True)),
        patch.object(utcms_config, "UTCMS_TRANSPORT", "web"),
    ):
        async with async_session() as session:
            client = Client(
                client_code="CLI-CD-2",
                name="Tenant Cooldown 2",
                email="cooldown2@example.com",
                username="cooldown_user2",
                full_name="Cooldown Admin 2",
                hashed_password="hash",
                is_active=True,
            )
            session.add(client)
            await session.commit()
            await session.refresh(client)

            driver = Driver(
                client_id=client.id,
                driver_national_code="9988776655",
                full_name="Driver Cooldown 2",
                utcms_username="drv_cooldown2",
                utcms_password_encrypted="enc_pwd",
                runtime_status=DriverStatus.READY.value,
                is_active=True,
            )
            session.add(driver)
            await session.commit()
            await session.refresh(driver)

            # Previous successful waybill completed 2 hours ago (duration 30m + 30m = 1 hour cooldown)
            # 2 hours > 1 hour -> cooldown elapsed!
            finished_at = now - timedelta(hours=2)
            last_success = WaybillJob(
                job_id="job-last-success-2",
                idempotency_key="idem-last-success-2",
                client_id=client.id,
                driver_id=driver.id,
                status=TaskStatus.SUCCESS.value,
                duration_min=30.0,
                reconciled_at=finished_at,
                updated_at=finished_at,
                payload_json={"origin": {"city": "تهران"}, "destination": {"city": "قم"}},
            )
            new_job = WaybillJob(
                job_id="job-new-standalone-2",
                idempotency_key="idem-new-standalone-2",
                client_id=client.id,
                driver_id=driver.id,
                status=TaskStatus.PENDING.value,
                source=TaskSource.MANUAL.value,
                payload_json={"origin": {"city": "قم"}, "destination": {"city": "کاشان"}},
                submit_after=now - timedelta(minutes=5),
                updated_at=now,
            )
            session.add_all([last_success, new_job])
            await session.commit()

        await rpa_runtime.store_session(
            client.id,
            driver.id,
            SessionBundle(
                cookies=[{"name": "sessionid", "value": "val2"}],
                user_agent="ua",
                issued_at=now.isoformat(),
                expires_at=(now + timedelta(hours=1)).isoformat(),
                session_version=1,
            ),
        )

        plan = await rpa_scheduler_service.plan_due_jobs()
        assert len(plan) == 1
        assert plan[0].job_id == "job-new-standalone-2"
        assert plan[0].reason == "session_ready"

    await engine.dispose()


@pytest.mark.asyncio
async def test_driver_antiflood_cooldown_skipped_for_route_chain_batches():
    """Verify that route_chain batch legs bypass the standalone cooldown logic."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    now = datetime.now(UTC).replace(tzinfo=None)

    with (
        patch("app.core.redis_client.redis_manager.get", new=AsyncMock(return_value=None)),
        patch("app.services.rpa_scheduler_service.async_session_factory", async_session),
        patch.object(utcms_submission_gate, "is_submission_allowed", new=AsyncMock(return_value=True)),
        patch.object(utcms_config, "UTCMS_TRANSPORT", "web"),
    ):
        async with async_session() as session:
            client = Client(
                client_code="CLI-CD-3",
                name="Tenant Cooldown 3",
                email="cooldown3@example.com",
                username="cooldown_user3",
                full_name="Cooldown Admin 3",
                hashed_password="hash",
                is_active=True,
            )
            session.add(client)
            await session.commit()
            await session.refresh(client)

            driver = Driver(
                client_id=client.id,
                driver_national_code="5544332211",
                full_name="Driver Cooldown 3",
                utcms_username="drv_cooldown3",
                utcms_password_encrypted="enc_pwd",
                runtime_status=DriverStatus.READY.value,
                is_active=True,
            )
            session.add(driver)
            await session.commit()
            await session.refresh(driver)

            batch = WaybillBatch(
                batch_id="batch-rc-1",
                client_id=client.id,
                target_count=2,
                interval_minutes=10,
                route_chain=True,
            )
            session.add(batch)
            await session.commit()
            await session.refresh(batch)

            # Leg 0 succeeded recently
            leg0_finished = now - timedelta(minutes=5)
            leg0 = WaybillJob(
                job_id="job-rc-leg-0",
                idempotency_key="idem-rc-leg-0",
                client_id=client.id,
                driver_id=driver.id,
                batch_id=batch.id,
                sequence_index=0,
                status=TaskStatus.SUCCESS.value,
                duration_min=60.0,
                reconciled_at=leg0_finished,
                updated_at=leg0_finished,
                payload_json={"origin": {"city": "تهران"}, "destination": {"city": "قم"}},
            )
            # Leg 1 in route chain
            leg1 = WaybillJob(
                job_id="job-rc-leg-1",
                idempotency_key="idem-rc-leg-1",
                client_id=client.id,
                driver_id=driver.id,
                batch_id=batch.id,
                sequence_index=1,
                status=TaskStatus.PENDING.value,
                source=TaskSource.MANUAL.value,
                payload_json={"origin": {"city": "قم"}, "destination": {"city": "کاشان"}},
                submit_after=now - timedelta(minutes=1),
                updated_at=now,
            )
            session.add_all([leg0, leg1])
            await session.commit()

        # Leg 1 should use route_chain interval (60m duration + 10m batch interval = 70m)
        plan = await rpa_scheduler_service.plan_due_jobs()
        assert len(plan) == 0

        async with async_session() as session:
            refreshed_leg1 = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-rc-leg-1"))).one()
            expected_leg1_after = leg0_finished + timedelta(minutes=70.0)
            assert abs((refreshed_leg1.submit_after - expected_leg1_after).total_seconds()) < 1.0

    await engine.dispose()
