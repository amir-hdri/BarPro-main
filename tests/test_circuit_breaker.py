import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.circuit_breaker import (
    WORKER_HEARTBEAT_STALE_SECONDS,
    NoHealthyWorkerError,
    _index_unavailable_from_rows,
    check_and_report_failure,
    get_next_ip_index_sync,
    get_routed_queue,
)


@pytest.fixture(autouse=True)
def three_ip_indices():
    with patch.dict(os.environ, {"AVAILABLE_IP_INDICES": "1,2,3"}):
        yield


@pytest.fixture(autouse=True)
def clean_redis_cache():
    import app.core.circuit_breaker

    app.core.circuit_breaker._redis_sync_client = None
    yield
    app.core.circuit_breaker._redis_sync_client = None


@pytest.fixture(autouse=True)
def clean_registry_caches():
    """Reset the worker-registry snapshot caches between tests."""
    import app.core.circuit_breaker

    app.core.circuit_breaker._worker_registry_snapshot = None
    app.core.circuit_breaker._worker_registry_snapshot_sync = None
    app.core.circuit_breaker._ip_index_cache = None
    app.core.circuit_breaker._ip_index_cache_expires = 0.0
    yield
    app.core.circuit_breaker._worker_registry_snapshot = None
    app.core.circuit_breaker._worker_registry_snapshot_sync = None
    app.core.circuit_breaker._ip_index_cache = None
    app.core.circuit_breaker._ip_index_cache_expires = 0.0


@pytest.fixture(autouse=True)
def mock_registry_healthy():
    """By default the worker registry filter reports NO dead workers and NO
    claimed indices (empty known set), so the existing tests keep exercising
    the pure Redis logic (empty known => keep the whole available pool)."""
    with (
        patch("app.core.circuit_breaker._get_unavailable_ip_indices_sync", return_value=set()),
        patch("app.core.circuit_breaker._get_unavailable_ip_indices", new_callable=AsyncMock, return_value=set()),
        patch("app.core.circuit_breaker._get_known_ip_indices_sync", return_value=set()),
        patch("app.core.circuit_breaker._get_known_ip_indices", new_callable=AsyncMock, return_value=set()),
    ):
        yield


@pytest.fixture
def mock_redis():
    with patch("redis.Redis.from_url") as mock_from_url:
        mock_client = MagicMock()
        mock_from_url.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_redis_manager():
    with patch("app.core.redis_client.redis_manager.get", new_callable=AsyncMock) as mock_get:
        mock_client = AsyncMock()
        mock_get.return_value = mock_client
        yield mock_client


def test_get_next_ip_index_sync_all_healthy(mock_redis):
    # Mock Redis so that no blocked keys exist
    mock_redis.exists.return_value = False
    mock_redis.incr.return_value = 1  # 1 % 3 = 1 -> selected_ip = healthy_ips[1]

    # healthy_ips = [1, 2, 3]
    # counter = 1 % 3 = 1 -> selected_ip = 2
    ip = get_next_ip_index_sync()
    assert ip == 2

    # Assert exists called for all 3 IPs
    assert mock_redis.exists.call_count == 3
    mock_redis.exists.assert_any_call("utcms:circuit_breaker:blocked:1")
    mock_redis.exists.assert_any_call("utcms:circuit_breaker:blocked:2")
    mock_redis.exists.assert_any_call("utcms:circuit_breaker:blocked:3")


def test_get_next_ip_index_sync_with_blocked(mock_redis):
    # Mock Redis: IP 2 is blocked, others are healthy
    def exists_side_effect(key):
        return key == "utcms:circuit_breaker:blocked:2"

    mock_redis.exists.side_effect = exists_side_effect
    mock_redis.incr.return_value = 0  # 0 % 2 = 0 -> selected_ip = healthy_ips[0] (which is 1)

    # healthy_ips = [1, 3]
    # counter = 0 % 2 = 0 -> selected_ip = 1
    ip = get_next_ip_index_sync()
    assert ip == 1


def test_get_next_ip_index_sync_all_blocked_raises(mock_redis):
    # Mock Redis: All IPs are blocked; do not hammer a known-bad fleet.
    mock_redis.exists.return_value = True
    with pytest.raises(NoHealthyWorkerError):
        get_next_ip_index_sync()


def test_get_routed_queue_standard():
    with patch("app.core.circuit_breaker.get_next_ip_index_sync", return_value=2):
        routed = get_routed_queue("waybill_tasks")
        assert routed == "waybill_tasks_2"


def test_get_routed_queue_system_bypass():
    # system queues (rpa_scheduler) should not be routed/suffixed
    routed = get_routed_queue("rpa_scheduler")
    assert routed == "rpa_scheduler"


