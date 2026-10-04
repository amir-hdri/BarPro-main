"""Regression tests for batch G fixes in app/automation/gps_shipping_manager.py.

- A2: fail-open 4011 recovery. The business-rule code is extracted structurally
  (never by substring of free text), and a failed 4011-recovery routes the job
  through JobStateMachine into unknown -> reconciling — never success.
- C3: driver session-vault Redis keys are scoped by tenant (client_id).
- F1: the per-driver auth-lock cache is loop-aware and bounded.
- F4: corrupt backoff/ETA values are logged with context, never silently swallowed.
- F5: a Redis per-trip claim lock stops two overlapping Beat runs from
  double-calling RegisterEndOfShipping.
"""

import asyncio
import json
import logging
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.automation import gps_shipping_manager as manager
from app.automation.gps_shipping_manager import ShippingState
from app.automation.utcms_mobile_client import UtcmsMobileApiError
from app.models_multitenant import WaybillJob

# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------


class FakeRedis:
    """Minimal async Redis with SET NX and compare-and-delete eval semantics."""

    def __init__(self):
        self.values: dict = {}
        self.ttls: dict = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.values:
            return None
        self.values[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    async def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)
            self.ttls.pop(key, None)

    async def scan(self, cursor=0, match=None, count=100):
        prefix = match[:-1] if match and match.endswith("*") else (match or "")
        keys = [k for k in self.values if str(k).startswith(prefix)]
        return 0, keys

    async def eval(self, _script, _count, key, token):
        if self.values.get(key) == token:
            self.values.pop(key, None)
            self.ttls.pop(key, None)
            return 1
        return 0


class FakeAsyncSessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


def make_fake_session(job, driver=None):
    session = AsyncMock()
    exec_res = Mock()
    exec_res.first.return_value = job
    exec_res.all.return_value = []
    session.exec.return_value = exec_res
    session.get.return_value = driver
    return session


@pytest.fixture
def isolated_auth_locks():
    """Snapshot/restore the module-global auth-lock cache around a test."""
    saved = dict(manager._LOCAL_AUTH_LOCKS)
    manager._LOCAL_AUTH_LOCKS.clear()
    try:
        yield
    finally:
        manager._LOCAL_AUTH_LOCKS.clear()
        manager._LOCAL_AUTH_LOCKS.update(saved)


# --------------------------------------------------------------------------
# A2: structured rule-code extraction (no free-text substring matching)
# --------------------------------------------------------------------------


def test_extract_utcms_rule_code_prefers_structured_result_code():
    err = UtcmsMobileApiError(
        "UTCMS RegisterEndOfShipping business rejection: x (code: 4011)",
        result_code=4011,
    )
    assert manager._extract_utcms_rule_code(err) == "4011"


def test_extract_utcms_rule_code_rejects_free_text_substring_match():
    # "4011" appears inside a doc number in free text, but the exception
    # carries no structured business-rule code -> must NOT count as 4011.
    err = UtcmsMobileApiError("request for doc 40110 failed: timeout", result_code=None)
    assert manager._extract_utcms_rule_code(err) is None


def test_extract_utcms_rule_code_falls_back_to_envelope_pattern():
    err = RuntimeError("UTCMS op business rejection: some message (code: 4011)")
    assert manager._extract_utcms_rule_code(err) == "4011"


def test_extract_utcms_rule_code_returns_none_without_any_code():
    assert manager._extract_utcms_rule_code(RuntimeError("connection reset by peer")) is None


