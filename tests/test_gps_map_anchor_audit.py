"""Map anchors and physical ETA remain authoritative in virtual GPS planning."""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from app.automation import gps_shipping_manager as shipping
from app.services import route_authority, shipping_travel_service
from app.travel.geometry import GeoPoint, encode_polyline

pytestmark = pytest.mark.unit
ORIGIN = (35.71234567, 51.41234567)
DESTINATION = (35.81234567, 51.51234567)


def pin_payload() -> dict:
    return {
        "metadata_json": {
            "origin": {
                "city": "تهران",
                "address": "نشانی انتخاب‌شدهٔ مبدأ",
                "coordinates": {"lat": ORIGIN[0], "lng": ORIGIN[1]},
            },
            "destination": {
                "city": "تهران",
                "address": "نشانی انتخاب‌شدهٔ مقصد",
                "coordinates": {"lat": DESTINATION[0], "lng": DESTINATION[1]},
            },
        }
    }


async def test_city_name_never_becomes_a_fake_map_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    route = AsyncMock()
    monkeypatch.setattr(route_authority, "resolve_route", route)
    with pytest.raises(ValueError, match="مختصات"):
        await shipping.init_shipping("missing-pins", "unused", {"origin": "تهران", "destination": "کرج"}, persist=False)
    route.assert_not_awaited()


@pytest.mark.parametrize("bad_pair", [{"lat": 35.2}, {"lat": 999, "lng": 51.4}, {"lat": True, "lng": 51.4}])
async def test_invalid_selected_pin_never_falls_through_to_stale_flat_coordinates(bad_pair: dict) -> None:
    payload = pin_payload()
    payload["metadata_json"]["origin"]["coordinates"] = bad_pair
    payload.update(origin_lat=32.6546, origin_lng=51.668)
    with pytest.raises(ValueError, match="مختصات"):
        await shipping.init_shipping("invalid-pin", "unused", payload, persist=False)


@pytest.mark.parametrize("bad_value", [True, float("inf"), -91.0, 91.0])
async def test_route_rejects_invalid_anchors_before_provider_io(monkeypatch: pytest.MonkeyPatch, bad_value) -> None:
    fetch = AsyncMock(return_value=None)
    monkeypatch.setattr(route_authority, "_fetch_neshan_route", fetch)
    with pytest.raises(ValueError):
        await route_authority.resolve_route(bad_value, 51.4, *DESTINATION)
    fetch.assert_not_awaited()


async def test_provider_cannot_silently_snap_or_replace_map_anchors(monkeypatch: pytest.MonkeyPatch) -> None:
    remote_polyline = encode_polyline([GeoPoint(32.65, 51.66), GeoPoint(32.75, 51.76)])
    monkeypatch.setattr(
        route_authority,
        "_fetch_neshan_route",
        AsyncMock(
            return_value={
                "polyline": remote_polyline,
                "distance_m": 15000,
                "duration_s": 3600,
            }
        ),
    )
    snapshot = await route_authority.resolve_route(*ORIGIN, *DESTINATION)
    assert snapshot["source"] == "haversine_fallback"
    assert snapshot["fallback_reason"] == "provider_anchor_mismatch"
    assert snapshot["is_real_route"] is False
    assert snapshot["points"][0] == list(ORIGIN)
    assert snapshot["points"][-1] == list(DESTINATION)


async def test_provider_encoding_preserves_requested_pin_separately(monkeypatch: pytest.MonkeyPatch) -> None:
    polyline = encode_polyline([GeoPoint(*ORIGIN), GeoPoint(35.76, 51.49), GeoPoint(*DESTINATION)])
    monkeypatch.setattr(
        route_authority,
        "_fetch_neshan_route",
        AsyncMock(
            return_value={
                "polyline": polyline,
                "distance_m": 18000,
                "duration_s": 3600,
            }
        ),
    )
    snapshot = await route_authority.resolve_route(*ORIGIN, *DESTINATION)
    assert snapshot["source"] == "neshan"
    assert snapshot["requested_origin"] == {"lat": ORIGIN[0], "lng": ORIGIN[1]}
    assert snapshot["requested_destination"] == {"lat": DESTINATION[0], "lng": DESTINATION[1]}
    assert snapshot["points"][0] == [round(value, 5) for value in ORIGIN]
    assert snapshot["snap_metadata"]["origin"]["distance_m"] < 1.0


async def test_normal_road_snap_uses_driveable_endpoints_and_preserves_requested_pin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapped_origin = GeoPoint(ORIGIN[0] + 0.0003, ORIGIN[1])
    snapped_end = GeoPoint(DESTINATION[0] - 0.0003, DESTINATION[1])
    polyline = encode_polyline([snapped_origin, snapped_end])
    monkeypatch.setattr(
        route_authority,
        "_fetch_neshan_route",
        AsyncMock(
            return_value={
                "polyline": polyline,
                "distance_m": 15000,
                "duration_s": 3600,
            }
        ),
    )
    snapshot = await route_authority.resolve_route(*ORIGIN, *DESTINATION)
    assert snapshot["source"] == "neshan"
    assert snapshot["road_anchor_verified"] is True
    assert snapshot["is_real_route"] is True
    assert snapshot["snap_metadata"]["origin"]["source"] == "neshan_road_endpoint"
    assert 30 < snapshot["snap_metadata"]["origin"]["distance_m"] < 40
    assert snapshot["points"][0] == [round(value, 5) for value in snapped_origin]
    assert snapshot["points"][-1] == [round(value, 5) for value in snapped_end]
    state = await shipping.init_shipping("snapped", "unused", pin_payload(), persist=False)
    assert [state.origin_lat, state.origin_lng] == snapshot["points"][0]
    assert [state.dest_lat, state.dest_lng] == snapshot["points"][-1]
    assert state.coordinate_source == "road_snapped"
    assert state.route_snapshot["requested_origin"] == {"lat": ORIGIN[0], "lng": ORIGIN[1]}
    assert shipping_travel_service.build_engine_for_state(state).route_distance_km > 0