@pytest.mark.asyncio
async def test_check_and_report_failure_no_match(mock_redis_manager):
    # Try with an error message that does not indicate IP block/timeout
    await check_and_report_failure("Invalid driver national code")

    # Redis set should not have been called
    mock_redis_manager.set.assert_not_called()


@pytest.mark.asyncio
async def test_check_and_report_failure_with_match(mock_redis_manager):
    # Set worker index
    os.environ["WORKER_IP_INDEX"] = "3"

    # Try with a matching error message
    await check_and_report_failure("Connection timed out to gateway server")

    # Redis set should be called for IP index 3
    mock_redis_manager.set.assert_called_once_with("utcms:circuit_breaker:blocked:3", "1", ex=1800)

    # Clean up environment
    os.environ.pop("WORKER_IP_INDEX", None)


def test_get_next_ip_index_sync_custom_indices(mock_redis):
    # Set only 2 IPs in environment
    os.environ["AVAILABLE_IP_INDICES"] = "1,2"
    mock_redis.exists.return_value = False
    mock_redis.incr.return_value = 1  # 1 % 2 = 1 -> selected_ip = healthy_ips[1] (which is 2)

    try:
        ip = get_next_ip_index_sync()
        assert ip == 2

        # Check that only indices 1 and 2 were checked
        assert mock_redis.exists.call_count == 2
        mock_redis.exists.assert_any_call("utcms:circuit_breaker:blocked:1")
        mock_redis.exists.assert_any_call("utcms:circuit_breaker:blocked:2")

        # Ensure index 3 was not checked
        with pytest.raises(AssertionError):
            mock_redis.exists.assert_any_call("utcms:circuit_breaker:blocked:3")
    finally:
        os.environ.pop("AVAILABLE_IP_INDICES", None)


# ---------------------------------------------------------------------------
# Worker-registry liveness filter (P1 fix: routing must not select queues
# whose worker is dead)
# ---------------------------------------------------------------------------


def test_get_next_ip_index_sync_excludes_dead_worker_index(mock_redis):
    """A worker that is offline/stale must take its IP index out of the pool."""
    mock_redis.exists.return_value = False  # no Redis blocks
    mock_redis.incr.return_value = 1  # 1 % 2 = 1 -> healthy_ips[1]

    with patch("app.core.circuit_breaker._get_unavailable_ip_indices_sync", return_value={2}):
        # healthy_ips = [1, 3] -> counter 1 % 2 = 1 -> ip 3
        ip = get_next_ip_index_sync()
    assert ip == 3

    # The dead index must never be checked as a candidate... but note Redis
    # `exists` is still called for it only via the fallback path — here the
    # pool is non-empty, so index 2 must not be consulted at all.
    for call in mock_redis.exists.call_args_list:
        assert call.args[0] != "utcms:circuit_breaker:blocked:2"


def test_get_next_ip_index_sync_registry_failure_fallback(mock_redis):
    """Registry errors must not break routing — fall back to all indices."""
    mock_redis.exists.return_value = False
    mock_redis.incr.return_value = 0

    with patch(
        "app.core.circuit_breaker._get_unavailable_ip_indices_sync",
        side_effect=RuntimeError("db down"),
    ):
        # Registry filter failed -> Redis-only -> healthy = [1, 2, 3]
        ip = get_next_ip_index_sync()
    assert ip == 1


def test_get_next_ip_index_sync_all_workers_dead_raises(mock_redis):
    """Never dispatch to queues positively known to have no live consumer."""
    mock_redis.exists.return_value = False
    mock_redis.incr.return_value = 2

    with patch("app.core.circuit_breaker._get_unavailable_ip_indices_sync", return_value={1, 2, 3}):
        with patch("app.core.circuit_breaker._get_known_ip_indices_sync", return_value={1, 2, 3}):
            with pytest.raises(NoHealthyWorkerError):
                get_next_ip_index_sync()


def test_get_next_ip_index_sync_registry_and_redis_combined(mock_redis):
    """Registry filter is complementary — Redis blocks still apply on top."""
    mock_redis.incr.return_value = 0

    def exists_side_effect(key):
        return key == "utcms:circuit_breaker:blocked:3"

    mock_redis.exists.side_effect = exists_side_effect

    with patch("app.core.circuit_breaker._get_unavailable_ip_indices_sync", return_value={2}):
        # registry kills 2, redis blocks 3 -> healthy = [1]
        ip = get_next_ip_index_sync()
    assert ip == 1


