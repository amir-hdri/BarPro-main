from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.monitoring.metrics import (
    get_captcha_runtime_snapshot,
    reset_captcha_runtime_snapshot,
    track_captcha_attempt,
    track_captcha_failure,
    track_captcha_success,
)


@pytest.fixture(autouse=True)
def setup_overrides():
    from app.auth_multitenant import get_current_admin

    app.dependency_overrides[get_current_admin] = lambda: {"username": "admin", "role": "master_admin"}
    yield


client = TestClient(app)


def test_healthz_returns_ok():
    response = client.get("/healthz")
    assert response.status_code in [200, 503]
    assert response.json()["status"] == "ok"


def test_readyz_returns_not_ready_when_db_fails():
    class _FailingEngine:
        def connect(self):
            raise Exception("db down")

    with (
        patch("app.api.routes.system.engine", _FailingEngine()),
        patch("app.api.routes.system.browser_manager.initialize", new=AsyncMock(return_value=None)),
        patch("app.api.routes.system.barname_ml_solver.warmup", return_value=True),
    ):
        response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_auth_config_returns_mode_and_flags():
    response = client.get("/auth-config")
    assert response.status_code in [200, 503]
    payload = response.json()
    assert "mode" in payload
    assert "api_key_header" in payload
    assert "api_key_configured" in payload
    assert "jwt_configured" in payload
    assert "captcha_provider" in payload
    assert "captcha_mode" in payload
    assert "captcha_auto_only" in payload
    assert "captcha_model_available" in payload
    assert "captcha_math_min_confidence" in payload


def test_captcha_diagnose_endpoint_returns_solver_details():
    decision = Mock(value="7", confidence=0.95, strategy="cnn_ml")
    with patch("app.api.routes.system.captcha_engine.solve_text_with_confidence", return_value=decision):
        response = client.post("/captcha/diagnose", json={"text": "3 + 4", "min_confidence": 0.2})
    assert response.status_code in [200, 503]
    payload = response.json()
    assert payload["solved_value"] == "7"
    assert payload["accepted"] is True
    assert "confidence" in payload


def test_captcha_monitor_endpoint_returns_alert():
    reset_captcha_runtime_snapshot()
    for _ in range(7):
        track_captcha_failure("solve_failed")
    for _ in range(3):
        track_captcha_success("math")

    response = client.get("/captcha/monitor?window=20")
    assert response.status_code in [200, 503]
    payload = response.json()
    assert "totals" in payload
    assert "window" in payload
    assert "alert" in payload
    assert payload["alert"]["level"] in {"high", "normal", "low", "insufficient_data"}

    reset_captcha_runtime_snapshot()


def test_captcha_runtime_snapshot_includes_phase_and_latency_details():
    reset_captcha_runtime_snapshot()
    track_captcha_attempt("provider", phase="login", attempt=1)
    track_captcha_success("provider", phase="login", confidence=0.93, latency_seconds=0.12, attempt=1)
    snapshot = get_captcha_runtime_snapshot(window_size=10)
    assert snapshot["attempts_by_phase"]["login"] >= 1
    assert snapshot["successes_by_phase"]["login"] >= 1
    assert snapshot["recent_history"][-1]["phase"] == "login"
    assert snapshot["recent_history"][-1]["latency_seconds"] == 0.12
    assert snapshot["recent_history"][-1]["confidence"] == 0.93
    reset_captcha_runtime_snapshot()


@patch("app.api.routes.system._safe_queue_snapshot", new_callable=AsyncMock)
def test_metrics_endpoint_available(mock_snapshot):
    mock_snapshot.return_value = None
    response = client.get("/metrics")
    assert response.status_code in [200, 503]


