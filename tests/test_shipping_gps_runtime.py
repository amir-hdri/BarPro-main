"""Run real shipping handlers with isolated storage and UTCMS transport.

These tests protect the existing transport while the Android bridge is built.
They do not claim to prove UTCMS's live business contract.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.api.routes import shipping_gps as routes
from app.automation.gps_shipping_manager import ShippingState


@pytest.fixture
def shipping_runtime(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    state = ShippingState(
        job_id="test-job",
        doc_no="test-document",
        status="in_transit",
        origin_lat=35.7,
        origin_lng=51.4,
        dest_lat=35.8,
        dest_lng=50.9,
        distance_km=70,
        waypoints=[{"ts": "2026-09-15T00:00:00Z"}, {"ts": "2026-09-15T02:00:00Z"}],
    )
    driver = SimpleNamespace(driver_national_code="test-driver", utcms_password_encrypted="test-encrypted")
    transport = Mock()
    transport.start_shipping_with_gps = AsyncMock(return_value={"resultCode": 200})
    transport.finish_shipping_with_gps = AsyncMock(return_value={"resultCode": 200})
    transport.register_end_of_shipping = AsyncMock(return_value={"resultCode": 200})
    transport.register_start_of_shipping = AsyncMock()
    login = AsyncMock(return_value=transport)
    save = AsyncMock()
    monkeypatch.setattr(routes.utcms_config, "ALLOW_LIVE_SUBMIT", True)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setattr(routes, "_get_job_and_driver", AsyncMock(return_value=({}, driver)))
    monkeypatch.setattr(routes, "load_shipping_state", AsyncMock(return_value=state))
    monkeypatch.setattr(routes, "init_shipping", AsyncMock(return_value=state))
    monkeypatch.setattr(routes, "save_shipping_state", save)
    monkeypatch.setattr(routes, "get_worker_proxy_url", Mock(return_value="http://squid:3128"))
    monkeypatch.setattr(routes, "get_or_login_client", login)
    monkeypatch.setattr("app.auth_multitenant.decrypt_driver_password", Mock(return_value="test-password"))
    return SimpleNamespace(state=state, transport=transport, login=login, save=save)


def start_request() -> routes.ShippingStartRequest:
    return routes.ShippingStartRequest(job_id="test-job", doc_no="test-document", latitude=35.7, longitude=51.4)


def finish_request() -> routes.ShippingFinishRequest:
    return routes.ShippingFinishRequest(job_id="test-job", latitude=35.8, longitude=50.9)


async def test_real_start_handler_uses_vault_and_only_start_endpoint(
    shipping_runtime: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = shipping_runtime
    monkeypatch.setattr(routes, "load_shipping_state", AsyncMock(return_value=None))
    result = await routes.start_shipping(start_request(), user_context={})
    runtime.login.assert_awaited_once_with(
        national_code="test-driver", password="test-password", proxy_url="http://squid:3128"
    )
    runtime.transport.start_shipping_with_gps.assert_awaited_once_with(
        doc_no="test-document", lat=35.7, lon=51.4, alt=0, speed=0, allow_live_submit=True
    )
    runtime.transport.register_start_of_shipping.assert_not_awaited()
    runtime.transport.finish_shipping_with_gps.assert_not_awaited()
    runtime.transport.register_end_of_shipping.assert_not_awaited()
    assert runtime.state.status == "in_transit"
    assert result["status"] == "started"
    runtime.save.assert_awaited_once_with(runtime.state)


async def test_real_finish_handler_orders_finish_before_history(shipping_runtime: SimpleNamespace) -> None:
    runtime = shipping_runtime
    result = await routes.finish_shipping(finish_request(), user_context={})
    calls = runtime.transport.mock_calls
    assert [call[0] for call in calls] == ["finish_shipping_with_gps", "register_end_of_shipping"]
    assert calls[0].kwargs == {
        "doc_no": "test-document",
        "lat": 35.8,
        "lon": 50.9,
        "alt": 0,
        "speed": 0,
        "total_distance_km": 70,
        "allow_live_submit": True,
    }
    assert calls[1].kwargs["document_id"] == "test-document"
    assert calls[1].kwargs["gps_list"] == runtime.state.gps_list
    assert runtime.state.gps_list[-1]["Type"] == 3
    assert result["status"] == "delivered"


@pytest.mark.parametrize("operation", ["start", "finish"])
async def test_real_handler_returns_503_before_login_when_proxy_is_missing(
    operation: str, shipping_runtime: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = shipping_runtime
    monkeypatch.setattr(routes, "get_worker_proxy_url", Mock(return_value=None))
    if operation == "start":
        monkeypatch.setattr(routes, "load_shipping_state", AsyncMock(return_value=None))
    handler, request = (
        (routes.start_shipping, start_request()) if operation == "start" else (routes.finish_shipping, finish_request())
    )
    with pytest.raises(HTTPException) as error:
        await handler(request, user_context={})
    assert error.value.status_code == 503
    runtime.login.assert_not_awaited()
    assert runtime.transport.mock_calls == []


async def test_finish_timeout_does_not_retry_or_report_delivered(shipping_runtime: SimpleNamespace) -> None:
    runtime = shipping_runtime
    runtime.transport.finish_shipping_with_gps.side_effect = TimeoutError("synthetic timeout")
    with pytest.raises(HTTPException) as error:
        await routes.finish_shipping(finish_request(), user_context={})
    assert error.value.status_code == 502
    runtime.transport.finish_shipping_with_gps.assert_awaited_once()
    runtime.transport.register_end_of_shipping.assert_not_awaited()
    assert runtime.state.status == "failed"
    with pytest.raises(HTTPException) as repeated:
        await routes.finish_shipping(finish_request(), user_context={})
    assert repeated.value.status_code == 409
    runtime.transport.finish_shipping_with_gps.assert_awaited_once()
