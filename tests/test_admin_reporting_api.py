import unittest.mock
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.auth_multitenant import get_current_admin
from app.main import app

client = TestClient(app)


async def override_get_current_admin():
    return {"username": "admin", "role": "master_admin"}


app.dependency_overrides[get_current_admin] = override_get_current_admin


@unittest.mock.patch("app.core.config.utcms_config.API_AUTH_MODE", "off")
def test_get_clients_summary_success():
    mock_summary_data = {
        "total_clients": 1,
        "active_clients": 1,
        "page": 1,
        "page_size": 50,
        "total_rows": 1,
        "rows": [
            {"client_id": 1, "client_code": "C123", "name": "Test Client", "total_drivers": 5, "success_rate": 95.0}
        ],
    }

    with patch(
        "app.api.routes.admin_reporting.admin_reporting_service.client_summary",
        new=AsyncMock(return_value=mock_summary_data),
    ) as mock_service:
        response = client.get("/api/v1/admin/reports/clients/summary")

        assert response.status_code == 200
        assert response.json() == mock_summary_data

        # Verify defaults
        mock_service.assert_called_once_with(page=1, page_size=50, date_from=None, date_to=None)


@unittest.mock.patch("app.core.config.utcms_config.API_AUTH_MODE", "off")
def test_get_clients_summary_with_query_params():
    mock_summary_data = {
        "total_clients": 10,
        "active_clients": 8,
        "page": 2,
        "page_size": 20,
        "total_rows": 10,
        "rows": [],
    }

    with patch(
        "app.api.routes.admin_reporting.admin_reporting_service.client_summary",
        new=AsyncMock(return_value=mock_summary_data),
    ) as mock_service:
        response = client.get(
            "/api/v1/admin/reports/clients/summary?page=2&page_size=20&date_from=2023-01-01&date_to=2023-12-31"
        )

        assert response.status_code == 200
        assert response.json() == mock_summary_data

        # Verify passed parameters
        mock_service.assert_called_once_with(page=2, page_size=20, date_from="2023-01-01", date_to="2023-12-31")


@unittest.mock.patch("app.core.config.utcms_config.API_AUTH_MODE", "off")
def test_get_clients_summary_invalid_params():
    with patch(
        "app.api.routes.admin_reporting.admin_reporting_service.client_summary", new=AsyncMock()
    ) as mock_service:
        # Invalid page (less than 1)
        response = client.get("/api/v1/admin/reports/clients/summary?page=0")
        assert response.status_code == 422

        # Invalid page_size (less than 1)
        response = client.get("/api/v1/admin/reports/clients/summary?page_size=0")
        assert response.status_code == 422

        # Invalid page_size (greater than 200)
        response = client.get("/api/v1/admin/reports/clients/summary?page_size=201")
        assert response.status_code == 422

        mock_service.assert_not_called()


def test_get_clients_summary_unauthorized():
    app.dependency_overrides.clear()
    response = client.get("/api/v1/admin/reports/clients/summary")
    assert response.status_code == 401
