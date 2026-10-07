"""Verify FakeTraveler applies exactly the map-registered waybill coordinates.

When the Android bridge is enabled, /shipping/start must apply the waybill's
stored origin (state.origin_lat/lng — pinned on the map by the user) via
FakeTraveler BEFORE the readback verification, and /shipping/finish must do
the same with the stored destination. The operator's request anchor is only
used for the _assert_route_anchor check, never for the mock location.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from app.api.routes import shipping_gps as routes
from app.automation.gps_shipping_manager import ShippingState
from app.services import shipping_travel_service


@pytest.fixture
def faketraveler_runtime(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    # Waybill state: coordinates as pinned on the map (deliberately different
    # from the operator's request anchor to prove the waybill wins).
    state = ShippingState(
        job_id="test-job",
        doc_no="test-document",
        status="ready",
        origin_lat=35.70000,
        origin_lng=51.40000,
        dest_lat=35.80000,
        dest_lng=50.90000,
        distance_km=70,
        waypoints=[],
        # The finish tests flip status to "in_transit"; a real in_transit trip
        # already carries a past physical ETA (shipping_wait_reason passes) and
        # the origin Type-2 witness /start persisted, so prepare_shipping_trace
        # reaches 2 points once the Type-3 destination is appended. Harmless for
        # the start tests, which append their own origin.
        estimated_end_at="2020-01-01T00:00:00+00:00",
        gps_list=[
            {
                "Type": 2,
                "Latitude": 35.70000,
                "Longitude": 51.40000,
                "Speed": 0,
                "Altitude": 1000,
                "Date": "2020-01-01T00:00:00.000Z",
                "DateTime": "2020-01-01T00:00:00.000Z",
                "Provider": "android_faketraveler_applied",
                "Provenance": "android_verified",
            }
        ],
    )
    driver = SimpleNamespace(driver_national_code="test-driver", utcms_password_encrypted="test-encrypted")
    transport = Mock()
    transport.register_start_of_shipping = AsyncMock(return_value={"resultCode": 200})
    transport.finish_shipping_with_gps = AsyncMock(return_value={"resultCode": 200})
    transport.register_end_of_shipping = AsyncMock(return_value={"resultCode": 200})
    monkeypatch.setattr(routes.utcms_config, "ALLOW_LIVE_SUBMIT", True)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setattr(routes, "_get_job_and_driver", AsyncMock(return_value=({}, driver)))
    monkeypatch.setattr(routes, "load_shipping_state", AsyncMock(return_value=None))
    monkeypatch.setattr(routes, "init_shipping", AsyncMock(return_value=state))
    monkeypatch.setattr(routes, "save_shipping_state", AsyncMock())
    # record_shipping_rejection() persists via gps_shipping_manager's own
    # save_shipping_state global (not the routes alias); isolate it so any
    # rejection-path test here never writes to the tableless test DB.
    monkeypatch.setattr("app.automation.gps_shipping_manager.save_shipping_state", AsyncMock())
    monkeypatch.setattr(routes, "get_worker_proxy_url", Mock(return_value="http://squid:3128"))
    monkeypatch.setattr(routes, "get_or_login_client", AsyncMock(return_value=transport))
    # Mutation lock is the Redis SET-NX completion claim imported into the route
    # module (shared with Beat auto-complete), not an rpa_runtime driver lock.
    monkeypatch.setattr(routes, "_acquire_completion_claim", AsyncMock(return_value="test-claim-token"))
    monkeypatch.setattr(routes, "_release_completion_claim", AsyncMock())
    monkeypatch.setattr("app.auth_multitenant.decrypt_driver_password", Mock(return_value="test-password"))
    # Bridge enabled
    monkeypatch.setattr(
        "app.android_bridge.client.BridgeConfig.from_env",
        classmethod(lambda cls: SimpleNamespace(enabled=True)),
    )
    # Readback verification succeeds
    original_verify = shipping_travel_service.verify_android_anchor
    monkeypatch.setattr(
        "app.services.shipping_travel_service.verify_android_anchor",
        AsyncMock(return_value={"verified": True, "observation": {}}),
    )
    return SimpleNamespace(state=state, transport=transport, original_verify_android_anchor=original_verify)


async def test_start_applies_waybill_origin_to_faketraveler(
    faketraveler_runtime: SimpleNamespace,
) -> None:
    """apply_location must receive the waybill's stored origin, not the request anchor."""
    applied: list[tuple[float, float]] = []

    async def fake_apply(self, lat: float, lon: float, **kwargs) -> None:
        applied.append((lat, lon))

    with patch("app.android_bridge.controller.AndroidShippingController.apply_location", fake_apply):
        req = routes.ShippingStartRequest(
            job_id="test-job",
            doc_no="test-document",
            latitude=35.70001,  # operator anchor (slightly off — still within tolerance)
            longitude=51.40001,
        )
        result = await routes.start_shipping(req, user_context={})

    assert result["status"] == "started"
    assert applied == [(35.70000, 51.40000)], (
        "FakeTraveler must apply the waybill's map-registered origin, " f"got {applied}"
    )


