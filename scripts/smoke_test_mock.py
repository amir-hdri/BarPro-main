import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

# Add project root to path
sys.path.append(os.getcwd())

from app.main import app


async def run_smoke_test():
    print("Starting smoke test simulation...")

    # Configure mock environment
    with (
        patch("app.core.config.utcms_config.API_AUTH_MODE", "off"),
        patch("app.automation.browser.browser_manager.initialize", new_callable=AsyncMock),
        patch("app.automation.browser.browser_manager.create_context", new_callable=AsyncMock) as mock_ctx,
        patch("app.automation.browser.browser_manager.new_page", new_callable=AsyncMock),
        patch("app.automation.browser.browser_manager.close_context", new_callable=AsyncMock),
        patch("app.automation.auth.UTCMSAuthenticator") as MockAuth,
        patch("app.automation.waybill_enhanced.EnhancedWaybillManager") as MockManager,
    ):
        # Mock browser session
        mock_ctx.return_value = ("mock_session_id", AsyncMock())

        # Mock auth success
        auth_instance = MockAuth.return_value
        auth_instance._is_logged_in = AsyncMock(return_value=True)

        # Mock waybill manager success
        manager_instance = MockManager.return_value
        manager_instance.create_waybill_with_map = AsyncMock(
            return_value={
                "success": True,
                "status": "validated",
                "validation_summary": {"ready_for_submit": True},
                "origin_method": "map",
                "destination_method": "map",
            }
        )

        client = TestClient(app)

        payload = {
            "session_id": "smoke_test",
            "operation_mode": "safe",
            "sender": {"name": "Ali Test", "phone": "09121234567", "address": "Tehran", "national_code": "1234567890"},
            "receiver": {"name": "Reza Test", "phone": "09127654321", "address": "Mashhad"},
            "origin": {
                "province": "Tehran",
                "city": "Tehran",
                "address": "Azadi",
                "coordinates": {"lat": 35.6892, "lng": 51.3890},
            },
            "destination": {
                "province": "Razavi Khorasan",
                "city": "Mashhad",
                "address": "Imam Reza",
                "coordinates": {"lat": 36.2972, "lng": 59.6067},
            },
            "cargo": {"type": "General", "weight": 5000, "count": 1, "description": "Test Cargo"},
            "vehicle": {
                "driver_national_code": "0000000000",
                "driver_phone": "09120000000",
                "plate": "12A34567",
                "type": "Truck",
            },
            "financial": {"cost": 10000000, "payment_method": "Cash"},
        }

        print("Sending request to /waybill/create-with-map...")
        response = client.post("/waybill/create-with-map", json=payload)

        if response.status_code == 200:
            print("Response Status: 200 OK")
            print("Response Body:", response.json())
            print("Smoke test PASSED.")
        else:
            print(f"Response Status: {response.status_code}")
            print("Response Body:", response.text)
            print("Smoke test FAILED.")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_smoke_test())