@pytest.mark.asyncio
async def test_get_next_ip_index_async_excludes_dead_worker(mock_redis_manager):
    """Async path applies the same complementary registry filter."""
    mock_redis_manager.exists.return_value = False
    mock_redis_manager.incr.return_value = 1

    with patch(
        "app.core.circuit_breaker._get_unavailable_ip_indices",
        new_callable=AsyncMock,
        return_value={1},
    ):
        # healthy = [2, 3] -> counter 1 % 2 = 1 -> ip 3
        ip = await _get_next_ip_index_async_helper()
    assert ip == 3


async def _get_next_ip_index_async_helper():
    from app.core.circuit_breaker import get_next_ip_index

    return await get_next_ip_index()


# --- unit tests for the registry-row reduction -------------------------------


def _hb(seconds_ago: int) -> datetime:
    return datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=seconds_ago)


def test_index_unavailable_from_rows_stale_and_offline():
    rows = [
        (1, "active", _hb(120)),  # stale heartbeat (older than 90s)
        (2, "offline", _hb(10)),  # offline
        (3, "active", _hb(10)),  # healthy
        (None, "active", _hb(10)),  # unattributed -> ignored
    ]
    assert _index_unavailable_from_rows(rows) == {1, 2}


def test_index_unavailable_from_rows_any_alive_keeps_index():
    """If ANY worker claiming an index is alive, the index stays in the pool."""
    rows = [
        (2, "offline", _hb(120)),
        (2, "active", _hb(5)),  # second worker on same index is alive
        (3, "active", _hb(300)),
    ]
    assert _index_unavailable_from_rows(rows) == {3}


def test_index_unavailable_from_rows_no_rows():
    assert _index_unavailable_from_rows([]) == set()


def test_registry_index_state_known_vs_unavailable():
    """_registry_index_state returns (known, unavailable) separately.

    An index that no worker has EVER claimed (e.g. index 4 in a two-node
    topology) is NOT part of ``known`` — the router must not dispatch to it even
    though it is also not ``unavailable`` (NEW-2 / GAP 2)."""
    from app.core.circuit_breaker import _registry_index_state

    rows = [
        (1, "active", _hb(5)),  # healthy claimed
        (2, "offline", _hb(10)),  # claimed, dead
        (None, "active", _hb(5)),  # unattributed -> ignored
    ]
    known, unavailable = _registry_index_state(rows)
    assert known == {1, 2}
    assert unavailable == {2}


def test_get_next_ip_index_sync_excludes_unclaimed_index(mock_redis):
    """An index in AVAILABLE_IP_INDICES that no worker has ever claimed must be
    dropped from the pool (NEW-2)."""
    os.environ["AVAILABLE_IP_INDICES"] = "1,2,3"
    mock_redis.exists.return_value = False
    mock_redis.incr.return_value = 0

    try:
        with patch("app.core.circuit_breaker._get_known_ip_indices_sync", return_value={1, 2}):
            # healthy = [1, 2] (3 was never claimed) -> counter 0 % 2 = 0 -> ip 1
            ip = get_next_ip_index_sync()
        assert ip == 1
        # index 3 must never even be consulted as a candidate
        for call in mock_redis.exists.call_args_list:
            assert call.args[0] != "utcms:circuit_breaker:blocked:3"
    finally:
        os.environ.pop("AVAILABLE_IP_INDICES", None)


def test_get_next_ip_index_sync_unclaimed_plus_redis_block(mock_redis):
    """Known-index filtering composes with Redis blocks."""
    os.environ["AVAILABLE_IP_INDICES"] = "1,2,3"
    mock_redis.incr.return_value = 0

    def exists_side_effect(key):
        return key == "utcms:circuit_breaker:blocked:2"

    mock_redis.exists.side_effect = exists_side_effect

    try:
        with patch("app.core.circuit_breaker._get_known_ip_indices_sync", return_value={1, 2, 3}):
            # known = {1,2,3}, redis blocks 2 -> healthy = [1, 3] -> ip 1
            ip = get_next_ip_index_sync()
        assert ip == 1
    finally:
        os.environ.pop("AVAILABLE_IP_INDICES", None)


def test_stale_threshold_boundary():
    rows = [
        (1, "active", _hb(WORKER_HEARTBEAT_STALE_SECONDS - 1)),  # fresh
        (2, "active", _hb(WORKER_HEARTBEAT_STALE_SECONDS + 1)),  # stale
        (3, "active", None),  # missing heartbeat -> stale
    ]
    assert _index_unavailable_from_rows(rows) == {2, 3}


# --- worker_lifecycle.resolve_ip_index ---------------------------------------


