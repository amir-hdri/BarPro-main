"""
Unit tests for Admin Alert System, AlertManagerService, and Alert API endpoints.
"""

from datetime import datetime, UTC
from unittest.mock import AsyncMock, patch
import pytest

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

from app.models.admin import AdminAlert
from app.models_multitenant import WaybillJob
from app.orchestrator.alert_manager import AlertManagerService, admin_alert_service
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
async def test_create_alert_idempotency(async_db: AsyncSession):
    service = AlertManagerService()

    with patch("app.orchestrator.alert_manager.webhook_alert_manager.emit") as mock_emit, \
         patch("app.orchestrator.alert_manager.event_hub.publish", new_callable=AsyncMock) as mock_pub:

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

    with patch("app.orchestrator.alert_manager.webhook_alert_manager.emit"), \
         patch("app.orchestrator.alert_manager.event_hub.publish", new_callable=AsyncMock):

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
    from app.api.routes.admin_alerts import alertmanager_webhook
    from fastapi import HTTPException
    from app.core.config import utcms_config
    
    # Enable signature validation in test config
    with patch.object(utcms_config, "ALERT_WEBHOOK_SECRET", "super_secret"):
        req = MockRequest(headers={}, body=b"{}", json_data={})
        with pytest.raises(HTTPException) as exc_info:
            await alertmanager_webhook(req, session=async_db)
        assert exc_info.value.status_code == 403
        assert "Missing signature" in exc_info.value.detail


@pytest.mark.asyncio
async def test_webhook_valid_signature_firing(async_db: AsyncSession):
    from app.api.routes.admin_alerts import alertmanager_webhook
    from app.core.config import utcms_config
    from sqlmodel import select
    import hmac
    import hashlib
    import time
    import json
    
    payload = {
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "HealthyProxiesLow",
                    "severity": "critical",
                    "worker_id": "worker-abc"
                },
                "annotations": {
                    "summary": "Proxy count low",
                    "description": "Only 1 healthy proxy left"
                },
                "startsAt": "2026-08-01T10:00:00Z"
            }
        ]
    }
    
    payload_bytes = json.dumps(payload).encode("utf-8")
    timestamp = str(int(time.time()))
    secret = "test_webhook_secret"
    
    message_to_sign = f"{timestamp}.".encode("utf-8") + payload_bytes
    signature = hmac.new(
        secret.encode("utf-8"),
        message_to_sign,
        hashlib.sha256
    ).hexdigest()
    
    headers = {
        "X-Barpro-Timestamp": timestamp,
        "X-Barpro-Signature": signature
    }
    
    req = MockRequest(headers=headers, body=payload_bytes, json_data=payload)
    
    with patch.object(utcms_config, "ALERT_WEBHOOK_SECRET", secret), \
         patch("app.orchestrator.alert_manager.webhook_alert_manager.emit") as mock_emit, \
         patch("app.orchestrator.alert_manager.event_hub.publish", new_callable=AsyncMock) as mock_pub:
         
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
    from app.api.routes.admin_alerts import alertmanager_webhook
    from app.core.config import utcms_config
    from sqlmodel import select
    import hmac
    import hashlib
    import time
    import json
    
    # 1. Create a firing alert first
    fired_alert = AdminAlert(
        severity="critical",
        category="HealthyProxiesLow",
        message="Only 1 healthy proxy left",
        dedupe_key="alertmanager_HealthyProxiesLow_worker-abc",
        is_acknowledged=False,
        created_at=datetime.now(UTC).replace(tzinfo=None)
    )
    async_db.add(fired_alert)
    await async_db.commit()
    
    payload = {
        "alerts": [
            {
                "status": "resolved",
                "labels": {
                    "alertname": "HealthyProxiesLow",
                    "severity": "critical",
                    "worker_id": "worker-abc"
                },
                "annotations": {
                    "summary": "Proxy count low",
                    "description": "Only 1 healthy proxy left"
                },
                "startsAt": "2026-08-01T10:00:00Z"
            }
        ]
    }
    
    payload_bytes = json.dumps(payload).encode("utf-8")
    timestamp = str(int(time.time()))
    secret = "test_webhook_secret"
    
    message_to_sign = f"{timestamp}.".encode("utf-8") + payload_bytes
    signature = hmac.new(
        secret.encode("utf-8"),
        message_to_sign,
        hashlib.sha256
    ).hexdigest()
    
    headers = {
        "X-Barpro-Timestamp": timestamp,
        "X-Barpro-Signature": signature
    }
    
    req = MockRequest(headers=headers, body=payload_bytes, json_data=payload)
    
    with patch.object(utcms_config, "ALERT_WEBHOOK_SECRET", secret), \
         patch("app.orchestrator.alert_manager.event_hub.publish", new_callable=AsyncMock) as mock_pub:
         
        res = await alertmanager_webhook(req, session=async_db)
        assert res["status"] == "success"
        assert res["processed_alerts"] == 1
        
        # Verify alert is now acknowledged automatically in DB
        stmt = select(AdminAlert).where(AdminAlert.dedupe_key == "alertmanager_HealthyProxiesLow_worker-abc")
        db_alert = (await async_db.execute(stmt)).scalar_one_or_none()
        
        assert db_alert is not None
        assert db_alert.is_acknowledged is True
        assert db_alert.acknowledged_by == 0  # 0 indicates system resolved

