"""Tests for Hub phone connection status tracking and admin alerts.

Covers two deliberately separated halves (see
``app/services/hub_liveness_service.py``):

* ``GET /api/v1/admin/hub-status`` is **read-only** — it must never create or
  acknowledge an alert, because an alert raised only while an administrator has
  the dashboard open cannot notify anyone.
* ``monitor.hub_liveness`` (beat) owns raising / auto-acknowledging the
  ``hub:disconnected`` alert.
"""

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth_multitenant import create_access_token
from app.core.config import utcms_config
from app.main import app
from app.services.hub_liveness_service import evaluate_hub_liveness, sweep_hub_liveness

# Test-only webhook token. Never reuse a real deployment secret in a fixture:
# committed test data is permanent and world-readable once pushed.
TEST_WEBHOOK_TOKEN = "test-otp-webhook-token-0000000000000000000000000000"
HUB_NUMBERS = ["09966567754", "09047119812"]


@pytest.fixture
def master_admin_token():
    return create_access_token(
        client_id=0,
        client_code=utcms_config.MASTER_ADMIN_USERNAME,
        email="admin@barpro.ir",
        role="master_admin",
    )


@pytest.mark.asyncio
async def test_hub_health_check_records_hub_state():
    headers = {
        "X-OTP-Webhook-Token": TEST_WEBHOOK_TOKEN,
        "X-App-Role": "HUB",
        "X-Device-Id": "hub-phone-pixel-01",
    }
    payload = {
        "event": "HEALTH_CHECK",
        "app_role": "HUB",
        "device_id": "hub-phone-pixel-01",
        "hub_numbers": HUB_NUMBERS,
        "permissions": {"receive_sms": True, "send_sms": True},
    }

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.set = AsyncMock()

    with (
        patch("app.core.config.utcms_config.OTP_WEBHOOK_SECRET", TEST_WEBHOOK_TOKEN),
        patch("app.core.redis_client.redis_manager.get", return_value=mock_redis),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.post("/api/v1/otp/sms-forwarder", json=payload, headers=headers)
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "ready"

        # Verify Redis recorded hub state
        set_calls = [c for c in mock_redis.set.call_args_list if "rpa:forwarder:hub:connected" in str(c)]
        assert len(set_calls) > 0


@pytest.mark.asyncio
async def test_get_hub_status_endpoint_connected(master_admin_token: str):
    now = time.time()
    hub_data = {
        "app_role": "HUB",
        "device_id": "hub-pixel-01",
        "last_seen": now - 30,  # 30 seconds ago
        "last_health_at": now - 30,
        "permissions": {"receive_sms": True, "send_sms": True},
        "hub_numbers": HUB_NUMBERS,
    }

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=json.dumps(hub_data))
    mock_redis.exists = AsyncMock(return_value=0)

    headers = {"Authorization": f"Bearer {master_admin_token}"}

    with patch("app.core.redis_client.redis_manager.get", return_value=mock_redis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get("/api/v1/admin/hub-status", headers=headers)
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "connected"
            assert data["is_connected"] is True
            assert "09966567754" in data["hub_numbers"]
            assert data["stale_after_seconds"] == utcms_config.HUB_HEARTBEAT_STALE_SECONDS


@pytest.mark.asyncio
async def test_get_hub_status_reports_disconnected_without_side_effects(master_admin_token: str):
    """A stale heartbeat is reported, but the GET must not touch the alert table."""
    now = time.time()
    hub_data = {
        "app_role": "HUB",
        "device_id": "hub-pixel-01",
        "last_seen": now - (utcms_config.HUB_HEARTBEAT_STALE_SECONDS + 120),
        "last_health_at": now - (utcms_config.HUB_HEARTBEAT_STALE_SECONDS + 120),
        "permissions": {"receive_sms": True, "send_sms": True},
        "hub_numbers": HUB_NUMBERS,
    }

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=json.dumps(hub_data))
    mock_redis.exists = AsyncMock(return_value=0)

    headers = {"Authorization": f"Bearer {master_admin_token}"}

    with (
        patch("app.core.redis_client.redis_manager.get", return_value=mock_redis),
        patch("app.orchestrator.alert_manager.admin_alert_service.create_alert", new_callable=AsyncMock) as mock_alert,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get("/api/v1/admin/hub-status", headers=headers)
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "disconnected"
            assert data["is_connected"] is False
            # Read-only contract: alerting belongs to the beat sweep.
            assert not mock_alert.called


def test_healthy_heartbeat_at_full_interval_is_not_stale():
    """Regression: the threshold must not equal the Hub ping interval.

    The Hub pings on a fixed delay of ``healthCheckIntervalMinutes`` (default
    5 min). With a threshold equal to that interval, ``now - last_seen``
    legitimately reaches the full interval just before every ping, so a healthy
    Hub flaps into ``disconnected`` on every cycle and raises a high-severity
    alert each time.
    """
    now = time.time()
    interval = utcms_config.HUB_HEARTBEAT_INTERVAL_SECONDS

    assert (
        utcms_config.HUB_HEARTBEAT_STALE_SECONDS > interval
    ), "stale threshold must exceed the ping interval or healthy hubs flap"

    # A ping that arrives one second late is still healthy.
    liveness = evaluate_hub_liveness({"last_seen": now - (interval + 1)}, now=now)
    assert liveness.is_connected is True

    # Two consecutive missed pings are still tolerated at the 3x default.
    liveness = evaluate_hub_liveness({"last_seen": now - (interval * 2 + 5)}, now=now)
    assert liveness.is_connected is True

    # Beyond the threshold it is genuinely disconnected.
    liveness = evaluate_hub_liveness({"last_seen": now - (utcms_config.HUB_HEARTBEAT_STALE_SECONDS + 1)}, now=now)
    assert liveness.is_connected is False


def test_never_seen_hub_is_disconnected():
    liveness = evaluate_hub_liveness({})
    assert liveness.is_connected is False
    assert liveness.last_seen is None
    assert liveness.seconds_ago is None
    assert liveness.hub_numbers == list(utcms_config.HUB_NUMBERS)


@pytest.mark.asyncio
async def test_sweep_raises_alert_when_hub_stale():
    now = time.time()
    hub_data = {"last_seen": now - (utcms_config.HUB_HEARTBEAT_STALE_SECONDS + 300)}

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=json.dumps(hub_data))
    session = AsyncMock()

    with (
        patch("app.core.redis_client.redis_manager.get", return_value=mock_redis),
        patch(
            "app.services.hub_liveness_service.admin_alert_service.create_alert", new_callable=AsyncMock
        ) as mock_alert,
    ):
        result = await sweep_hub_liveness(session)

    assert result["status"] == "disconnected"
    assert result["alert_raised"] is True
    assert mock_alert.called
    kwargs = mock_alert.call_args[1]
    assert kwargs["severity"] == "high"
    assert kwargs["category"] == "hub_connection"
    assert kwargs["dedupe_key"] == "hub:disconnected"