def test_resolve_ip_index_precedence():
    from app.orchestrator.worker_lifecycle import resolve_ip_index

    with patch.dict(os.environ, {"WORKER_IP_INDEX": "3", "WORKER_ID": "99"}, clear=False):
        # 1. explicit WORKER_IP_INDEX wins
        assert resolve_ip_index("99", "worker-node-2") == 3

    with patch.dict(os.environ, {"WORKER_IP_INDEX": "", "WORKER_ID": "2"}, clear=False):
        # 2. numeric worker_id
        assert resolve_ip_index("2", "worker-node-9") == 2

    with patch.dict(os.environ, {"WORKER_IP_INDEX": "", "WORKER_ID": "node-a"}, clear=False):
        # 3. hostname trailing suffix
        assert resolve_ip_index("node-a", "worker-node-4") == 4

    with patch.dict(os.environ, {"WORKER_IP_INDEX": "", "WORKER_ID": "node-a"}, clear=False):
        # 4. unresolvable -> None (fail-safe)
        assert resolve_ip_index("node-a", "worker-node-2026") is None


# ---------------------------------------------------------------------------
# Egress-failure -> breaker wiring.
#
# Measured before EGRESS_FAILURE_MARKERS was wired into the breaker: five of
# these six real egress errors were retried forever while the broken IP index
# stayed in the routing pool, because IP_BLOCK_PATTERNS only held 13 generic
# phrases and none of them matched a Chrome net:: error or a TLS handshake EOF.
# Each row below is one of those measured failures.
# ---------------------------------------------------------------------------
EGRESS_ERRORS_THAT_MUST_TRIP = [
    "net::ERR_CONNECTION_CLOSED",
    "TLS handshake: EOF",
    "SSL: UNEXPECTED_EOF_WHILE_READING",
    "408 Request Timeout",
    "net::ERR_CONNECTION_RESET",
    "ERR_CONNECTION_CLOSED",
]

# Worker-local faults. These are retryable but say nothing about the egress
# path, so blocking the IP index would evict a healthy route from rotation.
WORKER_LOCAL_ERRORS_THAT_MUST_NOT_TRIP = [
    "Target page, context or browser has been closed",
    "Browser has been closed",
    "Execution context was destroyed",
    "Page crashed",
    "Invalid driver national code",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("error_msg", EGRESS_ERRORS_THAT_MUST_TRIP)
async def test_egress_failures_trip_the_breaker(mock_redis_manager, error_msg):
    with patch.dict(os.environ, {"WORKER_IP_INDEX": "2"}, clear=False):
        await check_and_report_failure(error_msg)

    mock_redis_manager.set.assert_called_once_with("utcms:circuit_breaker:blocked:2", "1", ex=1800)


@pytest.mark.asyncio
@pytest.mark.parametrize("error_msg", WORKER_LOCAL_ERRORS_THAT_MUST_NOT_TRIP)
async def test_worker_local_failures_do_not_trip_the_breaker(mock_redis_manager, error_msg):
    with patch.dict(os.environ, {"WORKER_IP_INDEX": "2"}, clear=False):
        await check_and_report_failure(error_msg)

    mock_redis_manager.set.assert_not_called()


@pytest.mark.asyncio
async def test_breaker_needs_worker_ip_index_to_block(mock_redis_manager):
    """Without WORKER_IP_INDEX there is no index to block — must not guess."""
    with patch.dict(os.environ, {"WORKER_IP_INDEX": ""}, clear=False):
        await check_and_report_failure("net::ERR_CONNECTION_CLOSED")

    mock_redis_manager.set.assert_not_called()


@pytest.mark.asyncio
async def test_breaker_survives_redis_outage(mock_redis_manager):
    """A Redis failure must not propagate into the RPA error path."""
    mock_redis_manager.set.side_effect = RuntimeError("redis down")

    with patch.dict(os.environ, {"WORKER_IP_INDEX": "1"}, clear=False):
        await check_and_report_failure("net::ERR_CONNECTION_CLOSED")


def test_breaker_pattern_table_covers_both_halves():
    """BLOCK_OR_EGRESS_PATTERNS must stay the union of both source tables."""
    from app.core.circuit_breaker import BLOCK_OR_EGRESS_PATTERNS, IP_BLOCK_PATTERNS
    from app.core.network import EGRESS_FAILURE_MARKERS

    assert set(IP_BLOCK_PATTERNS) <= set(BLOCK_OR_EGRESS_PATTERNS)
    assert set(EGRESS_FAILURE_MARKERS) <= set(BLOCK_OR_EGRESS_PATTERNS)


def test_breaker_does_not_key_on_browser_lifecycle_markers():
    """Regression guard: wiring the FULL retry table in would evict healthy IPs."""
    from app.core.circuit_breaker import BLOCK_OR_EGRESS_PATTERNS
    from app.core.network import BROWSER_LIFECYCLE_MARKERS

    assert not (set(BROWSER_LIFECYCLE_MARKERS) & set(BLOCK_OR_EGRESS_PATTERNS))
