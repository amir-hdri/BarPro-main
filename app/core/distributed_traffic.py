"""Distributed traffic controller with Redis-based semaphore for multi-worker environments."""

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Optional

from app.core.config import utcms_config

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as aioredis

    REDIS_AVAILABLE = True
except ImportError:
    aioredis = None
    REDIS_AVAILABLE = False


@dataclass
class DistributedTrafficSnapshot:
    active_requests: int
    queued_requests: int
    next_allowed_in_seconds: float
    blocked_for_seconds: float
    active_safe: int = 0
    active_full: int = 0
    queued_safe: int = 0
    queued_full: int = 0
    distributed: bool = False
    semaphore_available: bool = False


class DistributedSemaphore:
    """Redis-based distributed semaphore for multi-worker concurrency control."""

    def __init__(self, redis_client: aioredis.Redis, name: str, max_concurrent: int):
        self._redis = redis_client
        self._name = f"semaphore:{name}"
        self._max_concurrent = max_concurrent
        self._lock_key = f"{self._name}:lock"
        self._clients_key = f"{self._name}:clients"
        self._client_id = str(uuid.uuid4())

    async def acquire(self, timeout: float = 30.0) -> bool:
        """Acquire a slot in the distributed semaphore."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Use Redis Lua script for atomic check-and-set
                lua_script = """
                local current = redis.call('SCARD', KEYS[1])
                local max_concurrent = tonumber(ARGV[1])
                local client_id = ARGV[2]
                
                if current < max_concurrent then
                    redis.call('SADD', KEYS[1], client_id)
                    redis.call('EXPIRE', KEYS[1], 300)
                    return 1
                else
                    return 0
                end
                """

                result = await self._redis.eval(
                    lua_script,
                    1,
                    self._clients_key,
                    str(self._max_concurrent),
                    self._client_id,
                )

                if result == 1:
                    logger.debug(
                        "semaphore_acquired",
                        extra={
                            "extra_fields": {
                                "semaphore": self._name,
                                "client_id": self._client_id,
                            }
                        },
                    )
                    return True

                # Wait and retry
                await asyncio.sleep(0.1)

            except Exception as exc:
                logger.warning(
                    "semaphore_acquire_failed",
                    extra={"extra_fields": {"error": str(exc)}},
                )
                await asyncio.sleep(0.2)

        logger.warning(
            "semaphore_acquire_timeout",
            extra={
                "extra_fields": {
                    "semaphore": self._name,
                    "timeout": timeout,
                }
            },
        )
        return False

    async def release(self) -> None:
        """Release the distributed semaphore."""
        try:
            await self._redis.srem(self._clients_key, self._client_id)
            logger.debug(
                "semaphore_released",
                extra={
                    "extra_fields": {
                        "semaphore": self._name,
                        "client_id": self._client_id,
                    }
                },
            )
        except Exception as exc:
            logger.warning(
                "semaphore_release_failed",
                extra={"extra_fields": {"error": str(exc)}},
            )

    async def get_active_count(self) -> int:
        """Get current active count across all workers."""
        try:
            return await self._redis.scard(self._clients_key)
        except Exception:
            return 0


class DistributedTrafficController:
    """Traffic controller with distributed semaphore support."""

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None
        self._semaphore: Optional[DistributedSemaphore] = None
        self._local_semaphore: Optional[asyncio.Semaphore] = None
        self._lock = asyncio.Lock()
        self._next_allowed_at = 0.0
        self._blocked_until = 0.0
        self._is_distributed = False

    async def initialize(self) -> bool:
        """Initialize distributed traffic controller."""
        if REDIS_AVAILABLE and utcms_config.QUEUE_ENABLED:
            try:
                self._redis = aioredis.from_url(
                    utcms_config.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True,
                )
                await self._redis.ping()
                
                self._semaphore = DistributedSemaphore(
                    self._redis,
                    name="waybill",
                    max_concurrent=utcms_config.WAYBILL_MAX_CONCURRENT,
                )
                self._is_distributed = True
                
                logger.info(
                    "distributed_traffic_controller_initialized",
                    extra={
                        "extra_fields": {
                            "max_concurrent": utcms_config.WAYBILL_MAX_CONCURRENT,
                            "redis_url": utcms_config.REDIS_URL,
                        }
                    },
                )
                return True
            except Exception as exc:
                logger.warning(
                    "distributed_controller_fallback_to_local",
                    extra={"extra_fields": {"error": str(exc)}},
                )

        # Fallback to local semaphore
        self._local_semaphore = asyncio.Semaphore(max(1, utcms_config.WAYBILL_MAX_CONCURRENT))
        self._is_distributed = False
        
        logger.info(
            "local_traffic_controller_initialized",
            extra={"extra_fields": {"max_concurrent": utcms_config.WAYBILL_MAX_CONCURRENT}},
        )
        return False

    async def _wait_for_pacing(self):
        """Wait for rate limiting and pacing."""
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            wait_seconds = max(0.0, self._next_allowed_at - now, self._blocked_until - now)
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)

            import random
            jitter = random.uniform(0, max(0.0, utcms_config.WAYBILL_JITTER_SECONDS))
            gap = max(0.0, utcms_config.WAYBILL_MIN_GAP_SECONDS) + jitter
            self._next_allowed_at = loop.time() + gap

    async def acquire(self, mode: str = "safe"):
        """Acquire a slot for processing."""
        if self._is_distributed and self._semaphore:
            acquired = await self._semaphore.acquire(timeout=30.0)
            if not acquired:
                raise TimeoutError("Failed to acquire distributed semaphore")
        elif self._local_semaphore:
            await self._local_semaphore.acquire()
        
        await self._wait_for_pacing()

    async def release(self, mode: str = "safe"):
        """Release the acquired slot."""
        if self._is_distributed and self._semaphore:
            await self._semaphore.release()
        elif self._local_semaphore:
            self._local_semaphore.release()

    async def mark_temporary_block(self, multiplier: float = 1.0):
        """Mark temporary block for backoff."""
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            base = max(0.0, utcms_config.WAYBILL_BLOCK_BACKOFF_SECONDS)
            max_backoff = max(base, utcms_config.WAYBILL_BLOCK_BACKOFF_MAX_SECONDS)
            backoff = min(max_backoff, base * max(1.0, multiplier))
            self._blocked_until = max(self._blocked_until, now + backoff)

    async def snapshot(self) -> DistributedTrafficSnapshot:
        """Get current traffic snapshot."""
        loop = asyncio.get_running_loop()
        now = loop.time()
        
        active_count = 0
        if self._is_distributed and self._semaphore:
            active_count = await self._semaphore.get_active_count()
        elif self._local_semaphore:
            active_count = utcms_config.WAYBILL_MAX_CONCURRENT - self._local_semaphore._value

        return DistributedTrafficSnapshot(
            active_requests=active_count,
            queued_requests=0,
            next_allowed_in_seconds=max(0.0, self._next_allowed_at - now),
            blocked_for_seconds=max(0.0, self._blocked_until - now),
            distributed=self._is_distributed,
            semaphore_available=self._is_distributed and self._semaphore is not None,
        )

    @asynccontextmanager
    async def slot(self, mode: str = "safe"):
        """Context manager for acquiring and releasing a slot."""
        await self.acquire(mode=mode)
        try:
            yield
        finally:
            await self.release(mode=mode)

    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None
            self._semaphore = None


# Global instance
distributed_traffic_controller = DistributedTrafficController()
