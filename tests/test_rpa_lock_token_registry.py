"""Durable lock-token registry tests.

Regression coverage for the driver-lock stall: ``release_lock`` used to rely
solely on a ContextVar for token ownership proof. When the token was lost
across an asyncio task/thread boundary the release silently skipped deletion,
leaving the lock alive for the full RPA_LOCK_TTL_SECONDS window and blocking
the driver with ``driver_submission_in_progress``.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.rpa_runtime_service import rpa_runtime


class _FakeRedis:
    """Minimal async Redis double implementing SET NX EX / GET / DEL / EVAL."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.eval_calls: list[tuple[str, str]] = []

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def get(self, key: str):
        return self.store.get(key)

    async def delete(self, *keys: str):
        deleted = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                deleted += 1
        return deleted

    async def exists(self, key: str):
        return 1 if key in self.store else 0

    async def ttl(self, key: str):
        return -2 if key not in self.store else -1

    async def eval(self, script: str, numkeys: int, key: str, token: str):
        self.eval_calls.append((key, token))
        # Mirror the compare-and-delete Lua semantics
        if self.store.get(key) == token:
            del self.store[key]
            return 1
        return 0


@pytest.mark.asyncio
async def test_release_recalls_token_from_registry_when_contextvar_lost():
    fake = _FakeRedis()
    lock_key = "lock:submit:7:42"
    with patch.object(rpa_runtime, "_get_redis", new=AsyncMock(return_value=fake)):
        acquired = await rpa_runtime.acquire_lock(lock_key, ttl_seconds=120)
        assert acquired is True
        assert lock_key in fake.store
        # Registry entry written alongside the lock
        assert fake.store[f"locktok:{lock_key}"]

        # Simulate the ContextVar being lost across a task/thread boundary
        rpa_runtime._lock_tokens.set(None)
        assert lock_key not in (rpa_runtime._lock_tokens.get() or {})

        await rpa_runtime.release_lock(lock_key)

        # Ownership was proven via the recalled token -> lock deleted
        assert lock_key not in fake.store
        assert fake.eval_calls == [(lock_key, fake.eval_calls[0][1])]
        # Registry cleaned up after successful release
        assert f"locktok:{lock_key}" not in fake.store


@pytest.mark.asyncio
async def test_release_without_any_token_never_deletes_foreign_lock():
    fake = _FakeRedis()
    lock_key = "lock:submit:7:43"
    with patch.object(rpa_runtime, "_get_redis", new=AsyncMock(return_value=fake)):
        await rpa_runtime.acquire_lock(lock_key, ttl_seconds=120)
        # Wipe both the ContextVar AND the durable registry
        rpa_runtime._lock_tokens.set(None)
        await rpa_runtime._forget_lock_token(lock_key)

        await rpa_runtime.release_lock(lock_key)

        # No ownership proof -> lock must remain until TTL expiry
        assert lock_key in fake.store


@pytest.mark.asyncio
async def test_recalled_stale_token_cannot_delete_reacquired_lock():
    """Ownership safety: a token recalled after re-acquisition must not delete."""
    fake = _FakeRedis()
    lock_key = "lock:auth:9:11"
    with patch.object(rpa_runtime, "_get_redis", new=AsyncMock(return_value=fake)):
        await rpa_runtime.acquire_lock(lock_key, ttl_seconds=120)
        stale_registry_value = fake.store[f"locktok:{lock_key}"]

        # Owner B force-takes over with its own token (admin path)
        await rpa_runtime.force_release_lock(lock_key)
        reacquired = await rpa_runtime.acquire_lock(lock_key, ttl_seconds=120)
        assert reacquired is True

        # A stale holder replays the old registry value — compare-and-delete
        # must reject it because the live lock value differs.
        script_ok = await fake.eval("cmp", 1, lock_key, stale_registry_value)
        assert script_ok == 0
        assert lock_key in fake.store
