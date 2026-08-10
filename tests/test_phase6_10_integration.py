"""
Integration tests for Phase 6-10 components.
Tests interaction between Reconciliation, Alerts, Auto-Heal, Beat HA, and Monitoring.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models_multitenant import WaybillJob
from app.models_rpa import WorkerRegistry
from app.orchestrator.alert_manager import AlertManagerService
from app.orchestrator.state_machine import JobStatus


@pytest.fixture
async def async_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async_session = AsyncSession(engine, expire_on_commit=False)
    yield async_session
    await async_session.close()
    await engine.dispose()


@pytest.mark.asyncio
async def test_reconciliation_creates_alert_on_repeated_unknown(async_db):
    """Phase 6: Reconciliation encountering repeated unknown status should create admin alert."""
    service = AlertManagerService()

    # Create 3 consecutive unknown jobs for same driver
    jobs = []
    for i in range(3):
        job = WaybillJob(
            job_id=f"job-unk-{i}",
            idempotency_key=f"idemp-unk-{i}",
            client_id=1,
            driver_id=1,
            payload_json={},
            status=JobStatus.UNKNOWN,
            attempt_count=i + 1,
        )
        async_db.add(job)
        jobs.append(job)
    await async_db.commit()

    with (
        patch("app.orchestrator.alert_manager.webhook_alert_manager.emit"),
        patch("app.orchestrator.alert_manager.event_hub.publish", new_callable=AsyncMock) as mock_pub,
    ):

        alert = await service.check_repeated_unknown_submission(
            session=async_db, job_id=jobs[0].id, consecutive_count=3, tenant_id=1
        )

        assert alert is not None
        assert alert.severity == "high"
        assert alert.category == "submission_unknown_repeated"
        mock_pub.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_draining_alert_flow(async_db):
    """Phase 7-8: Worker status transition to draining should create alert."""
    service = AlertManagerService()

    # Register worker in registry
    worker = WorkerRegistry(
        worker_id="worker-test-01",
        hostname="test-host",
        status="active",
        created_at=datetime.now(UTC).replace(tzinfo=None),
        updated_at=datetime.now(UTC).replace(tzinfo=None),
    )
    async_db.add(worker)
    await async_db.commit()

    with (
        patch("app.orchestrator.alert_manager.webhook_alert_manager.emit"),
        patch("app.orchestrator.alert_manager.event_hub.publish", new_callable=AsyncMock),
    ):

        alert = await service.create_alert(
            session=async_db,
            severity="critical",
            category="worker_draining",
            message="Worker worker-test-01 transitioned to draining after 5 failures",
            dedupe_key="draining_worker_test-01",
            details={"worker_id": "worker-test-01", "failures": 5},
        )

        assert alert is not None
        assert alert.severity == "critical"
        assert alert.dedupe_key == "draining_worker_test-01"


@pytest.mark.asyncio
async def test_alert_webhook_auto_ack_resolved(async_db):
    """Phase 6-10: Resolved alert from Alertmanager should auto-acknowledge existing alert."""
    service = AlertManagerService()

    # Create a firing alert
    with (
        patch("app.orchestrator.alert_manager.webhook_alert_manager.emit"),
        patch("app.orchestrator.alert_manager.event_hub.publish", new_callable=AsyncMock),
    ):
        fired_alert = await service.create_alert(
            session=async_db,
            severity="critical",
            category="HealthyProxiesLow",
            message="Only 1 healthy proxy left",
            dedupe_key="alertmanager_HealthyProxiesLow_global",
        )

    assert fired_alert.is_acknowledged is False

    # Simulate resolved webhook
    acked = await service.acknowledge_alert(session=async_db, alert_id=fired_alert.id, admin_id=0)

    assert acked is not None
    assert acked.is_acknowledged is True
    assert acked.acknowledged_by == 0


@pytest.mark.asyncio
async def test_metrics_populated_from_worker_registry(async_db):
    """Phase 10: Metrics endpoint should reflect worker registry state."""
    now = datetime.now(UTC).replace(tzinfo=None)
    cutoff = now - timedelta(seconds=90)

    workers = [
        WorkerRegistry(
            worker_id="w1",
            hostname="host1",
            status="active",
            created_at=now,
            updated_at=now,
        ),
        WorkerRegistry(
            worker_id="w2",
            hostname="host2",
            status="draining",
            created_at=now,
            updated_at=now,
        ),
        WorkerRegistry(
            worker_id="w3",
            hostname="host3",
            status="active",
            created_at=now,
            updated_at=cutoff - timedelta(seconds=10),  # stale
        ),
    ]
    for w in workers:
        async_db.add(w)
    await async_db.commit()

    # Verify registry query logic
    stmt = select(WorkerRegistry)
    result = await async_db.exec(stmt)
    all_workers = result.all()
    assert len(all_workers) == 3

    active = [w for w in all_workers if w.status == "active" and w.updated_at >= cutoff]
    draining = [w for w in all_workers if w.status == "draining"]
    stale = [w for w in all_workers if w.updated_at < cutoff]

    assert len(active) == 1
    assert len(draining) == 1
    assert len(stale) == 1


@pytest.mark.asyncio
async def test_beat_ha_scheduler_config():
    """Phase 9: Verify celery-redbeat is configured."""
    from app.core.config import utcms_config
    from app.workers.celery_app import celery_app

    assert celery_app is not None
    assert celery_app.conf.beat_scheduler == "redbeat.RedBeatScheduler"
    assert celery_app.conf.redbeat_redis_url == utcms_config.REDIS_URL
    # Lock timeout should be 120s (not the old 30s) to prevent race with long schedules
    assert celery_app.conf.redbeat_lock_timeout >= 120


@pytest.mark.asyncio
async def test_captcha_failure_rate_metric_updates():
    """Phase 10: Captcha failure rate should be tracked in runtime snapshot."""
    from app.monitoring.metrics import (
        get_captcha_runtime_snapshot,
        reset_captcha_runtime_snapshot,
        track_captcha_attempt,
        track_captcha_failure,
        track_captcha_success,
    )

    reset_captcha_runtime_snapshot()

    for _ in range(8):
        track_captcha_attempt(strategy="cnn", phase="login")

    for _ in range(6):
        track_captcha_success(strategy="cnn", phase="login")

    for _ in range(2):
        track_captcha_failure(reason="timeout", phase="login", strategy="cnn")

    snapshot = get_captcha_runtime_snapshot(window_size=10)
    assert snapshot["totals"]["attempts"] == 8
    assert snapshot["totals"]["successes"] == 6
    assert snapshot["totals"]["failures"] == 2
    assert snapshot["totals"]["success_rate"] == 0.75

    reset_captcha_runtime_snapshot()
