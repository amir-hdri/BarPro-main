from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.core.exceptions import WaybillError
from app.core.network import is_retryable_network_error
from app.schemas.waybill import (
    CargoModel,
    FinancialModel,
    GeoCoordinateModel,
    LocationModel,
    OperationMode,
    ReceiverModel,
    SenderModel,
    VehicleModel,
    WaybillMapRequest,
)
from app.services.waybill_service import WaybillService


def _request() -> WaybillMapRequest:
    return WaybillMapRequest(
        session_id="network-test",
        operation_mode=OperationMode.SAFE,
        sender=SenderModel(name="S", phone="0912", address="A", national_code="1234567890"),
        receiver=ReceiverModel(name="R", phone="0912", address="B"),
        origin=LocationModel(province="P1", city="C1", address="O", coordinates=GeoCoordinateModel(lat=1.0, lng=1.0)),
        destination=LocationModel(
            province="P2",
            city="C2",
            address="D",
            coordinates=GeoCoordinateModel(lat=2.0, lng=2.0),
        ),
        cargo=CargoModel(type="General", weight=1000, count=1, description="x"),
        vehicle=VehicleModel(driver_national_code="123", driver_phone="0912", plate="12A34567", type="Truck"),
        financial=FinancialModel(cost=1000, payment_method="Cash"),
    )


def test_retryable_network_error_detects_dns_and_timeout():
    assert is_retryable_network_error("net::ERR_NAME_NOT_RESOLVED")
    assert is_retryable_network_error("could not resolve host")
    assert is_retryable_network_error("ReadTimeout")
    assert not is_retryable_network_error("field validation failed")


@pytest.mark.asyncio
async def test_service_maps_retryable_waybill_error_to_503():
    service = WaybillService()
    request = _request()

    with patch("app.automation.browser.browser_manager.initialize", AsyncMock()), patch(
        "app.automation.browser.browser_manager.create_context", AsyncMock(return_value=("sid", AsyncMock()))
    ), patch("app.automation.browser.browser_manager.new_page", AsyncMock(return_value=AsyncMock())), patch(
        "app.automation.browser.browser_manager.close_context", AsyncMock()
    ), patch("app.automation.auth.UTCMSAuthenticator") as auth_cls, patch(
        "app.automation.waybill_enhanced.EnhancedWaybillManager"
    ) as manager_cls, patch("app.automation.reporting.report_service.record_request", AsyncMock()), patch(
        "app.automation.reporting.report_service.record_failure", AsyncMock()
    ), patch("app.core.config.utcms_config.UTCMS_USERNAME", "user"), patch(
        "app.core.config.utcms_config.UTCMS_PASSWORD", "pass"
    ):
        auth_instance = auth_cls.return_value
        auth_instance._is_logged_in = AsyncMock(return_value=True)

        manager_instance = manager_cls.return_value
        manager_instance.create_waybill_with_map = AsyncMock(
            side_effect=WaybillError("net::ERR_NAME_NOT_RESOLVED")
        )

        with pytest.raises(HTTPException) as exc:
            await service.create_waybill_with_map(request)

    assert exc.value.status_code == 503
