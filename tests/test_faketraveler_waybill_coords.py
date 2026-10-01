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

from app.api.routes import shipping_gps as routes
from app.automation.gps_shipping_manager import ShippingState


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
    monkeypatch.setattr(routes, "get_worker_proxy_url", Mock(return_value="http://squid:3128"))
    monkeypatch.setattr(routes, "get_or_login_client", AsyncMock(return_value=transport))
    monkeypatch.setattr(routes.rpa_runtime, "acquire_lock", AsyncMock(return_value=True))
    monkeypatch.setattr(routes.rpa_runtime, "release_lock", AsyncMock())
    monkeypatch.setattr("app.auth_multitenant.decrypt_driver_password", Mock(return_value="test-password"))
    # Bridge enabled
    monkeypatch.setattr(
        "app.android_bridge.client.BridgeConfig.from_env",
        classmethod(lambda cls: SimpleNamespace(enabled=True)),
    )
    # Readback verification succeeds
    monkeypatch.setattr(
        "app.services.shipping_travel_service.verify_android_anchor",
        AsyncMock(return_value={"verified": True, "observation": {}}),
    )
    return SimpleNamespace(state=state, transport=transport)


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


async def test_start_fails_closed_when_apply_fails(
    faketraveler_runtime: SimpleNamespace,
) -> None:
    """If FakeTraveler apply fails, /start must 503 — never silently continue."""

    async def failing_apply(self, lat: float, lon: float, **kwargs) -> None:
        raise RuntimeError("adb unreachable")

    from fastapi import HTTPException

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