# --------------------------------------------------------------------------
# A2: failed 4011-recovery -> unknown/reconciling via JobStateMachine, never success
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_4011_recovery_never_marks_success():
    """A recovery failure (register_start_of_shipping raises) must NOT mark the
    trip delivered/success. The ShippingState goes to "unknown" and the
    WaybillJob is routed through JobStateMachine into reconciling with the
    machine's transition validation — mutation_status/reconciled_at are NOT
    fabricated (reconciliation has not completed).
    """
    state = ShippingState(
        job_id="job-a2-recovery",
        doc_no="1349757758",
        doc_id="226164459",
        status="in_transit",
        dest_lat=39.11,
        dest_lng=45.06,
        origin_lat=39.22,
        origin_lng=45.03,
    )
    job = WaybillJob(
        job_id="job-a2-recovery",
        idempotency_key="idem-a2-recovery",
        client_id=7,
        driver_id=1,
        document_id="226164459",
        payload_json={},
        status="success",  # waybill issuance already succeeded
        result_json={"tracking_code": "1349757758"},
        mutation_status="dispatched",
    )
    driver = SimpleNamespace(id=1, client_id=7, driver_national_code="4929889601", utcms_password_encrypted="enc")

    mock_client = AsyncMock()
    # UTCMS says "start of shipping was never registered" (4011 variant) ...
    mock_client.register_end_of_shipping.return_value = {
        "resultCode": 4011,
        "resultMessage": "شروع حمل ثبت نشده است",
    }
    # ... and the recovery attempt itself fails (auth/network/portal error).
    mock_client.register_start_of_shipping.side_effect = RuntimeError("recovery boom: connection refused")

    redis = FakeRedis()
    session = make_fake_session(job, driver)

    with (
        patch("app.core.config.utcms_config.ALLOW_LIVE_SUBMIT", True),
        patch("app.automation.gps_shipping_manager.load_shipping_state", AsyncMock(return_value=state)),
        patch("app.automation.gps_shipping_manager.save_shipping_state", AsyncMock()),
        patch("app.automation.gps_shipping_manager._get_redis", AsyncMock(return_value=redis)),
        patch("app.automation.gps_shipping_manager.get_or_login_client", AsyncMock(return_value=mock_client)),
        patch("app.auth_multitenant.decrypt_driver_password", return_value="plain-pwd"),
        patch("app.core.database.async_session_factory", lambda: FakeAsyncSessionContext(session)),
    ):
        result = await manager.auto_complete_shipping("job-a2-recovery", force=True)

    # 1. Never declared delivered/success.
    assert result["status"] == "unknown"
    assert result["reason"] == "completion_recovery_failed"
    assert state.status == "unknown"
    assert state.status != "delivered"
    assert state.backoff_until  # bounded retry, not a dead end

    # 2. Job routed through the machine: success -> needs_review -> reconciling.
    assert job.status == "reconciling"
    assert result["routed_to"] == "reconciling"

    # 3. Fail-closed evidence semantics: the machine's SUCCESS gate inputs are
    #    NOT fabricated — reconciliation has not actually completed.
    assert job.mutation_status == "dispatched"
    assert job.reconciled_at is None
    assert job.result_json["shipping_completion"]["reason"] == "completion_recovery_failed"


@pytest.mark.asyncio
async def test_structured_4011_exception_still_self_declares():
    """An exception carrying a STRUCTURED result_code=4011 is still the genuine
    self-declared-end business rule -> delivered. (The fix only stops free-text
    substring matches from counting as rule 4011.)
    """
    state = ShippingState(
        job_id="job-a2-4011exc",
        doc_no="1349757758",
        doc_id="226164459",
        status="in_transit",
        dest_lat=39.11,
        dest_lng=45.06,
        origin_lat=39.22,
        origin_lng=45.03,
    )
    job = SimpleNamespace(
        job_id="job-a2-4011exc",
        driver_id=1,
        client_id=7,
        document_id="226164459",
        status="in_transit",
        result_json={"tracking_code": "1349757758"},
        updated_at=None,
    )
    driver = SimpleNamespace(id=1, client_id=7, driver_national_code="4929889601", utcms_password_encrypted="enc")

    mock_client = AsyncMock()
    mock_client.register_end_of_shipping.side_effect = UtcmsMobileApiError(
        "UTCMS RegisterEndOfShipping business rejection: پایان حمل بر اساس خوداظهاری (code: 4011)",
        result_code=4011,
    )

    redis = FakeRedis()
    session = make_fake_session(job, driver)

    with (
        patch("app.core.config.utcms_config.ALLOW_LIVE_SUBMIT", True),
        patch("app.automation.gps_shipping_manager.load_shipping_state", AsyncMock(return_value=state)),
        patch("app.automation.gps_shipping_manager.save_shipping_state", AsyncMock()),
        patch("app.automation.gps_shipping_manager._get_redis", AsyncMock(return_value=redis)),
        patch("app.automation.gps_shipping_manager.get_or_login_client", AsyncMock(return_value=mock_client)),
        patch("app.auth_multitenant.decrypt_driver_password", return_value="plain-pwd"),
        patch("app.core.database.async_session_factory", lambda: FakeAsyncSessionContext(session)),
    ):
        result = await manager.auto_complete_shipping("job-a2-4011exc", force=True)

    assert result["status"] == "delivered"
    assert result["result"]["resultCode"] == 4011
    assert result["result"]["mode"] == "self_declared_auto_complete"
    assert state.status == "delivered"


