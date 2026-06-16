"""Shared Redis accessors with authenticated lazy async initialization."""

from __future__ import annotations

import asyncio

from app.core.config import utcms_config

try:
    import redis.asyncio as aioredis
except ImportError:  # pragma: no cover
    aioredis = None


def _build_redis_kwargs() -> dict:
    kwargs = {
        "encoding": "utf-8",
        "decode_responses": True,
    }
    password = (utcms_config.REDIS_PASSWORD or "").strip()
    if password:
        kwargs["password"] = password
    return kwargs


class RedisConnectionManager:
    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock: asyncio.Lock | None = None

    async def get(self):
        if aioredis is None:
            return None

        current_loop = asyncio.get_running_loop()
        if self._lock is None or self._loop != current_loop:
            self._lock = asyncio.Lock()

        if self._redis is None or self._loop != current_loop:
            async with self._lock:
                if self._redis is None or self._loop != current_loop:
                    if self._redis is not None:
                        try:
                            await self._redis.close()
                        except Exception:
                            pass
                        self._redis = None
                    self._redis = aioredis.from_url(
                        utcms_config.REDIS_URL,
                        **_build_redis_kwargs(),
                    )
                    self._loop = current_loop
        return self._redis

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.close()
            self._redis = None
            self._loop = None


redis_manager = RedisConnectionManager()
