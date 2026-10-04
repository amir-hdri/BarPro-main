"""Run real shipping handlers with isolated storage and UTCMS transport.

These tests protect the existing transport while the Android bridge is built.
They do not claim to prove UTCMS's live business contract.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.api.routes import shipping_gps as routes
from app.automation.gps_shipping_manager import ShippingState, ShippingStatePersistenceError
from app.automation.shipping_contract import shipping_acknowledged


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


async def test_start_rejects_preprocessing_code_and_stays_retryable(
    shipping_runtime: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A DOCUMENTED pre-processing rejection proves no start was accepted, so
    the durable 'starting' fence rolls back to the retryable 'ready'.
    'unknown' is reserved for ambiguous failures where a mutation might have
    silently landed."""
    runtime = shipping_runtime
    monkeypatch.setattr(routes, "load_shipping_state", AsyncMock(return_value=None))
    # 4006 is the only documented pre-processing refusal. shipping_acknowledged
    # treats rule 4006 as an accepted self-declared start UNLESS the message
    # explicitly negates it, so an explicitly-negated 4006 is the one response
    # that reaches the rollback branch. Pin that precondition here: if the
    # contract's veto changes, this fails loudly instead of silently drifting.
    rejected_4006 = {"resultCode": 4006, "resultMessage": "ثبت شروع حمل برای این بارنامه مجاز نیست"}
    assert shipping_acknowledged(rejected_4006, start=True) is False
    runtime.transport.register_start_of_shipping.return_value = rejected_4006
    with pytest.raises(HTTPException) as error:
        await routes.start_shipping(start_request(), user_context={})
    assert error.value.status_code == 502
    # A refusal that created nothing must stay retryable, never fail open to
    # the ambiguous 'unknown'.
    assert runtime.state.status == "ready"
    runtime.save.assert_awaited()