# --------------------------------------------------------------------------
# C3: tenant-scoped driver vault keys
# --------------------------------------------------------------------------


def test_scoped_driver_key_format():
    assert manager._scoped_driver_key("token", 7, "001") == "utcms:driver:token:7:001"
    assert manager._scoped_driver_key("refresh", 7, "001") == "utcms:driver:refresh:7:001"
    assert manager._scoped_driver_key("auth-lock", 7, "001") == "utcms:driver:auth-lock:7:001"
    # Legacy shape only when no tenant is available.
    assert manager._scoped_driver_key("token", None, "001") == "utcms:driver:token:001"


@pytest.mark.asyncio
async def test_two_tenants_sharing_national_code_get_distinct_keys():
    redis = FakeRedis()
    with patch("app.automation.gps_shipping_manager._get_redis", AsyncMock(return_value=redis)):
        await manager.cache_token("001", "tok-tenant-7", client_id=7)
        await manager.cache_token("001", "tok-tenant-9", client_id=9)

        assert await manager.get_cached_token("001", client_id=7) == "tok-tenant-7"
        assert await manager.get_cached_token("001", client_id=9) == "tok-tenant-9"

    assert "utcms:driver:token:7:001" in redis.values
    assert "utcms:driver:token:9:001" in redis.values


@pytest.mark.asyncio
async def test_scoped_lookup_never_falls_back_to_unscoped_key():
    redis = FakeRedis()
    redis.values["utcms:driver:token:001"] = "tok-legacy-unscoped"
    with patch("app.automation.gps_shipping_manager._get_redis", AsyncMock(return_value=redis)):
        # A scoped lookup must not read another tenant's (or legacy) session.
        assert await manager.get_cached_token("001", client_id=7) is None
        # And the unscoped caller shape keeps working for callers without a tenant.
        assert await manager.get_cached_token("001") == "tok-legacy-unscoped"


@pytest.mark.asyncio
async def test_invalidate_cached_session_is_tenant_scoped():
    redis = FakeRedis()
    with patch("app.automation.gps_shipping_manager._get_redis", AsyncMock(return_value=redis)):
        await manager.cache_token("001", "tok-7", client_id=7)
        await manager.cache_token("001", "tok-9", client_id=9)
        await manager.invalidate_cached_session("001", client_id=7)

        assert await manager.get_cached_token("001", client_id=7) is None
        assert await manager.get_cached_token("001", client_id=9) == "tok-9"


# --------------------------------------------------------------------------
# F1: loop-aware, bounded auth-lock cache
# --------------------------------------------------------------------------


def test_auth_lock_cache_is_bounded(isolated_auth_locks):
    async def fill():
        for i in range(manager._AUTH_LOCK_ENTRIES_MAX + 100):
            manager._get_auth_lock(f"9{i:09d}")
        return len(manager._LOCAL_AUTH_LOCKS)

    count = asyncio.run(fill())
    assert count <= manager._AUTH_LOCK_ENTRIES_MAX


def test_auth_lock_cache_evicts_oldest_first(isolated_auth_locks):
    async def fill():
        first_lock = manager._get_auth_lock("evict-first-001")
        for i in range(manager._AUTH_LOCK_ENTRIES_MAX):
            manager._get_auth_lock(f"evict-fill-{i:04d}")
        return first_lock, manager._get_auth_lock("evict-first-001")

    first_lock, reacquired = asyncio.run(fill())
    # The oldest entry was evicted once the bound was hit, so a fresh lock
    # object is created for the same national code.
    assert reacquired is not first_lock
    assert len(manager._LOCAL_AUTH_LOCKS) <= manager._AUTH_LOCK_ENTRIES_MAX


