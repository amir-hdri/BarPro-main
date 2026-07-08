"""Shared Redis accessors with authenticated lazy async initialization."""

from __future__ import annotations

import logging
import threading

from app.core.config import utcms_config

try:
    import redis.asyncio as aioredis
except ImportError:  # pragma: no cover
    aioredis = None

logger = logging.getLogger(__name__)


def _build_redis_kwargs() -> dict:
    kwargs = {
        "encoding": "utf-8",
        "decode_responses": True,
        "max_connections": 20,
    }
    password = (utcms_config.REDIS_PASSWORD or "").strip()
    if password:
        kwargs["password"] = password
    return kwargs


class RedisConnectionManager:
    """Thread-safe Redis connection manager that works across Celery event loops.

    Note: `threading.Lock` is used instead of `asyncio.Lock` because Celery
    workers may run tasks across different event loops. The lock only protects
    the synchronous check-and-create section; no `await` is called while holding it.
    """

    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None
        self._lock = threading.Lock()

    async def _close_existing(self) -> None:
        """Close current redis connection (must NOT be called under _lock)."""
        redis_to_close = None
        with self._lock:
            if self._redis is not None:
                redis_to_close = self._redis
                self._redis = None

        if redis_to_close is not None:
            try:
                await redis_to_close.close()
            except Exception as exc:
                logger.warning("Error closing Redis connection: %s", exc)

    async def get(self):
        if aioredis is None:
            return None

        # Fast path (no lock needed — reading is fine with Python GIL)
        if self._redis is not None:
            return self._redis

        # Slow path — create a new connection. No await under the lock.
        new_client = None
        with self._lock:
            # Double-check after acquiring lock
            if self._redis is not None:
                return self._redis
            # Build client object synchronously (no IO here yet)
            new_client = aioredis.from_url(
                utcms_config.REDIS_URL,
                **_build_redis_kwargs(),
            )
            self._redis = new_client

        return self._redis

    async def close(self) -> None:
        """Gracefully close the Redis connection."""
        await self._close_existing()


redis_manager = RedisConnectionManager()
