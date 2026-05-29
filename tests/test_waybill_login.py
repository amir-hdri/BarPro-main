from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.api.routes.waybill_map import (
    CargoModel,
    FinancialModel,
    GeoCoordinateModel,
    LocationModel,
    ReceiverModel,
    SenderModel,
    UTCMSLoginModel,
    VehicleModel,
    WaybillMapRequest,
    create_waybill_with_map,
)


def create_mock_request():
    return WaybillMapRequest(
        session_id="test_session",
        sender=SenderModel(name="Sender", phone="09121234567", address="Addr", national_code="1234567890"),
        receiver=ReceiverModel(name="Receiver", phone="09121234567", address="Addr"),
        origin=LocationModel(province="Test", city="City", address="Addr", coordinates=GeoCoordinateModel(lat=1.0, lng=1.0)),
        destination=LocationModel(province="Test", city="City", address="Addr", coordinates=GeoCoordinateModel(lat=2.0, lng=2.0)),
        cargo=CargoModel(type="Type", weight=1000, count=1, description="Desc"),
        vehicle=VehicleModel(driver_national_code="1234567890", driver_phone="09121234567", plate="12A34567", type="Truck"),
        financial=FinancialModel(cost=1000000, payment_method="Cash")
    )

@pytest.mark.asyncio
async def test_waybill_login_success():
    # Mock dependencies
    mock_request = create_mock_request()
    mock_request.utcms_auth = UTCMSLoginModel(
        username="testuser",
        password="testpass",
        login_url="https://barname.utcms.ir/Barname/Account/Login",
    )

    with patch("app.automation.browser.browser_manager.initialize", new_callable=AsyncMock) as mock_init, \
         patch("app.automation.browser.browser_manager.create_context", new_callable=AsyncMock) as mock_create_context, \
         patch("app.automation.browser.browser_manager.new_page", new_callable=AsyncMock) as mock_new_page, \
         patch("app.automation.browser.browser_manager.save_auth_state", new_callable=AsyncMock) as mock_save_auth_state, \
         patch("app.automation.browser.browser_manager.close_context", new_callable=AsyncMock) as mock_close_context, \
         patch("app.automation.auth.UTCMSAuthenticator") as MockAuth, \
         patch("app.automation.waybill_enhanced.EnhancedWaybillManager") as MockManager, \
         patch("app.automation.reporting.report_service.record_request", new_callable=AsyncMock), \
         patch("app.automation.reporting.report_service.record_success", new_callable=AsyncMock), \
         patch("app.automation.reporting.report_service.record_map_usage", new_callable=AsyncMock) as mock_record_map_usage:

        # Setup mock page and context
        mock_page = AsyncMock()
        mock_context = AsyncMock()
        mock_new_page.return_value = mock_page
        mock_create_context.return_value = ("session_uuid", mock_context) # Updated to return tuple

        # Setup authenticator mock
        mock_auth_instance = MockAuth.return_value
        mock_auth_instance._is_logged_in = AsyncMock(return_value=False)
        mock_auth_instance.login = AsyncMock(return_value=True)

        # Setup manager mock
        mock_manager_instance = MockManager.return_value
        mock_manager_instance.create_waybill_with_map = AsyncMock(return_value={"origin_method": "map"})

        # Call the function
        result = await create_waybill_with_map(mock_request)

        # Assertions
        mock_auth_instance._is_logged_in.assert_called_once()
        mock_auth_instance.login.assert_called_once_with(
            "testuser",
            "testpass",
            login_url="https://barname.utcms.ir/Barname/Account/Login",
        )
        assert "auth_state_path" in mock_create_context.await_args.kwargs
        mock_save_auth_state.assert_awaited_once()
        mock_manager_instance.create_waybill_with_map.assert_called_once()
        mock_record_map_usage.assert_called_once_with("unknown")
        assert result["origin_method"] == "map"

@pytest.mark.asyncio
async def test_waybill_login_with_request_credentials():
    mock_request = create_mock_request()
    mock_request.utcms_auth = UTCMSLoginModel(
        username="user_from_request",
        password="pass_from_request",
        login_url="https://barname.utcms.ir/Barname/Account/Login",
    )

    with patch("app.automation.browser.browser_manager.initialize", new_callable=AsyncMock), \
         patch("app.automation.browser.browser_manager.create_context", new_callable=AsyncMock) as mock_create_context, \
         patch("app.automation.browser.browser_manager.new_page", new_callable=AsyncMock) as mock_new_page, \
         patch("app.automation.browser.browser_manager.save_auth_state", new_callable=AsyncMock) as mock_save_auth_state, \
         patch("app.automation.browser.browser_manager.close_context", new_callable=AsyncMock), \
         patch("app.automation.auth.UTCMSAuthenticator") as MockAuth, \
         patch("app.automation.waybill_enhanced.EnhancedWaybillManager") as MockManager, \
         patch("app.automation.reporting.report_service.record_request", new_callable=AsyncMock), \
         patch("app.automation.reporting.report_service.record_success", new_callable=AsyncMock), \
         patch("app.automation.reporting.report_service.record_map_usage", new_callable=AsyncMock):

        mock_page = AsyncMock()
        mock_context = AsyncMock()
        mock_new_page.return_value = mock_page
        mock_create_context.return_value = ("session_uuid", mock_context)

        mock_auth_instance = MockAuth.return_value
        mock_auth_instance._is_logged_in = AsyncMock(return_value=False)
        mock_auth_instance.login = AsyncMock(return_value=True)

        mock_manager_instance = MockManager.return_value
        mock_manager_instance.create_waybill_with_map = AsyncMock(return_value={"origin_method": "map"})

        await create_waybill_with_map(mock_request)

        mock_auth_instance.login.assert_called_once_with(
            "user_from_request",
            "pass_from_request",
            login_url="https://barname.utcms.ir/Barname/Account/Login",
        )
        assert "auth_state_path" in mock_create_context.await_args.kwargs
        mock_save_auth_state.assert_awaited_once()