def test_auth_locks_are_loop_aware(isolated_auth_locks):
    """A lock awaited on one event loop is never shared with another loop:
    each loop gets its own lock object (the old module-global dict shared one
    asyncio.Lock across loops -> RuntimeError on await)."""
    results: dict = {}

    def worker():
        loop = asyncio.new_event_loop()
        try:

            async def get():
                lock = manager._get_auth_lock("loop-case-001")
                async with lock:
                    return lock

            results["other"] = loop.run_until_complete(get())
        finally:
            loop.close()

    async def main_side():
        lock = manager._get_auth_lock("loop-case-001")
        async with lock:
            return lock

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    main_lock = asyncio.run(main_side())

    assert results["other"] is not main_lock
    # Both locks were awaited on their own loop without RuntimeError.


def test_auth_lock_is_tenant_scoped(isolated_auth_locks):
    async def get_both():
        return (
            manager._get_auth_lock("tenant-case-001", "7"),
            manager._get_auth_lock("tenant-case-001", "9"),
        )

    lock7, lock9 = asyncio.run(get_both())
    assert lock7 is not lock9


# --------------------------------------------------------------------------
# F4: corrupt values are logged, never silently swallowed
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_corrupt_backoff_value_is_logged_and_job_stays_eligible(caplog):
    state = ShippingState(
        job_id="job-f4-backoff",
        status="in_transit",
        # A real (past) ETA so the trip is otherwise due: a corrupt COOLDOWN
        # must not dead-end it, while a MISSING ETA fails closed separately
        # (test_missing_estimated_end_at_is_not_due).
        estimated_end_at="2020-01-01T00:00:00+00:00",
        backoff_until="not-a-datetime",
    )
    redis = FakeRedis()
    redis.values["utcms:shipping:job:job-f4-backoff"] = json.dumps(state.to_dict())
    session = make_fake_session(None)

    with (
        patch("app.automation.gps_shipping_manager._get_redis", AsyncMock(return_value=redis)),
        patch("app.core.database.async_session_factory", lambda: FakeAsyncSessionContext(session)),
        caplog.at_level(logging.WARNING, logger="app.automation.gps_shipping_manager"),
    ):
        due = await manager.get_due_in_transit_jobs()

    assert any(s.job_id == "job-f4-backoff" for s in due)  # still eligible, as before
    assert "shipping_backoff_parse_failed" in caplog.text
    assert "job-f4-backoff" in caplog.text


@pytest.mark.asyncio
async def test_corrupt_shipping_state_blob_is_logged(caplog):
    redis = FakeRedis()
    redis.values["utcms:shipping:job:job-f4-blob"] = "{not valid json"
    session = make_fake_session(None)

    with (
        patch("app.automation.gps_shipping_manager._get_redis", AsyncMock(return_value=redis)),
        patch("app.core.database.async_session_factory", lambda: FakeAsyncSessionContext(session)),
        caplog.at_level(logging.WARNING, logger="app.automation.gps_shipping_manager"),
    ):
        due = await manager.get_due_in_transit_jobs()

    assert due == []
    assert "shipping_state_decode_failed" in caplog.text


# --------------------------------------------------------------------------
# F5: per-trip completion claim lock
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_completion_claim_second_claimant_skips():
    """Two overlapping auto_complete_shipping calls for the same trip: exactly
    one proceeds, the second skips with completion_claim_held."""
    state = ShippingState(job_id="job-f5-claim", status="in_transit")
    redis = FakeRedis()
    entered: list[str] = []

    async def slow_inner(job_id, force=False):
        entered.append(job_id)
        await asyncio.sleep(0.2)
        return {"status": "delivered", "result": {}}

    with (
        patch("app.automation.gps_shipping_manager.load_shipping_state", AsyncMock(return_value=state)),
        patch("app.automation.gps_shipping_manager._get_redis", AsyncMock(return_value=redis)),
        patch.object(manager, "_auto_complete_shipping_inner", side_effect=slow_inner),
    ):
        res1, res2 = await asyncio.gather(
            manager.auto_complete_shipping("job-f5-claim"),
            manager.auto_complete_shipping("job-f5-claim"),
        )

    statuses = sorted(r["status"] for r in (res1, res2))
    assert statuses == ["delivered", "skipped"]
    skipped = next(r for r in (res1, res2) if r["status"] == "skipped")
    assert skipped["reason"] == "completion_claim_held"
    assert entered == ["job-f5-claim"]  # inner ran exactly once


