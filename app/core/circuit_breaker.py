"""
Circuit Breaker and Round-Robin Queue Dispatcher for Multi-IP Architecture.

This module provides:
1. `check_and_report_failure`: Mark the current worker IP as blocked for 30 minutes in Redis on UTCMS limit/block/timeout.
2. `get_routed_queue`: Route tasks to a specific queue suffix based on healthy IP availability (Round-Robin).
3. `AsyncCircuitBreaker`: In-memory circuit breaker pattern for external service isolation.
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import redis
from sqlalchemy import select

from app.core.config import utcms_config
from app.core.database import async_session_factory
from app.core.network import EGRESS_FAILURE_MARKERS
from app.core.redis_client import redis_manager
from app.models_rpa import WorkerRegistry


class CircuitOpenError(Exception):
    def __init__(self, retry_after_seconds: float):
        super().__init__("circuit_open")
        self.retry_after_seconds = retry_after_seconds


class NoHealthyWorkerError(RuntimeError):
    """Raised when the registry knows the fleet but none can consume work."""


@dataclass
class CircuitSnapshot:
    state: str
    failure_count: int
    retry_after_seconds: float


class AsyncCircuitBreaker:
    def __init__(
        self,
        enabled: bool = True,
        failure_threshold: int = 5,
        recovery_seconds: int = 30,
        half_open_max_calls: int = 1,
    ):
        self._enabled = enabled
        self._failure_threshold = max(1, failure_threshold)
        self._recovery_seconds = max(1, recovery_seconds)
        self._half_open_max_calls = max(1, half_open_max_calls)

        self._state = "closed"
        self._failure_count = 0
        self._opened_at: float | None = None
        self._half_open_inflight = 0
        self._lock: asyncio.Lock | None = None
        self._lock_loop: asyncio.AbstractEventLoop | None = None

    @property
    def _safe_lock(self) -> asyncio.Lock:
        """Recreate lock if event loop changed (cross-loop safety for workers)."""
        current = asyncio.get_event_loop()
        if self._lock is None or self._lock_loop != current:
            self._lock = asyncio.Lock()
            self._lock_loop = current
        return self._lock

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    async def allow_request(self) -> None:
        if not self._enabled:
            return

        async with self._safe_lock:
            self._move_open_to_half_open_if_ready()

            if self._state == "open":
                raise CircuitOpenError(retry_after_seconds=self._remaining_open_seconds())

            if self._state == "half_open":
                if self._half_open_inflight >= self._half_open_max_calls:
                    raise CircuitOpenError(retry_after_seconds=self._remaining_open_seconds())
                self._half_open_inflight += 1

    async def record_success(self) -> None:
        if not self._enabled:
            return

        async with self._safe_lock:
            self._state = "closed"
            self._failure_count = 0
            self._opened_at = None
            self._half_open_inflight = 0

    async def record_failure(self) -> None:
        if not self._enabled:
            return

        async with self._safe_lock:
            if self._state == "half_open":
                self._state = "open"
                self._opened_at = time.monotonic()
                self._half_open_inflight = 0
                self._failure_count = self._failure_threshold
                return

            self._failure_count += 1
            if self._failure_count >= self._failure_threshold:
                self._state = "open"
                self._opened_at = time.monotonic()
                self._half_open_inflight = 0

    async def snapshot(self) -> CircuitSnapshot:
        async with self._safe_lock:
            self._move_open_to_half_open_if_ready()
            return CircuitSnapshot(
                state=self._state,
                failure_count=self._failure_count,
                retry_after_seconds=self._remaining_open_seconds(),
            )

    def _remaining_open_seconds(self) -> float:
        if self._state != "open" or self._opened_at is None:
            return 0.0
        elapsed = time.monotonic() - self._opened_at
        return max(0.0, self._recovery_seconds - elapsed)

    def _move_open_to_half_open_if_ready(self) -> None:
        if self._state != "open" or self._opened_at is None:
            return
        if (time.monotonic() - self._opened_at) >= self._recovery_seconds:
            self._state = "half_open"
            self._half_open_inflight = 0


logger = logging.getLogger(__name__)

# Cached synchronous Redis client for get_next_ip_index_sync
_redis_sync_client: "redis.Redis | None" = None


def _get_redis_sync() -> "redis.Redis":
    global _redis_sync_client
    if _redis_sync_client is None:
        _redis_sync_client = redis.Redis.from_url(
            utcms_config.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            max_connections=10,
        )
    return _redis_sync_client


# TTL cache for IP index lookup — avoids hitting Redis on every call
_ip_index_cache: int | None = None
_ip_index_cache_expires: float = 0.0
_IP_INDEX_CACHE_TTL = 5.0  # seconds


# Typical block or network/timeout indicators from UTCMS.
#
# These are target-side signals: the response we got proves the remote side is
# refusing or throttling THIS IP, so the index must leave the pool.
IP_BLOCK_PATTERNS = [
    "blocked",
    "403",
    "429",
    "denied",
    "forbidden",
    "network error",
    "cannot connect",
    "ip restricted",
    "limiting",
    "rate limit",
    "ip banned",
    "waf blocked",
]

# The patterns above only cover 13 generic phrases, so real transport failures
# (net::ERR_CONNECTION_CLOSED, TLS handshake EOF, SSL UNEXPECTED_EOF, connection
# reset) never tripped the breaker and a worker with a dead egress path kept
# receiving work forever. EGRESS_FAILURE_MARKERS is the transport-layer half of
# the same decision, so the breaker consults both.
#
# Deliberately NOT the full RETRYABLE_NETWORK_MARKERS table: that one also
# covers browser-lifecycle crashes ("browser has been closed", "page crashed"),
# which are worker-local and would evict a healthy IP index from rotation.
BLOCK_OR_EGRESS_PATTERNS: tuple[str, ...] = (*IP_BLOCK_PATTERNS, *EGRESS_FAILURE_MARKERS)


async def check_and_report_failure(
    error_msg: str,
    egress_source: str | None = None,
    proxy_url: str | None = None,
) -> None:
    """
    Checks if the error message is indicative of an IP block or network timeout.
    - If the error originated from the Clean IP Pool (egress_source="clean_pool" or proxy_url provided),
      only that specific third-party proxy is marked blocked via mark_blocked(), leaving the worker
      and its IP index healthy and available for tasks.
    - If the error originated from the worker's dedicated Squid, flags the current worker's IP index
      as blocked in Redis for 30 minutes.
    """
    if not error_msg:
        return

    if egress_source is None and proxy_url is None:
        try:
            from app.automation.worker_proxy import get_current_egress_context

            egress_source, proxy_url = get_current_egress_context()
        except Exception:
            logger.debug("Circuit Breaker: could not resolve current egress context", exc_info=True)

    error_msg_lower = error_msg.lower()
    if any(pattern in error_msg_lower for pattern in BLOCK_OR_EGRESS_PATTERNS):
        dedicated_proxy_urls = {
            value.strip()
            for key, value in os.environ.items()
            if key.startswith("WORKER_") and key.endswith("_PROXY") and value.strip()
        }
        inferred_third_party_proxy = (
            egress_source is None
            and proxy_url
            and proxy_url not in dedicated_proxy_urls
            and "squid" not in proxy_url.lower()
            and "172.20.0.1" not in proxy_url
        )
        if egress_source == "clean_pool" or inferred_third_party_proxy:
            target_url = proxy_url or ""
            if target_url:
                try:
                    from app.automation.clean_ip_pool import clean_ip_pool

                    await clean_ip_pool.mark_blocked(target_url, duration_seconds=1800)
                    logger.warning(
                        f"Circuit Breaker: Clean IP Pool proxy {target_url} marked as BLOCKED "
                        f"due to error: {error_msg}. Worker IP index remains healthy."
                    )
                except Exception as exc:
                    logger.error(f"Failed to mark clean proxy blocked: {exc}")
            else:
                # Clean-pool egress failed but the specific proxy identity was
                # lost upstream. Punishing the worker's OWN IP index for a
                # third-party proxy problem would drain a healthy worker for
                # 30 minutes — log and move on instead.
                logger.warning(
                    "Circuit Breaker: clean-pool egress failure without proxy identity "
                    f"({error_msg}); worker IP index left untouched."
                )
            return

        ip_index = os.getenv("WORKER_IP_INDEX")
        if ip_index:
            try:
                available = get_available_ip_indices()
                if len(available) <= 1:
                    logger.warning(
                        f"Circuit Breaker: IP index {ip_index} had failure ({error_msg}) "
                        f"but is the ONLY available worker index ({available}). Skipping 30-min block to prevent total fleet paralysis."
                    )
                    return
                r_async = await redis_manager.get()
                if r_async is not None:
                    key = f"utcms:circuit_breaker:blocked:{ip_index}"
                    # Flag as blocked for 30 minutes (1800 seconds)
                    await r_async.set(key, "1", ex=1800)
                    logger.warning(
                        f"Circuit Breaker: IP index {ip_index} marked as BLOCKED "
                        f"for 30 minutes in Redis due to error: {error_msg}"
                    )
            except Exception as exc:
                logger.error(f"Failed to set circuit breaker block in Redis: {exc}")
        else:
            logger.debug("IP failure detected, but WORKER_IP_INDEX environment variable is not set.")


def get_available_ip_indices() -> list[int]:
    """Parse list of available IP indices from environment."""
    raw = os.getenv("AVAILABLE_IP_INDICES", "1,2,3")
    try:
        return [int(x.strip()) for x in raw.split(",") if x.strip()]
    except Exception:
        return [1, 2, 3]


# ---------------------------------------------------------------------------
# Worker-registry liveness filter (complement to the Redis circuit breaker)
#
# ``get_next_ip_index*`` historically only looked at Redis "blocked" keys
# (``utcms:circuit_breaker:blocked:{i}``). A remotely crashed worker never
# writes such a key, so its queue kept being selected forever, creating the
# ClaimReaper WAITING_RETRY -> Scheduler -> same dead queue loop.
#
# The complementary filter below consults ``worker_registry``: any IP index
# that is positively attributed (via ``ip_index``) to workers which are NOT
# ``active`` or whose ``last_heartbeat_at`` is older than
# ``WORKER_HEARTBEAT_STALE_SECONDS`` is removed from the routing pool.
#
# Fail-safe rules:
#   * An index with NO registry rows (unclaimed) stays in the pool — we only
#     exclude indices we can POSITIVELY attribute to dead workers, so a
#     partially migrated fleet never shrinks the pool incorrectly.
#   * Any DB/registry error => empty unavailable-set => previous behavior
#     (Redis-only routing), the system never stops.
# ---------------------------------------------------------------------------

# Heartbeat loop in worker_lifecycle writes every
# WORKER_REGISTRY_HEARTBEAT_SECONDS (default 30s); stale = 3 missed beats.
WORKER_HEARTBEAT_STALE_SECONDS = int(3 * getattr(utcms_config, "WORKER_REGISTRY_HEARTBEAT_SECONDS", 30.0))

# Short TTL cache so the registry snapshot is not queried on every dispatch.
# The overall IP selection is already cached for 5s; this bounds DB load
# while keeping dead-worker detection latency well under the 5-minute
# ClaimReaper cycle.
_WORKER_REGISTRY_CACHE_TTL = 5.0

# (known_indices, unavailable_indices, expires_monotonic) — one cache per
# async/sync path. ``known`` = indices positively claimed by >= 1 registry row,
# ``unavailable`` = indices claimed only by dead/stale workers.
_worker_registry_snapshot: tuple[frozenset[int], frozenset[int], float] | None = None
_worker_registry_snapshot_sync: tuple[frozenset[int], frozenset[int], float] | None = None

# Lazily-created synchronous engine for the legacy sync routing path.
_worker_sync_engine = None
_WorkerSyncSession = None


def _is_stale_heartbeat(last_heartbeat_at: datetime | None) -> bool:
    """True when the heartbeat is missing or older than the stale threshold."""
    if last_heartbeat_at is None:
        return True
    # worker_registry stores naive UTC datetimes (see worker_lifecycle._now)
    now = datetime.now(UTC).replace(tzinfo=None)
    return (now - last_heartbeat_at) > timedelta(seconds=WORKER_HEARTBEAT_STALE_SECONDS)


def _registry_index_state(rows) -> tuple[set[int], set[int]]:
    """Reduce (ip_index, status, last_heartbeat_at) rows to (known, unavailable).

    * ``known`` — every IP index positively claimed by at least one registry
      row. An index that has NEVER been seen is deliberately excluded from
      this set so a misconfigured ``AVAILABLE_IP_INDICES`` can never steer
      dispatch to a phantom queue (NEW-2 / GAP 2).
    * ``unavailable`` — indices where at least one worker claims the index and
      NONE of its claiming workers is active AND fresh.
    """
    claims: dict[int, list[bool]] = {}
    for ip_index, status, last_heartbeat_at in rows:
        if ip_index is None:
            continue
        healthy = status == "active" and not _is_stale_heartbeat(last_heartbeat_at)
        claims.setdefault(int(ip_index), []).append(healthy)
    return (
        set(claims),
        {idx for idx, flags in claims.items() if not any(flags)},
    )


def _index_unavailable_from_rows(rows) -> set[int]:
    """Reduce (ip_index, status, last_heartbeat_at) rows to dead indices.

    An index is unavailable ONLY when at least one worker claims it and NONE
    of its claiming workers is active AND fresh. Unclaimed indices are kept
    (kept — never shrinks the pool on partial migration).
    """
    return _registry_index_state(rows)[1]


def _known_indices_from_rows(rows) -> set[int]:
    """Indices positively claimed by >= 1 registry row (see _registry_index_state)."""
    return _registry_index_state(rows)[0]


def _get_worker_sync_session():
    """Return a synchronous session factory for the registry (lazy, thread-safe enough)."""
    global _worker_sync_engine, _WorkerSyncSession
    if _WorkerSyncSession is None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        sync_url = utcms_config.DATABASE_URL
        if sync_url.startswith("postgresql+asyncpg://"):
            sync_url = sync_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        elif sync_url.startswith("sqlite+aiosqlite://"):
            # Local dev convenience — sync engine cannot use the async driver.
            sync_url = sync_url.replace("sqlite+aiosqlite://", "sqlite://")
        connect_args = {"connect_timeout": 2} if sync_url.startswith("postgresql") else {}
        _worker_sync_engine = create_engine(
            sync_url,
            pool_size=2,
            max_overflow=1,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        _WorkerSyncSession = sessionmaker(_worker_sync_engine, expire_on_commit=False)
    return _WorkerSyncSession


async def _get_registry_state() -> tuple[set[int], set[int]]:
    """Async registry lookup — (known, unavailable) IP-index sets.

    Fail-safe: returns (empty, empty) on any error (routing falls back to the
    previous Redis-only behavior and never shrinks the pool incorrectly).
    """
    global _worker_registry_snapshot
    now = time.monotonic()
    if _worker_registry_snapshot is not None and now < _worker_registry_snapshot[2]:
        return set(_worker_registry_snapshot[0]), set(_worker_registry_snapshot[1])

    known: set[int] = set()
    unavailable: set[int] = set()
    try:
        async with async_session_factory() as session:
            stmt = select(
                WorkerRegistry.ip_index,
                WorkerRegistry.status,
                WorkerRegistry.last_heartbeat_at,
            ).where(WorkerRegistry.ip_index.is_not(None))
            result = await session.exec(stmt)
            known, unavailable = _registry_index_state(result.all())
    except NoHealthyWorkerError:
        raise
    except Exception as exc:
        # Fail-safe: registry is a complement, never a hard dependency.
        logger.warning(f"Worker registry health check failed (async) — falling back to Redis-only routing: {exc}")
        known, unavailable = set(), set()

    _worker_registry_snapshot = (frozenset(known), frozenset(unavailable), now + _WORKER_REGISTRY_CACHE_TTL)
    return known, unavailable


def _get_registry_state_sync() -> tuple[set[int], set[int]]:
    """Sync registry lookup (legacy routing path) — same semantics as async."""
    global _worker_registry_snapshot_sync
    now = time.monotonic()
    if _worker_registry_snapshot_sync is not None and now < _worker_registry_snapshot_sync[2]:
        return set(_worker_registry_snapshot_sync[0]), set(_worker_registry_snapshot_sync[1])

    known: set[int] = set()
    unavailable: set[int] = set()
    try:
        session_factory = _get_worker_sync_session()
        with session_factory() as session:
            stmt = select(
                WorkerRegistry.ip_index,
                WorkerRegistry.status,
                WorkerRegistry.last_heartbeat_at,
            ).where(WorkerRegistry.ip_index.is_not(None))
            rows = session.execute(stmt).all()
            known, unavailable = _registry_index_state(rows)
    except NoHealthyWorkerError:
        raise
    except Exception as exc:
        logger.warning(f"Worker registry health check failed (sync) — falling back to Redis-only routing: {exc}")
        known, unavailable = set(), set()

    _worker_registry_snapshot_sync = (frozenset(known), frozenset(unavailable), now + _WORKER_REGISTRY_CACHE_TTL)
    return known, unavailable


async def _get_unavailable_ip_indices() -> set[int]:
    """Async registry lookup — indices attributed to dead/stale workers."""
    return (await _get_registry_state())[1]


def _get_unavailable_ip_indices_sync() -> set[int]:
    """Sync registry lookup — indices attributed to dead/stale workers."""
    return _get_registry_state_sync()[1]


async def _get_known_ip_indices() -> set[int]:
    """Async registry lookup — indices positively claimed by >= 1 worker."""
    return (await _get_registry_state())[0]


def _get_known_ip_indices_sync() -> set[int]:
    """Sync registry lookup — indices positively claimed by >= 1 worker."""
    return _get_registry_state_sync()[0]


async def get_next_ip_index() -> int:
    """Async IP index lookup with TTL caching — does NOT block the event loop.

    Uses the shared ``redis_manager`` (async) and caches the result for
    ``_IP_INDEX_CACHE_TTL`` seconds.  Falls back to the first available
    index when Redis is unavailable.
    """
    global _ip_index_cache, _ip_index_cache_expires

    now = time.monotonic()
    if _ip_index_cache is not None and now < _ip_index_cache_expires:
        return _ip_index_cache

    available_indices = get_available_ip_indices()
    try:
        r = await redis_manager.get()
        if r is None:
            if utcms_config.is_production():
                raise NoHealthyWorkerError("Redis is unavailable for dispatcher routing (fail-closed)")
            return available_indices[0] if available_indices else 1

        # Complementary filter: drop indices attributed to dead/stale workers,
        # and — when the registry knows anything at all — drop indices that no
        # worker has EVER claimed (misconfigured AVAILABLE_IP_INDICES -> no
        # phantom queue dispatch). Fail-safe: on any registry error both sets
        # are empty and the pool degrades to the previous Redis-only behavior.
        try:
            unavailable_from_registry = await _get_unavailable_ip_indices()
            known_from_registry = await _get_known_ip_indices()
        except Exception as reg_exc:
            logger.warning(f"Registry lookup failed (async) — falling back to Redis-only: {reg_exc}")
            unavailable_from_registry = set()
            known_from_registry = set()

        healthy_ips: list[int] = []
        for i in available_indices:
            if i in unavailable_from_registry:
                continue
            if known_from_registry and i not in known_from_registry:
                continue
            if not await r.exists(f"utcms:circuit_breaker:blocked:{i}"):
                healthy_ips.append(i)

        if not healthy_ips and known_from_registry:
            raise NoHealthyWorkerError("No active, fresh and unblocked worker IP is available")

        if not healthy_ips:
            # Registry is unavailable/empty: preserve the historical fail-safe.
            healthy_ips = [i for i in available_indices if not await r.exists(f"utcms:circuit_breaker:blocked:{i}")]

        if not healthy_ips:
            raise NoHealthyWorkerError("All configured worker IPs are temporarily blocked")

        counter = await r.incr("utcms:dispatcher:counter")
        selected_ip = healthy_ips[counter % max(len(healthy_ips), 1)]

        _ip_index_cache = selected_ip
        _ip_index_cache_expires = now + _IP_INDEX_CACHE_TTL
        return selected_ip
    except NoHealthyWorkerError:
        raise
    except Exception as exc:
        logger.error(f"Failed to get next IP index from Redis (async): {exc}")
        if utcms_config.is_production():
            raise NoHealthyWorkerError(f"Worker routing failed (fail-closed): {exc}") from exc
        return available_indices[0] if available_indices else 1


async def get_routed_queue_async(base_queue: str) -> str:
    """Async version of ``get_routed_queue`` — preferred for async callers."""
    EXEMPT_QUEUES = {"rpa_scheduler"}
    if base_queue in EXEMPT_QUEUES:
        return base_queue

    ip_index = await get_next_ip_index()
    routed = f"{base_queue}_{ip_index}"
    logger.info(f"Routed task queue from {base_queue} -> {routed} (IP Index: {ip_index})")
    return routed


def get_next_ip_index_sync() -> int:
    """Synchronous IP index lookup (legacy — blocks the event loop).

    Prefer :func:`get_next_ip_index` in async code paths.
    """
    available_indices = get_available_ip_indices()
    try:
        r = _get_redis_sync()

        # Complementary filter: drop indices attributed to dead/stale workers,
        # and — when the registry knows anything at all — drop indices that no
        # worker has EVER claimed (misconfigured AVAILABLE_IP_INDICES -> no
        # phantom queue dispatch). Fail-safe: on any registry error both sets
        # are empty and the pool degrades to the previous Redis-only behavior.
        try:
            unavailable_from_registry = _get_unavailable_ip_indices_sync()
            known_from_registry = _get_known_ip_indices_sync()
        except Exception as reg_exc:
            logger.warning(f"Registry lookup failed (sync) — falling back to Redis-only: {reg_exc}")
            unavailable_from_registry = set()
            known_from_registry = set()

        # Check blocked keys in Redis + worker-registry liveness
        healthy_ips = []
        for i in available_indices:
            if i in unavailable_from_registry:
                continue
            if known_from_registry and i not in known_from_registry:
                continue
            if not r.exists(f"utcms:circuit_breaker:blocked:{i}"):
                healthy_ips.append(i)

        if not healthy_ips and known_from_registry:
            raise NoHealthyWorkerError("No active, fresh and unblocked worker IP is available")

        if not healthy_ips:
            # Registry is unavailable/empty: preserve the historical fail-safe.
            healthy_ips = [i for i in available_indices if not r.exists(f"utcms:circuit_breaker:blocked:{i}")]

        if not healthy_ips:
            raise NoHealthyWorkerError("All configured worker IPs are temporarily blocked")

        # Increment global counter
        counter = r.incr("utcms:dispatcher:counter")
        # Select IP (safe: healthy_ips has at least one entry from fallback above)
        selected_ip = healthy_ips[counter % max(len(healthy_ips), 1)]
        return selected_ip
    except NoHealthyWorkerError:
        raise
    except Exception as exc:
        logger.error(f"Failed to get next IP index from Redis (sync): {exc}")
        if utcms_config.is_production():
            raise NoHealthyWorkerError(f"Worker routing failed (fail-closed): {exc}") from exc
        # Default fallback to first available
        return available_indices[0] if available_indices else 1


def get_routed_queue(base_queue: str) -> str:
    """
    Suffix the base queue with a healthy IP index (e.g. waybill_tasks_2).

    NOTE: This uses synchronous Redis and will block the event loop.
    Prefer :func:`get_routed_queue_async` in async code paths.
    """
    # Exclude system queues that shouldn't be partitioned
    EXEMPT_QUEUES = {"rpa_scheduler"}
    if base_queue in EXEMPT_QUEUES:
        return base_queue

    ip_index = get_next_ip_index_sync()
    routed = f"{base_queue}_{ip_index}"
    logger.info(f"Routed task queue from {base_queue} -> {routed} (IP Index: {ip_index})")
    return routed
