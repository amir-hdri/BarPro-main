"""Tests for Redis-backed queue-depth counters and drift self-healing.

These tests use an in-memory fake Redis so they run without a real Redis server.
"""

from __future__ import annotations

import importlib

import pytest

from app.services.task_service import WaybillTaskService


class _FakeRedis:
    """Minimal async fake for the redis-py API used by task_service."""

    def __init__(self):
        self._hash: dict[str, dict[str, str]] = {}
        self._kv: dict[str, str] = {}
        self._deleted: list[str] = []
        self._published: list[tuple[str, str]] = []
        self.pubsub_calls = 0

    async def get(self, key: str):
        return self._kv.get(key)

    async def set(self, key: str, value, ex=None):
        self._kv[key] = str(value)
        return True

    async def delete(self, key: str):
        self._deleted.append(key)
        self._kv.pop(key, None)
        return 1

    async def exists(self, key: str):
        return 1 if key in self._kv else 0

    async def setnx(self, key: str, value):
        if key in self._kv:
            return False
        self._kv[key] = str(value)
        return True

    # alias used by some redis clients
    async def set(self, key, value, nx=False, ex=None):  # noqa: F811
        if nx and key in self._kv:
            return False
        self._kv[key] = str(value)
        return True

    async def hset(self, key: str, mapping=None, **kwargs):
        target = self._hash.setdefault(key, {})
        if mapping:
            target.update({k: str(v) for k, v in mapping.items()})
        target.update({k: str(v) for k, v in kwargs.items()})
        return len(mapping or kwargs)

    async def hgetall(self, key: str):
        return dict(self._hash.get(key, {}))

    async def hincrby(self, key: str, field: str, amount: int):
        target = self._hash.setdefault(key, {})
        cur = int(target.get(field, 0))
        target[field] = str(cur + amount)
        return cur + amount

    async def publish(self, channel: str, message: str):
        self._published.append((channel, message))
        return 1

    def pubsub(self):
        self.pubsub_calls += 1
        return _FakePubSub()

    def pipeline(self):
        return _FakePipeline(self)

    async def close(self):
        return None


class _FakePubSub:
    async def subscribe(self, *args, **kwargs):
        return None

    async def unsubscribe(self, *args, **kwargs):
        return None

    async def get_message(self, *args, **kwargs):
        return None

    async def close(self):
        return None


class _FakePipeline:
    """Collects pipelined commands and applies them on execute()."""

    def __init__(self, fr: _FakeRedis) -> None:
        self._fr = fr
        self._commands: list[tuple] = []

    def hincrby(self, key: str, field: str, amount: int):
        self._commands.append((key, field, amount))
        return self

    async def execute(self):
        for key, field, amount in self._commands:
            await self._fr.hincrby(key, field, amount)
        self._commands = []
        return True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


@pytest.fixture
def fake_redis(monkeypatch):
    fr = _FakeRedis()

    async def _fake_get():
        return fr

    # `import app.services.task_service as ts` resolves to the package-bound
    # singleton instance (see app/services/__init__.py), not the module. Use
    # importlib to get the real module so we can monkeypatch module-level names.
    ts = importlib.import_module("app.services.task_service")

    monkeypatch.setattr(ts.redis_manager, "get", _fake_get)
    return fr


@pytest.mark.asyncio
async def test_seed_then_adjust_updates_counters(fake_redis):
    svc = WaybillTaskService()
    # Seed with one queued task
    await fake_redis.hset(
        svc.QUEUE_DEPTH_KEY,
        mapping={k: "0" for k in svc._queue_depth_status_values()},
    )
    fake_redis._hash[svc.QUEUE_DEPTH_KEY]["queued"] = "1"
    await fake_redis.set(svc.QUEUE_DEPTH_SEEDED, "1")

    snapshot_before = await svc._queue_depth_snapshot()
    assert snapshot_before["queued"] == 1

    # queued -> succeeded
    await svc._adjust_queue_depth("queued", "succeeded")
    snapshot_after = await svc._queue_depth_snapshot()
    assert snapshot_after["queued"] == 0
    assert snapshot_after["succeeded"] == 1


@pytest.mark.asyncio
async def test_reconcile_overwrites_stale_cache_from_db(fake_redis, monkeypatch):
    svc = WaybillTaskService()

    # Seed a WRONG cache: says 5 queued, but DB (fake) has 2 queued + 1 failed
    await fake_redis.hset(
        svc.QUEUE_DEPTH_KEY,
        mapping={k: "0" for k in svc._queue_depth_status_values()},
    )
    fake_redis._hash[svc.QUEUE_DEPTH_KEY]["queued"] = "5"
    await fake_redis.set(svc.QUEUE_DEPTH_SEEDED, "1")

    class _Row:
        def __init__(self, status):
            self.status = status

        def __getitem__(self, idx):
            # reconcile_queue_depth reads row[0]
            return self.status

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class _FakeSession:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def execute(self, *a, **k):
            return _Result([_Row("queued"), _Row("queued"), _Row("failed")])

    monkeypatch.setattr(svc, "_ensure_queue_depth_seeded", lambda *a, **k: __import__("asyncio").sleep(0))
    ts = importlib.import_module("app.services.task_service")

    def _fake_session(*a, **k):
        return _FakeSession()

    monkeypatch.setattr(ts, "AsyncSession", _fake_session)

    result = await svc.reconcile_queue_depth()
    assert result is not None
    assert result["queued"] == 2
    assert result["failed"] == 1
    assert result["succeeded"] == 0


@pytest.mark.asyncio
async def test_adjust_is_noop_when_status_unchanged(fake_redis):
    svc = WaybillTaskService()
    await fake_redis.hset(
        svc.QUEUE_DEPTH_KEY,
        mapping={k: "0" for k in svc._queue_depth_status_values()},
    )
    fake_redis._hash[svc.QUEUE_DEPTH_KEY]["processing"] = "3"
    await fake_redis.set(svc.QUEUE_DEPTH_SEEDED, "1")

    await svc._adjust_queue_depth("processing", "processing")
    snap = await svc._queue_depth_snapshot()
    assert snap["processing"] == 3  # unchanged