async def test_unverified_road_snapshot_cannot_be_persisted_for_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(route_authority, "_fetch_neshan_route", AsyncMock(return_value=None))
    persist = AsyncMock()
    monkeypatch.setattr(shipping, "save_shipping_state", persist)
    preview = await shipping.init_shipping("preview", "unused", pin_payload(), persist=False)
    assert preview.coordinate_source == "map_pin_unverified"
    with pytest.raises(ValueError, match="تأیید نشده"):
        await shipping.init_shipping("real-trip", "unused", pin_payload(), persist=True)
    persist.assert_not_awaited()


@pytest.mark.parametrize("field,value", [("distance_m", -1), ("duration_s", float("nan"))])
async def test_invalid_provider_metrics_are_explicit_fallback(monkeypatch: pytest.MonkeyPatch, field, value) -> None:
    provider = {
        "polyline": encode_polyline([GeoPoint(*ORIGIN), GeoPoint(*DESTINATION)]),
        "distance_m": 15000,
        "duration_s": 3600,
        field: value,
    }
    monkeypatch.setattr(route_authority, "_fetch_neshan_route", AsyncMock(return_value=provider))
    snapshot = await route_authority.resolve_route(*ORIGIN, *DESTINATION)
    assert snapshot["source"] == "haversine_fallback"
    assert snapshot["fallback_reason"] == "provider_geometry_invalid"


async def test_malformed_provider_polyline_is_explicit_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(route_authority, "_fetch_neshan_route", AsyncMock(return_value={"polyline": {"bad": True}}))
    snapshot = await route_authority.resolve_route(*ORIGIN, *DESTINATION)
    assert snapshot["fallback_reason"] == "provider_geometry_invalid"
    assert snapshot["road_anchor_verified"] is False


@pytest.mark.parametrize("point", [[float("nan"), 51.4], [True, 51.4], [91.0, 51.4], [35.7]])
def test_persisted_snapshot_rejects_invalid_points(point: list) -> None:
    with pytest.raises(ValueError, match="invalid route"):
        route_authority.geometry_from_snapshot({"points": [point, list(DESTINATION)], "source": "neshan"})


async def test_longer_route_duration_extends_eta_without_changing_pins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        route_authority,
        "resolve_route",
        AsyncMock(
            return_value={
                "source": "neshan",
                "distance_km": 130.0,
                "duration_s": 10800.0,
                "anchor_hash": "fixture",
            }
        ),
    )
    state = await shipping.init_shipping("route-eta", "unused", pin_payload(), persist=False)
    assert (state.origin_lat, state.origin_lng) == ORIGIN
    assert (state.dest_lat, state.dest_lng) == DESTINATION
    assert state.origin_address == "نشانی انتخاب‌شدهٔ مبدأ"
    assert state.distance_km == 130.0
    duration = datetime.fromisoformat(state.estimated_end_at) - datetime.fromisoformat(state.created_at)
    assert duration.total_seconds() >= 10800
    assert state.gps_list == []


def test_mismatched_frozen_route_cannot_drive_virtual_gps() -> None:
    state = shipping.ShippingState(
        origin_lat=ORIGIN[0],
        origin_lng=ORIGIN[1],
        dest_lat=DESTINATION[0],
        dest_lng=DESTINATION[1],
        route_snapshot={
            "origin": {"lat": 32.6, "lng": 51.6},
            "destination": {"lat": 32.7, "lng": 51.7},
            "points": [[32.6, 51.6], [32.7, 51.7]],
            "source": "neshan",
        },
    )
    with pytest.raises(ValueError, match="anchor"):
        shipping_travel_service.build_engine_for_state(state)


def test_corrupt_eta_is_not_permission_to_finish_shipping() -> None:
    state = shipping.ShippingState(job_id="corrupt-eta", status="in_transit", estimated_end_at="not-a-date")
    wait = shipping.shipping_wait_reason(state)
    assert wait is not None
    assert wait["status"] == "waiting_eta"
    assert wait["reason"] == "invalid_estimated_end_at"


async def test_preview_exposes_road_points_separately_from_gps_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.routes import shipping_gps as routes

    road_start = GeoPoint(35.71265, 51.41235)
    road_end = GeoPoint(35.81205, 51.51235)
    monkeypatch.setattr(routes, "_get_job_and_driver", AsyncMock(return_value=(pin_payload(), None)))
    monkeypatch.setattr(routes, "load_shipping_state", AsyncMock(return_value=None))
    monkeypatch.setattr(
        route_authority,
        "_fetch_neshan_route",
        AsyncMock(
            return_value={
                "polyline": encode_polyline([road_start, road_end]),
                "distance_m": 15000,
                "duration_s": 3600,
            }
        ),
    )
    status = await routes.get_shipping_status("preview-job", user_context={})
    assert status["status"] == "not_started"
    assert status["route_points"] == [list(road_start), list(road_end)]
    assert status["gps_list"] == status["waypoints"] == []
    assert status["requested_origin"] == {"lat": ORIGIN[0], "lng": ORIGIN[1]}
    assert (status["origin"]["lat"], status["origin"]["lng"]) == tuple(road_start)
    assert status["road_anchor_verified"] is True
