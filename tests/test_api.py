from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.auth_multitenant import get_current_admin
from app.main import app

import pytest


@pytest.fixture(autouse=True)
def setup_overrides():
    app.dependency_overrides[get_current_admin] = lambda: {"username": "admin", "role": "master_admin"}
    yield


client = TestClient(app)


def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "سیستم اتوماسیون UTCMS فعال است"}


def test_traffic_status():
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


def test_enqueue_waybill_endpoint():
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


def test_enqueue_waybill_blank_idempotency_header_uses_auto_key():
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


def test_waybill_task_status_endpoint():
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


def test_correlation_header_round_trip():
    with patch("app.core.config.utcms_config.API_AUTH_MODE", "off"):
        response = client.get("/", headers={"X-Correlation-ID": "corr-root"})

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "corr-root"


def test_system_event_history_endpoint():
    with patch("app.realtime.events.event_hub.history", return_value=[{"task_id": "task-1", "status": "queued"}]):
        response = client.get("/events/history?task_id=task-1")

    assert response.status_code == 200
    assert response.json()["events"][0]["task_id"] == "task-1"


def test_worker_heartbeats_endpoint():
    with (
        patch(
            "app.core.worker_heartbeat.worker_heartbeat_registry.snapshot",
            return_value={"task-1": {"status": "running"}},
        ),
        patch(
            "app.core.worker_heartbeat.worker_heartbeat_registry.detect_stalled",
            return_value={},
        ),
    ):
        response = client.get("/workers/heartbeats")

    assert response.status_code == 200
    assert "task-1" in response.json()["active"]


@patch("app.main.init_db", new_callable=AsyncMock)
@patch("app.automation.browser.browser_manager.close", new_callable=AsyncMock)
def test_lifespan(mock_close, mock_init_db):
    with TestClient(app):
        pass
    mock_init_db.assert_called()
    mock_close.assert_called()


def test_management_summary_endpoint():
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
