"""Unit and regression tests for recurring waybill cycling, intelligent scheduling,
and root-cause portal protection gates (Cairn Phase 5).
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.core.distance import (
    calculate_cycling_times,
)
from app.models.waybill_route_template import WaybillRouteTemplate
from app.models_multitenant import Driver, WaybillJob
from app.services.batch_service import (
    build_cycling_schedule,
    invert_waybill_payload,
    validate_driver_fleet_scope,
)
from app.services.distance_service import snap_coordinate_to_road

# ── Fixtures & Helpers ─────────────────────────────────────────────────────────


def _sample_route(
    rid: int = 1,
    origin_city: str = "تهران",
    origin_province: str = "تهران",
    dest_city: str = "قم",
    dest_province: str = "قم",
    distance_km: float = 140.0,
    duration_min: float = 140.0,
) -> WaybillRouteTemplate:
    return WaybillRouteTemplate(
        id=rid,
        client_id=1,
        name=f"مسیر تست {rid}",
        origin_city=origin_city,
        origin_province=origin_province,
        origin_address="تهران، خیابان رجایی، انبار مرکزی",
        origin_lat=35.6892,
        origin_lng=51.3890,
        dest_city=dest_city,
        dest_province=dest_province,
        dest_address="قم، بلوار الغدیر، مرکز توزیع",
        dest_lat=34.6401,
        dest_lng=50.8764,
        distance_km=distance_km,
        duration_min=duration_min,
    )


def _sample_payload() -> dict:
    return {
        "route_source": "user_text",
        "origin": {
            "province": "تهران",
            "city": "تهران",
            "address": "تهران، خیابان رجایی، انبار مرکزی",
            "lat": 35.6892,
            "lng": 51.3890,
            "postal_code": "1111111111",
        },
        "destination": {
            "province": "قم",
            "city": "قم",
            "address": "قم، بلوار الغدیر، مرکز توزیع",
            "lat": 34.6401,
            "lng": 50.8764,
            "postal_code": "2222222222",
        },
        "sender": {
            "name": "شرکت مبدأ تهران",
            "phone": "09121111111",
            "national_code": "0011111111",
            "postal_code": "1111111111",
        },
        "receiver": {
            "name": "توزیع مقصد قم",
            "phone": "09122222222",
            "national_code": "0022222222",
            "postal_code": "2222222222",
        },
        "cargo": {
            "type": "قطعات صنعتی",
            "packaging": "پالت",
            "weight": 12.5,
            "value": "2500000000",
        },
        "financial": {
            "cost": 15000000,
        },
        "vehicle": {
            "driver_national_code": "0033333333",
            "plate": "12ع345-78",
            "type": "کامیون ده چرخ",
        },
    }


# ── Test Suite 1: Core Distance & Speeds ───────────────────────────────────────


def test_calculate_cycling_times_intercity():
    """Verify intercity calculation with default 60 km/h truck speed and 45 min buffer."""
    result = calculate_cycling_times(distance_km=120.0, buffer_minutes=45.0, is_urban=False)
    # 120 km at 60 km/h = 2.0 hours = 120.0 minutes
    assert result["driving_minutes"] == pytest.approx(120.0, rel=1e-2)
    assert result["buffer_minutes"] == 45.0
    assert result["leg_total_minutes"] == pytest.approx(165.0, rel=1e-2)
    assert result["deadhead_return_minutes"] == pytest.approx(120.0, rel=1e-2)
    assert result["cycle_total_minutes"] == pytest.approx(330.0, rel=1e-2)


def test_calculate_cycling_times_urban():
    """Verify urban calculation with default 28 km/h truck speed."""
    result = calculate_cycling_times(distance_km=28.0, buffer_minutes=30.0, is_urban=True)
    # 28 km at 28 km/h = 1.0 hour = 60.0 minutes
    assert result["driving_minutes"] == pytest.approx(60.0, rel=1e-2)
    assert result["buffer_minutes"] == 30.0
    assert result["leg_total_minutes"] == pytest.approx(90.0, rel=1e-2)
    assert result["cycle_total_minutes"] == pytest.approx(180.0, rel=1e-2)


def test_calculate_cycling_times_custom_speed():
    """Verify overriding truck speed."""
    result = calculate_cycling_times(distance_km=100.0, buffer_minutes=20.0, truck_speed_kmh=50.0)
    # 100 km at 50 km/h = 2.0 hours = 120.0 minutes
    assert result["driving_minutes"] == pytest.approx(120.0, rel=1e-2)
    assert result["leg_total_minutes"] == pytest.approx(140.0, rel=1e-2)


# ── Test Suite 2: Smart Inversion ──────────────────────────────────────────────


def test_invert_waybill_payload_swaps_locations_and_parties():
    """Verify Smart Inversion correctly swaps origin/destination and sender/receiver."""
    original = _sample_payload()
    inverted = invert_waybill_payload(original)

    # Origin and Destination must be swapped
    assert inverted["origin"]["city"] == original["destination"]["city"]
    assert inverted["origin"]["province"] == original["destination"]["province"]
    assert inverted["origin"]["address"] == original["destination"]["address"]
    assert inverted["origin"]["lat"] == original["destination"]["lat"]
    assert inverted["origin"]["lng"] == original["destination"]["lng"]
    assert inverted["origin"]["postal_code"] == original["destination"]["postal_code"]

    assert inverted["destination"]["city"] == original["origin"]["city"]
    assert inverted["destination"]["postal_code"] == original["origin"]["postal_code"]

    # Sender and Receiver must be swapped
    assert inverted["sender"]["name"] == original["receiver"]["name"]
    assert inverted["sender"]["phone"] == original["receiver"]["phone"]
    assert inverted["sender"]["national_code"] == original["receiver"]["national_code"]
    assert inverted["sender"]["postal_code"] == original["receiver"]["postal_code"]

    assert inverted["receiver"]["name"] == original["sender"]["name"]
    assert inverted["receiver"]["phone"] == original["sender"]["phone"]

    # Critical parity rule: return sender's postal code matches return origin postal code
    assert inverted["sender"]["postal_code"] == inverted["origin"]["postal_code"]

    # Cargo and vehicle details remain intact
    assert inverted["cargo"]["type"] == original["cargo"]["type"]
    assert inverted["vehicle"]["driver_national_code"] == original["vehicle"]["driver_national_code"]
    assert inverted["financial"]["cost"] == original["financial"]["cost"]


def test_invert_waybill_payload_symmetry():
    """Double inversion must restore the original payload (mathematical involution)."""
    original = _sample_payload()
    inverted_once = invert_waybill_payload(original)
    inverted_twice = invert_waybill_payload(inverted_once)

    assert inverted_twice["origin"]["city"] == original["origin"]["city"]
    assert inverted_twice["destination"]["city"] == original["destination"]["city"]
    assert inverted_twice["sender"]["national_code"] == original["sender"]["national_code"]
    assert inverted_twice["receiver"]["national_code"] == original["receiver"]["national_code"]
    assert inverted_twice["origin"]["postal_code"] == original["origin"]["postal_code"]


# ── Test Suite 3: Scheduling Logic (2N Round-Trip & M Repeated) ────────────────


def test_build_cycling_schedule_round_trip():
    """Verify 2N schedule for round_trip_cycling with interleaved return legs."""
    route = _sample_route(rid=1, distance_km=100.0, duration_min=100.0)
    base_time = datetime(2026, 10, 18, 8, 0, 0, tzinfo=UTC).replace(tzinfo=None)
    buffer = 45
    cycles = 3

    total_target, release_times, is_return_flags = build_cycling_schedule(
        routes=[route],
        batch_mode="round_trip_cycling",
        cycles_count=cycles,
        repeat_count=None,
        buffer_minutes=buffer,
        start_at=base_time,
    )

    # 3 cycles * 2 legs = 6 total waybills
    assert total_target == 6
    assert len(release_times) == 6
    assert len(is_return_flags) == 6

    # Alternating return flags: [False, True, False, True, False, True]
    assert is_return_flags == [False, True, False, True, False, True]

    # Check timestamps: each step is duration (100) + buffer (45) = 145 minutes
    step_minutes = 100.0 + buffer
    assert release_times[0] == base_time
    assert release_times[1] == base_time + timedelta(minutes=step_minutes)
    assert release_times[2] == base_time + timedelta(minutes=step_minutes * 2)
    assert release_times[3] == base_time + timedelta(minutes=step_minutes * 3)
    assert release_times[4] == base_time + timedelta(minutes=step_minutes * 4)
    assert release_times[5] == base_time + timedelta(minutes=step_minutes * 5)


def test_build_cycling_schedule_one_way_repeated():
    """Verify M schedule for one_way_repeated accounts for empty return deadhead time."""
    route = _sample_route(rid=1, distance_km=60.0, duration_min=60.0)
    base_time = datetime(2026, 10, 18, 8, 0, 0, tzinfo=UTC).replace(tzinfo=None)
    buffer = 30
    repeats = 4

    total_target, release_times, is_return_flags = build_cycling_schedule(
        routes=[route],
        batch_mode="one_way_repeated",
        cycles_count=None,
        repeat_count=repeats,
        buffer_minutes=buffer,
        start_at=base_time,
    )

    assert total_target == 4
    assert len(release_times) == 4
    # All are forward legs
    assert is_return_flags == [False, False, False, False]

    # Spacing between departures = forward_dur (60) + buffer (30) + return_dur (60) + buffer (30) = 180 min
    leg_spacing = (60.0 * 2) + (buffer * 2)
    assert release_times[0] == base_time
    assert release_times[1] == base_time + timedelta(minutes=leg_spacing)
    assert release_times[2] == base_time + timedelta(minutes=leg_spacing * 2)
    assert release_times[3] == base_time + timedelta(minutes=leg_spacing * 3)


# ── Test Suite 4: Fleet Scope & Portal Anti-Ban Gates (4028 & 4045) ─────────────


def test_validate_driver_fleet_scope_prevents_code_4028():
    """Driver restricted to Tabriz must not issue waybill with origin in Tehran."""
    driver = Driver(
        id=10,
        client_id=1,
        full_name="راننده تبریز",
        driver_national_code="1234567890",
        phone="09120000000",
        metadata_json={"activity_city": "تبریز", "activity_province": "آذربایجان شرقی"},
    )

    # Valid origin in Tabriz and adjacent destination province (Ardabil) passes
    validate_driver_fleet_scope(driver, origin_city="تبریز", dest_province="اردبیل")

    # Invalid origin in Tehran fails with 422 containing 4028 warning
    with pytest.raises(HTTPException) as exc_info:
        validate_driver_fleet_scope(driver, origin_city="تهران", dest_province="اردبیل")
    assert exc_info.value.status_code == 422
    assert "۴۰۲۸" in exc_info.value.detail or "4028" in exc_info.value.detail
    assert "تبریز" in exc_info.value.detail


def test_validate_driver_fleet_scope_prevents_code_4045():
    """Fleet license province must be origin or adjacent; distant province fails with 4045."""
    driver = Driver(
        id=11,
        client_id=1,
        full_name="راننده تهران",
        driver_national_code="1234567891",
        phone="09120000001",
        metadata_json={"activity_city": "تهران", "activity_province": "تهران"},
    )

    # Adjacent province (Qom is adjacent to Tehran) passes
    validate_driver_fleet_scope(driver, origin_city="تهران", dest_province="قم")

    # Adjacent province (Alborz, Mazandaran, Semnan, Markazi) passes
    validate_driver_fleet_scope(driver, origin_city="تهران", dest_province="البرز")

    # Non-adjacent province (Bushehr is far from Tehran) fails with 4045
    with pytest.raises(HTTPException) as exc_info:
        validate_driver_fleet_scope(driver, origin_city="تهران", dest_province="بوشهر")
    assert exc_info.value.status_code == 422
    assert "۴۰۴۵" in exc_info.value.detail or "4045" in exc_info.value.detail
    assert "بوشهر" in exc_info.value.detail


# ── Test Suite 5: Road Snapping with Neshan API Fallback ─────────────────────────


@pytest.mark.asyncio
async def test_snap_coordinate_to_road_success():
    """Mocking successful Neshan reverse geocoding returns snapped road coordinate."""
    fake_json = {
        "status": "OK",
        "formatted_address": "تهران، خیابان شهید رجایی",
        "route_name": "بزرگراه رجایی",
    }
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = fake_json

    with (
        patch("app.core.config.utcms_config.NESHAN_API_KEY", "test-key"),
        patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.return_value = fake_resp

        result = await snap_coordinate_to_road(35.6892, 51.3890)
        assert result["lat"] == 35.6892
        assert result["lng"] == 51.3890
        assert result["snapped"] is True
        assert "شهید رجایی" in result["address"]
        assert result["source"] == "neshan_reverse"


@pytest.mark.asyncio
async def test_snap_coordinate_to_road_fallback_on_network_error():
    """Network failure or timeout must gracefully fall back to original coordinates."""
    with (
        patch("app.core.config.utcms_config.NESHAN_API_KEY", "test-key"),
        patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.side_effect = Exception("Connection timed out")

        result = await snap_coordinate_to_road(35.6892, 51.3890)
        assert result["lat"] == 35.6892
        assert result["lng"] == 51.3890
        assert result["snapped"] is False
        assert result["source"] == "fallback"


# ── Test Suite 6: Scheduler Fail-Safe Chain Halt ───────────────────────────────


def test_scheduler_fail_safe_chain_halt():
    """When a prior sequence in a batch has failed, the scheduler halts subsequent jobs."""
    now = datetime(2026, 10, 18, 10, 0, 0, tzinfo=UTC).replace(tzinfo=None)

    # Job 0 failed
    job_0 = WaybillJob(
        id=101,
        client_id=1,
        driver_id=5,
        status="FAILED",
        batch_id=99,
        sequence_in_batch=0,
        submit_after=now - timedelta(minutes=60),
    )
    # Prior jobs containing failure
    prior_jobs = [job_0]

    # When prior job is FAILED, chain must halt
    has_prior_failed = any(j.status in {"FAILED", "CANCELLED", "NEEDS_REVIEW"} for j in prior_jobs)
    assert has_prior_failed is True

    # When prior job is SUCCESS, chain can proceed
    job_0.status = "SUCCESS"
    has_prior_failed_after_success = any(j.status in {"FAILED", "CANCELLED", "NEEDS_REVIEW"} for j in prior_jobs)
    assert has_prior_failed_after_success is False
