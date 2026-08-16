import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest
from fastapi import HTTPException

from app.automation.http_browser_bridge import UtcmsHttpBrowserBridge
from app.core.error_taxonomy import ErrorCategory
from app.models_multitenant import TaskStatus, WaybillJob
from app.orchestrator.state_machine import JobStatus
from app.schemas.itmb_ws import WS01InsertBOLRequest
from app.services.itmb_ws_service import ITMBWSService
from app.workers.waybill_worker import _is_retryable


def _sample_itmb_payload():
    return {
        "CompanyCode": "COMPANY01",
        "ServicePassword": "secret-pass",
        "InsertTime": 1710000000,
        "InsertPosition": {
            "Latitude": 35.6892,
            "Longitude": 51.3890,
            "Altitude": 1200,
            "Bearing": 90,
            "NumberOfSatellite": 8,
            "PDOP": 2,
            "GPSSpeed": 0,
            "GPSMaxSpeed": 0,
            "GPSTotalTraveledDistance": 0,
        },
        "bol": {
            "PlaqueID": "1234567",
            "PlaqueSN": 12,
            "PlaqueType": "IRI",
            "DriverNationalCode": "1234567890",
            "OWNERNATIONALID": "12345678901",
            "SenderType": 2,
            "SenderName": "ارسال کننده",
            "SenderAddress": "تهران",
            "RecieverType": 2,
            "RecieverName": "گیرنده",
            "RecieverAddress": "مشهد",
            "Freightage": 1000,
            "PreFreightage": 200,
            "FreightageTax": 100,
            "CompanyCommission": 50,
            "ITServiceCost": 30,
            "InfoServiceCost": 20,
            "InsuranceCosts": 10,
            "TotalAmountPayment": 1410,
            "SerialNo": 10001,
            "IssuerNaCode": "0987654321",
            "IssueDate": 1710000000,
            "LoadingPlaceAddress": "مبدا",
            "OffLoadingPlaceAddress": "مقصد",
            "Goods": [
                {
                    "GoodID": 10,
                    "WeightKg": 1500.5,
                    "Value": 2,
                    "PackingTypeID": 3,
                    "GoodtypeID": 1,
                    "Description": "محصول",
                }
            ],
        },
    }


@pytest.mark.asyncio
async def test_bridge_does_not_retry_mutating_post_method() -> None:
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page, timeout=5.0)

    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 503
    mock_response.headers = {}
    mock_response.content = b"Service Unavailable"
    mock_session.request.return_value = mock_response
    bridge._new_session = MagicMock(return_value=mock_session)
    bridge._session = mock_session

    request = MagicMock()
    request.url = "https://barname.utcms.ir/Barname/PrintReport/printbarnameNew"
    request.method = "POST"
    request.resource_type = "xhr"
    request.post_data_buffer = b"payload"
    request.all_headers = AsyncMock(return_value={"Content-Type": "application/x-www-form-urlencoded"})

    route = MagicMock()
    route.request = request
    route.fulfill = AsyncMock()

    await bridge._fulfill_utcms(route, request)

    # Must be called exactly ONCE for POST, never retried
    assert mock_session.request.call_count == 1
    route.fulfill.assert_awaited_once()
    assert route.fulfill.await_args.kwargs["status"] == 503


@pytest.mark.asyncio
async def test_bridge_retries_safe_get_method_on_transient_error() -> None:
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page, timeout=5.0)

    mock_session = MagicMock()
    res_503 = MagicMock(status_code=503, headers={}, content=b"Err")
    res_200 = MagicMock(status_code=200, headers={"Content-Type": "text/html"}, content=b"OK")
    mock_session.request.side_effect = [res_503, res_200]
    bridge._new_session = MagicMock(return_value=mock_session)
    bridge._session = mock_session

    request = MagicMock()
    request.url = "https://barname.utcms.ir/Barname/Document/fillStates"
    request.method = "GET"
    request.resource_type = "fetch"
    request.post_data_buffer = None
    request.all_headers = AsyncMock(return_value={})

    route = MagicMock()
    route.request = request
    route.fulfill = AsyncMock()

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await bridge._fulfill_utcms(route, request)

    # GET is safe and was retried on 503
    assert mock_session.request.call_count == 2
    route.fulfill.assert_awaited_once()
    assert route.fulfill.await_args.kwargs["status"] == 200


@pytest.mark.asyncio
async def test_bridge_mutating_failure_aborts_route_without_chromium_fallback() -> None:
    page = MagicMock()
    bridge = UtcmsHttpBrowserBridge(page)

    route = MagicMock()
    route.request.url = "https://barname.utcms.ir/Barname/PrintReport/printbarnameNew"
    route.request.method = "POST"
    route.request.resource_type = "xhr"
    route.continue_ = AsyncMock()
    route.abort = AsyncMock()

    with patch.object(bridge, "_fulfill_utcms", side_effect=RuntimeError("Connection timeout")):
        await bridge._handle_route(route)

    # Fallback to continue_ is FORBIDDEN for mutating POST
    route.continue_.assert_not_awaited()
    route.abort.assert_awaited_once()


