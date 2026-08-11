from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth_multitenant import get_current_admin
from app.main import app


@pytest.fixture(autouse=True)
def setup_overrides():
    app.dependency_overrides[get_current_admin] = lambda: {"username": "admin", "role": "master_admin"}
    yield
    app.dependency_overrides.pop(get_current_admin, None)


@pytest.fixture
def client():
    """Create a fresh TestClient for each test to prevent state leakage."""
    with TestClient(app) as test_client:
        yield test_client


def test_read_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "سیستم اتوماسیون UTCMS فعال است"}


def test_traffic_status(client):
    with patch("app.core.config.utcms_config.API_AUTH_MODE", "off"):
        response = client.get("/waybill/traffic-status")
    assert response.status_code == 200
    body = response.json()
    assert "active_requests" in body
    assert "queued_requests" in body
    assert "next_allowed_in_seconds" in body
    assert "blocked_for_seconds" in body


def _queue_payload():
    return {
        "session_id": "api-queue",
        "sender": {"name": "x", "phone": "1", "address": "a", "national_code": "1234567890"},
        "receiver": {"name": "y", "phone": "2", "address": "b"},
        "origin": {"province": "p", "city": "c", "address": "a", "coordinates": {"lat": 1, "lng": 1}},
        "destination": {
            "province": "p2",
            "city": "c2",
            "address": "a2",
            "coordinates": {"lat": 2, "lng": 2},
        },
        "cargo": {"weight": 1000},
        "vehicle": {},
        "financial": {},
    }


def test_enqueue_waybill_endpoint(client):
    with (
        patch("app.core.config.utcms_config.API_AUTH_MODE", "off"),
        patch(
            "app.queue.queue_manager.queue_manager.enqueue_waybill",
            new=AsyncMock(
                return_value={
                    "task_id": "task-1",
                    "idempotency_key": "idem-1",
                    "correlation_id": "corr-1",
                    "status": "queued",
                    "queued": True,
                    "reused": False,
                    "celery_task_id": "celery-1",
                }
            ),
        ),
    ):
        response = client.post("/waybill/queue/create-with-map", json=_queue_payload())

    assert response.status_code == 200
    assert response.json()["task_id"] == "task-1"
    assert response.json()["status"] == "queued"
    assert response.json()["correlation_id"] == "corr-1"


def test_enqueue_waybill_blank_idempotency_header_uses_auto_key(client):
    with (
        patch("app.core.config.utcms_config.API_AUTH_MODE", "off"),
        patch(
            "app.queue.queue_manager.queue_manager.enqueue_waybill",
            new=AsyncMock(
                return_value={
                    "task_id": "task-2",
                    "idempotency_key": "auto-generated",
                    "correlation_id": "corr-2",
                    "status": "queued",
                    "queued": True,
                    "reused": False,
                    "celery_task_id": "celery-2",
                }
            ),
        ) as mocked_enqueue,
    ):
        response = client.post(
            "/waybill/queue/create-with-map",
            json=_queue_payload(),
            headers={"X-Idempotency-Key": "   "},
        )

    assert response.status_code == 200
    assert mocked_enqueue.await_count == 1
    assert mocked_enqueue.await_args.kwargs["idempotency_key"] is None


def test_waybill_task_status_endpoint(client):
    with (
        patch("app.core.config.utcms_config.API_AUTH_MODE", "off"),
        patch(
            "app.queue.queue_manager.queue_manager.get_task_status",
            new=AsyncMock(
                return_value={
                    "task_id": "task-1",
                    "idempotency_key": "idem-1",
                    "correlation_id": "corr-1",
                    "status": "succeeded",
                    "attempt_count": 1,
                    "max_retries": 5,
                    "retryable": False,
                    "celery_task_id": "celery-1",
                    "worker_id": "worker-a",
                    "error_category": None,
                    "last_error": None,
                    "result": {"success": True},
                    "created_at": "2025-01-01T00:00:00",
                    "updated_at": "2025-01-01T00:00:01",
                    "started_at": "2025-01-01T00:00:00",
                    "finished_at": "2025-01-01T00:00:01",
                }
            ),
        ),
    ):
        response = client.get("/waybill/tasks/task-1")

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
    assert response.json()["correlation_id"] == "corr-1"


def test_correlation_header_round_trip(client):
    with patch("app.core.config.utcms_config.API_AUTH_MODE", "off"):
        response = client.get("/", headers={"X-Correlation-ID": "corr-root"})

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "corr-root"


def test_system_event_history_endpoint(client):
    with patch("app.realtime.events.event_hub.history", return_value=[{"task_id": "task-1", "status": "queued"}]):
        response = client.get("/events/history?task_id=task-1")

    assert response.status_code == 200
    assert response.json()["events"][0]["task_id"] == "task-1"


def test_worker_heartbeats_endpoint(client):
    import json
    from datetime import UTC, datetime
    from unittest.mock import MagicMock

    from app.core.database import get_session

    mock_worker = MagicMock()
    mock_worker.worker_id = "task-1"
    mock_worker.hostname = "server-a"
    mock_worker.status = "active"
    # Ensure it's not detected as stalled by using a very recent heartbeat
    mock_worker.last_heartbeat_at = datetime.now(UTC).replace(tzinfo=None)
    mock_worker.capabilities_json = json.dumps(["waybill"])
    mock_worker.capacity = 1

    mock_result = MagicMock()
    mock_result.all.return_value = [mock_worker]

    mock_session = AsyncMock()
    mock_session.exec = AsyncMock(return_value=mock_result)

    app.dependency_overrides[get_session] = lambda: mock_session
    try:
        response = client.get("/workers/heartbeats")
        assert response.status_code == 200
        assert "task-1" in response.json()["active"]
    finally:
        app.dependency_overrides.pop(get_session, None)


@patch("app.main.init_db", new_callable=AsyncMock)
@patch("app.automation.browser.browser_manager.close", new_callable=AsyncMock)
@patch("app.core.distributed_traffic.distributed_traffic_controller.initialize", new_callable=AsyncMock)
@patch("app.core.distributed_traffic.distributed_traffic_controller.close", new_callable=AsyncMock)
@patch("app.realtime.events.event_hub.start_subscriber")
@patch("app.realtime.events.event_hub.stop_subscriber", new_callable=AsyncMock)
@patch("app.services.task_service.task_service._ensure_queue_depth_seeded", new_callable=AsyncMock)
@patch("app.core.rate_limiter.rate_limiter.close", new_callable=AsyncMock)
def test_lifespan(
    mock_close_rl,
    mock_seed,
    mock_stop_sub,
    mock_start_sub,
    mock_dc_close,
    mock_dc_init,
    mock_close,
    mock_init_db,
):
    with TestClient(app):
        pass
    mock_init_db.assert_called()
    mock_close.assert_called()


def test_management_summary_endpoint(client):
    mock_summary_data = {
        "customers_count": 5,
        "routes_count": 10,
        "accounts_count": 15,
        "queue_count": 20,
        "active_accounts_count": 10,
        "otp_accounts_count": 2,
        "session_ready_accounts_count": 8,
        "queued_local_items_count": 5,
        "imported_queue_items_count": 15,
        "external_synced_items_count": 15,
    }
    with (
        patch("app.core.config.utcms_config.API_AUTH_MODE", "off"),
        patch(
            "app.api.routes.management.management_service.summary", new=AsyncMock(return_value=mock_summary_data)
        ) as mock_summary,
    ):
        response = client.get("/management/summary")

    assert response.status_code == 200
    assert response.json() == mock_summary_data
    mock_summary.assert_called_once()
