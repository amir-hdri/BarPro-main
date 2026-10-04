"""Comprehensive tests for the automated shipping lifecycle in BarPro.

Covers:
1. init_shipping: sets created_at and computes estimated_end_at (minimum 20 min buffer or proportional duration).
2. get_due_in_transit_jobs: filters in-transit jobs in Redis and DB based on estimated_end_at vs current time.
3. auto_complete_shipping: returns waiting_eta when ETA is not yet reached and force is False.
4. auto_complete_shipping: when force=True or past ETA, builds and submits 2-point GPS evidence (origin + destination).
5. auto_complete_shipping: handles UTCMS 4011 (self-declared start completion) gracefully, marks delivered, and updates DB WaybillJob.
"""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.automation.gps_shipping_manager import (
    ShippingState,
    auto_complete_shipping,
    get_due_in_transit_jobs,
    init_shipping,
)
from app.automation.utcms_mobile_client import UtcmsMobileClient


class FakeAsyncSessionContext:
    """Async context manager mock for async_session_factory."""

    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


@pytest.fixture(autouse=True)
def _isolate_claim_and_live_submit(monkeypatch):
    """Isolate the two cross-cutting gates that are NOT the subject of these
    lifecycle tests:

    * the Redis SET-NX completion claim (``_acquire_completion_claim``), which
      now fails CLOSED when Redis is unreachable; and
    * ``ALLOW_LIVE_SUBMIT`` (default False), the unconditional live-submit gate.

    Granting the claim and enabling live submit for every test here is harmless
    for the ``init_shipping``/``get_due`` tests (which never reach either) and
    lets the ``auto_complete_shipping`` tests exercise their real intent. Tests
    that specifically target the claim live in ``test_gps_shipping_batch_g.py``.
    """
    monkeypatch.setattr(
        "app.automation.gps_shipping_manager._acquire_completion_claim",
        AsyncMock(return_value="claim-token"),
    )
    monkeypatch.setattr("app.automation.gps_shipping_manager._release_completion_claim", AsyncMock())
    monkeypatch.setattr("app.core.config.utcms_config.ALLOW_LIVE_SUBMIT", True)


# ==============================================================================
# 1. Tests for init_shipping created_at & estimated_end_at calculation
# ==============================================================================


@pytest.mark.asyncio
async def test_init_shipping_sets_created_at_and_minimum_20_min_buffer():
    """Verify init_shipping sets created_at and enforces at least 20 min buffer for short routes."""
    now_before = datetime.now(UTC)
    payload = {
        "originLat": 39.22,
        "originLng": 45.03,
        "destLat": 39.23,
        "destLng": 45.04,
        "distance_km": 2.0,
    }
    state = await init_shipping(
        job_id="job-short-buffer",
        doc_no="1349700001",
        payload=payload,
        doc_id="226100001",
        persist=False,
    )
    now_after = datetime.now(UTC)

    assert state.created_at, "created_at must not be empty"
    assert state.estimated_end_at, "estimated_end_at must not be empty"

    created_dt = datetime.fromisoformat(state.created_at)
    estimated_dt = datetime.fromisoformat(state.estimated_end_at)

    assert now_before <= created_dt <= now_after
    diff_minutes = (estimated_dt - created_dt).total_seconds() / 60.0
    # Minimum buffer is 20 minutes
    assert 19.9 <= diff_minutes <= 20.1

    # Verify serialization roundtrip preserves both fields
    d = state.to_dict()
    assert d["created_at"] == state.created_at
    assert d["estimated_end_at"] == state.estimated_end_at

    restored = ShippingState.from_dict(d)
    assert restored.created_at == state.created_at
    assert restored.estimated_end_at == state.estimated_end_at


@pytest.mark.asyncio
async def test_init_shipping_computes_proportional_duration_for_long_distance():
    """Verify init_shipping calculates proportional travel duration for long trips."""
    # 650 km at 65 km/h is 10 hours (600 minutes)
    payload = {
        "originLat": 35.6892,
        "originLng": 51.3890,  # Tehran
        "destLat": 38.0800,
        "destLng": 46.2919,  # Tabriz (~650 km)
        "distance_km": 650.0,
    }
    state = await init_shipping(
        job_id="job-long-trip",
        doc_no="1349700002",
        payload=payload,
        doc_id="226100002",
        persist=False,
    )

    created_dt = datetime.fromisoformat(state.created_at)
    estimated_dt = datetime.fromisoformat(state.estimated_end_at)

    duration_minutes = (estimated_dt - created_dt).total_seconds() / 60.0
    # Expected: 650 / 65 * 60 = 600 minutes, significantly exceeding the 20 min minimum
    assert duration_minutes >= 550.0
    assert duration_minutes > 20.0


# ==============================================================================
# 2. Tests for get_due_in_transit_jobs ETA filtering
# ==============================================================================