@pytest.mark.asyncio
async def test_completion_claim_is_released_after_completion():
    """After a completion finishes, the claim is released so a later Beat run
    can proceed (TTL alone would also bound a crashed claim)."""
    state = ShippingState(job_id="job-f5-release", status="in_transit")
    redis = FakeRedis()

    async def quick_inner(job_id, force=False):
        return {"status": "delivered", "result": {}}

    with (
        patch("app.automation.gps_shipping_manager.load_shipping_state", AsyncMock(return_value=state)),
        patch("app.automation.gps_shipping_manager._get_redis", AsyncMock(return_value=redis)),
        patch.object(manager, "_auto_complete_shipping_inner", side_effect=quick_inner),
    ):
        first = await manager.auto_complete_shipping("job-f5-release")
        assert first["status"] == "delivered"
        # Claim released: a subsequent run is not blocked.
        second = await manager.auto_complete_shipping("job-f5-release")
        assert second["status"] == "delivered"
    assert manager.COMPLETION_CLAIM_KEY.format(job_id="job-f5-release") not in redis.values


@pytest.mark.asyncio
async def test_completion_claim_manually_held_blocks_completion():
    """A claim held by another worker/run (present in Redis) blocks completion."""
    state = ShippingState(job_id="job-f5-held", status="in_transit")
    redis = FakeRedis()
    redis.values[manager.COMPLETION_CLAIM_KEY.format(job_id="job-f5-held")] = "other-worker-token"
    inner_calls: list[str] = []

    async def counting_inner(job_id, force=False):
        inner_calls.append(job_id)
        return {"status": "delivered", "result": {}}

    with (
        patch("app.automation.gps_shipping_manager.load_shipping_state", AsyncMock(return_value=state)),
        patch("app.automation.gps_shipping_manager._get_redis", AsyncMock(return_value=redis)),
        patch.object(manager, "_auto_complete_shipping_inner", side_effect=counting_inner),
    ):
        result = await manager.auto_complete_shipping("job-f5-held")

    assert result == {"status": "skipped", "reason": "completion_claim_held", "job_id": "job-f5-held"}
    assert inner_calls == []


# --------------------------------------------------------------------------
# FINDING 4: the durable "finishing"/"starting" fence has a reaper
# --------------------------------------------------------------------------


def _fenced_state(job_id: str, *, status: str, age_seconds: int, now):
    from datetime import timedelta

    return ShippingState(
        job_id=job_id,
        status=status,
        estimated_end_at=(now - timedelta(hours=1)).isoformat(),
        last_attempt_at=(now - timedelta(seconds=age_seconds)).isoformat(),
        completion_attempts=1,
    )


@pytest.mark.asyncio
async def test_abandoned_finishing_fence_is_reclaimed_and_swept_again():
    """A worker OOM-killed between the durable fence and the response left Redis
    on "finishing" while the DB mirror still said "in_transit". The claim
    expired but nothing reset the status, and the Redis entry shadowed the DB
    fallback for its 7-day TTL: the trip was never completed and never surfaced
    as failed.
    """
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    state = _fenced_state(
        "job-fence-stuck", status="finishing", age_seconds=manager.COMPLETION_CLAIM_TTL_SECONDS + 60, now=now
    )
    redis = FakeRedis()
    redis.values[f"utcms:shipping:job:{state.job_id}"] = json.dumps(state.to_dict())
    session = make_fake_session(None)

    with (
        patch("app.automation.gps_shipping_manager._get_redis", AsyncMock(return_value=redis)),
        patch("app.automation.gps_shipping_manager.save_shipping_state", AsyncMock()) as mock_save,
        patch("app.core.database.async_session_factory", lambda: FakeAsyncSessionContext(session)),
    ):
        due = await manager.get_due_in_transit_jobs(now_dt=now)

    assert [s.job_id for s in due] == ["job-fence-stuck"]
    assert due[0].status == "in_transit"
    mock_save.assert_awaited()  # the reclaim is durable, not in-memory only
    assert "reclaimed abandoned finishing fence" in due[0].last_error_message


