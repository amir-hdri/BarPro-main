from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.schemas.waybill import (
    CargoModel,
    FinancialModel,
    GeoCoordinateModel,
    LocationModel,
    OperationMode,
    ReceiverModel,
    SenderModel,
    UTCMSLoginModel,
    VehicleModel,
    WaybillMapRequest,
)
from app.services.waybill_service import WaybillService


def create_request(operation_mode: OperationMode = OperationMode.SAFE) -> WaybillMapRequest:
    return WaybillMapRequest(
        session_id="svc-test",
        operation_mode=operation_mode,
        sender=SenderModel(name="Sender", phone="0912", address="Addr", national_code="1234567890"),
        receiver=ReceiverModel(name="Receiver", phone="0912", address="Addr"),
        origin=LocationModel(province="A", city="B", address="C", coordinates=GeoCoordinateModel(lat=1.0, lng=1.0)),
        destination=LocationModel(
            province="D", city="E", address="F", coordinates=GeoCoordinateModel(lat=2.0, lng=2.0)
        ),
        cargo=CargoModel(type="General", weight=1000, count=1, description="test"),
        vehicle=VehicleModel(driver_national_code="123", driver_phone="0912", plate="12A34567", type="Truck"),
        financial=FinancialModel(cost=1000, payment_method="Cash"),
    )


@pytest.mark.asyncio
async def test_service_returns_safe_mode_response():
    service = WaybillService()
    request = create_request(OperationMode.SAFE)

    with (
        patch("app.automation.browser.browser_manager.initialize", AsyncMock()),
        patch("app.automation.browser.browser_manager.create_context", AsyncMock(return_value=("sid", AsyncMock()))),
        patch("app.automation.browser.browser_manager.new_page", AsyncMock(return_value=AsyncMock())),
        patch("app.automation.browser.browser_manager.close_context", AsyncMock()),
        patch("app.automation.auth.UTCMSAuthenticator") as auth_cls,
        patch("app.automation.waybill_enhanced.EnhancedWaybillManager") as manager_cls,
        patch("app.automation.reporting.report_service.record_request", AsyncMock()),
        patch("app.automation.reporting.report_service.record_success", AsyncMock()),
        patch("app.automation.reporting.report_service.record_map_usage", AsyncMock()),
    ):
        auth_instance = auth_cls.return_value
        auth_instance._is_logged_in = AsyncMock(return_value=True)

        manager_instance = manager_cls.return_value
        manager_instance.create_waybill_with_map = AsyncMock(
            return_value={"success": True, "status": "validated", "validation_summary": {"ready_for_submit": True}}
        )

        response = await service.create_waybill_with_map(request)

    assert response["mode"] == "safe"
    assert response["status"] == "validated"
    assert "request_id" in response
    assert response["validation_summary"]["has_driver_data"] is True


@pytest.mark.asyncio
async def test_service_blocks_full_mode_without_env_flag():
    service = WaybillService()
    request = create_request(OperationMode.FULL)

    with patch("app.core.config.utcms_config.ALLOW_LIVE_SUBMIT", False):
        with pytest.raises(HTTPException) as exc:
            await service.create_waybill_with_map(request)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_service_rejects_full_mode_when_preflight_requirements_missing():
    service = WaybillService()
    request = create_request(OperationMode.FULL)
    request.vehicle.driver_national_code = None
    request.vehicle.plate = None

    with patch("app.core.config.utcms_config.ALLOW_LIVE_SUBMIT", True):
        with pytest.raises(HTTPException) as exc:
            await service.create_waybill_with_map(request)

    assert exc.value.status_code == 422
    assert "missing_requirements" in exc.value.detail


@pytest.mark.asyncio
async def test_service_returns_503_when_login_fails_due_to_network():
    service = WaybillService()
    request = create_request(OperationMode.FULL)
    request.utcms_auth = UTCMSLoginModel(
        username="user",
        password="pass",
        login_url="https://barname.utcms.ir/Barname/Account/Login",
    )

    with (
        patch("app.core.config.utcms_config.ALLOW_LIVE_SUBMIT", True),
        patch("app.automation.browser.browser_manager.initialize", AsyncMock()),
        patch("app.automation.browser.browser_manager.create_context", AsyncMock(return_value=("sid", AsyncMock()))),
        patch("app.automation.browser.browser_manager.new_page", AsyncMock(return_value=AsyncMock())),
        patch("app.automation.browser.browser_manager.close_context", AsyncMock()),
        patch("app.automation.auth.UTCMSAuthenticator") as auth_cls,
        patch("app.automation.reporting.report_service.record_request", AsyncMock()),
        patch("app.automation.reporting.report_service.record_failure", AsyncMock()),
    ):
        auth_instance = auth_cls.return_value
        auth_instance._is_logged_in = AsyncMock(return_value=False)
        auth_instance.login = AsyncMock(return_value=False)
        auth_instance.last_error = "دسترسی به صفحه ورود UTCMS ممکن نشد (ERR_NAME_NOT_RESOLVED)."

        with pytest.raises(HTTPException) as exc:
            await service.create_waybill_with_map(request)

    assert exc.value.status_code == 503
    assert "اتصال" in exc.value.detail