@pytest.mark.asyncio
async def test_itmb_insert_bol_does_not_retry_on_timeout_or_500() -> None:
    service = ITMBWSService()
    request = WS01InsertBOLRequest(**_sample_itmb_payload())

    call_count = 0

    def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectTimeout("Connection timed out after 30s")

    with patch("httpx.AsyncClient.post", side_effect=mock_post), \
         patch("app.services.itmb_baseinfo_service.itmb_baseinfo_service.validate_bol_references", return_value={"valid": True}):
        with pytest.raises(HTTPException) as exc_info:
            await service.insert_bol(request)

        assert exc_info.value.status_code == 503
        # Exactly one attempt, no automatic retry on mutating WS01
        assert call_count == 1


def test_is_retryable_rejects_ambiguous_and_unconfirmed_mutations() -> None:
    # 1. Ambiguous mutation status must NEVER be retried
    assert not _is_retryable({"mutation_status": "ambiguous", "error_category": "network_error"})
    assert not _is_retryable({"mutation_attempted": True, "error_category": "system_error"})

    # 2. Submission unconfirmed category must NEVER be retried
    assert not _is_retryable({"error_category": "submission_unconfirmed"})
    assert not _is_retryable({"error_category": ErrorCategory.SUBMISSION_UNCONFIRMED.value})

    # 3. Status unknown or reconciling must NEVER be retried
    assert not _is_retryable({"status": "unknown"})
    assert not _is_retryable({"status": "reconciling"})

    # 4. Pure pre-mutation login/captcha failure IS retryable
    assert _is_retryable({"error_category": "captcha_failed", "status": "failed"})
    assert _is_retryable({"error_category": "network_error", "status": "failed"})


@pytest.mark.asyncio
async def test_timeout_after_submit_transitions_to_unknown_without_retry() -> None:
    from app.automation.waybill_enhanced import EnhancedWaybillManager

    page = MagicMock()
    page.on = MagicMock()
    context = MagicMock()
    manager = EnhancedWaybillManager(page, context)

    # Mock page elements
    page.locator.return_value.first.wait_for = AsyncMock()
    manager._handle_submit_captcha_if_present = AsyncMock()
    manager._click_once_no_retry = AsyncMock(return_value=(True, None))
    manager._close_blocking_overlays = AsyncMock()
    manager._wait_for_network_settle = AsyncMock()
    manager._wait_for_response_match = AsyncMock(return_value=MagicMock())

    # Simulate timeout waiting for submit response after click
    manager._consume_json_response = AsyncMock(side_effect=TimeoutError("Response timeout after 30s"))

    result = await manager._submit_waybill(otp_value=None, job_id="job_test_timeout")

    assert result["status"] == "unknown"
    assert result["mutation_status"] == "ambiguous"
    assert result["error_category"] == "submission_unconfirmed"
    assert not _is_retryable(result)


@pytest.mark.asyncio
async def test_connection_reset_after_submit_transitions_to_unknown_without_retry() -> None:
    from app.automation.waybill_enhanced import EnhancedWaybillManager

    page = MagicMock()
    page.on = MagicMock()
    context = MagicMock()
    manager = EnhancedWaybillManager(page, context)

    # Mock page elements
    page.locator.return_value.first.wait_for = AsyncMock()
    manager._handle_submit_captcha_if_present = AsyncMock()
    manager._click_once_no_retry = AsyncMock(return_value=(True, None))
    manager._close_blocking_overlays = AsyncMock()
    manager._wait_for_network_settle = AsyncMock()
    manager._wait_for_response_match = AsyncMock(return_value=MagicMock())

    # Simulate connection reset after submit click
    manager._consume_json_response = AsyncMock(side_effect=ConnectionResetError("Connection reset by peer"))

    result = await manager._submit_waybill(otp_value=None, job_id="job_test_reset")

    assert result["status"] == "unknown"
    assert result["mutation_status"] == "ambiguous"
    assert result["error_category"] == "submission_unconfirmed"
    assert not _is_retryable(result)


@pytest.mark.asyncio
async def test_click_once_no_retry_does_not_retry_on_post_click_error() -> None:
    from app.automation.waybill_enhanced import EnhancedWaybillManager

    page = MagicMock()
    page.on = MagicMock()
    context = MagicMock()
    manager = EnhancedWaybillManager(page, context)

    mock_locator = AsyncMock()
    click_calls = 0

    async def mock_click(*args, **kwargs):
        nonlocal click_calls
        click_calls += 1
        raise RuntimeError("Target page, context or browser has been closed")

    mock_locator.click = mock_click
    manager.smart_locator = MagicMock()
    manager.smart_locator.locate = AsyncMock(return_value=mock_locator)

    clicked, error = await manager._click_once_no_retry(["#btnSubmit"], "ثبت نهایی")

    # Click was attempted exactly ONCE
    assert click_calls == 1
    assert clicked is True
    assert error is not None
    assert "closed" in str(error)

