from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@patch("app.automation.browser.browser_manager.initialize", new_callable=AsyncMock)
@patch("app.automation.browser.browser_manager.close", new_callable=AsyncMock)
def test_create_waybill_validation_error(mock_close, mock_init):
    """
    Test that the waybill creation endpoint validates input data correctly.
    It should return 422 Unprocessable Entity when required fields are missing.
    """
    # Payload with empty sender, receiver, etc.
    payload = {
        "session_id": "test_session",
        "sender": {},
        "receiver": {},
        "origin": {
            "province": "Tehran",
            "city": "Tehran",
            "address": "Some address",
            "coordinates": {"lat": 35.0, "lng": 51.0},
        },
        "destination": {
            "province": "Mashhad",
            "city": "Mashhad",
            "address": "Some address",
            "coordinates": {"lat": 36.0, "lng": 59.0},
        },
        "cargo": {},
        "vehicle": {},
        "financial": {},
    }

    # We use context manager to handle lifespan events properly
    with patch("app.core.config.utcms_config.API_AUTH_MODE", "off"), TestClient(app) as client:
        response = client.post("/waybill/create-with-map", json=payload)

        # Expect 422 Validation Error
        assert response.status_code == 422
        res_json = response.json()
        errors = res_json.get("details", res_json.get("detail", []))

        # Verify specific fields are missing
        error_locs = [str(e["loc"][-1]) for e in errors]
        assert "name" in error_locs  # sender.name, receiver.name
        assert "weight" in error_locs  # cargo.weight


@patch("app.automation.browser.browser_manager.initialize", new_callable=AsyncMock)
@patch("app.automation.browser.browser_manager.close", new_callable=AsyncMock)
def test_create_waybill_valid_payload(mock_close, mock_init):
    """
    Test that a valid payload passes validation.
    It might fail later due to mocked browser, but should pass 422 check.
    """
    # We mock the manager to avoid actual logic execution failure
    with patch("app.automation.waybill_enhanced.EnhancedWaybillManager") as MockManager:
        # Mock instance and method
        instance = MockManager.return_value
        instance.create_waybill_with_map = AsyncMock(return_value={"success": True, "origin_method": "map"})

        # Mock auth to avoid login check failure
        with patch("app.automation.auth.UTCMSAuthenticator") as MockAuth:
            auth_instance = MockAuth.return_value
            auth_instance._is_logged_in = AsyncMock(return_value=True)

            # Also need to mock browser_manager.create_context and new_page
            with (
                patch("app.automation.browser.browser_manager.create_context", new_callable=AsyncMock) as mock_ctx,
                patch("app.automation.browser.browser_manager.new_page", new_callable=AsyncMock),
                patch("app.automation.browser.browser_manager.close_context", new_callable=AsyncMock),
            ):

                # Ensure create_context returns a tuple (session_id, context)
                mock_ctx.return_value = ("mock_session_id", AsyncMock())

                payload = {
                    "session_id": "test_session",
                    "sender": {
                        "name": "Sender Name",
                        "phone": "09123456789",
                        "address": "Sender Address",
                        "national_code": "1234567890",
                    },
                    "receiver": {"name": "Receiver Name", "phone": "09987654321", "address": "Receiver Address"},
                    "origin": {
                        "province": "Tehran",
                        "city": "Tehran",
                        "address": "Origin Address",
                        "coordinates": {"lat": 35.6892, "lng": 51.3890},
                    },
                    "destination": {
                        "province": "Mashhad",
                        "city": "Mashhad",
                        "address": "Dest Address",
                        "coordinates": {"lat": 36.2972, "lng": 59.6067},
                    },
                    "cargo": {"type": "General", "weight": 1000, "count": 10, "description": "Test Cargo"},
                    "vehicle": {
                        "driver_national_code": "0000000000",
                        "driver_phone": "09120000000",
                        "plate": "12A34567",
                        "type": "Truck",
                    },
                    "financial": {"cost": 5000000, "payment_method": "Cash"},
                }

                with (
                    patch("app.core.config.utcms_config.API_AUTH_MODE", "off"),
                    patch(
                        "app.api.routes.waybill_map.waybill_service.create_waybill_with_map",
                        new_callable=AsyncMock,
                        return_value={"success": True, "origin_method": "map"},
                    ),
                    TestClient(app) as client,
                ):
                    response = client.post("/waybill/create-with-map", json=payload)

                    # Should be 200 OK because we mocked everything
                    assert response.status_code == 200
                    assert response.json()["success"] is True
