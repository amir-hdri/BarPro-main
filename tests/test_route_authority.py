"""Route Authority + travel wiring + Android observer (GPS remediation phases)."""

import pytest

from app.automation.gps_shipping_manager import ShippingState
from app.services.route_authority import geometry_from_snapshot, resolve_route, utc_now_iso
from app.services.shipping_travel_service import (
    advance_travel_execution,
    build_engine_for_state,
    compute_measured_distance_km,
    is_arrival_reached,
)
from app.travel.android_observer import AdbLocationObserver


def test_utc_now_iso_is_utc_zulu() -> None:
    stamp = utc_now_iso()
    assert stamp.endswith("Z")
    assert "T" in stamp


@pytest.mark.asyncio
async def test_resolve_route_fallback_is_explicit() -> None:
    snapshot = await resolve_route(35.6892, 51.3890, 32.6546, 51.6680)
    assert snapshot["source"] == "haversine_fallback"
    assert snapshot["is_real_route"] is False
    assert snapshot["distance_km"] > 0
    assert snapshot["polyline"]
    assert snapshot["anchor_hash"]
    assert snapshot["route_version"].startswith("route-authority/")
    geometry = geometry_from_snapshot(snapshot)
    assert geometry.total_distance_km > 0
    assert geometry.is_real_route is False


@pytest.mark.asyncio
async def test_route_snapshot_roundtrip_preserves_geometry() -> None:
    first = await resolve_route(36.2611, 50.4423, 36.1696, 50.6119)
    second = await resolve_route(36.2611, 50.4423, 36.1696, 50.6119)
    assert first["anchor_hash"] == second["anchor_hash"]
    assert first["polyline"] == second["polyline"]


def test_compute_measured_distance_prefers_telemetry() -> None:
    # Two fixes ~90 km apart against a 100 km road route → telemetry wins.
    state = ShippingState(
        job_id="j",
        distance_km=100.0,
        route_distance_km=100.0,
        gps_list=[
            {"Latitude": 35.0, "Longitude": 51.0},
            {"Latitude": 35.8, "Longitude": 51.3},
        ],
    )
    derived = compute_measured_distance_km(state)
    assert 0.5 * 100.0 <= derived <= 1.8 * 100.0
    assert derived != 100.0  # proves telemetry span was used, not the fallback


def test_compute_measured_distance_falls_back_to_route() -> None:
    state = ShippingState(job_id="j", distance_km=70.0, route_distance_km=62.5, gps_list=[])
    assert compute_measured_distance_km(state) == 62.5


@pytest.mark.asyncio
async def test_travel_engine_builds_from_snapshot() -> None:
    from datetime import UTC, datetime

    snapshot = await resolve_route(35.6892, 51.3890, 35.8, 51.5)
    created_at = "2026-09-27T10:00:00+00:00"
    state = ShippingState(
        job_id="j",
        origin_lat=35.6892,
        origin_lng=51.3890,
        dest_lat=35.8,
        dest_lng=51.5,
        route_snapshot=snapshot,
        route_distance_km=snapshot["distance_km"],
        created_at=created_at,
    )
    engine = build_engine_for_state(state)
    assert engine.route_distance_km > 0
    # Sample exactly at departure → progress 0, not arrived yet.
    report = advance_travel_execution(state, now=datetime.fromisoformat(created_at).replace(tzinfo=UTC))
    assert report["advanced"] is True
    assert state.travel_progress == 0.0
    assert is_arrival_reached(state) is False


def test_observer_parse_dump_prefers_last_fix() -> None:
    dump = """
    Last Known Locations:
      gps: provider=gps lat=35.100000 lon=51.200000 age=5s
      fused: provider=fused lat=35.100050 lon=51.200050 age=3s
    Mocked by cl.coders.faketraveler
    """
    parsed = AdbLocationObserver.parse_dump(dump)
    assert parsed is not None
    provider, lat, lon, is_mock, age = parsed
    assert provider == "fused"
    assert abs(lat - 35.100050) < 1e-9
    assert is_mock is True
    assert age == 3.0


def test_observer_parse_dump_rejects_garbage() -> None:
    assert AdbLocationObserver.parse_dump("no location here") is None
    assert AdbLocationObserver.parse_dump("lat=999, lon=999") is None
