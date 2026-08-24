"""Redis-backed runtime state for Phase 1 hybrid RPA orchestration."""

from __future__ import annotations

import json
import logging
import secrets
import threading
import time
from contextvars import ContextVar
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from app.core.business_time import business_date_str
from app.core.config import utcms_config
from app.core.redis_client import redis_manager
from app.rpa.contracts import RuntimeCounterSnapshot, SessionBundle

logger = logging.getLogger(__name__)


class RPADistributedRuntime:
    def __init__(self) -> None:
        self._memory: dict[str, tuple[str, float | None]] = {}
        self._lock = threading.Lock()
        self._lock_tokens: ContextVar[dict[str, str] | None] = ContextVar("rpa_lock_tokens", default=None)

    def _get_lock(self) -> threading.Lock:
        return self._lock

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

    async def _set_value(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        redis = await self._get_redis()
        if redis is not None:
            await redis.set(key, value, ex=ttl_seconds)
            return
        expires_at = time.time() + ttl_seconds if ttl_seconds else None
        with self._get_lock():
            self._memory[key] = (value, expires_at)

    async def _get_value(self, key: str) -> str | None:
        redis = await self._get_redis()
        if redis is not None:
            return await redis.get(key)
        with self._get_lock():
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
        with self._get_lock():
            self._memory.pop(key, None)

    async def acquire_lock(self, key: str, ttl_seconds: int) -> bool:
        token = secrets.token_urlsafe(24)
        redis = await self._get_redis()
        if redis is not None:
            acquired = bool(await redis.set(key, token, ex=ttl_seconds, nx=True))
            if acquired:
                tokens = (self._lock_tokens.get() or {}).copy()
                tokens[key] = token
                self._lock_tokens.set(tokens)
                await self._remember_lock_token(key, token, ttl_seconds)
            return acquired
        # NOTE: _remember_lock_token must run OUTSIDE _get_lock(): it acquires
        # the same non-reentrant threading.Lock internally.
        acquired_in_memory = False
        with self._get_lock():
            current = self._memory.get(key)
            if current is not None:
                _, expires_at = current
                if expires_at is None or expires_at > time.time():
                    return False
            self._memory[key] = (token, time.time() + ttl_seconds)
            acquired_in_memory = True
        if acquired_in_memory:
            tokens = (self._lock_tokens.get() or {}).copy()
            tokens[key] = token
            self._lock_tokens.set(tokens)
            await self._remember_lock_token(key, token, ttl_seconds)
            return True

    @staticmethod
    def _lock_token_registry_key(key: str) -> str:
        return f"locktok:{key}"

    async def _remember_lock_token(self, key: str, token: str, ttl_seconds: int) -> None:
        """Durably remember the lock token for the lock's lifetime.

        The release path compares the recalled token against the live lock value
        via a compare-and-delete Lua script, so a stale/foreign token can never
        delete someone else's lock — durability here does not weaken ownership.
        """
        try:
            await self._set_value(
                self._lock_token_registry_key(key),
                token,
                ttl_seconds=int(ttl_seconds) + 60,
            )
        except Exception:
            logger.warning("rpa_lock_token_remember_failed_for_key_%s", key, exc_info=True)

    async def _recall_lock_token(self, key: str) -> str | None:
        try:
            return await self._get_value(self._lock_token_registry_key(key))
        except Exception:
            logger.warning("rpa_lock_token_recall_failed_for_key_%s", key, exc_info=True)
            return None

    async def _forget_lock_token(self, key: str) -> None:
        try:
            await self._delete_value(self._lock_token_registry_key(key))
        except Exception:
            logger.warning("rpa_lock_token_forget_failed_for_key_%s", key, exc_info=True)

    async def release_lock(self, key: str, token: str | None = None) -> None:
        tokens = (self._lock_tokens.get() or {}).copy()
        if token is None:
            token = tokens.pop(key, None)
        else:
            tokens.pop(key, None)
        self._lock_tokens.set(tokens)
        if token is None:
            # ContextVar lost across an asyncio task/thread boundary: recall the
            # token from the durable registry written at acquire time. The Lua
            # compare-and-delete below still proves ownership before deleting.
            token = await self._recall_lock_token(key)
        redis = await self._get_redis()
        if redis is not None:
            if token is None:
                # No token in ContextVar nor registry. NEVER delete without
                # ownership proof — log and let the TTL expire.
                logger.warning(
                    "rpa_lock_release_token_missing_for_key_%s — skipping delete; lock will expire via TTL",
                    key,
                )
                return
            script = """
            if redis.call('get', KEYS[1]) == ARGV[1] then
                return redis.call('del', KEYS[1])
            end
            return 0
            """
            try:
                await redis.eval(script, 1, key, token)
            except Exception:
                logger.warning("rpa_lock_release_failed", exc_info=True)
            finally:
                await self._forget_lock_token(key)
            return
        # NOTE: _forget_lock_token must run OUTSIDE _get_lock(): it acquires the
        # same non-reentrant threading.Lock internally.
        memory_released = False
        with self._get_lock():
            current = self._memory.get(key)
            if current is not None and token is not None and current[0] == token:
                self._memory.pop(key, None)
                memory_released = True
        if memory_released:
            await self._forget_lock_token(key)

    async def renew_lock(self, key: str, ttl_seconds: int, token: str | None = None) -> bool:
        """Extend the TTL of an owned lock without releasing it (C3 fix).

        The driver submit/auth locks are acquired BEFORE the browser launches and
        must outlive a full bot window (browser start + up to JOB_TIMEOUT_SECONDS
        of automation). A fixed TTL alone can expire mid-execution, letting a
        second job for the same driver acquire the lock and submit in PARALLEL —
        exactly what the lock exists to prevent. The worker calls this on its
        lease-renewal schedule; ownership is proven by comparing the live lock
        value against the caller's token (ContextVar → durable registry fallback,
        same policy as release_lock), so a foreign execution can never extend a
        lock it does not hold.

        Returns True when the live lock was extended, False when the lock is
        gone or owned by someone else.
        """
        if token is None:
            tokens = self._lock_tokens.get() or {}
            token = tokens.get(key)
            if token is None:
                token = await self._recall_lock_token(key)
        if token is None:
            return False
        redis = await self._get_redis()
        if redis is not None:
            script = """
            if redis.call('get', KEYS[1]) == ARGV[1] then
                return redis.call('expire', KEYS[1], ARGV[2])
            end
            return 0
            """
            try:
                renewed = await redis.eval(script, 1, key, token, int(ttl_seconds))
                return bool(renewed)
            except Exception:
                logger.warning("rpa_lock_renew_failed", exc_info=True)
                return False
        with self._get_lock():
            current = self._memory.get(key)
            if current is not None and current[0] == token:
                self._memory[key] = (current[0], time.time() + ttl_seconds)
                return True
        return False

    async def force_release_lock(self, key: str, token: str | None = None) -> None:
        """Administrative recovery only: remove a lock without ownership checks.

        When ``token`` is provided the lock is only deleted if its current value
        matches (compare-and-delete), so a caller that knows the expected owner
        cannot release a lock held by another execution. With no token the lock
        is forcibly removed regardless of owner (admin escalation path).
        """
        tokens = (self._lock_tokens.get() or {}).copy()
        tokens.pop(key, None)
        self._lock_tokens.set(tokens)
        redis = await self._get_redis()
        if redis is not None:
            if token is not None:
                script = """
                if redis.call('get', KEYS[1]) == ARGV[1] then
                    return redis.call('del', KEYS[1])
                end
                return 0
                """
                try:
                    await redis.eval(script, 1, key, token)
                except Exception:
                    logger.warning("rpa_lock_force_release_failed", exc_info=True)
                finally:
                    await self._forget_lock_token(key)
                return
            try:
                await redis.delete(key)
            finally:
                await self._forget_lock_token(key)
            return
        with self._get_lock():
            if token is None or (self._memory.get(key) is not None and self._memory[key][0] == token):
                self._memory.pop(key, None)
        await self._forget_lock_token(key)

    async def is_lock_held(self, key: str) -> bool:
        """Return True if the lock key currently exists (regardless of owner)."""
        return (await self._get_value(key)) is not None

    async def get_lock_ttl(self, key: str) -> int | None:
        """Return remaining TTL in seconds for a lock key.

        Returns None when the key does not exist.
        Returns -1 when the key exists but has no TTL (memory fallback).
        """
        redis = await self._get_redis()
        if redis is not None:
            ttl = await redis.ttl(key)
            # Redis returns -2 when key does not exist, -1 when no TTL
            return None if ttl == -2 else ttl
        with self._get_lock():
            payload = self._memory.get(key)
            if payload is None:
                return None
            _, expires_at = payload
            if expires_at is None:
                return -1
            remaining = int(expires_at - time.time())
            return max(remaining, 0)

    async def list_driver_locks(self) -> list[dict]:
        """Return all active driver submit/auth locks with their remaining TTL.

        Uses Redis SCAN for non-blocking key enumeration (patterns: ``lock:submit:*`` and ``lock:auth:*``).
        Falls back to the in-memory store when Redis is unavailable.
        Returns a list of dicts: {"key", "ttl_seconds", "type"}.
        """
        results: list[dict] = []
        redis = await self._get_redis()
        if redis is not None:
            for pattern in ("lock:submit:*", "lock:auth:*"):
                try:
                    cursor = 0
                    while True:
                        cursor, keys = await redis.scan(cursor, match=pattern, count=100)
                        for key in keys:
                            key_str = key if isinstance(key, str) else key.decode("utf-8", errors="replace")
                            ttl = await redis.ttl(key)
                            lock_type = "submit" if key_str.startswith("lock:submit:") else "auth"
                            parts = key_str.split(":")
                            # key format: lock:<type>:<client_id>:<driver_id>
                            client_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
                            driver_id = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else None
                            results.append(
                                {
                                    "key": key_str,
                                    "lock_type": lock_type,
                                    "client_id": client_id,
                                    "driver_id": driver_id,
                                    "ttl_seconds": ttl if ttl >= 0 else None,
                                }
                            )
                        if cursor == 0:
                            break
                except Exception:
                    logger.warning("rpa_lock_list_failed", exc_info=True)
        else:
            with self._get_lock():
                now = time.time()
                for key, (_, expires_at) in list(self._memory.items()):
                    if not (key.startswith("lock:submit:") or key.startswith("lock:auth:")):
                        continue
                    if expires_at is not None and expires_at <= now:
                        continue
                    lock_type = "submit" if key.startswith("lock:submit:") else "auth"
                    parts = key.split(":")
                    client_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
                    driver_id = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else None
                    remaining = int(expires_at - now) if expires_at else -1
                    results.append(
                        {
                            "key": key,
                            "lock_type": lock_type,
                            "client_id": client_id,
                            "driver_id": driver_id,
                            "ttl_seconds": max(remaining, 0),
                        }
                    )
        return results

    async def store_session(self, client_id: int, driver_id: int, bundle: SessionBundle) -> None:
        await self._set_value(
            self.session_key(client_id, driver_id),
            json.dumps(asdict(bundle), ensure_ascii=False),
            ttl_seconds=utcms_config.RPA_SESSION_TTL_SECONDS,
        )

    async def get_session(self, client_id: int, driver_id: int) -> SessionBundle | None:
        raw = await self._get_value(self.session_key(client_id, driver_id))
        if not raw:
            return None
        return SessionBundle(**json.loads(raw))

    async def delete_session(self, client_id: int, driver_id: int) -> None:
        await self._delete_value(self.session_key(client_id, driver_id))

    async def increment_attempt(self, client_id: int, driver_id: int, at: datetime | None = None) -> int:
        return await self._increment_counter(self.counter_attempts_key(client_id, driver_id, business_date_str(at)))

    async def increment_success(self, client_id: int, driver_id: int, at: datetime | None = None) -> int:
        return await self._increment_counter(self.counter_successes_key(client_id, driver_id, business_date_str(at)))

    async def counter_snapshot(
        self, client_id: int, driver_id: int, at: datetime | None = None
    ) -> RuntimeCounterSnapshot:
        date_key = business_date_str(at)
        attempts = int(await self._get_value(self.counter_attempts_key(client_id, driver_id, date_key)) or 0)
        successes = int(await self._get_value(self.counter_successes_key(client_id, driver_id, date_key)) or 0)
        return RuntimeCounterSnapshot(business_date=date_key, attempts=attempts, successes=successes)

    async def apply_cooldown(self, scope: str, scope_id: str, ttl_seconds: int) -> None:
        payload = datetime.now(UTC).replace(tzinfo=None).isoformat()
        await self._set_value(self.cooldown_key(scope, scope_id), payload, ttl_seconds=ttl_seconds)

    async def cooldown_active(self, scope: str, scope_id: str) -> bool:
        return (await self._get_value(self.cooldown_key(scope, scope_id))) is not None

    async def _increment_counter(self, key: str) -> int:
        redis = await self._get_redis()
        if redis is not None:
            value = await redis.incr(key)
            await redis.expire(key, int(timedelta(days=3).total_seconds()))
            return int(value)
        with self._get_lock():
            payload = self._memory.get(key)
            current = int(payload[0]) if payload else 0
            current += 1
            self._memory[key] = (str(current), time.time() + int(timedelta(days=3).total_seconds()))
            return current


rpa_runtime = RPADistributedRuntime()
