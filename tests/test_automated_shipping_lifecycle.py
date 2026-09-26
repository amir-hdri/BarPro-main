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
    # Job 4: In transit, empty ETA -> DUE (failsafe)
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
    assert "job-no-eta" in due_job_ids
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
    """Verify auto_complete_shipping handles UTCMS 4011 exception gracefully, marks delivered, and updates DB job."""
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
        result_json={"tracking_code": "1349757758"},
        updated_at=None,
    )

    mock_client = AsyncMock(spec=UtcmsMobileClient)
    # Simulate UTCMS 4011 error raised as exception
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

    # 1. auto_complete_shipping return value
    assert result["status"] == "delivered"
    assert result["result"]["resultCode"] == 4011
    assert result["result"]["mode"] == "self_declared_auto_complete"

    # 2. Shipping state marked delivered
    assert state.status == "delivered"

    # 3. Database WaybillJob updated
    assert mock_job.status == "success"
    assert "end_shipping" in mock_job.result_json
    assert mock_job.result_json["end_shipping"]["resultCode"] == 4011
    assert mock_job.result_json["end_shipping"]["mode"] == "self_declared_auto_complete"
    assert "completed_at" in mock_job.result_json
    mock_session.commit.assert_awaited()


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
    assert mock_job.status == "success"
    assert mock_job.result_json["end_shipping"]["resultCode"] == 4011
    assert state.status == "delivered"


@pytest.mark.asyncio
async def test_auto_complete_shipping_raises_on_non_4011_exception():
    """Verify auto_complete_shipping re-raises genuine errors (e.g. 500 server error) and does not mark delivered."""
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
        with pytest.raises(RuntimeError, match="Fatal network error 500"):
            await auto_complete_shipping("job-err-test", force=True)

    assert state.status == "in_transit"