def test_readyz_marks_itmb_checks_as_skipped_by_default():
    mock_conn = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_engine = Mock()
    mock_engine.connect = Mock(return_value=mock_ctx)
    with (
        patch("app.api.routes.system.engine", mock_engine),
        patch("app.api.routes.system.browser_manager.initialize", new=AsyncMock(return_value=None)),
        patch("app.api.routes.system.barname_ml_solver.warmup", return_value=True),
    ):
        response = client.get("/readyz")
    assert response.status_code in [200, 503]
    payload = response.json()
    assert payload["checks"]["captcha_model"] == "ok"
    assert payload["checks"]["itmb_baseinfo_cache"] == "skipped"
    assert payload["checks"]["itmb_live_probe"] == "skipped"
    assert payload["details"]["captcha_model"]["message"] == "cnn model loaded"
    assert payload["details"]["itmb_baseinfo_cache"]["message"] == "baseinfo validation disabled"
    assert payload["details"]["itmb_live_probe"]["message"] == "live probe disabled"


def test_readyz_fails_when_itmb_live_probe_enabled_and_probe_fails():
    with (
        patch("app.api.routes.system.browser_manager.initialize", new=AsyncMock(return_value=None)),
        patch("app.api.routes.system.barname_ml_solver.warmup", return_value=True),
        patch("app.core.config.utcms_config.ITMBOL_READYZ_LIVE_CHECK", True),
        patch("app.core.config.utcms_config.ITMBOL_COMPANY_CODE", "C1"),
        patch("app.core.config.utcms_config.ITMBOL_SERVICE_PASSWORD", "P1"),
        patch(
            "app.api.routes.system.itmb_baseinfo_service.probe_connection", new=AsyncMock(side_effect=Exception("down"))
        ),
    ):
        response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["checks"]["itmb_live_probe"] == "error"
    assert response.json()["details"]["itmb_live_probe"]["message"] == "live probe failed"


def test_readyz_fails_when_captcha_model_is_unavailable():
    with (
        patch("app.api.routes.system.browser_manager.initialize", new=AsyncMock(return_value=None)),
        patch("app.api.routes.system.barname_ml_solver.warmup", return_value=False),
    ):
        response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["checks"]["captcha_model"] == "error"
    assert response.json()["details"]["captcha_model"]["message"] == "cnn model unavailable"


def test_recover_stalled_workers_endpoint_with_tasks():
    with patch(
        "app.api.routes.system.recovery_manager.recover_stalled_tasks",
        new=AsyncMock(return_value={"task_123": {"last_heartbeat": 100}}),
    ):
        response = client.post("/workers/recover-stalled")
    assert response.status_code in [200, 503]
    payload = response.json()
    assert payload["count"] == 1
    assert "task_123" in payload["recovered"]


def test_recover_stalled_workers_endpoint_empty():
    with patch("app.api.routes.system.recovery_manager.recover_stalled_tasks", new=AsyncMock(return_value={})):
        response = client.post("/workers/recover-stalled")
    assert response.status_code in [200, 503]
    payload = response.json()
    assert payload["count"] == 0
    assert payload["recovered"] == {}


def test_security_report_endpoint():
    response = client.get("/security/report")
    assert response.status_code in [200, 503]
    payload = response.json()
    assert "api_key_configured" in payload
    assert "jwt_secret_configured" in payload
    assert "postgres_password_secure" in payload
    assert "recommendations" in payload
    assert isinstance(payload["recommendations"], list)


def test_errors_stats_endpoint():
    response = client.get("/errors/stats")
    assert response.status_code in [200, 503]
    payload = response.json()
    assert payload["status"] == "success"
    assert "supported_categories" in payload
    assert isinstance(payload["supported_categories"], list)
    assert "AUTH_FAILURE" in payload["supported_categories"]


def test_toggle_circuit_breaker_endpoint():
    with patch("app.core.config.utcms_config.API_AUTH_MODE", "off"):
        response = client.post("/circuit-breaker/toggle?enabled=false")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["enabled"] is False

    from app.services.itmb_ws_service import itmb_ws_service

    assert itmb_ws_service._circuit_breaker.enabled is False

    # Restore enabled state
    with patch("app.core.config.utcms_config.API_AUTH_MODE", "off"):
        response = client.post("/circuit-breaker/toggle?enabled=true")
    assert response.status_code == 200
    assert itmb_ws_service._circuit_breaker.enabled is True