@pytest.mark.asyncio
async def test_starting_fence_is_reclaimed_too():
    """``/shipping/start`` writes the same kind of fence before its first POST."""
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    state = _fenced_state(
        "job-fence-start", status="starting", age_seconds=manager.COMPLETION_CLAIM_TTL_SECONDS + 5, now=now
    )
    redis = FakeRedis()
    redis.values[f"utcms:shipping:job:{state.job_id}"] = json.dumps(state.to_dict())
    session = make_fake_session(None)

    with (
        patch("app.automation.gps_shipping_manager._get_redis", AsyncMock(return_value=redis)),
        patch("app.automation.gps_shipping_manager.save_shipping_state", AsyncMock()),
        patch("app.core.database.async_session_factory", lambda: FakeAsyncSessionContext(session)),
    ):
        due = await manager.get_due_in_transit_jobs(now_dt=now)

    assert [s.job_id for s in due] == ["job-fence-start"]


@pytest.mark.asyncio
async def test_live_fence_is_never_stolen_from_the_worker_holding_the_claim():
    """The reaper must not race a worker that is mid-mutation: a held claim (of
    EITHER key generation) means the fence is live, however old it looks.
    """
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    for template in (manager.COMPLETION_CLAIM_KEY, manager.LEGACY_COMPLETION_CLAIM_KEY):
        state = _fenced_state("job-fence-live", status="finishing", age_seconds=99_999, now=now)
        redis = FakeRedis()
        redis.values[f"utcms:shipping:job:{state.job_id}"] = json.dumps(state.to_dict())
        redis.values[template.format(job_id=state.job_id)] = "worker-token"
        session = make_fake_session(None)

        with (
            patch("app.automation.gps_shipping_manager._get_redis", AsyncMock(return_value=redis)),
            patch("app.automation.gps_shipping_manager.save_shipping_state", AsyncMock()) as mock_save,
            patch("app.core.database.async_session_factory", lambda s=session: FakeAsyncSessionContext(s)),
        ):
            due = await manager.get_due_in_transit_jobs(now_dt=now)

        assert due == [], f"a fence held under {template} must not be reclaimed"
        mock_save.assert_not_awaited()


@pytest.mark.asyncio
async def test_fresh_fence_within_the_claim_ttl_is_left_alone():
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    state = _fenced_state("job-fence-fresh", status="finishing", age_seconds=30, now=now)
    redis = FakeRedis()
    redis.values[f"utcms:shipping:job:{state.job_id}"] = json.dumps(state.to_dict())
    session = make_fake_session(None)

    with (
        patch("app.automation.gps_shipping_manager._get_redis", AsyncMock(return_value=redis)),
        patch("app.automation.gps_shipping_manager.save_shipping_state", AsyncMock()) as mock_save,
        patch("app.core.database.async_session_factory", lambda: FakeAsyncSessionContext(session)),
    ):
        due = await manager.get_due_in_transit_jobs(now_dt=now)

    assert due == []
    mock_save.assert_not_awaited()


@pytest.mark.asyncio
async def test_redis_decision_still_wins_over_a_stale_db_mirror():
    """Guard the invariant the reclaim deliberately does NOT trade away: Redis is
    authoritative and the DB envelope is only a fallback for Redis loss, so a
    fail-closed "unknown" (or a fresh "delivered") must never be resurrected by
    a stale DB mirror that still says "in_transit".
    """
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    past = (now - timedelta(hours=2)).isoformat()
    redis = FakeRedis()
    for job_id, status in (("job-redis-unknown", "unknown"), ("job-redis-delivered", "delivered")):
        redis.values[f"utcms:shipping:job:{job_id}"] = json.dumps(
            ShippingState(job_id=job_id, status=status, estimated_end_at=past).to_dict()
        )
    stale_jobs = [
        SimpleNamespace(
            job_id=job_id,
            result_json={
                "_shipping_state": ShippingState(job_id=job_id, status="in_transit", estimated_end_at=past).to_dict()
            },
        )
        for job_id in ("job-redis-unknown", "job-redis-delivered")
    ]
    session = AsyncMock()
    exec_res = Mock()
    exec_res.all.return_value = stale_jobs
    exec_res.first.return_value = None
    session.exec.return_value = exec_res

    with (
        patch("app.automation.gps_shipping_manager._get_redis", AsyncMock(return_value=redis)),
        patch("app.core.database.async_session_factory", lambda: FakeAsyncSessionContext(session)),
    ):
        due = await manager.get_due_in_transit_jobs(now_dt=now)

    assert due == []


