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
        # A real in_transit trip already carries the origin Type-2 witness that
        # /start appended + persisted, and a physical ETA. Past ETA → finish's
        # shipping_wait_reason() passes; the seeded origin lets prepare_shipping_trace
        # reach the required 2 points once the Type-3 destination is appended.
        estimated_end_at="2020-01-01T00:00:00+00:00",
        gps_list=[
            {
                "Type": 2,
                "Latitude": 35.7,
                "Longitude": 51.4,
                "Speed": 0,
                "Altitude": 1000,
                "Date": "2020-01-01T00:00:00.000Z",
                "DateTime": "2020-01-01T00:00:00.000Z",
                "Provider": "operator_anchor",
                "Provenance": "operator_confirmed",
            }
        ],
    )
    driver = SimpleNamespace(driver_national_code="test-driver", utcms_password_encrypted="test-encrypted")
    transport = Mock()
    transport.start_shipping_with_gps = AsyncMock(return_value={"resultCode": 200})
    transport.finish_shipping_with_gps = AsyncMock(return_value={"resultCode": 200})
    transport.register_end_of_shipping = AsyncMock(return_value={"resultCode": 200})
    transport.register_start_of_shipping = AsyncMock(return_value={"resultCode": 200})
    login = AsyncMock(return_value=transport)
    save = AsyncMock()
    monkeypatch.setattr(routes.utcms_config, "ALLOW_LIVE_SUBMIT", True)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setattr(routes, "_get_job_and_driver", AsyncMock(return_value=({}, driver)))
    monkeypatch.setattr(routes, "load_shipping_state", AsyncMock(return_value=state))
    monkeypatch.setattr(routes, "init_shipping", AsyncMock(return_value=state))
    monkeypatch.setattr(routes, "save_shipping_state", save)
    # record_shipping_rejection() (gps_shipping_manager) persists through that
    # module's OWN save_shipping_state global, not the routes alias above, so the
    # finish-rejection path would otherwise hit the tableless test DB. Isolate it.
    monkeypatch.setattr("app.automation.gps_shipping_manager.save_shipping_state", AsyncMock())
    monkeypatch.setattr(routes, "get_worker_proxy_url", Mock(return_value="http://squid:3128"))
    monkeypatch.setattr(routes, "get_or_login_client", login)
    # The per-job mutation lock is now a Redis SET-NX completion claim (the same
    # one Beat's auto-complete uses), imported into the route module — not an
    # rpa_runtime driver lock. Patch the real seam so the handler never touches
    # Redis and the claim is always granted.
    monkeypatch.setattr(routes, "_acquire_completion_claim", AsyncMock(return_value="test-claim-token"))
    monkeypatch.setattr(routes, "_release_completion_claim", AsyncMock())
    monkeypatch.setattr("app.auth_multitenant.decrypt_driver_password", Mock(return_value="test-password"))
    return SimpleNamespace(state=state, transport=transport, login=login, save=save)


def start_request() -> routes.ShippingStartRequest:
    return routes.ShippingStartRequest(job_id="test-job", doc_no="test-document", latitude=35.7, longitude=51.4)


def finish_request() -> routes.ShippingFinishRequest:
    return routes.ShippingFinishRequest(
        job_id="test-job",
        latitude=35.8,
        longitude=50.9,
        measured_distance_km=70,
    )


