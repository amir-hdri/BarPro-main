"""Verification tests for automated waybill registration and GPS shipping lifecycle."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.automation.gps_shipping_manager import (
    DEFAULT_CITY_COORDS,
    ShippingState,
    auto_complete_shipping,
    find_city_coordinates,
    init_shipping,
)
from app.automation.utcms_mobile_client import UtcmsMobileClient
from app.automation.waybill_bot_multitenant import WaybillAutomationBot


def test_city_coordinates_includes_all_schedule_cities():
    """Verify that schedule cities like شوط, دیزج, مرگان, طالقان, کاشمر are present."""
    assert "شوط" in DEFAULT_CITY_COORDS
    assert "دیزج" in DEFAULT_CITY_COORDS
    assert "مرگان" in DEFAULT_CITY_COORDS
    assert "طالقان" in DEFAULT_CITY_COORDS
    assert "کاشمر" in DEFAULT_CITY_COORDS

    shot_coords = find_city_coordinates("شوط")
    assert shot_coords is not None
    assert round(shot_coords[0], 2) == 39.22
    assert round(shot_coords[1], 2) == 45.03

    taleqan_coords = find_city_coordinates("طالقان")
    assert taleqan_coords is not None
    assert round(taleqan_coords[0], 2) == 36.18


@pytest.mark.asyncio
async def test_init_shipping_stores_doc_id():
    """Verify that init_shipping correctly records and stores doc_id."""
    state = await init_shipping(
        job_id="test-job-99",
        doc_no="1349757758",
        payload={
            "originLat": 39.22,
            "originLng": 45.03,
            "destLat": 39.11,
            "destLng": 45.06,
        },
        doc_id="226164459",
        persist=False,
    )
    assert state.doc_id == "226164459"
    assert state.doc_no == "1349757758"
    assert state.to_dict()["doc_id"] == "226164459"


@pytest.mark.asyncio
async def test_mobile_execution_enriches_compact_payload_and_starts_shipping():
    """Verify that a compact schedule payload without explicit coordinates or cargo items
    is properly enriched, submitted, and immediately triggers RegisterStartOfShipping.
    """
    bot = WaybillAutomationBot(proxy_url="http://squid:3128")

    compact_payload = {
        "origin": "آذربایجان غربی، شوط، دیزج",
        "destination": "آذربایجان غربی، شوط، مرگان",
        "cargo_type": "محصولات کشاورزی",
        "cargo_weight": 2500,
        "cargo_value": "50000000",
        "plate_number": "32ع444ایران27",
        "driver_national_code": "4929889601",
        "fare": "5,000,000",
    }

    mock_client = AsyncMock(spec=UtcmsMobileClient)
    mock_client.token = "test-token"
    mock_auth = SimpleNamespace(token="test-token", expires_at="2026-09-27T00:00:00Z")
    mock_client.login.return_value = mock_auth
    mock_client.get_user_fleet_list.return_value = {"obj": []}
    mock_client.auto_solve_captcha.return_value = ("", "test-cap")

    # Mock insert_document returning UTCMS document ID and tracking code
    mock_client.insert_document.return_value = {
        "resultCode": 200,
        "obj": {"id": 226164459, "docNo": "1349757758", "isOtpNeeded": False},
    }
    mock_client.extract_document_id.return_value = 226164459
    mock_client.extract_tracking_code.return_value = "1349757758"
    mock_client.extract_otp_required.return_value = False

    mock_client.register_start_of_shipping.return_value = {"resultCode": 200, "resultMessage": "ثبت شد"}

    with (
        patch("app.automation.utcms_mobile_client.UtcmsMobileClient", return_value=mock_client),
        patch("app.automation.gps_shipping_manager.save_shipping_state", AsyncMock()),
    ):
        result = await bot._execute_mobile_waybill_job(
            username="4929889601",
            password="test-password",
            payload=compact_payload,
            job_id="job-live-test",
            client_id=1,
            allow_live_submit=True,
        )

    assert result["status"] == "success"
    assert result["tracking_code"] == "1349757758"
    assert result["document_id"] == 226164459

    # Verify that RegisterStartOfShipping was called with integer DocId and coordinates
    mock_client.register_start_of_shipping.assert_awaited_once()
    call_kwargs = mock_client.register_start_of_shipping.await_args.kwargs
    assert call_kwargs["document_id"] == 226164459
    assert call_kwargs["allow_live_submit"] is True
    # Coordinates should be from شوط (origin)
    assert round(call_kwargs["latitude"], 2) == 39.22
    assert round(call_kwargs["longitude"], 2) == 45.03


@pytest.mark.asyncio
async def test_auto_complete_shipping_calls_register_end_of_shipping():
    """Verify auto_complete_shipping calls register_end_of_shipping with destination point."""
    state = ShippingState(
        job_id="test-job-finish",
        doc_no="1349757758",
        doc_id="226164459",
        status="in_transit",
        dest_lat=39.11,
        dest_lng=45.06,
        distance_km=25.0,
    )

    mock_driver = SimpleNamespace(
        id=1,
        driver_national_code="4929889601",
        utcms_password_encrypted="encrypted-pwd",
    )
    mock_job = SimpleNamespace(job_id="test-job-finish", driver_id=1)

    mock_client = AsyncMock(spec=UtcmsMobileClient)
    mock_client.register_end_of_shipping.return_value = {"resultCode": 200, "resultMessage": "پایان حمل ثبت شد"}

    mock_session = AsyncMock()
    mock_res = AsyncMock()
    mock_res.first = lambda: mock_job
    mock_session.exec.return_value = mock_res
    mock_session.get.return_value = mock_driver

    with (
        patch("app.automation.gps_shipping_manager.load_shipping_state", AsyncMock(return_value=state)),
        patch("app.automation.gps_shipping_manager.save_shipping_state", AsyncMock()),
        patch("app.automation.gps_shipping_manager.get_or_login_client", AsyncMock(return_value=mock_client)),
        patch("app.auth_multitenant.decrypt_driver_password", return_value="decrypted-pwd"),
        patch("app.core.database.async_session_factory") as mock_db,
    ):
        mock_db.return_value.__aenter__.return_value = mock_session
        res = await auto_complete_shipping("test-job-finish")

    assert res["status"] == "delivered"
    mock_client.register_end_of_shipping.assert_awaited_once()
    call_kwargs = mock_client.register_end_of_shipping.await_args.kwargs
    assert call_kwargs["document_id"] == "226164459"
    assert call_kwargs["allow_live_submit"] is True
    assert len(call_kwargs["gps_list"]) >= 1
    dest_pt = call_kwargs["gps_list"][-1]
    assert dest_pt["Latitude"] == 39.11
    assert dest_pt["Longitude"] == 45.06