@pytest.mark.asyncio
async def test_missing_estimated_end_at_is_not_due():
    """FINDING 10: the arrival gate in front of the terminal POST was deleted, so
    the ETA is the only client-side trigger left. A blank ETA used to mean "no
    wait", making such an envelope due IMMEDIATELY with nothing left to stop it.
    """
    state = ShippingState(job_id="job-no-eta-failclosed", status="in_transit", estimated_end_at="")
    redis = FakeRedis()
    redis.values[f"utcms:shipping:job:{state.job_id}"] = json.dumps(state.to_dict())
    session = make_fake_session(None)

    with (
        patch("app.automation.gps_shipping_manager._get_redis", AsyncMock(return_value=redis)),
        patch("app.core.database.async_session_factory", lambda: FakeAsyncSessionContext(session)),
    ):
        due = await manager.get_due_in_transit_jobs()

    assert due == []
    wait = manager.shipping_wait_reason(state)
    assert wait is not None
    assert wait["reason"] == "missing_estimated_end_at"


# --------------------------------------------------------------------------
# FINDING 7: rolling-deploy claim-key compatibility
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_covers_both_key_generations_during_a_rolling_deploy():
    """In Model B, Central is updated while Workers 2/3 still run the previous
    image, which claims the OLD key. Without claiming both, Central's new key
    is free and BOTH generations POST RegisterEndOfShipping for one trip.
    """
    redis = FakeRedis()
    new_key = manager.COMPLETION_CLAIM_KEY.format(job_id="job-rolling")
    legacy_key = manager.LEGACY_COMPLETION_CLAIM_KEY.format(job_id="job-rolling")
    assert new_key != legacy_key

    with patch("app.automation.gps_shipping_manager._get_redis", AsyncMock(return_value=redis)):
        token = await manager._acquire_completion_claim("job-rolling")
        assert token
        assert redis.values[new_key] == token
        assert redis.values[legacy_key] == token
        # A concurrent claimant of either generation is refused.
        assert await manager._acquire_completion_claim("job-rolling") is None
        await manager._release_completion_claim("job-rolling", token)
        assert new_key not in redis.values
        assert legacy_key not in redis.values


@pytest.mark.asyncio
async def test_old_image_holding_only_the_legacy_key_blocks_the_new_claim():
    """The exact rolling-deploy hazard, and the half-claim must be rolled back
    so the previous generation is not starved by an orphaned lock either.
    """
    redis = FakeRedis()
    legacy_key = manager.LEGACY_COMPLETION_CLAIM_KEY.format(job_id="job-old-worker")
    new_key = manager.COMPLETION_CLAIM_KEY.format(job_id="job-old-worker")
    redis.values[legacy_key] = "worker-2-old-image-token"

    with patch("app.automation.gps_shipping_manager._get_redis", AsyncMock(return_value=redis)):
        assert await manager._acquire_completion_claim("job-old-worker") is None

    assert redis.values[legacy_key] == "worker-2-old-image-token"  # untouched
    assert new_key not in redis.values, "the partially acquired new key must be rolled back"


def test_claim_ttl_comment_matches_the_constant():
    """FINDING 12: the comment claimed a 10-minute TTL for a 900-second value."""
    import inspect

    source = inspect.getsource(manager)
    assert manager.COMPLETION_CLAIM_TTL_SECONDS == 900
    assert "a 15-minute claim TTL" in source
    assert "a 10-minute claim TTL" not in source
