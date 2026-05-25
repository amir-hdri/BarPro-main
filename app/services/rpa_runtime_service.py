"""Redis-backed runtime state for Phase 1 hybrid RPA orchestration."""
from __future__ import annotations

import asyncio
from dataclasses import asdict
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.core.business_time import business_date_str
from app.core.config import utcms_config
from app.core.redis_client import redis_manager
from app.rpa.contracts import RuntimeCounterSnapshot, SessionBundle


class RPADistributedRuntime:
    def __init__(self) -> None:
        self._memory: dict[str, tuple[str, float | None]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def session_key(client_id: int, driver_id: int) -> str:
        return f"session:{client_id}:{driver_id}"

    @staticmethod
    def auth_lock_key(client_id: int, driver_id: int) -> str:
        return f"lock:auth:{client_id}:{driver_id}"

    @staticmethod
    def submit_lock_key(client_id: int, driver_id: int) -> str:
        return f"lock:submit:{client_id}:{driver_id}"

    @staticmethod
    def counter_attempts_key(client_id: int, driver_id: int, date_key: str) -> str:
        return f"counter:attempts:{date_key}:{client_id}:{driver_id}"

    @staticmethod
    def counter_successes_key(client_id: int, driver_id: int, date_key: str) -> str:
        return f"counter:successes:{date_key}:{client_id}:{driver_id}"

    @staticmethod
    def cooldown_key(scope: str, scope_id: str) -> str:
        return f"cooldown:{scope}:{scope_id}"

    async def _get_redis(self):
        return await redis_manager.get()

    async def _set_value(self, key: str, value: str, ttl_seconds: Optional[int] = None) -> None:
        redis = await self._get_redis()
        if redis is not None:
            await redis.set(key, value, ex=ttl_seconds)
            return
        expires_at = time.time() + ttl_seconds if ttl_seconds else None
        async with self._lock:
            self._memory[key] = (value, expires_at)

    async def _get_value(self, key: str) -> Optional[str]:
        redis = await self._get_redis()
        if redis is not None:
            return await redis.get(key)
        async with self._lock:
            payload = self._memory.get(key)
            if payload is None:
                return None
            value, expires_at = payload
            if expires_at and expires_at <= time.time():
                self._memory.pop(key, None)
                return None
            return value

    async def _delete_value(self, key: str) -> None:
        redis = await self._get_redis()
        if redis is not None:
            await redis.delete(key)
            return
        async with self._lock:
            self._memory.pop(key, None)

    async def acquire_lock(self, key: str, ttl_seconds: int) -> bool:
        redis = await self._get_redis()
        if redis is not None:
            return bool(await redis.set(key, "1", ex=ttl_seconds, nx=True))
        async with self._lock:
            current = self._memory.get(key)
            if current is not None:
                _, expires_at = current
                if expires_at is None or expires_at > time.time():
                    return False
            self._memory[key] = ("1", time.time() + ttl_seconds)
            return True

    async def release_lock(self, key: str) -> None:
        await self._delete_value(key)

    async def store_session(self, client_id: int, driver_id: int, bundle: SessionBundle) -> None:
        await self._set_value(
            self.session_key(client_id, driver_id),
            json.dumps(asdict(bundle), ensure_ascii=False),
            ttl_seconds=utcms_config.RPA_SESSION_TTL_SECONDS,
        )

    async def get_session(self, client_id: int, driver_id: int) -> Optional[SessionBundle]:
        raw = await self._get_value(self.session_key(client_id, driver_id))
        if not raw:
            return None
        return SessionBundle(**json.loads(raw))

    async def delete_session(self, client_id: int, driver_id: int) -> None:
        await self._delete_value(self.session_key(client_id, driver_id))

    async def increment_attempt(self, client_id: int, driver_id: int, at: Optional[datetime] = None) -> int:
        return await self._increment_counter(self.counter_attempts_key(client_id, driver_id, business_date_str(at)))

    async def increment_success(self, client_id: int, driver_id: int, at: Optional[datetime] = None) -> int:
        return await self._increment_counter(self.counter_successes_key(client_id, driver_id, business_date_str(at)))

    async def counter_snapshot(self, client_id: int, driver_id: int, at: Optional[datetime] = None) -> RuntimeCounterSnapshot:
        date_key = business_date_str(at)
        attempts = int(await self._get_value(self.counter_attempts_key(client_id, driver_id, date_key)) or 0)
        successes = int(await self._get_value(self.counter_successes_key(client_id, driver_id, date_key)) or 0)
        return RuntimeCounterSnapshot(business_date=date_key, attempts=attempts, successes=successes)

    async def apply_cooldown(self, scope: str, scope_id: str, ttl_seconds: int) -> None:
        payload = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        await self._set_value(self.cooldown_key(scope, scope_id), payload, ttl_seconds=ttl_seconds)

    async def cooldown_active(self, scope: str, scope_id: str) -> bool:
        return (await self._get_value(self.cooldown_key(scope, scope_id))) is not None

    async def _increment_counter(self, key: str) -> int:
        redis = await self._get_redis()
        if redis is not None:
            value = await redis.incr(key)
            await redis.expire(key, int(timedelta(days=3).total_seconds()))
            return int(value)
        async with self._lock:
            payload = self._memory.get(key)
            current = int(payload[0]) if payload else 0
            current += 1
            self._memory[key] = (str(current), time.time() + int(timedelta(days=3).total_seconds()))
            return current


rpa_runtime = RPADistributedRuntime()
