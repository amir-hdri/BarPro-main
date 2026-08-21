from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.auth_multitenant import get_current_admin
from app.main import app

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_sensitive_system_endpoints_require_admin_authentication():
    previous_override = app.dependency_overrides.pop(get_current_admin, None)
    try:
        with TestClient(app) as client:
            assert client.get("/auth-config").status_code == 401
            assert client.get("/api/system/clean-ips").status_code == 401
            assert client.get("/system/clean-ips").status_code == 401
            assert client.post("/api/system/clean-ips/refresh").status_code == 401
            assert client.get("/api/v1/admin/readyz").status_code == 401
    finally:
        if previous_override is not None:
            app.dependency_overrides[get_current_admin] = previous_override


def test_canonical_clean_ip_endpoint_is_available_to_admin():
    previous_override = app.dependency_overrides.get(get_current_admin)
    app.dependency_overrides[get_current_admin] = lambda: {"username": "admin", "role": "master_admin"}
    try:
        with (
            patch(
                "app.automation.clean_ip_pool.clean_ip_pool.get_all_clean_ips",
                new=AsyncMock(return_value=[]),
            ),
            TestClient(app) as client,
        ):
            response = client.get("/api/system/clean-ips")
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_current_admin, None)
        else:
            app.dependency_overrides[get_current_admin] = previous_override

    assert response.status_code == 200
    assert response.json()["active_count"] == 0
    assert response.json()["proxies"] == []


def test_admin_readyz_keeps_diagnostics_but_never_returns_broker_credentials():
    checks = {
        "database": "ok",
        "browser": "ok",
        "config": "ok",
        "captcha_model": "ok",
        "itmb_config": "ok",
        "itmb_baseinfo_cache": "ok",
        "itmb_live_probe": "ok",
        "queue": "ok",
        "circuit_breaker": "ok",
    }
    details = {
        "database": {"message": "database connection ok"},
        "queue": {
            "message": "queue configured",
            "snapshot": {"queued": 3},
            "broker": "redis://:do-not-expose@redis:6379/0",
        },
        "circuit_breaker": {"message": "circuit healthy", "status": {"state": "closed"}},
    }
    previous_override = app.dependency_overrides.get(get_current_admin)
    app.dependency_overrides[get_current_admin] = lambda: {"username": "admin", "role": "master_admin"}
    try:
        with (
            patch("app.api.routes.system._readyz_snapshot", new=AsyncMock(return_value=(checks, details))),
            TestClient(app) as client,
        ):
            response = client.get("/api/v1/admin/readyz")
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_current_admin, None)
        else:
            app.dependency_overrides[get_current_admin] = previous_override

    assert response.status_code == 200
    assert response.json()["details"]["queue"]["snapshot"] == {"queued": 3}
    assert "broker" not in response.text.lower()
    assert "redis://" not in response.text.lower()


def test_nginx_blocks_legacy_backend_alias_and_preserves_canonical_api_proxy():
    config = (PROJECT_ROOT / "infra/nginx/http-server.conf").read_text(encoding="utf-8")

    assert "rewrite ^/backend/" not in config
    assert "location = /backend" in config
    assert "location ^~ /backend/" in config
    assert config.count("return 404;") >= 2
    assert "location ~ ^/api/v1/(.*)" in config
    assert "proxy_pass $backend_upstream;" in config