@pytest.mark.asyncio
async def test_get_due_in_transit_jobs_filters_redis_correctly():
    """Verify get_due_in_transit_jobs only returns jobs past their estimated_end_at in Redis."""
    now = datetime.now(UTC)

    # Job 1: In transit, past ETA -> DUE
    state_due = ShippingState(
        job_id="job-due-1",
        status="in_transit",
        estimated_end_at=(now - timedelta(minutes=5)).isoformat(),
    )
    # Job 2: In transit, future ETA -> NOT DUE
    state_waiting = ShippingState(
        job_id="job-waiting-1",
        status="in_transit",
        estimated_end_at=(now + timedelta(minutes=25)).isoformat(),
    )
    # Job 3: Delivered, past ETA -> NOT DUE (already completed)
    state_delivered = ShippingState(
        job_id="job-delivered-1",
        status="delivered",
        estimated_end_at=(now - timedelta(minutes=10)).isoformat(),
    )
    # Job 4: In transit, empty ETA -> NOT DUE (fail-closed). The arrival gate
    # that used to precede the terminal POST is gone, so the ETA is the only
    # client-side trigger left; treating a blank one as satisfied made such an
    # envelope due immediately with nothing to stop it.
    state_no_eta = ShippingState(
        job_id="job-no-eta",
        status="in_transit",
        estimated_end_at="",
    )

    fake_redis_data = {
        "utcms:shipping:job:job-due-1": json.dumps(state_due.to_dict()),
        "utcms:shipping:job:job-waiting-1": json.dumps(state_waiting.to_dict()),
        "utcms:shipping:job:job-delivered-1": json.dumps(state_delivered.to_dict()),
        "utcms:shipping:job:job-no-eta": json.dumps(state_no_eta.to_dict()),
    }

    mock_redis = AsyncMock()
    mock_redis.scan.return_value = (0, list(fake_redis_data.keys()))
    mock_redis.get.side_effect = lambda k: fake_redis_data.get(k)

    mock_session = AsyncMock()
    mock_exec_res = Mock()
    mock_exec_res.all.return_value = []
    mock_session.exec.return_value = mock_exec_res

    with (
        patch("app.automation.gps_shipping_manager._get_redis", AsyncMock(return_value=mock_redis)),
        patch("app.core.database.async_session_factory", lambda: FakeAsyncSessionContext(mock_session)),
    ):
        due = await get_due_in_transit_jobs(now_dt=now)

    due_job_ids = {s.job_id for s in due}
    assert "job-due-1" in due_job_ids
    assert "job-no-eta" not in due_job_ids
    assert "job-waiting-1" not in due_job_ids
    assert "job-delivered-1" not in due_job_ids


@pytest.mark.asyncio
async def test_get_due_in_transit_jobs_falls_back_to_db_and_deduplicates():
    """Verify get_due_in_transit_jobs retrieves in-transit jobs from DB and deduplicates with Redis."""
    now = datetime.now(UTC)

    # Job in Redis
    state_redis = ShippingState(
        job_id="job-redis",
        status="in_transit",
        estimated_end_at=(now - timedelta(minutes=5)).isoformat(),
    )
    # Job only in DB (past ETA)
    state_db_due = ShippingState(
        job_id="job-db-due",
        status="in_transit",
        estimated_end_at=(now - timedelta(minutes=15)).isoformat(),
    )
    # Job only in DB (future ETA)
    state_db_future = ShippingState(
        job_id="job-db-future",
        status="in_transit",
        estimated_end_at=(now + timedelta(minutes=20)).isoformat(),
    )

    mock_redis = AsyncMock()
    mock_redis.scan.return_value = (0, ["utcms:shipping:job:job-redis"])
    mock_redis.get.return_value = json.dumps(state_redis.to_dict())

    job_db_1 = SimpleNamespace(
        job_id="job-redis",  # Duplicate in DB
        status="in_transit",
        result_json={"_shipping_state": state_redis.to_dict()},
    )
    job_db_2 = SimpleNamespace(
        job_id="job-db-due",
        status="in_transit",
        result_json={"_shipping_state": state_db_due.to_dict()},
    )
    job_db_3 = SimpleNamespace(
        job_id="job-db-future",
        status="in_transit",
        result_json={"_shipping_state": state_db_future.to_dict()},
    )

    mock_session = AsyncMock()
    mock_exec_res = Mock()
    mock_exec_res.all.return_value = [job_db_1, job_db_2, job_db_3]
    mock_session.exec.return_value = mock_exec_res

    with (
        patch("app.automation.gps_shipping_manager._get_redis", AsyncMock(return_value=mock_redis)),
        patch("app.core.database.async_session_factory", lambda: FakeAsyncSessionContext(mock_session)),
    ):
        due = await get_due_in_transit_jobs(now_dt=now)

    due_job_ids = [s.job_id for s in due]
    assert due_job_ids.count("job-redis") == 1
    assert "job-db-due" in due_job_ids
    assert "job-db-future" not in due_job_ids


