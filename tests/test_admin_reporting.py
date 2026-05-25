from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth_multitenant import get_current_admin
from app.schemas.admin import DriverReportFilter
from app.api.routes.admin_reporting import router

# Create an isolated FastAPI app for testing this router
app_for_test = FastAPI()
app_for_test.include_router(router)

client = TestClient(app_for_test)


def test_get_driver_report_unauthorized():
    """Test that the endpoint rejects requests without admin authentication."""
    response = client.get("/admin/reports/drivers/report")
    assert response.status_code == 401


def test_get_driver_report_success_no_filters():
    """Test that the endpoint works correctly with default parameters."""
    mock_report_data = {
        "items": [
            {
                "driver_id": 1,
                "first_name": "Test",
                "last_name": "Driver",
                "total_waybills": 5,
            }
        ],
        "total": 1,
        "page": 1,
        "page_size": 50,
    }

    # Mock the admin dependency
    app_for_test.dependency_overrides[get_current_admin] = lambda: {"sub": "admin123", "role": "admin"}

    with patch("app.api.routes.admin_reporting.admin_reporting_service.driver_report", new_callable=AsyncMock) as mock_driver_report:
        mock_driver_report.return_value = mock_report_data

        try:
            response = client.get("/admin/reports/drivers/report")

            assert response.status_code == 200
            assert response.json() == mock_report_data

            # Verify the service was called with default parameters
            mock_driver_report.assert_called_once()
            called_kwargs = mock_driver_report.call_args.kwargs
            assert "filters" in called_kwargs
            filters = called_kwargs["filters"]
            assert isinstance(filters, DriverReportFilter)
            assert filters.client_id is None
            assert filters.page == 1
            assert filters.page_size == 50
        finally:
            # Clear overrides
            app_for_test.dependency_overrides.clear()


def test_get_driver_report_success_with_filters():
    """Test that the endpoint correctly parses and passes query parameters."""
    mock_report_data = {
        "items": [],
        "total": 0,
        "page": 2,
        "page_size": 20,
    }

    # Mock the admin dependency
    app_for_test.dependency_overrides[get_current_admin] = lambda: {"sub": "admin123", "role": "admin"}

    with patch("app.api.routes.admin_reporting.admin_reporting_service.driver_report", new_callable=AsyncMock) as mock_driver_report:
        mock_driver_report.return_value = mock_report_data

        try:
            response = client.get(
                "/admin/reports/drivers/report",
                params={
                    "client_id": 10,
                    "driver_id": 42,
                    "plate_id": 100,
                    "status": "success",
                    "date_from": "2023-01-01",
                    "date_to": "2023-12-31",
                    "operation_type": "api",
                    "page": 2,
                    "page_size": 20,
                }
            )

            assert response.status_code == 200
            assert response.json() == mock_report_data

            # Verify the service was called with the provided filters
            mock_driver_report.assert_called_once()
            called_kwargs = mock_driver_report.call_args.kwargs
            assert "filters" in called_kwargs
            filters = called_kwargs["filters"]
            assert isinstance(filters, DriverReportFilter)
            assert filters.client_id == 10
            assert filters.driver_id == 42
            assert filters.plate_id == 100
            assert filters.status == "success"
            assert filters.date_from == "2023-01-01"
            assert filters.date_to == "2023-12-31"
            assert filters.operation_type == "api"
            assert filters.page == 2
            assert filters.page_size == 20
        finally:
            # Clear overrides
            app_for_test.dependency_overrides.clear()
