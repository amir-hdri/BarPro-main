"""Shared Redis accessors with authenticated lazy async initialization."""
from __future__ import annotations

import asyncio
from typing import Optional

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
        self._redis: Optional["aioredis.Redis"] = None
        self._lock = asyncio.Lock()

    async def get(self):
        if aioredis is None:
            return None
        if self._redis is None:
            async with self._lock:
                if self._redis is None:
                    self._redis = aioredis.from_url(
                        utcms_config.REDIS_URL,
                        **_build_redis_kwargs(),
                    )
        return self._redis

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.close()
            self._redis = None


redis_manager = RedisConnectionManager()