@pytest.mark.asyncio
async def test_get_due_in_transit_jobs_with_custom_now_dt():
    """Verify get_due_in_transit_jobs respects the custom now_dt passed to it."""
    base_time = datetime(2026, 9, 26, 12, 0, 0, tzinfo=UTC)
    state = ShippingState(
        job_id="job-custom-time",
        status="in_transit",
        estimated_end_at="2026-09-26T12:30:00+00:00",
    )

    mock_redis = AsyncMock()
    mock_redis.scan.return_value = (0, ["utcms:shipping:job:job-custom-time"])
    mock_redis.get.return_value = json.dumps(state.to_dict())

    mock_session = AsyncMock()
    mock_exec_res = Mock()
    mock_exec_res.all.return_value = []
    mock_session.exec.return_value = mock_exec_res

    with (
        patch("app.automation.gps_shipping_manager._get_redis", AsyncMock(return_value=mock_redis)),
        patch("app.core.database.async_session_factory", lambda: FakeAsyncSessionContext(mock_session)),
    ):
        # Before ETA (12:15) -> Not due
        due_before = await get_due_in_transit_jobs(now_dt=base_time + timedelta(minutes=15))
        assert len(due_before) == 0

        # After ETA (12:45) -> Due
        due_after = await get_due_in_transit_jobs(now_dt=base_time + timedelta(minutes=45))
        assert len(due_after) == 1
        assert due_after[0].job_id == "job-custom-time"


# ==============================================================================
# 3. Tests for auto_complete_shipping waiting ETA
# ==============================================================================


@pytest.mark.asyncio
async def test_auto_complete_shipping_returns_waiting_eta_when_in_transit_not_forced():
    """Verify auto_complete_shipping returns waiting_eta if estimated_end_at is in the future and force=False."""
    now = datetime.now(UTC)
    future_eta = (now + timedelta(minutes=15)).isoformat()
    state = ShippingState(
        job_id="job-wait-test",
        doc_no="1349757758",
        doc_id="226164459",
        status="in_transit",
        estimated_end_at=future_eta,
        dest_lat=39.11,
        dest_lng=45.06,
    )

    with (
        patch("app.automation.gps_shipping_manager.load_shipping_state", AsyncMock(return_value=state)),
        patch("app.automation.gps_shipping_manager.get_or_login_client") as mock_login,
    ):
        result = await auto_complete_shipping("job-wait-test", force=False)

    assert result["status"] == "waiting_eta"
    assert result["remaining_seconds"] > 0
    assert result["estimated_end_at"] == future_eta
    mock_login.assert_not_called()


@pytest.mark.asyncio
async def test_auto_complete_shipping_skipped_cases():
    """Verify auto_complete_shipping handles non-transit states and missing data gracefully."""
    # 1. State not in transit
    state_done = ShippingState(job_id="job-done", status="delivered")
    with patch("app.automation.gps_shipping_manager.load_shipping_state", AsyncMock(return_value=state_done)):
        res = await auto_complete_shipping("job-done")
        assert res == {"status": "skipped", "reason": "not_in_transit"}

    # 2. State missing doc_id and doc_no
    state_no_doc = ShippingState(job_id="job-no-doc", status="in_transit", doc_id="", doc_no="")
    with patch("app.automation.gps_shipping_manager.load_shipping_state", AsyncMock(return_value=state_no_doc)):
        res = await auto_complete_shipping("job-no-doc", force=True)
        assert res == {"status": "skipped", "reason": "missing_doc_id"}

    # 3. State missing destination coordinates
    state_no_coords = ShippingState(
        job_id="job-no-coords", status="in_transit", doc_id="2261000", dest_lat=0.0, dest_lng=0.0
    )
    with patch("app.automation.gps_shipping_manager.load_shipping_state", AsyncMock(return_value=state_no_coords)):
        res = await auto_complete_shipping("job-no-coords", force=True)
        assert res == {"status": "skipped", "reason": "missing_dest_coordinates"}


# ==============================================================================
# 4. Tests for auto_complete_shipping sending 2-point GPS evidence
# ==============================================================================