async def test_finish_applies_waybill_destination_to_faketraveler(
    faketraveler_runtime: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """apply_location must receive the waybill's stored destination on finish."""
    runtime = faketraveler_runtime
    runtime.state.status = "in_transit"
    monkeypatch.setattr(routes, "load_shipping_state", AsyncMock(return_value=runtime.state))
    applied: list[tuple[float, float]] = []

    async def fake_apply(self, lat: float, lon: float, **kwargs) -> None:
        applied.append((lat, lon))

    with patch("app.android_bridge.controller.AndroidShippingController.apply_location", fake_apply):
        req = routes.ShippingFinishRequest(
            job_id="test-job",
            latitude=35.80001,
            longitude=50.90001,
            measured_distance_km=70,
        )
        result = await routes.finish_shipping(req, user_context={})

    assert result["status"] == "delivered"
    assert applied == [(35.80000, 50.90000)], (
        "FakeTraveler must apply the waybill's map-registered destination, " f"got {applied}"
    )


@pytest.mark.parametrize("destination", [False, True])
async def test_original_pin_request_applies_snapped_street_to_android_and_mobile(
    faketraveler_runtime: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, destination: bool
) -> None:
    runtime = faketraveler_runtime
    state = runtime.state
    state.coordinate_source = "road_snapped"
    original_origin = {"lat": state.origin_lat + 0.0005, "lng": state.origin_lng}
    original_dest = {"lat": state.dest_lat + 0.0005, "lng": state.dest_lng}
    state.route_snapshot = {
        "road_anchor_verified": True,
        "requested_origin": original_origin,
        "requested_destination": original_dest,
        "origin": {"lat": state.origin_lat, "lng": state.origin_lng},
        "destination": {"lat": state.dest_lat, "lng": state.dest_lng},
        "snap_metadata": {"origin": {"distance_m": 55.6, "source": "neshan_road_endpoint"}},
        "polyline": "fixture",
    }
    applied = AsyncMock()
    with patch("app.android_bridge.controller.AndroidShippingController.apply_location", new=applied):
        if destination:
            state.status = "in_transit"
            monkeypatch.setattr(routes, "load_shipping_state", AsyncMock(return_value=state))
            result = await routes.finish_shipping(
                routes.ShippingFinishRequest(
                    job_id=state.job_id, latitude=original_dest["lat"], longitude=original_dest["lng"]
                ),
                user_context={},
            )
            applied.assert_awaited_once_with(state.dest_lat, state.dest_lng)
            terminal = runtime.transport.register_end_of_shipping.await_args.kwargs["gps_list"][-1]
            assert (terminal["Latitude"], terminal["Longitude"]) == (state.dest_lat, state.dest_lng)
        else:
            result = await routes.start_shipping(
                routes.ShippingStartRequest(
                    job_id=state.job_id,
                    doc_no=state.doc_no,
                    latitude=original_origin["lat"],
                    longitude=original_origin["lng"],
                ),
                user_context={},
            )
            applied.assert_awaited_once_with(state.origin_lat, state.origin_lng)
            wire = runtime.transport.register_start_of_shipping.await_args.kwargs
            assert (wire["latitude"], wire["longitude"]) == (state.origin_lat, state.origin_lng)
    assert result["requested_origin"] == original_origin
    assert result["requested_destination"] == original_dest


async def test_start_rejects_unverified_road_snapshot_before_android(faketraveler_runtime: SimpleNamespace) -> None:
    faketraveler_runtime.state.coordinate_source = "map_pin_unverified"
    applied = AsyncMock()
    with patch("app.android_bridge.controller.AndroidShippingController.apply_location", new=applied):
        with pytest.raises(HTTPException) as error:
            await routes.start_shipping(
                routes.ShippingStartRequest(job_id="test-job", doc_no="test-document", latitude=35.7, longitude=51.4),
                user_context={},
            )
    assert error.value.status_code == 422
    applied.assert_not_awaited()
    faketraveler_runtime.transport.register_start_of_shipping.assert_not_awaited()


async def test_start_fails_closed_when_apply_fails(
    faketraveler_runtime: SimpleNamespace,
) -> None:
    """If FakeTraveler apply fails, /start must 503 — never silently continue."""

    async def failing_apply(self, lat: float, lon: float, **kwargs) -> None:
        raise RuntimeError("adb unreachable")

    with patch("app.android_bridge.controller.AndroidShippingController.apply_location", failing_apply):
        req = routes.ShippingStartRequest(
            job_id="test-job",
            doc_no="test-document",
            latitude=35.7,
            longitude=51.4,
        )
        with pytest.raises(HTTPException) as exc_info:
            await routes.start_shipping(req, user_context={})

    assert exc_info.value.status_code == 503
    assert "FakeTraveler" in exc_info.value.detail


# ─────────────────────────────────────────────────────────────────────────────
# Batch-B regression tests (2026-10-02 audit follow-ups)
# ─────────────────────────────────────────────────────────────────────────────


def _persistent_state_store(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Mirror Redis with a fake save/load pair so a persisted terminal state
    (the old B1 behavior) surfaces as a 409 on the retry /start."""
    stored: dict = {}

    async def fake_save(state: ShippingState) -> None:
        stored["state"] = state

    async def fake_load(job_id: str):
        return stored.get("state")

    monkeypatch.setattr(routes, "save_shipping_state", fake_save)
    monkeypatch.setattr(routes, "load_shipping_state", fake_load)
    return stored


def _start_request(lat: float = 35.7, lng: float = 51.4) -> routes.ShippingStartRequest:
    return routes.ShippingStartRequest(job_id="test-job", doc_no="test-document", latitude=lat, longitude=lng)


async def test_start_apply_failure_keeps_job_retryable(
    faketraveler_runtime: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B1: a transient FakeTraveler apply failure must not brick the waybill.

    First /start 503s; nothing terminal may be persisted, so a second /start
    is accepted (409-free) and 503s again on the still-failing device.
    """
    stored = _persistent_state_store(monkeypatch)

    async def failing_apply(self, lat: float, lon: float, **kwargs) -> None:
        raise RuntimeError("adb hiccup")

    with patch("app.android_bridge.controller.AndroidShippingController.apply_location", failing_apply):
        with pytest.raises(HTTPException) as first:
            await routes.start_shipping(_start_request(), user_context={})
    assert first.value.status_code == 503
    assert "FakeTraveler" in first.value.detail
    assert all(
        state.status != "failed" for state in stored.values()
    ), "transient apply failure persisted a terminal state — the waybill would be bricked"

    with patch("app.android_bridge.controller.AndroidShippingController.apply_location", failing_apply):
        with pytest.raises(HTTPException) as second:
            await routes.start_shipping(_start_request(), user_context={})
    assert second.value.status_code == 503, "retry /start was bricked instead of staying retryable"


async def test_start_readback_failure_keeps_job_retryable(
    faketraveler_runtime: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B1 (readback branch): readback runs before any UTCMS mutation, so a
    transient readback failure must also stay retryable (503, no persisted
    "failed") instead of bricking the waybill."""
    stored = _persistent_state_store(monkeypatch)
    monkeypatch.setattr(
        "app.services.shipping_travel_service.verify_android_anchor",
        AsyncMock(return_value={"verified": False, "reason": "readback_unavailable"}),
    )

    async def ok_apply(self, lat: float, lon: float, **kwargs) -> None:
        return None

    with patch("app.android_bridge.controller.AndroidShippingController.apply_location", ok_apply):
        with pytest.raises(HTTPException) as first:
            await routes.start_shipping(_start_request(), user_context={})
    assert first.value.status_code == 503
    assert all(
        state.status != "failed" for state in stored.values()
    ), "transient readback failure persisted a terminal state — the waybill would be bricked"

    with patch("app.android_bridge.controller.AndroidShippingController.apply_location", ok_apply):
        with pytest.raises(HTTPException) as second:
            await routes.start_shipping(_start_request(), user_context={})
    assert second.value.status_code == 503, "retry /start was bricked instead of staying retryable"


async def test_start_readback_verifies_stored_origin_with_10m_offset_anchor(
    faketraveler_runtime: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B2: an operator anchor 10 m from the pinned origin passes the 0.0002°
    route gate; readback must compare the STORED origin (what apply wrote to
    the device), so the 5 m readback tolerance can never deterministically
    fail a legitimately-gated anchor."""
    from datetime import UTC, datetime

    captured: dict = {}
    real_verify = faketraveler_runtime.original_verify_android_anchor

    async def spy_verify(**kwargs):
        captured.update(kwargs)
        return await real_verify(**kwargs)

    monkeypatch.setattr("app.services.shipping_travel_service.verify_android_anchor", spy_verify)

    # The device reports exactly what apply_location wrote: the stored origin.
    now = datetime.now(UTC)
    observation = SimpleNamespace(
        latitude=35.7,
        longitude=51.4,
        provider="fused",
        serial="test-serial",
        is_mock=True,
        sampled_at=now,
        observed_at=now,
    )

    class FakeObserver:
        def __init__(self, config):
            pass

        async def observe(self):
            return observation

    monkeypatch.setattr("app.travel.android_observer.AdbLocationObserver", FakeObserver)

    async def ok_apply(self, lat: float, lon: float, **kwargs) -> None:
        return None

    ten_m_deg = 10.0 / 111320.0  # ~10 m north — inside the 0.0002° (~22 m) gate
    with patch("app.android_bridge.controller.AndroidShippingController.apply_location", ok_apply):
        result = await routes.start_shipping(_start_request(lat=35.7 + ten_m_deg), user_context={})

    assert result["status"] == "started"
    assert result["gps_provider"] == "android_faketraveler_applied"
    assert captured["expected_lat"] == 35.7, "readback must compare the stored origin, not the request anchor"
    assert captured["expected_lng"] == 51.4, "readback must compare the stored origin, not the request anchor"


async def test_finish_readback_verifies_stored_destination_with_10m_offset_anchor(
    faketraveler_runtime: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B2 (finish side): same alignment for the destination — readback compares
    the stored destination coords, so a gated 10 m operator offset succeeds."""
    from datetime import UTC, datetime

    runtime = faketraveler_runtime
    runtime.state.status = "in_transit"
    monkeypatch.setattr(routes, "load_shipping_state", AsyncMock(return_value=runtime.state))

    captured: dict = {}
    real_verify = runtime.original_verify_android_anchor

    async def spy_verify(**kwargs):
        captured.update(kwargs)
        return await real_verify(**kwargs)

    monkeypatch.setattr("app.services.shipping_travel_service.verify_android_anchor", spy_verify)

    now = datetime.now(UTC)
    observation = SimpleNamespace(
        latitude=35.8,
        longitude=50.9,
        provider="fused",
        serial="test-serial",
        is_mock=True,
        sampled_at=now,
        observed_at=now,
    )

    class FakeObserver:
        def __init__(self, config):
            pass

        async def observe(self):
            return observation

    monkeypatch.setattr("app.travel.android_observer.AdbLocationObserver", FakeObserver)

    async def ok_apply(self, lat: float, lon: float, **kwargs) -> None:
        return None

    ten_m_deg = 10.0 / 111320.0
    with patch("app.android_bridge.controller.AndroidShippingController.apply_location", ok_apply):
        result = await routes.finish_shipping(
            routes.ShippingFinishRequest(
                job_id="test-job",
                latitude=35.8 + ten_m_deg,
                longitude=50.9,
                measured_distance_km=70,
            ),
            user_context={},
        )

    assert result["status"] == "delivered"
    assert captured["expected_lat"] == 35.8, "readback must compare the stored destination, not the request anchor"
    assert captured["expected_lng"] == 50.9, "readback must compare the stored destination, not the request anchor"
