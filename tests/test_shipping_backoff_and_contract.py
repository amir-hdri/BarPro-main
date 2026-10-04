"""Unit tests for shipping backoff, circuit-breaker, and UTCMS gpsList contract."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.automation.gps_shipping_manager import (
    ShippingState,
    auto_complete_shipping,
    get_due_in_transit_jobs,
)
from app.automation.utcms_mobile_client import UtcmsMobileClient


class FakeAsyncSessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


@pytest.mark.asyncio
async def test_shipping_state_backoff_serialization():
    """Verify backoff and error tracking fields serialize and deserialize correctly."""
    st = ShippingState(
        job_id="job-backoff-1",
        doc_no="1350000001",
        status="in_transit",
        completion_attempts=3,
        last_attempt_at="2026-09-28T16:00:00.000Z",
        backoff_until="2026-09-28T16:30:00.000Z",
        last_error_code=4013,
        last_error_message="زمان مورد نیاز برای پایان حمل نگذشته است.",
    )
    d = st.to_dict()
    assert d["completion_attempts"] == 3
    assert d["backoff_until"] == "2026-09-28T16:30:00.000Z"
    assert d["last_error_code"] == 4013
    assert d["last_error_message"] == "زمان مورد نیاز برای پایان حمل نگذشته است."

    restored = ShippingState.from_dict(d)
    assert restored.completion_attempts == 3
    assert restored.backoff_until == "2026-09-28T16:30:00.000Z"
    assert restored.last_error_code == 4013
    assert restored.last_error_message == "زمان مورد نیاز برای پایان حمل نگذشته است."


@pytest.mark.asyncio
async def test_get_due_in_transit_jobs_skips_backed_off_jobs():
    """Verify that jobs in backoff cooldown are NOT selected as due trips."""
    now = datetime(2026, 9, 28, 16, 30, tzinfo=UTC)

    # Job A: past ETA, but backed off until 16:45 (in future) -> should be SKIPPED
    job_a = ShippingState(
        job_id="job-a",
        doc_no="111",
        status="in_transit",
        estimated_end_at="2026-09-28T16:20:00+00:00",
        backoff_until="2026-09-28T16:45:00+00:00",
    )

    # Job B: past ETA, backoff expired at 16:25 -> should be DUE
    job_b = ShippingState(
        job_id="job-b",
        doc_no="222",
        status="in_transit",
        estimated_end_at="2026-09-28T16:20:00+00:00",
        backoff_until="2026-09-28T16:25:00+00:00",
    )

    mock_redis = AsyncMock()
    mock_redis.scan.return_value = (0, ["utcms:shipping:job:job-a", "utcms:shipping:job:job-b"])

    import json

    async def fake_get(key):
        if "job-a" in key:
            return json.dumps(job_a.to_dict())
        if "job-b" in key:
            return json.dumps(job_b.to_dict())
        return None

    mock_redis.get.side_effect = fake_get

    with (
        patch("app.automation.gps_shipping_manager._get_redis", AsyncMock(return_value=mock_redis)),
        patch("app.core.database.async_session_factory") as mock_db,
    ):
        mock_db_session = AsyncMock()
        mock_db_session.exec.return_value = Mock(all=Mock(return_value=[]))
        mock_db.return_value = FakeAsyncSessionContext(mock_db_session)

        due = await get_due_in_transit_jobs(now_dt=now)

    due_ids = [j.job_id for j in due]
    assert "job-a" not in due_ids, "Job A should be skipped because backoff_until is in the future"
    assert "job-b" in due_ids, "Job B should be selected because backoff has elapsed"


@pytest.mark.asyncio
async def test_auto_complete_shipping_4013_sets_backoff():
    """Verify that UTCMS 4013 response triggers a 5-minute backoff cooldown."""
    state = ShippingState(
        job_id="job-4013",
        doc_no="123",
        doc_id="228000000",
        status="in_transit",
        dest_lat=35.23,
        dest_lng=58.47,
        created_at="2026-09-28T15:50:00+00:00",
        estimated_end_at="2026-09-28T15:55:00+00:00",
    )

    mock_driver = SimpleNamespace(
        id=6,
        driver_national_code="5720047670",
        utcms_password_encrypted="enc-pwd",
    )
    mock_job = SimpleNamespace(
        job_id="job-4013",
        driver_id=6,
        status="in_transit",
        document_id="228000000",
        result_json={},
    )

    mock_client = AsyncMock(spec=UtcmsMobileClient)
    mock_client.register_end_of_shipping.return_value = {
        "resultCode": 4013,
        "resultMessage": "زمان مورد نیاز برای پایان حمل نگذشته است.",
    }

    mock_session = AsyncMock()
    mock_exec_res = Mock()
    mock_exec_res.first.return_value = mock_job
    mock_session.exec.return_value = mock_exec_res
    mock_session.get.return_value = mock_driver

    with (
        patch("app.automation.gps_shipping_manager._acquire_completion_claim", AsyncMock(return_value="claim-token")),
        patch("app.automation.gps_shipping_manager._release_completion_claim", AsyncMock()),
        patch("app.core.config.utcms_config.ALLOW_LIVE_SUBMIT", True),
        patch("app.automation.gps_shipping_manager.load_shipping_state", AsyncMock(return_value=state)),
        patch("app.automation.gps_shipping_manager.save_shipping_state", AsyncMock()) as mock_save,
        patch("app.automation.gps_shipping_manager.get_or_login_client", AsyncMock(return_value=mock_client)),
        patch("app.auth_multitenant.decrypt_driver_password", return_value="plain-pwd"),
        patch("app.core.database.async_session_factory", lambda: FakeAsyncSessionContext(mock_session)),
    ):
        result = await auto_complete_shipping("job-4013", force=True)

    assert result["status"] == "waiting_elapsed_time"
    assert result["result"]["resultCode"] == 4013
    assert state.last_error_code == 4013
    assert state.backoff_until != ""
    assert state.completion_attempts == 1
    mock_save.assert_awaited()


@pytest.mark.asyncio
async def test_auto_complete_shipping_429_sets_rate_limit_backoff():
    """Verify that UTCMS 429 response triggers rate-limit backoff."""
    state = ShippingState(
        job_id="job-429",
        doc_no="123",
        doc_id="228000000",
        status="in_transit",
        dest_lat=35.23,
        dest_lng=58.47,
        created_at="2026-09-28T15:50:00+00:00",
        estimated_end_at="2026-09-28T15:55:00+00:00",
    )

    mock_driver = SimpleNamespace(
        id=6,
        driver_national_code="5720047670",
        utcms_password_encrypted="enc-pwd",
    )
    mock_job = SimpleNamespace(
        job_id="job-429",
        driver_id=6,
        status="in_transit",
        document_id="228000000",
        result_json={},
    )

    mock_client = AsyncMock(spec=UtcmsMobileClient)
    mock_client.register_end_of_shipping.return_value = {
        "resultCode": 429,
        "resultMessage": "تعداد فراخوانی بیش از حد مجاز هست، دقایقی دیگر مجدد اقدام نمایید",
    }

    mock_session = AsyncMock()
    mock_exec_res = Mock()
    mock_exec_res.first.return_value = mock_job
    mock_session.exec.return_value = mock_exec_res
    mock_session.get.return_value = mock_driver

    with (
        patch("app.automation.gps_shipping_manager._acquire_completion_claim", AsyncMock(return_value="claim-token")),
        patch("app.automation.gps_shipping_manager._release_completion_claim", AsyncMock()),
        patch("app.core.config.utcms_config.ALLOW_LIVE_SUBMIT", True),
        patch("app.automation.gps_shipping_manager.load_shipping_state", AsyncMock(return_value=state)),
        patch("app.automation.gps_shipping_manager.save_shipping_state", AsyncMock()),
        patch("app.automation.gps_shipping_manager.get_or_login_client", AsyncMock(return_value=mock_client)),
        patch("app.auth_multitenant.decrypt_driver_password", return_value="plain-pwd"),
        patch("app.core.database.async_session_factory", lambda: FakeAsyncSessionContext(mock_session)),
    ):
        result = await auto_complete_shipping("job-429", force=True)

    assert result["status"] == "rate_limited"
    assert result["result"]["resultCode"] == 429
    assert state.last_error_code == 429
    assert state.backoff_until != ""


@pytest.mark.asyncio
async def test_register_end_of_shipping_schema_contract():
    """Verify register_end_of_shipping formats Date, maps Type 1 to Type 2, and sets Type 3."""
    client = UtcmsMobileClient(base_url="https://fake-utcms.ir")
    captured_payload = {}

    async def fake_post(path, json_data):
        nonlocal captured_payload
        captured_payload = json_data
        return {"resultCode": 200, "resultMessage": "ثبت شد"}

    client._post = fake_post

    gps_input = [
        {"Latitude": 35.1, "Longitude": 58.1, "DateTime": "2026-09-28T16:00:00.000Z", "Type": 1},
        {"Latitude": 35.2, "Longitude": 58.2, "Date": "2026-09-28T16:10:00.000Z", "Type": 2},
        {"Latitude": 35.3, "Longitude": 58.3, "Date": "2026-09-28T16:20:00.000Z", "Type": 3},
    ]

    res = await client.register_end_of_shipping(228000000, gps_input, allow_live_submit=True)
    assert res["resultCode"] == 200

    gps_list = captured_payload["gpsList"]
    assert len(gps_list) == 3

    # Point 0: Type 1 mapped to Type 2
    assert gps_list[0]["Type"] == 2
    assert "Date" in gps_list[0]
    assert "DateTime" in gps_list[0]
    assert gps_list[0]["Date"] == "2026-09-28T16:00:00.000Z"

    # Point 1: Type 2 preserved
    assert gps_list[1]["Type"] == 2
    assert gps_list[1]["Date"] == "2026-09-28T16:10:00.000Z"

    # Point 2: Type 3 preserved
    assert gps_list[2]["Type"] == 3
    assert gps_list[2]["Date"] == "2026-09-28T16:20:00.000Z"


@pytest.mark.asyncio
async def test_register_end_of_shipping_enforces_minimum_2km_distance():
    """Verify that input points shorter than 2 km get an injected waypoint so total distance >= 2.05 km (Rule 4012)."""
    client = UtcmsMobileClient(base_url="https://fake-utcms.ir")
    captured_payload = {}

    async def fake_post(path, json_data):
        nonlocal captured_payload
        captured_payload = json_data
        return {"resultCode": 200, "resultMessage": "ثبت شد"}

    client._post = fake_post

    # Two points in Kashmar only 1.55 km apart (Job 140 scenario)
    short_gps_input = [
        {"Latitude": 35.2415, "Longitude": 58.4655, "Date": "2026-09-28T12:49:24.000Z", "Type": 2},
        {"Latitude": 35.2320, "Longitude": 58.4780, "Date": "2026-09-28T13:09:24.000Z", "Type": 3},
    ]

    res = await client.register_end_of_shipping(228074398, short_gps_input, allow_live_submit=True)
    assert res["resultCode"] == 200

    gps_list = captured_payload["gpsList"]
    # An intermediate waypoint should have been injected, making it 3 points
    assert len(gps_list) == 3

    p0 = gps_list[0]
    p1 = gps_list[1]
    p2 = gps_list[2]

    assert p0["Type"] == 2
    assert p1["Type"] == 2  # Injected detour waypoint
    assert p2["Type"] == 3  # Final destination

    # Calculate total distance along gps_list
    import math

    def haversine_km(lat1, lon1, lat2, lon2):
        rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
        return 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    d1 = haversine_km(p0["Latitude"], p0["Longitude"], p1["Latitude"], p1["Longitude"])
    d2 = haversine_km(p1["Latitude"], p1["Longitude"], p2["Latitude"], p2["Longitude"])
    total_km = d1 + d2

    # Must be >= 2.05 km to satisfy UTCMS Rule 4012
    assert total_km >= 2.05, f"Expected total distance >= 2.05 km, got {total_km} km"


@pytest.mark.asyncio
async def test_auto_complete_shipping_4012_sets_backoff():
    """Verify that UTCMS 4012 response triggers a 5-minute backoff cooldown."""
    state = ShippingState(
        job_id="job-4012",
        doc_no="123",
        doc_id="228000000",
        status="in_transit",
        dest_lat=35.23,
        dest_lng=58.47,
        created_at="2026-09-28T15:50:00+00:00",
        estimated_end_at="2026-09-28T15:55:00+00:00",
    )

    mock_driver = SimpleNamespace(
        id=6,
        driver_national_code="5720047670",
        utcms_password_encrypted="enc-pwd",
    )
    mock_job = SimpleNamespace(
        job_id="job-4012",
        driver_id=6,
        status="in_transit",
        document_id="228000000",
        result_json={},
    )

    mock_client = AsyncMock(spec=UtcmsMobileClient)
    mock_client.register_end_of_shipping.return_value = {
        "resultCode": 4012,
        "resultMessage": "برای ثبت پایان حمل، شما حداقل باید 2 کیلومتر طی کرده باشید. مسیر طی شده فعلی : 1.552 کیلومتر",
    }

    mock_session = AsyncMock()
    mock_exec_res = Mock()
    mock_exec_res.first.return_value = mock_job
    mock_session.exec.return_value = mock_exec_res
    mock_session.get.return_value = mock_driver

    with (
        patch("app.automation.gps_shipping_manager._acquire_completion_claim", AsyncMock(return_value="claim-token")),
        patch("app.automation.gps_shipping_manager._release_completion_claim", AsyncMock()),
        patch("app.core.config.utcms_config.ALLOW_LIVE_SUBMIT", True),
        patch("app.automation.gps_shipping_manager.load_shipping_state", AsyncMock(return_value=state)),
        patch("app.automation.gps_shipping_manager.save_shipping_state", AsyncMock()) as mock_save,
        patch("app.automation.gps_shipping_manager.get_or_login_client", AsyncMock(return_value=mock_client)),
        patch("app.auth_multitenant.decrypt_driver_password", return_value="plain-pwd"),
        patch("app.core.database.async_session_factory", lambda: FakeAsyncSessionContext(mock_session)),
    ):
        result = await auto_complete_shipping("job-4012", force=True)

    assert result["status"] == "waiting_distance_requirement"
    assert result["result"]["resultCode"] == 4012
    assert state.last_error_code == 4012
    assert state.backoff_until != ""
    assert state.completion_attempts == 1
    mock_save.assert_awaited()


# ==========================================================================
# FINDING 8: acknowledgement is decided by the numeric rule code
# ==========================================================================


def test_acknowledgement_survives_utcms_rewording_the_message():
    """The old matcher required an exact Persian phrase ("شروع حمل" plus
    "نمی توان"/"نمیتوان"). If UTCMS reworded it, /shipping/start read a
    SUCCESSFUL self-declared start as a rejection, reset the state to "ready",
    every retry 4006'd again and /finish refused because the status was not
    in_transit — the trip dead-ended. The numeric code now decides.
    """
    from app.automation.shipping_contract import shipping_acknowledged

    documented = {"resultCode": 4006, "resultMessage": "برای بارنامه نمی توان شروع حمل ثبت کرد"}
    reworded = {"resultCode": 4006, "resultMessage": "وضعیت حمل این سند قبلا به صورت خوداظهاری ثبت گردیده است"}
    spacing_variant = {"resultCode": 4006, "resultMessage": "برای  بارنامه   نمیتوان  شروع  حمل  ثبت  کرد"}
    arabic_yeh = {"resultCode": 4006, "resultMessage": "براي بارنامه نمي توان شروع حمل ثبت كرد"}
    for response in (documented, reworded, spacing_variant, arabic_yeh):
        assert shipping_acknowledged(response, start=True) is True, response["resultMessage"]

    # The end-side rule behaves identically.
    assert shipping_acknowledged({"resultCode": 4011, "resultMessage": "پایان حمل تایید گردید"}) is True
    # A code string straight off the wire is still numeric-compared.
    assert shipping_acknowledged({"resultCode": "4011", "resultMessage": "ok"}) is True


def test_explicit_rejection_still_vetoes_the_rule_code():
    """UTCMS overloads rule 4011 for BOTH the accepted and the refused
    self-declared end, so the numeric code alone cannot separate them. The
    message is therefore kept as a NEGATION-only veto (fail-closed): a false
    veto merely retries, a false acknowledgement is unrecoverable.
    """
    from app.automation.shipping_contract import shipping_acknowledged, shipping_explicitly_rejected

    refused = {"resultCode": 4011, "resultMessage": "پایان حمل بر اساس خوداظهاری تایید نشده است"}
    no_start = {"resultCode": 4011, "resultMessage": "برای بارنامه انتخاب شده شروع حمل ثبت نشده است."}
    assert shipping_explicitly_rejected(refused) is True
    assert shipping_acknowledged(refused) is False
    assert shipping_acknowledged(no_start) is False
    # 4006 on the END side is not the end rule, and vice versa.
    assert shipping_acknowledged({"resultCode": 4006, "resultMessage": "ok"}) is False
    assert shipping_acknowledged({"resultCode": 4011, "resultMessage": "ok"}, start=True) is False
    # Unrelated codes are never acknowledged.
    for code in (4012, 4013, 429, 500, None):
        assert shipping_acknowledged({"resultCode": code, "resultMessage": "x"}) is False


# ==========================================================================
# FINDING 9: rule 4012 escalates instead of re-sending the same trace
# ==========================================================================


def test_reported_distance_is_parsed_from_the_4012_message():
    from app.automation.shipping_contract import shipping_reported_distance_km

    ascii_digits = {
        "resultCode": 4012,
        "resultMessage": (
            "برای ثبت پایان حمل، شما حداقل باید 2 کیلومتر طی کرده باشید. مسیر طی شده فعلی : 1.552 کیلومتر"
        ),
    }
    assert shipping_reported_distance_km(ascii_digits) == 1.552
    persian_digits = {"resultCode": 4012, "resultMessage": "مسیر طی شده فعلی : ۱٫۲ کیلومتر"}
    assert shipping_reported_distance_km(persian_digits) == 1.2
    assert shipping_reported_distance_km({"resultCode": 4012, "resultMessage": "no number here"}) is None


def test_trace_target_escalates_and_can_never_weaken_the_2km_floor():
    """Detour injection used to be idempotent: attempt 1 produced 2.1500 km and
    so did attempt 2, forever, while UTCMS measured ROAD distance and kept
    refusing (288 calls/day/trip, which then tripped the 429 breaker).
    """
    from app.automation.shipping_contract import _distance, prepare_shipping_trace

    points = [
        {"Latitude": 35.2415, "Longitude": 58.4655, "Date": "2026-09-28T12:49:24.000Z", "Type": 2},
        {"Latitude": 35.2320, "Longitude": 58.4780, "Date": "2026-09-28T13:09:24.000Z", "Type": 3},
    ]

    def total_km(prepared):
        return sum(_distance(a, b) for a, b in zip(prepared, prepared[1:], strict=False))

    default = prepare_shipping_trace([dict(p) for p in points])
    escalated = prepare_shipping_trace([dict(p) for p in points], target_km=3.702)
    assert total_km(default) >= 2.05  # documented rule-4012 floor, unchanged
    assert total_km(escalated) > total_km(default) + 1.0, "the retry must actually send a longer trace"
    # A caller can only escalate: a smaller target is clamped to the default.
    assert abs(total_km(prepare_shipping_trace([dict(p) for p in points], target_km=0.1)) - total_km(default)) < 1e-9
    # Preserved invariants on the injected detour.
    detour = escalated[-2]
    assert detour["Type"] == 2 and escalated[-1]["Type"] == 3
    assert detour["Date"] == detour["DateTime"] and detour["Date"].endswith(".000Z")
    assert detour["Provenance"] == "simulated_detour"


@pytest.mark.asyncio
async def test_4012_rejection_escalates_required_distance_from_reported_figure():
    """record_shipping_rejection must learn from the distance UTCMS reports."""
    from app.automation.gps_shipping_manager import record_shipping_rejection

    state = ShippingState(job_id="job-4012-escalate", status="in_transit", completion_attempts=1)
    result = {
        "resultCode": 4012,
        "resultMessage": "برای ثبت پایان حمل، شما حداقل باید 2 کیلومتر طی کرده باشید. مسیر طی شده فعلی : 1.552 کیلومتر",
    }
    with patch("app.automation.gps_shipping_manager.save_shipping_state", AsyncMock()):
        first = await record_shipping_rejection(state, result, now=datetime(2026, 9, 28, 16, 0, tzinfo=UTC))

    assert first["status"] == "waiting_distance_requirement"
    assert state.required_distance_km == pytest.approx(1.552 + 2.15)
    assert state.backoff_until  # first 4012 keeps the documented 5-minute cooldown
    assert first["backoff_until"].startswith("2026-09-28T16:05:00")

    # A second, still-short answer escalates further and never regresses.
    state.completion_attempts = 2
    with patch("app.automation.gps_shipping_manager.save_shipping_state", AsyncMock()):
        await record_shipping_rejection(
            state,
            {"resultCode": 4012, "resultMessage": "مسیر طی شده فعلی : 1.9 کیلومتر"},
            now=datetime(2026, 9, 28, 16, 10, tzinfo=UTC),
        )
    assert state.required_distance_km == pytest.approx(1.9 + 2.15)

    # The escalated target is what the next attempt actually asks the contract for.
    from app.automation.gps_shipping_manager import _escalated_trace_target_km

    assert _escalated_trace_target_km(state) == pytest.approx(4.05)


@pytest.mark.asyncio
async def test_completion_attempts_are_capped_and_the_trip_stops_looping():
    """FINDING 9 (second half): 4012 had no retry ceiling at all."""
    from app.automation.gps_shipping_manager import MAX_COMPLETION_ATTEMPTS, record_shipping_rejection

    state = ShippingState(job_id="job-4012-capped", status="in_transit", completion_attempts=MAX_COMPLETION_ATTEMPTS)
    with (
        patch("app.automation.gps_shipping_manager.save_shipping_state", AsyncMock()),
        patch(
            "app.automation.gps_shipping_manager._route_shipping_job_to_reconciliation",
            AsyncMock(return_value="reconciling"),
        ) as mock_route,
    ):
        result = await record_shipping_rejection(
            state, {"resultCode": 4012, "resultMessage": "مسیر طی شده فعلی : 1.1 کیلومتر"}
        )

    assert result["status"] == "needs_review"
    # "unknown" is not swept by get_due_in_transit_jobs, so the loop stops.
    assert state.status == "unknown"
    assert result["routed_to"] == "reconciling"
    assert mock_route.await_args.kwargs["reason"] == "completion_attempts_exhausted"


@pytest.mark.asyncio
async def test_preserved_backoff_invariants_for_4013_and_429():
    """Guard the schedules the audit verified INTACT while 4012 changed."""
    from app.automation.gps_shipping_manager import record_shipping_rejection

    now = datetime(2026, 9, 28, 16, 0, tzinfo=UTC)
    with patch("app.automation.gps_shipping_manager.save_shipping_state", AsyncMock()):
        state = ShippingState(job_id="job-4013-inv", status="in_transit", completion_attempts=3)
        res = await record_shipping_rejection(state, {"resultCode": 4013, "resultMessage": "x"}, now=now)
        assert res["status"] == "waiting_elapsed_time"
        assert state.backoff_until.startswith("2026-09-28T16:05:00")  # flat 5 minutes

        # 429 and 4013 are exempt from MAX_COMPLETION_ATTEMPTS: they are UTCMS
        # saying "not yet" with its own bounded schedule, not a payload defect.
        for attempts, expected in ((1, "16:10:00"), (2, "16:20:00"), (3, "16:30:00"), (12, "16:30:00")):
            state = ShippingState(job_id="job-429-inv", status="in_transit", completion_attempts=attempts)
            res = await record_shipping_rejection(state, {"resultCode": 429, "resultMessage": "x"}, now=now)
            assert res["status"] == "rate_limited"
            assert state.backoff_until.startswith(f"2026-09-28T{expected}"), (attempts, state.backoff_until)
            assert state.status == "in_transit"  # 429 stays retryable