async def test_real_start_handler_uses_vault_and_only_start_endpoint(
    shipping_runtime: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = shipping_runtime
    monkeypatch.setattr(routes, "load_shipping_state", AsyncMock(return_value=None))
    result = await routes.start_shipping(start_request(), user_context={})
    runtime.login.assert_awaited_once_with(
        national_code="test-driver",
        password="test-password",
        proxy_url="http://squid:3128",
        force_reauth=False,
        client_id=None,
    )
    runtime.transport.register_start_of_shipping.assert_awaited_once()
    runtime.transport.start_shipping_with_gps.assert_not_awaited()
    runtime.transport.finish_shipping_with_gps.assert_not_awaited()
    runtime.transport.register_end_of_shipping.assert_not_awaited()
    assert runtime.state.status == "in_transit"
    assert result["status"] == "started"
    # Two durable fences: status="starting" before the POST, status="in_transit"
    # after UTCMS acknowledges — so a crash mid-POST is recoverable as "unknown".
    assert runtime.save.await_count == 2
    runtime.save.assert_awaited_with(runtime.state)


async def test_real_finish_handler_calls_only_register_end_of_shipping(shipping_runtime: SimpleNamespace) -> None:
    runtime = shipping_runtime
    result = await routes.finish_shipping(finish_request(), user_context={})
    # The deprecated FinishShippingWithGps endpoint (now 404 on live UTCMS) is
    # gone: finish registers the end-of-shipping trace via RegisterEndOfShipping
    # only, with a 2-point gpsList (Type-2 origin → Type-3 destination).
    runtime.transport.finish_shipping_with_gps.assert_not_awaited()
    runtime.transport.register_end_of_shipping.assert_awaited_once()
    call = runtime.transport.register_end_of_shipping.mock_calls[0]
    assert call.kwargs["document_id"] == "test-document"
    assert call.kwargs["gps_list"] == runtime.state.gps_list
    assert call.kwargs["allow_live_submit"] is True
    assert runtime.state.gps_list[0]["Type"] == 2
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
    runtime.transport.register_end_of_shipping.side_effect = TimeoutError("synthetic timeout")
    with pytest.raises(HTTPException) as error:
        await routes.finish_shipping(finish_request(), user_context={})
    assert error.value.status_code == 502
    runtime.transport.finish_shipping_with_gps.assert_not_awaited()
    runtime.transport.register_end_of_shipping.assert_awaited_once()
    assert runtime.state.status == "unknown"
    with pytest.raises(HTTPException) as repeated:
        await routes.finish_shipping(finish_request(), user_context={})
    assert repeated.value.status_code == 409
    runtime.transport.register_end_of_shipping.assert_awaited_once()


async def test_start_rejects_business_error_and_stays_retryable(
    shipping_runtime: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A structured UTCMS rejection (resultCode present) means no start was
    accepted, so the job stays retryable ('ready'). 'unknown' is reserved for
    ambiguous failures where a mutation might have silently landed."""
    runtime = shipping_runtime
    monkeypatch.setattr(routes, "load_shipping_state", AsyncMock(return_value=None))
    runtime.transport.register_start_of_shipping.return_value = {"resultCode": 4014, "resultMessage": "rejected"}
    with pytest.raises(HTTPException) as error:
        await routes.start_shipping(start_request(), user_context={})
    assert error.value.status_code == 502
    assert runtime.state.status == "ready"
    runtime.save.assert_awaited()


async def test_finish_derives_measured_distance_when_missing(
    shipping_runtime: SimpleNamespace,
) -> None:
    """Phase 11: measured_distance is derived from telemetry/route, not required."""
    request = routes.ShippingFinishRequest(job_id="test-job", latitude=35.8, longitude=50.9)
    result = await routes.finish_shipping(request, user_context={})
    assert result["status"] == "delivered"
    # Auto-derived from Route Authority when the client omits it.
    assert result["measured_distance_km"] > 0
    assert result["measured_source"] == "route_derived"
    # The deprecated FinishShippingWithGps (which used to carry total_distance_km)
    # is gone; distance is now persisted on the delivered state, and the trace is
    # submitted via RegisterEndOfShipping only.
    shipping_runtime.transport.finish_shipping_with_gps.assert_not_awaited()
    shipping_runtime.transport.register_end_of_shipping.assert_awaited_once()
    assert shipping_runtime.state.measured_distance_km == result["measured_distance_km"]


async def test_finish_rejects_business_error_without_history_mutation(
    shipping_runtime: SimpleNamespace,
) -> None:
    """A structured finish rejection (4014) is a known business outcome, not an
    ambiguous failure: the trip stays 'in_transit' and retryable after cooldown,
    and the caller sees 409 with the rejection category — never a false delivery."""
    runtime = shipping_runtime
    runtime.transport.register_end_of_shipping.return_value = {"resultCode": 4014}
    with pytest.raises(HTTPException) as error:
        await routes.finish_shipping(finish_request(), user_context={})
    assert error.value.status_code == 409
    assert runtime.state.status == "in_transit"
    assert error.value.detail["status"] == "rejected"


async def test_shipping_lock_rejects_duplicate_mutation(
    shipping_runtime: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A second concurrent mutation can't win the Redis SET-NX completion claim
    # (shared with Beat auto-complete); the decorator 409s before the handler body,
    # so no driver login is ever attempted.
    monkeypatch.setattr(routes, "_acquire_completion_claim", AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as error:
        await routes.start_shipping(start_request(), user_context={})
    assert error.value.status_code == 409
    shipping_runtime.login.assert_not_awaited()
