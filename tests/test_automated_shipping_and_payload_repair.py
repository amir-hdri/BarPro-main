"""Verification tests for automated waybill registration and GPS shipping lifecycle."""

from datetime import UTC, datetime, timedelta
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
from app.travel.geometry import GeoPoint, encode_polyline


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
@pytest.mark.parametrize("with_selected_pins", [False, True])
async def test_mobile_execution_starts_shipping_only_with_selected_road_pins(with_selected_pins: bool):
    """The mobile transport requires explicit pins; shipping uses verified road endpoints."""
    bot = WaybillAutomationBot(proxy_url="http://squid:3128")

    compact_payload = {
        "origin": "آذربایجان غربی، شوط، دیزج خیابان آزمایشی یک",
        "destination": "آذربایجان غربی، شوط، مرگان خیابان آزمایشی دو",
        "cargo_type": "محصولات کشاورزی",
        "cargo_weight": 2500,
        "cargo_value": "50000000",
        "plate_number": "32ع444ایران27",
        "driver_national_code": "4929889601",
        "fare": "5,000,000",
        "metadata_json": {
            "origin": {"postal_code": "1456789312"},
            "destination": {"postalCode": "3156789312"},
            "sender": {
                "name": "علی رضایی",
                "phone": "09121234567",
                "national_code": "0084575948",
                "postal_code": "1456789312",
            },
            "receiver": {
                "name": "حسن محمدی",
                "phone": "09129876543",
                "national_code": "0012345679",
                "postalCode": "3156789312",
            },
        },
    }
    if with_selected_pins:
        compact_payload["metadata_json"]["origin"]["coordinates"] = {"lat": 39.22001, "lng": 45.03001}
        compact_payload["metadata_json"]["destination"]["coordinates"] = {"lat": 39.11001, "lng": 45.06001}
        # Older flattened pins must never replace the selected metadata pins.
        compact_payload.update(originLat=35.7, originLng=51.4, destLat=35.8, destLng=51.5)

    mock_client = AsyncMock(spec=UtcmsMobileClient)
    mock_client.token = "test-token"
    mock_auth = SimpleNamespace(token="test-token", refresh_token=None, expires_at="2026-09-27T00:00:00Z")
    mock_client.login.return_value = mock_auth
    mock_client.get_user_fleet_list.return_value = {"obj": []}
    mock_client.auto_solve_captcha.return_value = ("", "test-cap")
    mock_client.cap_token_from_solution.return_value = "test-cap"

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
        patch(
            "app.services.route_authority._fetch_neshan_route",
            AsyncMock(
                return_value={
                    "polyline": encode_polyline([GeoPoint(39.22, 45.03), GeoPoint(39.11, 45.06)]),
                    "distance_m": 15000,
                    "duration_s": 1500,
                }
            ),
        ) as fetch_route,
    ):
        result = await bot._execute_mobile_waybill_job(
            username="4929889601",
            password="test-password",
            payload=compact_payload,
            job_id="job-live-test",
            client_id=1,
            allow_live_submit=True,
        )

    if not with_selected_pins:
        assert result["status"] == "needs_review"
        assert result["error_category"] == "mobile_payload_validation_failed"
        assert "عرض جغرافیایی مبدا" in result["error"]
        assert "طول جغرافیایی مقصد" in result["error"]
        mock_client.login.assert_not_awaited()
        mock_client.insert_document.assert_not_awaited()
        mock_client.register_start_of_shipping.assert_not_awaited()
        fetch_route.assert_not_awaited()
        return

    assert result["status"] == "success", result
    assert result["tracking_code"] == "1349757758"
    assert result["document_id"] == 226164459
    submitted = mock_client.insert_document.await_args.args[0]
    assert submitted["origin"]["postal_code"] == "1456789312"
    assert submitted["destination"]["postal_code"] == "3156789312"
    assert submitted["sender"]["postal_code"] == "1456789312"
    assert submitted["receiver"]["postal_code"] == "3156789312"
    assert submitted["origin"]["address"] == "دیزج خیابان آزمایشی یک"
    assert submitted["receiver"]["name"] == "حسن محمدی"

    # Verify that RegisterStartOfShipping was called with integer DocId and coordinates
    mock_client.register_start_of_shipping.assert_awaited_once()
    call_kwargs = mock_client.register_start_of_shipping.await_args.kwargs
    assert call_kwargs["document_id"] == 226164459
    assert call_kwargs["allow_live_submit"] is True
    # Wire coordinates are the provider's effective road endpoint, not a city
    # centroid, stale flat pair or the nearby requested point.
    assert call_kwargs["latitude"] == 39.22
    assert call_kwargs["longitude"] == 45.03
    fetch_route.assert_awaited_once_with(39.22001, 45.03001, 39.11001, 45.06001)


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
        # Physically due: the ETA gate (shipping_wait_reason) is fail-closed on a
        # missing or future estimated_end_at, so a completion test must present a
        # satisfied ETA — Beat only ever calls auto_complete_shipping for due trips.
        estimated_end_at=(datetime.now(UTC) - timedelta(hours=1)).isoformat(),
    )

    mock_driver = SimpleNamespace(
        id=1,
        driver_national_code="4929889601",
        utcms_password_encrypted="encrypted-pwd",
    )
    mock_job = SimpleNamespace(job_id="test-job-finish", driver_id=1, document_id="226164459", result_json={})

    mock_client = AsyncMock(spec=UtcmsMobileClient)
    mock_client.register_end_of_shipping.return_value = {"resultCode": 200, "resultMessage": "پایان حمل ثبت شد"}

    mock_session = AsyncMock()
    mock_res = AsyncMock()
    mock_res.first = lambda: mock_job
    mock_session.exec.return_value = mock_res
    mock_session.get.return_value = mock_driver

    with (
        patch("app.automation.gps_shipping_manager._acquire_completion_claim", AsyncMock(return_value="claim-token")),
        patch("app.automation.gps_shipping_manager._release_completion_claim", AsyncMock()),
        patch("app.core.config.utcms_config.ALLOW_LIVE_SUBMIT", True),
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
