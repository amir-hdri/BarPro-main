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
    """Thread-safe Redis connection manager that works across Celery event loops."""

    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None
        self._lock = threading.Lock()

    async def _close_existing(self) -> None:
        if self._redis is not None:
            try:
                await self._redis.close()
            except Exception as exc:
                logger.warning("Error closing Redis connection: %s", exc)
            self._redis = None

    async def get(self):
        if aioredis is None:
            return None
        if self._redis is None:
            with self._lock:
                if self._redis is not None:
                    return self._redis
                await self._close_existing()
                self._redis = aioredis.from_url(
                    utcms_config.REDIS_URL,
                    **_build_redis_kwargs(),
                )
        return self._redis

    async def close(self) -> None:
        with self._lock:
            await self._close_existing()


redis_manager = RedisConnectionManager()
