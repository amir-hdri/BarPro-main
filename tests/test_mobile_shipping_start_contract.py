"""Contract tests for the mobile shipping START path and the legacy FINISH fallback.

Two defect classes are locked here:

1. ``UtcmsMobileClient.finish_shipping_with_gps`` FABRICATED a
   ``{"resultCode": 200, "resultMessage": "FinishShippingWithGps bypassed"}``
   envelope on a 404 instead of falling back to ``RegisterEndOfShipping`` the
   way its start-side twin does. No production caller remains, but the
   operator-run live scripts (``scripts/run_live_assisted_submission.py``,
   ``scripts/execute_job_109_mobile.py``) consume it, so an operator saw a 404
   reported as a successful registration while nothing had been registered.

2. ``WaybillAutomationBot._finalize_shipping_start`` ignored the UTCMS result
   entirely, hard-set ``in_transit`` unconditionally and swallowed every
   exception — so a refused start was recorded as in-transit, and a start that
   RAISED left the state at ``"ready"``, which ``get_due_in_transit_jobs``
   never selects, silently stranding a trip UTCMS already holds at code 1.
   It also never appended the origin witness, leaving the terminal POST with a
   1-point trace.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.automation.utcms_mobile_client import UtcmsMobileApiError, UtcmsMobileClient
from app.automation.waybill_bot_multitenant import WaybillAutomationBot

# ─────────────────────────────────────────────────────────────────────────────
# 1. finish_shipping_with_gps must never fabricate a success envelope
# ─────────────────────────────────────────────────────────────────────────────


def _client_with_posts(recorded: list[tuple[str, dict]], responses: dict[str, object]) -> UtcmsMobileClient:
    """A client whose `_post` is dispatched by path, recording every call.

    Nothing is constructed per call: the single client instance is reused, so
    this never models (nor encourages) a per-request session, which the UTCMS
    WAF punishes by throttling new TLS handshakes per egress IP.
    """
    client = UtcmsMobileClient(base_url="https://cptch.utcms.ir", token="t")

    async def fake_post(path: str, body: dict) -> dict:
        recorded.append((path, body))
        outcome = responses[path]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome  # type: ignore[return-value]

    client._post = fake_post  # type: ignore[method-assign]
    return client


@pytest.mark.asyncio
async def test_finish_shipping_with_gps_404_falls_back_to_register_end():
    """A 404 must route to the live endpoint, never to a fabricated 200.

    The terminal point is handed to ``RegisterEndOfShipping``; its contract
    validator (``prepare_shipping_trace``) requires a chronological
    origin -> destination trace, so a single-point finish is REJECTED rather
    than reported as registered. Either way the operator learns the truth.
    """
    recorded: list[tuple[str, dict]] = []
    client = _client_with_posts(
        recorded,
        {
            "/Document/FinishShippingWithGps": UtcmsMobileApiError("not found", status_code=404),
            "/Document/RegisterEndOfShipping": {"resultCode": 200, "resultMessage": "ok"},
        },
    )

    with pytest.raises(ValueError, match="origin and destination"):
        await client.finish_shipping_with_gps(doc_no="226164459", lat=35.7, lon=51.4, allow_live_submit=True)

    # The legacy endpoint was attempted exactly once and NOTHING was fabricated.
    assert [path for path, _ in recorded] == ["/Document/FinishShippingWithGps"]


@pytest.mark.asyncio
async def test_finish_shipping_with_gps_404_reaches_register_end_with_full_trace():
    """With a usable trace the fallback actually posts to RegisterEndOfShipping."""
    recorded: list[tuple[str, dict]] = []
    client = _client_with_posts(
        recorded,
        {
            "/Document/FinishShippingWithGps": UtcmsMobileApiError("not found", status_code=404),
            "/Document/RegisterEndOfShipping": {"resultCode": 200, "resultMessage": "پایان حمل ثبت شد"},
        },
    )

    # Patch the contract so this test exercises the ROUTING, not trace geometry
    # (trace preparation has its own dedicated coverage).
    origin = {"Latitude": 35.6, "Longitude": 51.3, "Type": 2, "Date": "2026-10-03T10:00:00.000Z"}
    with patch(
        "app.automation.shipping_contract.prepare_shipping_trace",
        side_effect=lambda points: [origin, *points],
    ):
        res = await client.finish_shipping_with_gps(doc_no="226164459", lat=35.7, lon=51.4, allow_live_submit=True)

    assert res["resultCode"] == 200
    assert "bypassed" not in str(res.get("resultMessage", ""))
    assert [path for path, _ in recorded] == [
        "/Document/FinishShippingWithGps",
        "/Document/RegisterEndOfShipping",
    ]
    terminal = recorded[-1][1]["gpsList"][-1]
    assert terminal["Latitude"] == 35.7
    assert terminal["Longitude"] == 51.4
    assert terminal["Type"] == 3


@pytest.mark.asyncio
async def test_finish_shipping_with_gps_non_404_still_propagates():
    """Only a 404 triggers the fallback; other API errors must surface."""
    recorded: list[tuple[str, dict]] = []
    client = _client_with_posts(
        recorded,
        {"/Document/FinishShippingWithGps": UtcmsMobileApiError("boom", status_code=500)},
    )
    with pytest.raises(UtcmsMobileApiError):
        await client.finish_shipping_with_gps(doc_no="226164459", lat=35.7, lon=51.4, allow_live_submit=True)
    assert [path for path, _ in recorded] == ["/Document/FinishShippingWithGps"]


# ─────────────────────────────────────────────────────────────────────────────
# 2. Post-issuance RegisterStartOfShipping must be validated, never assumed
# ─────────────────────────────────────────────────────────────────────────────

COMPACT_PAYLOAD = {
    "origin": "آذربایجان غربی، شوط، دیزج",
    "destination": "آذربایجان غربی، شوط، مرگان",
    "cargo_type": "محصولات کشاورزی",
    "cargo_weight": 2500,
    "cargo_value": "50000000",
    "plate_number": "32ع444ایران27",
    "driver_national_code": "4929889601",
    "fare": "5,000,000",
}


def _issuing_client(start_outcome) -> AsyncMock:
    """A mobile client that issues a waybill, then returns/raises `start_outcome`."""
    client = AsyncMock(spec=UtcmsMobileClient)
    client.token = "test-token"
    client.login.return_value = SimpleNamespace(
        token="test-token", refresh_token=None, expires_at="2026-10-04T00:00:00Z"
    )
    client.get_user_fleet_list.return_value = {"obj": []}
    client.auto_solve_captcha.return_value = ("", "test-cap")
    client.cap_token_from_solution.return_value = "test-cap"
    client.insert_document.return_value = {
        "resultCode": 200,
        "obj": {"id": 226164459, "docNo": "1349757758", "isOtpNeeded": False},
    }
    client.extract_document_id.return_value = 226164459
    client.extract_tracking_code.return_value = "1349757758"
    client.extract_otp_required.return_value = False
    if isinstance(start_outcome, Exception):
        client.register_start_of_shipping.side_effect = start_outcome
    else:
        client.register_start_of_shipping.return_value = start_outcome
    return client


async def _run_issuance(start_outcome):
    """Issue a waybill and return (job result, last persisted ShippingState)."""
    bot = WaybillAutomationBot(proxy_url="http://squid:3128")
    client = _issuing_client(start_outcome)
    saved = AsyncMock()
    with (
        patch("app.automation.utcms_mobile_client.UtcmsMobileClient", return_value=client),
        patch("app.automation.gps_shipping_manager.save_shipping_state", saved),
    ):
        result = await bot._execute_mobile_waybill_job(
            username="4929889601",
            password="test-password",
            payload=dict(COMPACT_PAYLOAD),
            job_id="job-start-contract",
            client_id=1,
            allow_live_submit=True,
        )
    assert saved.await_args_list, "shipping state was never persisted"
    return result, saved.await_args_list[-1].args[0]


def _step(result, name="mobile_start_shipping"):
    return next(s for s in result["steps"] if s["step"] == name)


@pytest.mark.asyncio
async def test_acknowledged_start_marks_in_transit_with_origin_witness():
    """A 200 start is in_transit AND records the origin point actually POSTed.

    `init_shipping` seeds `gps_list=[]` and nothing else on this path appends
    an origin, so without this witness the terminal POST built a 1-point trace.
    """
    result, state = await _run_issuance({"resultCode": 200, "resultMessage": "ثبت شد"})

    assert result["status"] == "success"
    assert state.status == "in_transit"
    assert _step(result)["status"] == "success"

    assert len(state.gps_list) == 1, "the origin witness must be recorded for the terminal trace"
    witness = state.gps_list[0]
    assert witness["Type"] == 2
    assert round(witness["Latitude"], 2) == 39.22  # شوط origin
    assert round(witness["Longitude"], 2) == 45.03
    assert witness["Date"].endswith("Z"), "UTCMS timestamps are strictly UTC ISO"
    # The witness must mirror what was sent to RegisterStartOfShipping.
    assert witness["Date"] == state.gps_list[0]["Date"]


@pytest.mark.asyncio
async def test_self_declared_4006_start_is_acknowledged():
    """Rule 4006 (self-declared start) is an acknowledgement, not a rejection."""
    _result, state = await _run_issuance(
        {
            "resultCode": 4006,
            "resultMessage": "برای بارنامه نمی توان شروع حمل ثبت کرد",
        }
    )
    assert state.status == "in_transit"
    assert len(state.gps_list) == 1


@pytest.mark.asyncio
async def test_rejected_start_is_not_recorded_as_in_transit():
    """An explicit UTCMS refusal must NOT be recorded as in_transit.

    Pre-fix the envelope claimed `in_transit` while UTCMS had refused, so the
    sweeper later chased a trip that never began.
    """
    result, state = await _run_issuance({"resultCode": 4025, "resultMessage": "مقدار کرایه را باید وارد کنید"})

    assert result["status"] == "success", "a refused start must never fail the registered waybill"
    assert state.status != "in_transit"
    assert state.status == "unknown"
    assert state.last_error_code == 4025
    assert "کرایه" in state.last_error_message
    assert _step(result)["status"] == "rejected"


@pytest.mark.asyncio
async def test_raising_start_stays_sweepable_instead_of_stranded_at_ready():
    """A start that RAISES is ambiguous: UTCMS may already hold the trip.

    Pre-fix the exception was swallowed and the state stayed at `"ready"`,
    which `get_due_in_transit_jobs` never selects — so the trip was silently
    never completed. It must stay sweepable, with the error recorded.
    """
    result, state = await _run_issuance(RuntimeError("squid tunnel reset"))

    assert result["status"] == "success", "a start blip must never fail the registered waybill"
    assert state.status == "in_transit", "an ambiguous start must remain sweepable"
    assert "squid tunnel reset" in state.last_error_message
    assert len(state.gps_list) == 1, "the attempted origin is still the trace's first witness"
    assert _step(result)["status"] == "unknown"


@pytest.mark.asyncio
async def test_sweeper_considers_ambiguous_start_but_not_rejected_start():
    """End-to-end through real persistence: only `in_transit` is ever swept.

    `get_due_in_transit_jobs` reconstructs each envelope with
    `ShippingState.from_dict` and keeps only `status == "in_transit"`, so the
    status written here is exactly what decides whether the trip can ever be
    completed.
    """
    from app.automation.gps_shipping_manager import ShippingState

    def considered(state) -> bool:
        return ShippingState.from_dict(state.to_dict()).status == "in_transit"

    _r1, ambiguous = await _run_issuance(RuntimeError("squid tunnel reset"))
    _r2, rejected = await _run_issuance({"resultCode": 4025, "resultMessage": "رد شد"})

    assert considered(ambiguous) is True, "an ambiguous start must not be stranded"
    assert considered(rejected) is False, "a refused start must not be chased by the sweeper"