@pytest.mark.asyncio
async def test_waybill_login_failure():
    # Mock dependencies
    mock_request = create_mock_request()
    mock_request.utcms_auth = UTCMSLoginModel(
        username="testuser",
        password="testpass",
        login_url="https://barname.utcms.ir/Barname/Account/Login",
    )

    with patch("app.automation.browser.browser_manager.initialize", new_callable=AsyncMock), \
         patch("app.automation.browser.browser_manager.create_context", new_callable=AsyncMock) as mock_create_context, \
         patch("app.automation.browser.browser_manager.new_page", new_callable=AsyncMock) as mock_new_page, \
         patch("app.automation.browser.browser_manager.save_auth_state", new_callable=AsyncMock), \
         patch("app.automation.browser.browser_manager.close_context", new_callable=AsyncMock), \
         patch("app.automation.auth.UTCMSAuthenticator") as MockAuth, \
         patch("app.automation.reporting.report_service.record_request", new_callable=AsyncMock), \
         patch("app.automation.reporting.report_service.record_failure", new_callable=AsyncMock):

        # Setup mock page and context
        mock_page = AsyncMock()
        mock_context = AsyncMock()
        mock_new_page.return_value = mock_page
        mock_create_context.return_value = ("session_uuid", mock_context) # Updated to return tuple

        # Setup authenticator mock to fail login
        mock_auth_instance = MockAuth.return_value
        mock_auth_instance._is_logged_in = AsyncMock(return_value=False)
        mock_auth_instance.login = AsyncMock(return_value=False)

        # Expect HTTPException
        with pytest.raises(HTTPException) as excinfo:
            await create_waybill_with_map(mock_request)

        # In my updated waybill_map.py, I explicitly re-raise HTTPException
        # except HTTPException as e:
        #     await report_service.record_failure()
        #     raise e
        # So it should be 401
        assert excinfo.value.status_code == 401
        assert "خطا در ورود به سامانه بارنامه" in excinfo.value.detail

@pytest.mark.asyncio
async def test_waybill_already_logged_in():
    # Mock dependencies
    mock_request = create_mock_request()

    with patch("app.automation.browser.browser_manager.initialize", new_callable=AsyncMock), \
         patch("app.automation.browser.browser_manager.create_context", new_callable=AsyncMock) as mock_create_context, \
         patch("app.automation.browser.browser_manager.new_page", new_callable=AsyncMock) as mock_new_page, \
         patch("app.automation.browser.browser_manager.save_auth_state", new_callable=AsyncMock) as mock_save_auth_state, \
         patch("app.automation.browser.browser_manager.close_context", new_callable=AsyncMock), \
         patch("app.automation.auth.UTCMSAuthenticator") as MockAuth, \
         patch("app.automation.waybill_enhanced.EnhancedWaybillManager") as MockManager, \
         patch("app.automation.reporting.report_service.record_request", new_callable=AsyncMock), \
         patch("app.automation.reporting.report_service.record_success", new_callable=AsyncMock), \
         patch("app.automation.reporting.report_service.record_map_usage", new_callable=AsyncMock):

        # Setup mock page and context
        mock_page = AsyncMock()
        mock_context = AsyncMock()
        mock_new_page.return_value = mock_page
        mock_create_context.return_value = ("session_uuid", mock_context) # Updated to return tuple

        # Setup authenticator mock to be already logged in
        mock_auth_instance = MockAuth.return_value
        mock_auth_instance._is_logged_in = AsyncMock(return_value=True)

        # Setup manager mock
        mock_manager_instance = MockManager.return_value
        mock_manager_instance.create_waybill_with_map = AsyncMock(return_value={"origin_method": "map"})

        # Call the function
        await create_waybill_with_map(mock_request)

        # Assertions
        mock_auth_instance._is_logged_in.assert_called_once()
        mock_auth_instance.login.assert_not_called()
        mock_save_auth_state.assert_awaited_once()

@pytest.mark.asyncio
async def test_waybill_missing_credentials():
    # Mock dependencies
    mock_request = create_mock_request()

    with patch("app.automation.browser.browser_manager.initialize", new_callable=AsyncMock), \
         patch("app.automation.browser.browser_manager.create_context", new_callable=AsyncMock) as mock_create_context, \
         patch("app.automation.browser.browser_manager.new_page", new_callable=AsyncMock) as mock_new_page, \
         patch("app.automation.browser.browser_manager.close_context", new_callable=AsyncMock), \
         patch("app.automation.auth.UTCMSAuthenticator") as MockAuth, \
         patch("app.automation.reporting.report_service.record_request", new_callable=AsyncMock), \
         patch("app.automation.reporting.report_service.record_failure", new_callable=AsyncMock), \
         patch("app.core.config.utcms_config.UTCMS_USERNAME", ""), \
         patch("app.core.config.utcms_config.UTCMS_PASSWORD", ""):

        # Setup mock page and context
        mock_page = AsyncMock()
        mock_context = AsyncMock()
        mock_new_page.return_value = mock_page
        mock_create_context.return_value = ("session_uuid", mock_context) # Updated to return tuple

        # Setup authenticator mock to report not logged in
        mock_auth_instance = MockAuth.return_value
        mock_auth_instance._is_logged_in = AsyncMock(return_value=False)

        # Expect HTTPException due to missing credentials
        with pytest.raises(HTTPException) as excinfo:
            await create_waybill_with_map(mock_request)

        assert excinfo.value.status_code == 401
        assert "اطلاعات ورود UTCMS" in excinfo.value.detail
