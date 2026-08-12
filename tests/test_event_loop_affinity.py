"""Regression tests for event-loop affinity of the shared async primitives.

Three defects met here, all invisible to the previous suite because it ran
without a live Redis:

1. `run_async` used `asyncio.run` for its pool branch, creating and destroying
   a loop per call. Any object cached across calls — the shared Redis client
   above all — was left holding transports on a dead loop, so the *second* call
   from a pool thread raised `RuntimeError: Event loop is closed`.
2. `run_async` also wrapped `future.result()` in the `except RuntimeError`
   intended for `get_running_loop()`, so that error was swallowed and the spent
   coroutine re-submitted, reporting a misleading "This event loop is already
   running".
3. `RedisConnectionManager` cached per thread but not per loop, so a thread that
   legitimately runs two loops got a client belonging to the first.

Each test asserts the *second* use, since the first always succeeds — that is
precisely why this survived so long in production.
"""

from __future__ import annotations

import asyncio
import gc
import socket
import threading
import warnings
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.redis import RedisConnectionManager, _force_close_sockets
from app.core.utils import close_thread_event_loop, run_async


def _run_in_fresh_loop(coro_factory):
    """Run a coroutine on a brand-new loop, then close it — as `asyncio.run` does."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro_factory())
    finally:
        loop.close()


class _LoopRecordingClient:
    """Stand-in for a redis client that refuses use from a foreign loop.

    Mirrors what redis-py does: its pooled connections hold asyncio transports,
    so a call from a different loop fails rather than silently reconnecting.
    """

    def __init__(self) -> None:
        self.owner_loop = asyncio.get_running_loop()
        self.connection_pool = MagicMock()
        self.connection_pool._available_connections = []
        self.connection_pool._in_use_connections = []
        self.closed = False

    async def ping(self) -> bool:
        current = asyncio.get_running_loop()
        if current is not self.owner_loop:
            raise RuntimeError("Event loop is closed")
        return True


def test_run_async_from_running_loop_survives_repeated_calls():
    """The pool branch must reuse its thread's loop, not build a new one per call.

    With `asyncio.run` in the pool branch, call 1 passed and call 2 raised
    `RuntimeError: Event loop is closed`, because the state cached on the pool
    thread outlived the loop that created it.
    """
    state: dict[str, asyncio.AbstractEventLoop] = {}

    async def _touch_loop_bound_state() -> str:
        loop = asyncio.get_running_loop()
        first = state.setdefault("loop", loop)
        if first is not loop:
            raise RuntimeError("Event loop is closed")
        return "ok"

    async def _driver() -> list[str]:
        # A running loop on this thread forces run_async down the pool branch.
        return [run_async(_touch_loop_bound_state()) for _ in range(4)]

    assert asyncio.run(_driver()) == ["ok"] * 4


def test_run_async_propagates_runtime_error_from_the_coroutine():
    """A RuntimeError raised by the coroutine must surface unchanged.

    It used to be caught by the `except RuntimeError` guarding
    `get_running_loop()`, after which the spent coroutine was re-submitted to
    the running loop and the caller saw "This event loop is already running" —
    hiding the real cause.
    """

    async def _explode() -> None:
        raise RuntimeError("original failure from inside the coroutine")

    async def _driver() -> None:
        with pytest.raises(RuntimeError, match="original failure from inside the coroutine"):
            run_async(_explode())

    asyncio.run(_driver())


def test_redis_manager_rebuilds_the_client_for_a_new_event_loop():
    """A client cached on a dead loop must be replaced, not handed back."""
    manager = RedisConnectionManager()
    built: list[_LoopRecordingClient] = []

    def _fake_from_url(*_args, **_kwargs) -> _LoopRecordingClient:
        client = _LoopRecordingClient()
        built.append(client)
        return client

    async def _use() -> bool:
        client = await manager.get()
        return await client.ping()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("app.core.redis.aioredis.from_url", _fake_from_url)
        assert _run_in_fresh_loop(_use) is True
        # Second loop: the cached client belongs to a loop that is now closed.
        assert _run_in_fresh_loop(_use) is True

    assert len(built) == 2, "expected a fresh client for the second loop"


def test_redis_manager_reuses_the_client_within_one_loop():
    """Loop-awareness must not cost us connection pooling."""
    manager = RedisConnectionManager()
    built = []

    def _fake_from_url(*_args, **_kwargs):
        client = _LoopRecordingClient()
        built.append(client)
        return client

    async def _use_three_times() -> None:
        for _ in range(3):
            client = await manager.get()
            assert await client.ping() is True

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("app.core.redis.aioredis.from_url", _fake_from_url)
        _run_in_fresh_loop(_use_three_times)

    assert len(built) == 1, f"client rebuilt {len(built)} times inside a single loop"


def test_redis_manager_caches_per_thread():
    """Two threads must not share one client (each owns a different loop)."""
    manager = RedisConnectionManager()
    built = []
    seen: list[object] = []

    def _fake_from_url(*_args, **_kwargs):
        client = _LoopRecordingClient()
        built.append(client)
        return client

    def _worker() -> None:
        async def _use():
            seen.append(await manager.get())

        _run_in_fresh_loop(_use)
        close_thread_event_loop()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("app.core.redis.aioredis.from_url", _fake_from_url)
        threads = [threading.Thread(target=_worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    assert len(built) == 2
    assert seen[0] is not seen[1]


def test_close_sync_drops_the_cached_client_without_a_loop():
    """Teardown paths have no usable loop, so closing must not require one."""
    manager = RedisConnectionManager()

    def _fake_from_url(*_args, **_kwargs):
        return _LoopRecordingClient()

    async def _use():
        return await manager.get()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("app.core.redis.aioredis.from_url", _fake_from_url)
        _run_in_fresh_loop(_use)

    assert manager._redis is not None
    manager.close_sync()  # no running loop here — must not raise
    assert manager._redis is None


def test_force_close_sockets_closes_pooled_sockets():
    """The socket, not just the connection object, has to be closed.

    Dropping the last reference to a connection only produces a
    `ResourceWarning`; the file descriptor survives until process exit.
    """
    sock = MagicMock()
    connection = MagicMock()
    connection._writer.transport._sock = sock
    transport = connection._writer.transport

    client = MagicMock()
    client.connection_pool._available_connections = [connection]
    client.connection_pool._in_use_connections = []

    assert _force_close_sockets(client) == 1
    sock.close.assert_called_once()
    assert connection._writer is None
    assert connection._reader is None
    # The transport must also be told its socket is gone, or its finalizer
    # warns about a descriptor that has in fact already been released.
    assert transport._sock is None
    assert transport._closing is True


def test_force_close_sockets_leaves_nothing_for_the_finalizers():
    """A real transport on a dead loop must be collectable without warning.

    This is the exact shape of the failure that made CI red. `__del__` runs
    whenever the collector gets around to it, so the warnings attached to
    arbitrary unrelated tests — and under `filterwarnings = error` they failed
    those tests. A `MagicMock` cannot prove this; only a real asyncio transport
    over a real socket can.
    """
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)

    async def _connect():
        return await asyncio.open_connection(*listener.getsockname())

    loop = asyncio.new_event_loop()
    try:
        reader, writer = loop.run_until_complete(_connect())
    finally:
        # Kill the loop while the connection is still open — what `asyncio.run`
        # did on every `run_async` call from a pool thread.
        loop.close()
        listener.close()

    connection = SimpleNamespace(_reader=reader, _writer=writer)
    client = SimpleNamespace(
        connection_pool=SimpleNamespace(
            _available_connections=[connection],
            _in_use_connections=[],
        )
    )

    assert _force_close_sockets(client) == 1

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        del reader, writer, connection, client
        gc.collect()

    assert [str(warning.message) for warning in caught] == []


def test_force_close_sockets_tolerates_a_client_without_a_pool():
    assert _force_close_sockets(MagicMock(connection_pool=None)) == 0