@pytest.mark.asyncio
async def test_auto_complete_shipping_with_force_true_sends_two_point_gps():
    """Verify auto_complete_shipping with force=True bypasses waiting ETA and sends origin + destination GPS points."""
    now = datetime.now(UTC)
    created_ts = (now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    future_eta = (now + timedelta(minutes=30)).isoformat()

    state = ShippingState(
        job_id="job-force-test",
        doc_no="1349757758",
        doc_id="226164459",
        status="in_transit",
        created_at=created_ts,
        estimated_end_at=future_eta,
        origin_lat=39.22,
        origin_lng=45.03,
        dest_lat=39.11,
        dest_lng=45.06,
        distance_km=25.0,
        gps_list=[],
    )

    mock_driver = SimpleNamespace(
        id=1,
        driver_national_code="4929889601",
        utcms_password_encrypted="encrypted-pwd",
    )
    mock_job = SimpleNamespace(
        job_id="job-force-test",
        driver_id=1,
        status="in_transit",
        document_id="226164459",
        result_json={},
    )

    mock_client = AsyncMock(spec=UtcmsMobileClient)
    mock_client.register_end_of_shipping.return_value = {
        "resultCode": 200,
        "resultMessage": "پایان حمل با موفقیت ثبت شد",
    }

    mock_session = AsyncMock()
    mock_exec_res = Mock()
    mock_exec_res.first.return_value = mock_job
    mock_session.exec.return_value = mock_exec_res
    mock_session.get.return_value = mock_driver

    with (
        patch("app.automation.gps_shipping_manager.load_shipping_state", AsyncMock(return_value=state)),
        patch("app.automation.gps_shipping_manager.save_shipping_state", AsyncMock()) as mock_save,
        patch("app.automation.gps_shipping_manager.get_or_login_client", AsyncMock(return_value=mock_client)),
        patch("app.auth_multitenant.decrypt_driver_password", return_value="plain-pwd"),
        patch("app.core.database.async_session_factory", lambda: FakeAsyncSessionContext(mock_session)),
    ):
        result = await auto_complete_shipping("job-force-test", force=True)

    assert result["status"] == "delivered"
    mock_client.register_end_of_shipping.assert_awaited_once()
    call_kwargs = mock_client.register_end_of_shipping.await_args.kwargs
    assert call_kwargs["document_id"] == "226164459"
    assert call_kwargs["allow_live_submit"] is True

    gps_list = call_kwargs["gps_list"]
    assert len(gps_list) == 2, f"Expected 2-point GPS evidence, got {len(gps_list)}"

    # Point 1: Origin
    assert gps_list[0]["Latitude"] == 39.22
    assert gps_list[0]["Longitude"] == 45.03
    assert gps_list[0]["DateTime"] == created_ts

    # Point 2: Destination
    assert gps_list[1]["Latitude"] == 39.11
    assert gps_list[1]["Longitude"] == 45.06
    assert gps_list[1]["Speed"] == 0.0

    # State updated to delivered
    assert state.status == "delivered"
    mock_save.assert_awaited()


@pytest.mark.asyncio
async def test_auto_complete_shipping_when_past_eta_sends_two_point_gps():
    """Verify auto_complete_shipping when past ETA (force=False) automatically sends 2-point GPS."""
    now = datetime.now(UTC)
    created_ts = (now - timedelta(minutes=40)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    past_eta = (now - timedelta(minutes=5)).isoformat()

    state = ShippingState(
        job_id="job-past-eta-test",
        doc_no="1349757758",
        doc_id="226164459",
        status="in_transit",
        created_at=created_ts,
        estimated_end_at=past_eta,
        origin_lat=36.18,
        origin_lng=50.76,
        dest_lat=36.25,
        dest_lng=50.85,
        distance_km=15.0,
        gps_list=[],
    )

    mock_driver = SimpleNamespace(
        id=2,
        driver_national_code="0321410408",
        utcms_password_encrypted="enc-pwd-2",
    )
    mock_job = SimpleNamespace(
        job_id="job-past-eta-test",
        driver_id=2,
        status="in_transit",
        document_id="226164459",
        result_json={},
    )

    mock_client = AsyncMock(spec=UtcmsMobileClient)
    mock_client.register_end_of_shipping.return_value = {"resultCode": 200, "resultMessage": "ثبت شد"}

    mock_session = AsyncMock()
    mock_exec_res = Mock()
    mock_exec_res.first.return_value = mock_job
    mock_session.exec.return_value = mock_exec_res
    mock_session.get.return_value = mock_driver

    with (
        patch("app.automation.gps_shipping_manager.load_shipping_state", AsyncMock(return_value=state)),
        patch("app.automation.gps_shipping_manager.save_shipping_state", AsyncMock()),
        patch("app.automation.gps_shipping_manager.get_or_login_client", AsyncMock(return_value=mock_client)),
        patch("app.auth_multitenant.decrypt_driver_password", return_value="plain-pwd"),
        patch("app.core.database.async_session_factory", lambda: FakeAsyncSessionContext(mock_session)),
    ):
        result = await auto_complete_shipping("job-past-eta-test", force=False)

    assert result["status"] == "delivered"
    call_kwargs = mock_client.register_end_of_shipping.await_args.kwargs
    gps_list = call_kwargs["gps_list"]
    assert len(gps_list) == 2
    assert gps_list[0]["Latitude"] == 36.18
    assert gps_list[0]["Longitude"] == 50.76
    assert gps_list[1]["Latitude"] == 36.25
    assert gps_list[1]["Longitude"] == 50.85


# ==============================================================================
# 5. Tests for UTCMS 4011 handling & DB WaybillJob update
# ==============================================================================


@pytest.mark.asyncio
async def test_auto_complete_shipping_handles_4011_exception_and_updates_db():
    """A free-text "4011" mention in an exception is NOT UTCMS business rule 4011
    (only a structured result_code counts). The terminal POST may have landed, so
    the flow fails CLOSED to 'unknown' for manual reconciliation — logged, never
    auto-retried, and neither the trip nor the DB job marked delivered/success.
    """
    state = ShippingState(
        job_id="job-4011-exc-test",
        doc_no="1349757758",
        doc_id="226164459",
        status="in_transit",
        dest_lat=39.11,
        dest_lng=45.06,
        origin_lat=39.22,
        origin_lng=45.03,
    )

    mock_driver = SimpleNamespace(
        id=1,
        driver_national_code="4929889601",
        utcms_password_encrypted="encrypted-pwd",
    )
    mock_job = SimpleNamespace(
        job_id="job-4011-exc-test",
        driver_id=1,
        status="in_transit",
        document_id="226164459",
        result_json={"tracking_code": "1349757758"},
        updated_at=None,
    )

    mock_client = AsyncMock(spec=UtcmsMobileClient)
    # Free-text "4011" mention WITHOUT a structured business-rule code.
    mock_client.register_end_of_shipping.side_effect = Exception(
        "UTCMS 4011: پایان حمل بر اساس خوداظهاری تایید شده است"
    )

    mock_session = AsyncMock()
    mock_exec_res = Mock()
    mock_exec_res.first.return_value = mock_job
    mock_session.exec.return_value = mock_exec_res
    mock_session.get.return_value = mock_driver

    with (
        patch("app.automation.gps_shipping_manager.load_shipping_state", AsyncMock(return_value=state)),
        patch("app.automation.gps_shipping_manager.save_shipping_state", AsyncMock()),
        patch("app.automation.gps_shipping_manager.get_or_login_client", AsyncMock(return_value=mock_client)),
        patch("app.auth_multitenant.decrypt_driver_password", return_value="plain-pwd"),
        patch("app.core.database.async_session_factory", lambda: FakeAsyncSessionContext(mock_session)),
    ):
        result = await auto_complete_shipping("job-4011-exc-test", force=True)

    # Free-text "4011" is NOT business-rule 4011; a register_end exception is
    # ambiguous (may have landed), so the flow fails CLOSED to 'unknown' for
    # manual reconciliation rather than propagating or auto-retrying.
    assert result["status"] == "unknown"
    assert state.status == "unknown"
    assert state.status != "delivered"
    assert state.last_error_message
    # Re-added guard (the audit found this assertion had been deleted rather
    # than the orphan-state defect it exposed being fixed): a failed completion
    # must stay recorded WITH a bounded cooldown, never be left with no backoff
    # and no reconciliation routing, which get_due_in_transit_jobs can never
    # sweep again.
    assert state.backoff_until, "a failed completion must persist a bounded cooldown"
    assert result["backoff_until"] == state.backoff_until
    assert result["routed_to"]

    # 2. Database WaybillJob is NOT marked success.
    assert mock_job.status != "success"
    assert "end_shipping" not in (mock_job.result_json or {})


@pytest.mark.asyncio
async def test_auto_complete_shipping_handles_4011_dict_response():
    """Verify auto_complete_shipping handles UTCMS 4011 resultCode dictionary gracefully."""
    state = ShippingState(
        job_id="job-4011-dict-test",
        doc_no="1349757758",
        doc_id="226164459",
        status="in_transit",
        dest_lat=39.11,
        dest_lng=45.06,
        origin_lat=39.22,
        origin_lng=45.03,
    )

    mock_driver = SimpleNamespace(
        id=1,
        driver_national_code="4929889601",
        utcms_password_encrypted="encrypted-pwd",
    )
    mock_job = SimpleNamespace(
        job_id="job-4011-dict-test",
        driver_id=1,
        status="in_transit",
        document_id="226164459",
        result_json={},
        updated_at=None,
    )

    mock_client = AsyncMock(spec=UtcmsMobileClient)
    # Simulate client returning resultCode 4011 dict
    mock_client.register_end_of_shipping.return_value = {
        "resultCode": 4011,
        "resultMessage": "پایان حمل بر اساس خوداظهاری تایید شد",
    }

    mock_session = AsyncMock()
    mock_exec_res = Mock()
    mock_exec_res.first.return_value = mock_job
    mock_session.exec.return_value = mock_exec_res
    mock_session.get.return_value = mock_driver

    with (
        patch("app.automation.gps_shipping_manager.load_shipping_state", AsyncMock(return_value=state)),
        patch("app.automation.gps_shipping_manager.save_shipping_state", AsyncMock()),
        patch("app.automation.gps_shipping_manager.get_or_login_client", AsyncMock(return_value=mock_client)),
        patch("app.auth_multitenant.decrypt_driver_password", return_value="plain-pwd"),
        patch("app.core.database.async_session_factory", lambda: FakeAsyncSessionContext(mock_session)),
    ):
        result = await auto_complete_shipping("job-4011-dict-test", force=True)

    assert result["status"] == "delivered"
    assert result["result"]["mode"] == "self_declared_auto_complete"
    # Shipping records delivery via the end_shipping witness + ShippingState;
    # it deliberately does NOT mutate the WaybillJob issuance status.
    assert mock_job.status == "in_transit"
    assert mock_job.result_json["end_shipping"]["resultCode"] == 4011
    assert state.status == "delivered"


@pytest.mark.asyncio
async def test_auto_complete_shipping_raises_on_non_4011_exception():
    """A genuine transport error during the terminal POST is ambiguous (it may
    have landed), so the flow fails CLOSED to 'unknown' for reconciliation and
    never marks the trip delivered — it does not propagate or auto-retry."""
    state = ShippingState(
        job_id="job-err-test",
        doc_no="1349757758",
        doc_id="226164459",
        status="in_transit",
        dest_lat=39.11,
        dest_lng=45.06,
        origin_lat=39.22,
        origin_lng=45.03,
    )

    mock_driver = SimpleNamespace(
        id=1,
        driver_national_code="4929889601",
        utcms_password_encrypted="encrypted-pwd",
    )
    mock_job = SimpleNamespace(
        job_id="job-err-test",
        driver_id=1,
        status="in_transit",
        document_id="226164459",
        result_json={},
    )

    mock_client = AsyncMock(spec=UtcmsMobileClient)
    mock_client.register_end_of_shipping.side_effect = RuntimeError("Fatal network error 500")

    mock_session = AsyncMock()
    mock_exec_res = Mock()
    mock_exec_res.first.return_value = mock_job
    mock_session.exec.return_value = mock_exec_res
    mock_session.get.return_value = mock_driver

    with (
        patch("app.automation.gps_shipping_manager.load_shipping_state", AsyncMock(return_value=state)),
        patch("app.automation.gps_shipping_manager.save_shipping_state", AsyncMock()),
        patch("app.automation.gps_shipping_manager.get_or_login_client", AsyncMock(return_value=mock_client)),
        patch("app.auth_multitenant.decrypt_driver_password", return_value="plain-pwd"),
        patch("app.core.database.async_session_factory", lambda: FakeAsyncSessionContext(mock_session)),
    ):
        result = await auto_complete_shipping("job-err-test", force=True)

    # Ambiguous terminal-POST error → fail CLOSED to 'unknown', never delivered.
    assert result["status"] == "unknown"
    assert state.status == "unknown"
    assert state.status != "delivered"
    # Re-added guard (see the note in the 4011-exception test above): the
    # outcome is recorded with a cooldown and routed, not orphaned.
    assert state.backoff_until, "a failed completion must persist a bounded cooldown"
    assert result["retryable"] is False
    assert result["routed_to"]


@pytest.mark.asyncio
async def test_auto_complete_shipping_handles_4011_no_start_shipping():
    """Verify auto_complete_shipping handles 4011 'شروع حمل ثبت نشده است' by calling register_start_of_shipping and settling."""
    state = ShippingState(
        job_id="job-4011-no-start-test",
        doc_no="1353083857",
        doc_id="229468123",
        status="in_transit",
        dest_lat=35.70,
        dest_lng=51.40,
        origin_lat=35.65,
        origin_lng=51.35,
    )

    mock_driver = SimpleNamespace(
        id=6,
        driver_national_code="0084575948",
        utcms_password_encrypted="encrypted-pwd",
    )
    mock_job = SimpleNamespace(
        job_id="job-4011-no-start-test",
        driver_id=6,
        status="in_transit",
        document_id="229468123",
        result_json={},
        updated_at=None,
    )

    mock_client = AsyncMock(spec=UtcmsMobileClient)
    # First call returns 4011 without start
    mock_client.register_end_of_shipping.side_effect = [
        {"resultCode": 4011, "resultMessage": "برای بارنامه انتخاب شده شروع حمل ثبت نشده است."},
        {"resultCode": 200, "resultMessage": "پایان حمل با موفقیت ثبت شد"},
    ]
    mock_client.register_start_of_shipping.return_value = {"resultCode": 200, "resultMessage": "شروع حمل ثبت شد"}

    mock_session = AsyncMock()
    mock_exec_res = Mock()
    mock_exec_res.first.return_value = mock_job
    mock_session.exec.return_value = mock_exec_res
    mock_session.get.return_value = mock_driver

    with (
        patch("app.automation.gps_shipping_manager.load_shipping_state", AsyncMock(return_value=state)),
        patch("app.automation.gps_shipping_manager.save_shipping_state", AsyncMock()),
        patch("app.automation.gps_shipping_manager.get_or_login_client", AsyncMock(return_value=mock_client)),
        patch("app.auth_multitenant.decrypt_driver_password", return_value="plain-pwd"),
        patch("app.core.database.async_session_factory", lambda: FakeAsyncSessionContext(mock_session)),
    ):
        result = await auto_complete_shipping("job-4011-no-start-test", force=True)

    assert result["status"] == "delivered"
    # Delivery is recorded on the shipping envelope, not the issuance status.
    assert mock_job.status == "in_transit"
    assert mock_job.result_json["end_shipping"]["resultCode"] == 200
    assert state.status == "delivered"
    mock_client.register_start_of_shipping.assert_awaited_once()


# ==============================================================================
# 6. Regression tests for the audited auto-complete defects
# ==============================================================================


def _completion_fixtures(job_id: str, *, job_status: str = "in_transit", **state_kwargs):
    """Build the (state, driver, job, session) quartet the completion path needs."""
    state = ShippingState(
        job_id=job_id,
        doc_no="1349757758",
        doc_id="226164459",
        status="in_transit",
        origin_lat=39.22,
        origin_lng=45.03,
        dest_lat=39.11,
        dest_lng=45.06,
        distance_km=25.0,
        **state_kwargs,
    )
    driver = SimpleNamespace(id=1, driver_national_code="4929889601", utcms_password_encrypted="enc-pwd")
    job = SimpleNamespace(
        job_id=job_id,
        driver_id=1,
        status=job_status,
        document_id="226164459",
        result_json={},
        updated_at=None,
        last_error=None,
    )
    session = AsyncMock()
    exec_res = Mock()
    exec_res.first.return_value = job
    session.exec.return_value = exec_res
    session.get.return_value = driver
    return state, driver, job, session


def _completion_patches(state, session, client):
    return (
        patch("app.automation.gps_shipping_manager.load_shipping_state", AsyncMock(return_value=state)),
        patch("app.automation.gps_shipping_manager.save_shipping_state", AsyncMock()),
        patch("app.automation.gps_shipping_manager.get_or_login_client", AsyncMock(return_value=client)),
        patch("app.auth_multitenant.decrypt_driver_password", return_value="plain-pwd"),
        patch("app.core.database.async_session_factory", lambda: FakeAsyncSessionContext(session)),
    )


@pytest.mark.asyncio
async def test_rejected_4011_is_never_recorded_as_a_delivery():
    """FINDING 1 (critical): UTCMS also returns rule 4011 to REFUSE a terminal
    registration ("... تایید نشده است"). The old guard short-circuited on
    ``resultCode != 4011``, so shipping_acknowledged was never asked about the
    one outcome it exists to validate and the refusal was stored as a delivery.
    """
    state, _driver, job, session = _completion_fixtures("job-4011-refused")
    client = AsyncMock(spec=UtcmsMobileClient)
    client.register_end_of_shipping.return_value = {
        "resultCode": 4011,
        "resultMessage": "پایان حمل بر اساس خوداظهاری تایید نشده است",
    }

    a, b, c, d, e = _completion_patches(state, session, client)
    with a, b, c, d, e:
        result = await auto_complete_shipping("job-4011-refused", force=True)

    assert result["status"] == "needs_review"
    assert result["result"]["resultCode"] == 4011
    # The trip is NOT delivered and the delivery witness is NOT written.
    assert state.status != "delivered"
    assert state.status == "unknown"
    assert "end_shipping" not in (job.result_json or {})
    assert "completed_at" not in (job.result_json or {})
    assert job.status != "success"
    # FINDING 11: the refusal is routed through JobStateMachine, not left for an
    # operator to spot the 409.
    assert "routed_to" in result
    assert (job.result_json or {}).get("shipping_completion", {}).get("reason") == "shipping_end_rejected_4011"


@pytest.mark.asyncio
async def test_acknowledged_4011_is_still_delivered():
    """The companion of the test above: a genuine self-declared end still lands."""
    state, _driver, job, session = _completion_fixtures("job-4011-ack")
    client = AsyncMock(spec=UtcmsMobileClient)
    client.register_end_of_shipping.return_value = {
        "resultCode": 4011,
        "resultMessage": "پایان حمل بر اساس خوداظهاری تایید شد",
    }

    a, b, c, d, e = _completion_patches(state, session, client)
    with a, b, c, d, e:
        result = await auto_complete_shipping("job-4011-ack", force=True)

    assert result["status"] == "delivered"
    assert result["result"]["mode"] == "self_declared_auto_complete"
    assert state.status == "delivered"
    assert job.result_json["end_shipping"]["resultCode"] == 4011
    # Never promoted through the issuance status (JobStateMachine owns that).
    assert job.status == "in_transit"


@pytest.mark.asyncio
async def test_transient_terminal_post_failure_stays_retryable_with_backoff():
    """FINDING 2: shipping_response() returns None for 503/502/504/500/408, and
    the old code turned that into a terminal orphan — status "unknown" with NO
    backoff and NO reconciliation routing, which get_due_in_transit_jobs then
    never sweeps again. These are the COMMON failures (_TRANSIENT_HTTP_STATUSES).
    """
    from app.automation.utcms_mobile_client import UtcmsMobileApiError

    state, _driver, job, session = _completion_fixtures("job-transient-503", job_status="success")
    client = AsyncMock(spec=UtcmsMobileClient)
    client.register_end_of_shipping.side_effect = UtcmsMobileApiError("upstream unavailable", status_code=503)

    a, b, c, d, e = _completion_patches(state, session, client)
    with a, b, c, d, e:
        result = await auto_complete_shipping("job-transient-503", force=True)

    assert result["status"] == "unknown"
    assert result["retryable"] is True
    # Retryable: the sweeper must be able to pick this trip up again.
    assert state.status == "in_transit"
    assert state.backoff_until, "a transient completion failure must persist a bounded cooldown"
    assert result["backoff_until"] == state.backoff_until
    # Routed through JobStateMachine so the ambiguity is visible, exactly as the
    # 4011-recovery branch does (success -> needs_review -> reconciling).
    assert result["routed_to"] == "reconciling"
    assert job.result_json["shipping_completion"]["status"] == "unknown"
    # Never silently delivered.
    assert state.status != "delivered"
    assert "end_shipping" not in (job.result_json or {})


@pytest.mark.asyncio
async def test_transient_failure_is_swept_again_once_the_cooldown_expires():
    """The retryable state from FINDING 2 really is re-selected by the sweeper."""
    now = datetime.now(UTC)
    state = ShippingState(
        job_id="job-transient-resweep",
        status="in_transit",
        estimated_end_at=(now - timedelta(minutes=30)).isoformat(),
        backoff_until=(now - timedelta(seconds=1)).isoformat(),
        completion_attempts=1,
    )
    mock_redis = AsyncMock()
    mock_redis.scan.return_value = (0, ["utcms:shipping:job:job-transient-resweep"])
    mock_redis.get.return_value = json.dumps(state.to_dict())
    mock_session = AsyncMock()
    mock_exec_res = Mock()
    mock_exec_res.all.return_value = []
    mock_session.exec.return_value = mock_exec_res

    with (
        patch("app.automation.gps_shipping_manager._get_redis", AsyncMock(return_value=mock_redis)),
        patch("app.core.database.async_session_factory", lambda: FakeAsyncSessionContext(mock_session)),
    ):
        due = await get_due_in_transit_jobs(now_dt=now)

    assert [s.job_id for s in due] == ["job-transient-resweep"]


@pytest.mark.asyncio
async def test_non_transient_terminal_post_failure_fails_closed_but_persists_backoff():
    """The distinction FINDING 2 asks to preserve: an ambiguous non-transient
    failure is NOT auto-retried, but it still persists state and a cooldown so
    the Beat tick cannot hot-loop it.
    """
    state, _driver, job, session = _completion_fixtures("job-ambiguous", job_status="success")
    client = AsyncMock(spec=UtcmsMobileClient)
    client.register_end_of_shipping.side_effect = RuntimeError("unexpected parser explosion")

    a, b, c, d, e = _completion_patches(state, session, client)
    with a, b, c, d, e:
        result = await auto_complete_shipping("job-ambiguous", force=True)

    assert result["status"] == "unknown"
    assert result["retryable"] is False
    assert state.status == "unknown"  # not swept again
    assert state.backoff_until, "even a fail-closed outcome must record a cooldown"
    assert result["routed_to"] == "reconciling"


@pytest.mark.asyncio
async def test_legacy_naive_created_at_does_not_abort_completion():
    """FINDING 3: utc_shipping_timestamp hard-raises on a naive timestamp, so a
    legacy envelope (created_at persisted without a zone) made
    auto_complete_shipping raise ValueError with NO state saved — no backoff
    recorded, the Beat tick repeating every 2 minutes forever, and a
    Session-Vault login (plus a cold CAPTCHA solve) burned on every pass.
    """
    state, _driver, job, session = _completion_fixtures(
        "job-legacy-naive",
        created_at="2026-09-28T15:50:00",  # naive: legacy persisted UTC
    )
    client = AsyncMock(spec=UtcmsMobileClient)
    client.register_end_of_shipping.return_value = {"resultCode": 200, "resultMessage": "ثبت شد"}

    a, b, c, d, e = _completion_patches(state, session, client)
    with a, b, c, d, e:
        result = await auto_complete_shipping("job-legacy-naive", force=True)

    assert result["status"] == "delivered"
    gps_list = client.register_end_of_shipping.await_args.kwargs["gps_list"]
    # The naive value is assumed UTC and wired in the strict UTCMS format.
    assert gps_list[0]["Date"] == "2026-09-28T15:50:00.000Z"
    assert gps_list[0]["DateTime"] == gps_list[0]["Date"]
    assert gps_list[-1]["Date"].endswith(".000Z")


@pytest.mark.asyncio
async def test_invalid_trace_records_backoff_instead_of_escaping_unpersisted():
    """FINDING 3 (second half): a trace the contract refuses must not escape
    un-persisted; it parks behind a cooldown so the sweep stops hot-looping.
    """
    state, _driver, job, session = _completion_fixtures("job-bad-trace")
    # A destination timestamp that precedes the origin breaks chronology.
    state.created_at = "2030-01-01T00:00:00+00:00"
    client = AsyncMock(spec=UtcmsMobileClient)

    a, b, c, d, e = _completion_patches(state, session, client)
    with a, b, c, d, e:
        result = await auto_complete_shipping("job-bad-trace", force=True)

    assert result["status"] == "needs_review"
    assert result["reason"] == "invalid_shipping_trace"
    assert state.backoff_until, "an invalid trace must persist a cooldown"
    assert state.status == "unknown"
    # The terminal POST was never attempted, so nothing is ambiguous upstream.
    client.register_end_of_shipping.assert_not_awaited()