@pytest.mark.asyncio
async def test_sweep_auto_acknowledges_with_audit_trail_on_recovery():
    """Auto-ack must be attributable and must not impersonate an operator."""
    now = time.time()
    hub_data = {"last_seen": now - 10}

    open_alert = MagicMock()
    open_alert.id = 42
    open_alert.details = {"seconds_ago": 1800}
    open_alert.is_acknowledged = False
    open_alert.acknowledged_by = 7  # stale value that must be cleared

    scalars = MagicMock()
    scalars.first = MagicMock(return_value=open_alert)
    executed = MagicMock()
    executed.scalars = MagicMock(return_value=scalars)

    session = AsyncMock()
    session.execute = AsyncMock(return_value=executed)
    session.add = MagicMock()

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=json.dumps(hub_data))

    with patch("app.core.redis_client.redis_manager.get", return_value=mock_redis):
        result = await sweep_hub_liveness(session)

    assert result["status"] == "connected"
    assert result["alert_auto_acknowledged"] is True
    assert open_alert.is_acknowledged is True
    assert open_alert.acknowledged_at is not None
    # Provenance: a system ack must not look like a human ack.
    assert open_alert.acknowledged_by is None
    assert open_alert.details["auto_resolved"] is True
    assert open_alert.details["auto_resolved_by"] == "monitor.hub_liveness"
    assert "auto_resolved_at" in open_alert.details
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_sweep_is_noop_when_connected_and_no_open_alert():
    now = time.time()
    hub_data = {"last_seen": now - 5}

    scalars = MagicMock()
    scalars.first = MagicMock(return_value=None)
    executed = MagicMock()
    executed.scalars = MagicMock(return_value=scalars)

    session = AsyncMock()
    session.execute = AsyncMock(return_value=executed)
    session.add = MagicMock()

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=json.dumps(hub_data))

    with patch("app.core.redis_client.redis_manager.get", return_value=mock_redis):
        result = await sweep_hub_liveness(session)

    assert result["status"] == "connected"
    assert result["alert_auto_acknowledged"] is False
    session.commit.assert_not_awaited()
