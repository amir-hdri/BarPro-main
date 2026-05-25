from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from app.main import app
import pytest

client = TestClient(app)

@pytest.mark.asyncio
async def test_detect_map_leaks_sensitive_info():
    """
    Test that the /detect-map endpoint leaks sensitive exception details in the response.
    This test is expected to pass BEFORE the fix (confirming the vulnerability)
    and FAIL AFTER the fix (confirming the fix works, but we'll modify the assertion then).
    """
    sensitive_info = "SENSITIVE_DB_INFO: connection string exposed"

    # Mock browser_manager.create_context to raise an exception with sensitive info
    with patch("app.api.routes.waybill_map.browser_manager.create_context", new_callable=AsyncMock) as mock_create_context:
        mock_create_context.side_effect = Exception(sensitive_info)

        # We also need to mock initialize since it's called before create_context
        with patch("app.api.routes.waybill_map.browser_manager.initialize", new_callable=AsyncMock), \
             patch("app.core.config.utcms_config.API_AUTH_MODE", "off"):

            response = client.post("/waybill/detect-map?session_id=test_session")

            # Assert that the status code is 500
            assert response.status_code == 500

            # Assert that the sensitive info is NOT present in the response detail
            response_json = response.json()
            assert sensitive_info not in response_json["detail"]
            assert response_json["detail"] == "خطای داخلی سرور در تشخیص نقشه"

@pytest.mark.asyncio
async def test_create_waybill_leaks_sensitive_info():
    """
    Test that the /create-with-map endpoint leaks sensitive exception details.
    """
    sensitive_info = "SENSITIVE_API_KEY: 12345 exposed"

    # Payload for create_waybill_with_map
    payload = {
        "session_id": "test_session",
        "sender": {
            "name": "Test Sender",
            "phone": "09123456789",
            "address": "Tehran",
            "national_code": "1234567890"
        },
        "receiver": {
            "name": "Test Receiver",
            "phone": "09123456789",
            "address": "Isfahan"
        },
        "origin": {
            "province": "Tehran",
            "city": "Tehran",
            "address": "Test Address",
            "coordinates": {"lat": 35.6892, "lng": 51.3890}
        },
        "destination": {
            "province": "Isfahan",
            "city": "Isfahan",
            "address": "Test Address",
            "coordinates": {"lat": 32.6546, "lng": 51.6680}
        },
        "cargo": {
            "type": "General",
            "weight": 1000,
            "count": 1,
            "description": "Test"
        },
        "vehicle": {
            "driver_national_code": "1234567890",
            "driver_phone": "09123456789",
            "plate": "12A34567",
            "type": "Truck"
        },
        "financial": {
            "cost": 1000000,
            "payment_method": "Cash"
        }
    }

    # Mock browser_manager.create_context
    with patch("app.api.routes.waybill_map.browser_manager.create_context", new_callable=AsyncMock) as mock_create_context:
        mock_create_context.side_effect = Exception(sensitive_info)

        with patch("app.api.routes.waybill_map.browser_manager.initialize", new_callable=AsyncMock), \
             patch("app.core.config.utcms_config.API_AUTH_MODE", "off"):
             # We also need to mock report_service because it's called before the browser logic
            with patch("app.api.routes.waybill_map.report_service.record_request", new_callable=AsyncMock):
                 with patch("app.api.routes.waybill_map.report_service.record_failure", new_callable=AsyncMock):
                    response = client.post("/waybill/create-with-map", json=payload)

                    assert response.status_code == 500
                    assert sensitive_info not in response.json()["detail"]
                    assert response.json()["detail"] == "خطای داخلی سرور در ثبت بارنامه"
