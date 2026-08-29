from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

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
    with patch("app.automation.browser_manager.create_context", new_callable=AsyncMock) as mock_create_context:
        mock_create_context.side_effect = Exception(sensitive_info)

        # We also need to mock initialize since it's called before create_context
        with (
            patch("app.automation.browser_manager.initialize", new_callable=AsyncMock),
            patch("app.core.config.utcms_config.API_AUTH_MODE", "off"),
        ):
            response = client.post("/waybill/detect-map?session_id=test_session")

            # Assert that the status code is 500
            assert response.status_code == 500

            # Assert that the sensitive info is NOT present in the response detail
            response_json = response.json()
            assert sensitive_info not in response_json["message"]
            assert response_json["message"] == "خطای داخلی سرور در تشخیص نقشه"


@pytest.mark.asyncio
async def test_create_waybill_leaks_sensitive_info():
    """
    Test that the /create-with-map endpoint leaks sensitive exception details.
    """
    sensitive_info = "SENSITIVE_API_KEY: 12345 exposed"

    # Payload for create_waybill_with_map
    payload = {
        "session_id": "test_session",
        "utcms_auth": {"username": "test-user", "password": "test-password"},
        "sender": {"name": "علی رضایی", "phone": "09123456789", "address": "خیابان آزادی پلاک ۱", "national_code": "0084575948"},
        "receiver": {"name": "رضا کرمی", "phone": "09129876543", "address": "بلوار جمهوری پلاک ۲"},
        "origin": {
            "province": "تهران",
            "city": "تهران",
            "address": "خیابان آزادی پلاک ۱",
            "coordinates": {"lat": 35.6892, "lng": 51.3890},
        },
        "destination": {
            "province": "اصفهان",
            "city": "اصفهان",
            "address": "بلوار جمهوری پلاک ۲",
            "coordinates": {"lat": 32.6546, "lng": 51.6680},
        },
        "cargo": {"type": "مصالح", "packaging": "فله", "weight": 1000, "value": 1000000, "count": 1, "description": "Test"},
        "vehicle": {
            "driver_national_code": "0084575948",
            "driver_phone": "09123333333",
            "plate": "12ب345ایران67",
            "type": "کامیون",
        },
        "financial": {"cost": 1000000, "payment_method": "Cash"},
    }

    # Mock browser_manager.create_context
    with patch("app.automation.browser_manager.create_context", new_callable=AsyncMock) as mock_create_context:
        mock_create_context.side_effect = Exception(sensitive_info)

        with (
            patch("app.automation.browser_manager.initialize", new_callable=AsyncMock),
            patch("app.core.config.utcms_config.API_AUTH_MODE", "off"),
        ):
            # We also need to mock report_service because it's called before the browser logic
            with patch("app.api.routes.waybill_map.report_service.record_request", new_callable=AsyncMock):
                with patch("app.api.routes.waybill_map.report_service.record_failure", new_callable=AsyncMock):
                    response = client.post("/waybill/create-with-map", json=payload)

                    assert response.status_code == 500
                    assert sensitive_info not in response.json()["message"]
                    assert response.json()["message"] == "خطای داخلی سرور در ثبت بارنامه"
