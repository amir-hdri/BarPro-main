"""Tests for worker and tenant isolation security (UFW-based architecture).

These tests verify that:
1. Tenant clients cannot access admin resources.
2. Tenant isolation works for driver and job deletion.
3. Unauthenticated users cannot delete resources.

Note: BarPro uses UFW Firewall + fixed IPs for inter-node security, not WireGuard.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
from app.main import app
from app.auth_multitenant import get_current_client, get_current_user_or_admin
from app.core.database import get_session
from app.models_multitenant import Client


@pytest.fixture(autouse=True)
def clean_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


def test_worker_cannot_delete_admin_resources(client):
    mock_client = Client(id=1, client_code="TENANT1", name="Tenant 1")
    app.dependency_overrides[get_current_client] = lambda: mock_client
    app.dependency_overrides[get_current_user_or_admin] = lambda: {"role": "client", "user": mock_client}
    
    # We do NOT override get_current_admin, so the request has client role and fails
    resp = client.delete("/api/v1/admin/clients/2")
    assert resp.status_code in (401, 403)


def test_tenant_isolation_delete_driver(client):
    mock_client = Client(id=1, client_code="TENANT1", name="Tenant 1")
    app.dependency_overrides[get_current_client] = lambda: mock_client
    app.dependency_overrides[get_current_user_or_admin] = lambda: {"role": "client", "user": mock_client}
    
    mock_session = AsyncMock()
    # session.get returns None (driver not found / not owned)
    mock_session.get.return_value = None
    app.dependency_overrides[get_session] = lambda: mock_session
    
    resp = client.delete("/api/v1/drivers/999")
    assert resp.status_code in (404, 403)


def test_tenant_isolation_delete_job(client):
    mock_client = Client(id=1, client_code="TENANT1", name="Tenant 1")
    app.dependency_overrides[get_current_client] = lambda: mock_client
    app.dependency_overrides[get_current_user_or_admin] = lambda: {"role": "client", "user": mock_client}
    
    mock_session = AsyncMock()
    # session.exec returns result whose first() is None (job not found / not owned)
    mock_result = MagicMock()
    mock_result.first.return_value = None
    mock_session.exec.return_value = mock_result
    app.dependency_overrides[get_session] = lambda: mock_session
    
    resp = client.delete("/api/v1/waybill-jobs/999")
    assert resp.status_code in (404, 403)


def test_unauthenticated_cannot_delete(client):
    # Clear overrides to ensure unauthenticated
    app.dependency_overrides.clear()
    
    resp = client.delete("/api/v1/waybill-jobs/1")
    assert resp.status_code in (401, 403)
