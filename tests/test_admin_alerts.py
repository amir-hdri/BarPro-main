"""
Unit tests for Admin Alert System, AlertManagerService, and Alert API endpoints.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

from app.models.admin import AdminAlert
from app.orchestrator.alert_manager import AlertManagerService


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
async def test_create_alert_idempotency(async_db: AsyncSession):
    service = AlertManagerService()

    with (
        patch("app.orchestrator.alert_manager.webhook_alert_manager.emit") as mock_emit,
        patch("app.orchestrator.alert_manager.event_hub.publish", new_callable=AsyncMock) as mock_pub,
    ):

        alert1 = await service.create_alert(
            session=async_db,
            severity="high",
            category="test_cat",
            message="First alert message",
            dedupe_key="dup_key_123",
            tenant_id=1,
        )

        assert alert1 is not None
        assert alert1.id is not None
        assert alert1.dedupe_key == "dup_key_123"
        assert alert1.severity == "high"
        mock_emit.assert_called_once()
        mock_pub.assert_awaited_once()

        # Create duplicate alert with same dedupe_key
        mock_emit.reset_mock()
        mock_pub.reset_mock()

        alert2 = await service.create_alert(
            session=async_db,
            severity="high",
            category="test_cat",
            message="Second alert message",
            dedupe_key="dup_key_123",
            tenant_id=1,
        )

        assert alert2 is not None
        assert alert2.id == alert1.id
        mock_emit.assert_not_called()
        mock_pub.assert_not_called()


@pytest.mark.asyncio
async def test_acknowledge_alert(async_db: AsyncSession):
    service = AlertManagerService()

    with patch("app.orchestrator.alert_manager.event_hub.publish", new_callable=AsyncMock):
        alert = await service.create_alert(
            session=async_db,
            severity="warning",
            category="system",
            message="System warning",
            dedupe_key="ack_test_key",
        )
        assert alert is not None
        assert alert.is_acknowledged is False

        acked_alert = await service.acknowledge_alert(session=async_db, alert_id=alert.id, admin_id=99)
        assert acked_alert is not None
        assert acked_alert.is_acknowledged is True
        assert acked_alert.acknowledged_by == 99
        assert acked_alert.acknowledged_at is not None


@pytest.mark.asyncio
async def test_check_repeated_unknown_submission(async_db: AsyncSession):
    service = AlertManagerService()

    with (
        patch("app.orchestrator.alert_manager.webhook_alert_manager.emit"),
        patch("app.orchestrator.alert_manager.event_hub.publish", new_callable=AsyncMock),
    ):

        # Threshold < 3 should not create alert
        alert_none = await service.check_repeated_unknown_submission(
            session=async_db, job_id=42, consecutive_count=2, tenant_id=1
        )
        assert alert_none is None

        # Threshold >= 3 should create alert
        alert_high = await service.check_repeated_unknown_submission(
            session=async_db, job_id=42, consecutive_count=3, tenant_id=1
        )
        assert alert_high is not None
        assert alert_high.severity == "high"
        assert alert_high.category == "submission_unknown_repeated"
        assert "42" in alert_high.message


class MockRequest:
    def __init__(self, headers: dict[str, str], body: bytes, json_data: dict):
        self.headers = headers
        self._body = body
        self._json = json_data

    async def body(self) -> bytes:
        return self._body

    async def json(self) -> dict:
        return self._json


@pytest.mark.asyncio
async def test_webhook_missing_signature(async_db: AsyncSession):
    from fastapi import HTTPException

    from app.api.routes.admin_alerts import alertmanager_webhook
    from app.core.config import utcms_config

    # Enable signature validation in test config
    with patch.object(utcms_config, "ALERT_WEBHOOK_SECRET", "super_secret"):
        req = MockRequest(headers={}, body=b"{}", json_data={})
        with pytest.raises(HTTPException) as exc_info:
            await alertmanager_webhook(req, session=async_db)
        assert exc_info.value.status_code == 403
        assert "Missing signature" in exc_info.value.detail


@pytest.mark.asyncio
async def test_webhook_fail_closed_for_edge_proxied_request_without_secret(async_db: AsyncSession):
    """Without ALERT_WEBHOOK_SECRET, requests that traversed nginx (X-Request-ID
    stamped by the edge proxy) must be rejected; direct internal callers pass."""
    from fastapi import HTTPException

    from app.api.routes.admin_alerts import alertmanager_webhook
    from app.core.config import utcms_config

    proxied = MockRequest(headers={"X-Request-ID": "nginx_generated_id"}, body=b"{}", json_data={})
    with patch.object(utcms_config, "ALERT_WEBHOOK_SECRET", ""):
        with pytest.raises(HTTPException) as exc_info:
            await alertmanager_webhook(proxied, session=async_db)
        assert exc_info.value.status_code == 403

        # Internal Alertmanager call: no X-Request-ID header → allowed through
        internal = MockRequest(headers={}, body=b'{"alerts": []}', json_data={"alerts": []})
        res = await alertmanager_webhook(internal, session=async_db)
        assert res["status"] == "success"
        assert res["processed_alerts"] == 0


@pytest.mark.asyncio
async def test_webhook_valid_signature_firing(async_db: AsyncSession):
    import hashlib
    import hmac
    import json
    import time

    from sqlmodel import select

    from app.api.routes.admin_alerts import alertmanager_webhook
    from app.core.config import utcms_config

    payload = {
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "HealthyProxiesLow", "severity": "critical", "worker_id": "worker-abc"},
                "annotations": {"summary": "Proxy count low", "description": "Only 1 healthy proxy left"},
                "startsAt": "2026-08-01T10:00:00Z",
            }
        ]
    }

    payload_bytes = json.dumps(payload).encode("utf-8")
    timestamp = str(int(time.time()))
    secret = "test_webhook_secret"

    message_to_sign = f"{timestamp}.".encode() + payload_bytes
    signature = hmac.new(secret.encode("utf-8"), message_to_sign, hashlib.sha256).hexdigest()

    headers = {"X-Barpro-Timestamp": timestamp, "X-Barpro-Signature": signature}

    req = MockRequest(headers=headers, body=payload_bytes, json_data=payload)

    with (
        patch.object(utcms_config, "ALERT_WEBHOOK_SECRET", secret),
        patch("app.orchestrator.alert_manager.webhook_alert_manager.emit"),
        patch("app.orchestrator.alert_manager.event_hub.publish", new_callable=AsyncMock),
    ):

        res = await alertmanager_webhook(req, session=async_db)
        assert res["status"] == "success"
        assert res["processed_alerts"] == 1

        # Verify alert created in DB with correct severity routing
        stmt = select(AdminAlert).where(AdminAlert.dedupe_key == "alertmanager_HealthyProxiesLow_worker-abc")
        db_alert = (await async_db.execute(stmt)).scalar_one_or_none()

        assert db_alert is not None
        assert db_alert.severity == "critical"
        assert db_alert.category == "HealthyProxiesLow"
        assert "Only 1 healthy proxy left" in db_alert.message
        assert db_alert.is_acknowledged is False


@pytest.mark.asyncio
async def test_webhook_valid_signature_resolved(async_db: AsyncSession):
    import hashlib
    import hmac
    import json
    import time

    from sqlmodel import select

    from app.api.routes.admin_alerts import alertmanager_webhook
    from app.core.config import utcms_config

    # 1. Create a firing alert first
    fired_alert = AdminAlert(
        severity="critical",
        category="HealthyProxiesLow",
        message="Only 1 healthy proxy left",
        dedupe_key="alertmanager_HealthyProxiesLow_worker-abc",
        is_acknowledged=False,
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )
    async_db.add(fired_alert)
    await async_db.commit()

    payload = {
        "alerts": [
            {
                "status": "resolved",
                "labels": {"alertname": "HealthyProxiesLow", "severity": "critical", "worker_id": "worker-abc"},
                "annotations": {"summary": "Proxy count low", "description": "Only 1 healthy proxy left"},
                "startsAt": "2026-08-01T10:00:00Z",
            }
        ]
    }

    payload_bytes = json.dumps(payload).encode("utf-8")
    timestamp = str(int(time.time()))
    secret = "test_webhook_secret"

    message_to_sign = f"{timestamp}.".encode() + payload_bytes
    signature = hmac.new(secret.encode("utf-8"), message_to_sign, hashlib.sha256).hexdigest()

    headers = {"X-Barpro-Timestamp": timestamp, "X-Barpro-Signature": signature}

    req = MockRequest(headers=headers, body=payload_bytes, json_data=payload)

    with (
        patch.object(utcms_config, "ALERT_WEBHOOK_SECRET", secret),
        patch("app.orchestrator.alert_manager.event_hub.publish", new_callable=AsyncMock),
    ):

        res = await alertmanager_webhook(req, session=async_db)
        assert res["status"] == "success"
        assert res["processed_alerts"] == 1

        # Verify alert is now acknowledged automatically in DB
        stmt = select(AdminAlert).where(AdminAlert.dedupe_key == "alertmanager_HealthyProxiesLow_worker-abc")
        db_alert = (await async_db.execute(stmt)).scalar_one_or_none()

        assert db_alert is not None
        assert db_alert.is_acknowledged is True
        assert db_alert.acknowledged_by == 0  # 0 indicates system resolved


@pytest.mark.asyncio
async def test_manual_reconcile_endpoint_audits_tracking_received_job_without_early_return(
    async_db: AsyncSession,
):
    """POST /api/v1/admin/alerts/reconcile/{job_id} must run the read-only
    History audit on a tracking-received job (audit_only=True) instead of
    early-returning — otherwise acknowledged jobs keep their operator success
    badge while the third witness is never attached."""
    import os
    from unittest.mock import MagicMock

    from app.api.routes.admin_alerts import reconcile_job_manually
    from app.models_multitenant import Client, WaybillJob
    from app.orchestrator.reconciliation_service import ReconciliationService, reconciliation_service
    from app.orchestrator.state_machine import JobStatus
    from app.orchestrator.utcms_reconciliation_scraper import ReconciliationResult, ScraperOutcome

    with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
        async_db.add(
            Client(
                id=1,
                client_code="ep_client",
                name="EP Client",
                username="epclient",
                full_name="EP Client",
                email="ep@client.com",
                hashed_password="x",
            )
        )
        job = WaybillJob(
            job_id="ep_tracking_audit",
            idempotency_key="idem_ep_tracking_audit",
            client_id=1,
            driver_id=None,
            payload_json={"origin_city_id": 1, "destination_city_id": 2},
            status=JobStatus.UNKNOWN,
            mutation_status="dispatched",
            result_json={
                "tracking_code": "UTC-EP-1",
                "confirmation_status": "tracking_received",
                "operator_acknowledged": True,
            },
        )
        async_db.add(job)
        await async_db.commit()
        await async_db.refresh(job)

        audit_flags: dict = {}
        real_reconcile = ReconciliationService.reconcile_job

        async def spy_reconcile(*, session, job_id, browser_manager=None, audit_only=False):
            audit_flags["audit_only"] = audit_only
            return await real_reconcile(
                reconciliation_service,
                session=session,
                job_id=job_id,
                browser_manager=browser_manager,
                audit_only=audit_only,
            )

        mock_bm = MagicMock()
        mock_bm.create_context = AsyncMock(return_value=("session-a", AsyncMock()))
        mock_bm.new_page = AsyncMock(return_value=AsyncMock())
        mock_bm.close_context = AsyncMock()
        mock_res = ReconciliationResult(outcome=ScraperOutcome.REGISTERED, tracking_code="UTC-EP-1")

        with (
            patch.object(reconciliation_service, "reconcile_job", new=AsyncMock(side_effect=spy_reconcile)),
            patch("app.orchestrator.reconciliation_service.BrowserManager", return_value=mock_bm),
            patch(
                "app.orchestrator.reconciliation_service.reconciliation_scraper.query_waybill_status",
                new_callable=AsyncMock,
            ) as mock_query,
        ):
            mock_query.return_value = mock_res
            resp = await reconcile_job_manually(job_id=job.id, session=async_db)

        # The endpoint forced the audit path — no early-return skip.
        assert audit_flags.get("audit_only") is True
        mock_query.assert_awaited()

        assert resp["status"] == "success"
        assert resp["current_status"] == JobStatus.SUCCESS

        await async_db.refresh(job)
        assert job.status == JobStatus.SUCCESS
        assert (job.result_json or {}).get("confirmation_status") == "confirmed_by_history"