@pytest.mark.parametrize(
    "result",
    [
        pytest.param({"resultCode": 4014, "resultMessage": "rejected"}, id="undocumented-code"),
        pytest.param({"resultCode": 429, "resultMessage": "too many requests"}, id="rate-limited"),
        pytest.param({"resultCode": 200.0, "resultMessage": "ok"}, id="non-int-200"),
        pytest.param({"resultCode": "4014"}, id="string-code"),
    ],
)
async def test_start_fails_closed_for_codes_that_do_not_prove_rejection(
    result: dict,
    shipping_runtime: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 6: a response code that does not PROVE a pre-processing refusal
    must never roll the fence back to 'ready'.

    UTCMS can accept the start and still answer 429 / an unrecognized code /
    a renumbered 200.0. Resetting to 'ready' invited the operator to retry and
    send a SECOND RegisterStartOfShipping for a start that already landed.
    """
    runtime = shipping_runtime
    monkeypatch.setattr(routes, "load_shipping_state", AsyncMock(return_value=None))
    runtime.transport.register_start_of_shipping.return_value = result
    with pytest.raises(HTTPException) as error:
        await routes.start_shipping(start_request(), user_context={})
    assert error.value.status_code == 502
    assert runtime.state.status == "unknown"
    runtime.transport.register_start_of_shipping.assert_awaited_once()


def test_start_preprocessing_allowlist_is_exactly_documented_codes() -> None:
    """Only codes that prove UTCMS refused before processing may reset state."""
    assert routes._start_rejection_is_preprocessing({"resultCode": 4006}) is True
    assert routes._start_rejection_is_preprocessing({"resultCode": "4006"}) is True
    for code in (None, True, False, 0, 200, 200.0, 429, 4011, 4012, 4013, 4014, "", "abc"):
        assert routes._start_rejection_is_preprocessing({"resultCode": code}) is False, code


@pytest.mark.parametrize("stale_status", ["starting"])
async def test_start_reenters_after_abandoned_starting_fence(
    stale_status: str,
    shipping_runtime: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 4: a state stranded at 'starting' must not brick a paid waybill.

    The fence is written before the first POST; if the request dies mid-POST
    (or its rollback save fails) nothing ever clears it, and /start 409'd
    while /finish 409'd on 'not in_transit' — with no reset endpoint.
    """
    runtime = shipping_runtime
    runtime.state.status = stale_status
    result = await routes.start_shipping(start_request(), user_context={})
    assert result["status"] == "started"
    assert runtime.state.status == "in_transit"
    runtime.transport.register_start_of_shipping.assert_awaited_once()


@pytest.mark.parametrize("acknowledged_status", ["in_transit", "finishing", "delivered", "unknown"])
async def test_start_still_refuses_states_that_may_hold_an_accepted_start(
    acknowledged_status: str,
    shipping_runtime: SimpleNamespace,
) -> None:
    """Re-entry is widened ONLY for 'starting'. Every status that records (or
    may record) an accepted start still 409s, so the fence keeps protecting
    against a duplicate RegisterStartOfShipping."""
    runtime = shipping_runtime
    runtime.state.status = acknowledged_status
    with pytest.raises(HTTPException) as error:
        await routes.start_shipping(start_request(), user_context={})
    assert error.value.status_code == 409
    runtime.transport.register_start_of_shipping.assert_not_awaited()
    runtime.login.assert_not_awaited()


async def test_starting_reentry_is_still_blocked_by_the_mutation_lock(
    shipping_runtime: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The double-submit guard is the Redis SET-NX claim, not the status check.

    A genuinely in-flight /start still holds the claim, so the widened
    'starting' re-entry can never produce two concurrent POSTs.
    """
    runtime = shipping_runtime
    runtime.state.status = "starting"
    monkeypatch.setattr(routes, "_acquire_completion_claim", AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as error:
        await routes.start_shipping(start_request(), user_context={})
    assert error.value.status_code == 409
    runtime.login.assert_not_awaited()
    runtime.transport.register_start_of_shipping.assert_not_awaited()


async def test_start_witness_matches_the_coordinates_sent_to_utcms(
    shipping_runtime: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 9: the recorded origin witness and the wire payload must be the
    same point; _assert_route_anchor tolerates ~22 m of drift between them."""
    runtime = shipping_runtime
    monkeypatch.setattr(routes, "load_shipping_state", AsyncMock(return_value=None))
    runtime.state.gps_list = []
    # Within the 0.0002 deg route-anchor tolerance but not identical.
    request = routes.ShippingStartRequest(
        job_id="test-job", doc_no="test-document", latitude=35.70015, longitude=51.40015
    )
    await routes.start_shipping(request, user_context={})
    call = runtime.transport.register_start_of_shipping.mock_calls[0]
    witness = runtime.state.gps_list[0]
    assert (witness["Latitude"], witness["Longitude"]) == (runtime.state.origin_lat, runtime.state.origin_lng)
    assert (call.kwargs["latitude"], call.kwargs["longitude"]) == (witness["Latitude"], witness["Longitude"])


async def test_finish_backfills_origin_for_auto_started_trip(
    shipping_runtime: SimpleNamespace,
) -> None:
    """Finding 1: a waybill auto-started by the issuance flow carries
    status='in_transit' with gps_list == [], because _finalize_shipping_start
    persists in_transit from init_shipping(gps_list=[]) without appending an
    origin point. Finishing it used to raise ValueError out of
    prepare_shipping_trace (<2 points) OUTSIDE every try block -> HTTP 500,
    and the trip could never be finished through the API.
    """
    runtime = shipping_runtime
    runtime.state.gps_list = []
    runtime.state.created_at = "2026-09-15T06:00:00+00:00"

    result = await routes.finish_shipping(finish_request(), user_context={})

    assert result["status"] == "delivered"
    submitted = runtime.transport.register_end_of_shipping.mock_calls[0].kwargs["gps_list"]
    assert len(submitted) >= 2
    assert submitted[0]["Type"] == 2
    assert submitted[-1]["Type"] == 3
    # The backfilled origin is the waybill's frozen route anchor, timestamped
    # from the recorded trip start -- never backdated, never (0, 0).
    assert (submitted[0]["Latitude"], submitted[0]["Longitude"]) == (
        runtime.state.origin_lat,
        runtime.state.origin_lng,
    )
    assert submitted[0]["Date"] == "2026-09-15T06:00:00.000Z"
    assert submitted[0]["Provenance"] == "route_anchor"


async def test_finish_backfill_tolerates_missing_created_at(shipping_runtime: SimpleNamespace) -> None:
    """A legacy envelope without created_at still finishes (stamped 'now')."""
    runtime = shipping_runtime
    runtime.state.gps_list = []
    runtime.state.created_at = ""
    result = await routes.finish_shipping(finish_request(), user_context={})
    assert result["status"] == "delivered"
    assert runtime.state.gps_list[0]["Type"] == 2


async def test_finish_refuses_backfill_without_origin_coordinates(shipping_runtime: SimpleNamespace) -> None:
    """A (0, 0) origin must never be synthesized onto the UTCMS wire."""
    runtime = shipping_runtime
    runtime.state.gps_list = []
    runtime.state.origin_lat = 0.0
    runtime.state.origin_lng = 0.0
    with pytest.raises(HTTPException) as error:
        await routes.finish_shipping(finish_request(), user_context={})
    assert error.value.status_code == 422
    runtime.transport.register_end_of_shipping.assert_not_awaited()


async def test_finish_reports_422_not_500_on_contract_violation(
    shipping_runtime: SimpleNamespace,
) -> None:
    """prepare_shipping_trace rejections are a client-visible 422, never a 500."""
    runtime = shipping_runtime
    # A non-chronological trace: the existing witness is stamped AFTER the
    # destination point the handler is about to append.
    runtime.state.gps_list = [
        {
            "Type": 2,
            "Latitude": 35.7,
            "Longitude": 51.4,
            "Speed": 0,
            "Altitude": 1000,
            "Date": "2999-01-01T00:00:00.000Z",
        }
    ]
    with pytest.raises(HTTPException) as error:
        await routes.finish_shipping(finish_request(), user_context={})
    assert error.value.status_code == 422
    assert isinstance(error.value.detail, str)
    runtime.transport.register_end_of_shipping.assert_not_awaited()


async def test_finish_rejection_detail_does_not_leak_the_utcms_envelope(
    shipping_runtime: SimpleNamespace,
) -> None:
    """Finding 2: the 409 body must be an allowlisted projection.

    record_shipping_rejection returns the verbatim decoded UTCMS body under
    'result'; main.py renders a non-str detail with str(exc.detail), so the
    whole upstream envelope used to be Python-repr'd into the client response.
    """
    runtime = shipping_runtime
    runtime.transport.register_end_of_shipping.return_value = {
        "resultCode": 4013,
        "resultMessage": "زمان مورد نیاز برای پایان حمل نگذشته است.",
        "data": {"internalTicket": "SECRET-UPSTREAM-TOKEN", "driverNationalCode": "0084575948"},
    }
    with pytest.raises(HTTPException) as error:
        await routes.finish_shipping(finish_request(), user_context={})
    detail = error.value.detail
    assert error.value.status_code == 409
    assert set(detail) == {"status", "resultCode", "message", "backoff_until"}
    assert detail["status"] == "waiting_elapsed_time"
    assert detail["resultCode"] == 4013
    assert "SECRET-UPSTREAM-TOKEN" not in str(detail)
    assert "0084575948" not in str(detail)
    # The operator still gets a readable Persian explanation.
    assert "پایان حمل" in detail["message"]


async def test_finish_wait_detail_is_a_persian_sentence(
    shipping_runtime: SimpleNamespace,
) -> None:
    """Finding 5: the ETA/backoff gate must not stringify its internal dict."""
    runtime = shipping_runtime
    runtime.state.estimated_end_at = (datetime.now(UTC) + timedelta(minutes=23)).isoformat()
    with pytest.raises(HTTPException) as error:
        await routes.finish_shipping(finish_request(), user_context={})
    assert error.value.status_code == 409
    detail = error.value.detail
    assert isinstance(detail, str)
    assert "remaining_seconds" not in detail and "waiting_eta" not in detail
    assert "دقیقه" in detail
    runtime.transport.register_end_of_shipping.assert_not_awaited()


async def test_finish_surfaces_502_even_when_failure_state_cannot_persist(
    shipping_runtime: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 3: save_shipping_state raises whenever the DB mirror fails (even
    if Redis succeeded). Unprotected, that escaped the except block and the
    intended 502 never ran, masking the real UTCMS cause behind a bare 500.
    """
    runtime = shipping_runtime
    runtime.transport.register_end_of_shipping.side_effect = TimeoutError("synthetic timeout")

    async def _save(state):
        if state.status == "unknown":  # only the post-failure rollback write fails
            raise ShippingStatePersistenceError("db mirror down")

    monkeypatch.setattr(routes, "save_shipping_state", AsyncMock(side_effect=_save))
    with pytest.raises(HTTPException) as error:
        await routes.finish_shipping(finish_request(), user_context={})
    assert error.value.status_code == 502
    assert error.value.detail == "UTCMS پایان حمل را تأیید نکرد"
    assert runtime.state.status == "unknown"


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
