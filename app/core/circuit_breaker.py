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

import redis

from app.core.config import utcms_config
from app.core.redis_client import redis_manager


class CircuitOpenError(Exception):
    def __init__(self, retry_after_seconds: float):
        super().__init__("circuit_open")
        self.retry_after_seconds = retry_after_seconds


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


# Typical block or network/timeout indicators from UTCMS
IP_BLOCK_PATTERNS = [
    "blocked",
    "timeout",
    "timed out",
    "403",
    "429",
    "denied",
    "forbidden",
    "network error",
    "cannot connect",
    "ip restricted",
    "limiting",
    "rate limit",
    "gateway",
]


async def check_and_report_failure(error_msg: str) -> None:
    """
    Checks if the error message is indicative of an IP block or network timeout,
    and if so, flags the current worker's IP index as blocked in Redis for 30 minutes.
    """
    if not error_msg:
        return

    error_msg_lower = error_msg.lower()
    if any(pattern in error_msg_lower for pattern in IP_BLOCK_PATTERNS):
        ip_index = os.getenv("WORKER_IP_INDEX")
        if ip_index:
            try:
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
            return available_indices[0] if available_indices else 1

        healthy_ips: list[int] = []
        for i in available_indices:
            if not await r.exists(f"utcms:circuit_breaker:blocked:{i}"):
                healthy_ips.append(i)

        if not healthy_ips:
            logger.warning(f"All IP addresses are currently blocked! Falling back to all {available_indices}")
            healthy_ips = available_indices

        counter = await r.incr("utcms:dispatcher:counter")
        selected_ip = healthy_ips[counter % max(len(healthy_ips), 1)]

        _ip_index_cache = selected_ip
        _ip_index_cache_expires = now + _IP_INDEX_CACHE_TTL
        return selected_ip
    except Exception as exc:
        logger.error(f"Failed to get next IP index from Redis (async): {exc}")
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

        # Check blocked keys in Redis
        healthy_ips = []
        for i in available_indices:
            if not r.exists(f"utcms:circuit_breaker:blocked:{i}"):
                healthy_ips.append(i)

        if not healthy_ips:
            logger.warning(f"All IP addresses are currently blocked! Falling back to all {available_indices}")
            healthy_ips = available_indices

        # Increment global counter
        counter = r.incr("utcms:dispatcher:counter")
        # Select IP (safe: healthy_ips has at least one entry from fallback above)
        selected_ip = healthy_ips[counter % max(len(healthy_ips), 1)]
        return selected_ip
    except Exception as exc:
        logger.error(f"Failed to get next IP index from Redis (sync): {exc}")
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
