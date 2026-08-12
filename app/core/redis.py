"""Shared Redis accessors with authenticated lazy async initialization."""

from __future__ import annotations

import asyncio
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
        "socket_connect_timeout": 5,
        "socket_timeout": 5,
        "retry_on_timeout": True,
        "health_check_interval": 30,
    }
    password = (utcms_config.REDIS_PASSWORD or "").strip()
    if password:
        kwargs["password"] = password
    return kwargs


def _detach_transport(transport) -> None:
    """Neutralize an asyncio transport whose event loop is gone.

    ``transport.close()`` / ``abort()`` are unusable here: both schedule the
    real teardown with ``loop.call_soon``, and the loop is closed. Left alone,
    two finalizers complain at garbage-collection time:

    * ``_SelectorTransport.__del__`` warns ``unclosed transport`` whenever
      ``_sock`` is still set — closing the socket behind its back does not
      clear it.
    * ``StreamWriter.__del__`` warns ``loop is closed`` unless
      ``transport.is_closing()`` is true, i.e. unless ``_closing`` is set.

    Those warnings become errors under ``filterwarnings = error``, and because
    they fire whenever the collector happens to run, they fail an arbitrary
    unrelated test. Setting both attributes tells each finalizer the truth: the
    file descriptor has already been released.
    """
    for attribute, value in (("_closing", True), ("_sock", None)):
        try:
            setattr(transport, attribute, value)
        except AttributeError:
            pass


def _force_close_sockets(client) -> int:
    """Close a client's sockets without awaiting, for a client whose loop is gone.

    ``Redis.aclose()`` cannot help here: it awaits, and awaiting requires the
    loop that owns the connections — the very loop that has been closed. The
    pooled connections hold asyncio transports, and dropping the last reference
    to one only emits ``ResourceWarning: unclosed socket`` at GC time; the file
    descriptor stays open until the process exits. So reach through the
    transport to the underlying socket and close that directly.

    Returns the number of sockets closed. Best-effort by design: a leaked fd is
    worth reporting but never worth raising over.
    """
    pool = getattr(client, "connection_pool", None)
    if pool is None:
        return 0

    connections = list(getattr(pool, "_available_connections", None) or [])
    connections += list(getattr(pool, "_in_use_connections", None) or [])

    closed = 0
    for connection in connections:
        writer = getattr(connection, "_writer", None)
        transport = getattr(writer, "transport", None) if writer is not None else None
        sock = getattr(transport, "_sock", None) if transport is not None else None
        if sock is not None:
            try:
                sock.close()
                closed += 1
            except OSError as exc:
                logger.debug("redis_socket_force_close_failed: %s", exc)
            _detach_transport(transport)
        # Drop the transport references so the connection cannot be reused and
        # does not re-emit a warning for a socket that is already gone.
        try:
            connection._reader = None
            connection._writer = None
        except AttributeError:
            pass
    return closed


class RedisConnectionManager:
    """Thread-safe Redis connection manager that works across Celery event loops.

    Note: `threading.Lock` is used instead of `asyncio.Lock` because Celery
    workers may run tasks across different event loops. The lock only protects
    the synchronous check-and-create section; no `await` is called while holding it.

    The cached client is keyed by *both* thread and event loop. A redis-py async
    client owns asyncio transports, so it is only usable from the loop that
    created its connections; handing a client built on loop A to loop B raises
    `RuntimeError: Event loop is closed` (or attaches a future to the wrong
    loop). Caching per thread alone was not enough, because a single thread can
    legitimately run more than one loop over its lifetime.
    """

    def __init__(self) -> None:
        self._local = threading.local()
        self._lock = threading.Lock()
        # Every client this manager has handed out, keyed by the thread that
        # owns it. `threading.local` is only readable from its own thread, so a
        # teardown running on one thread cannot reach — let alone close — the
        # clients cached on others. This registry makes `close_sync` complete.
        self._all_clients: dict[int, object] = {}

    @staticmethod
    def _current_loop() -> asyncio.AbstractEventLoop | None:
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            # Called outside a running loop (sync helper, GC, shutdown). There
            # is no loop identity to match, so treat the cache as usable.
            return None

    @property
    def _redis(self) -> aioredis.Redis | None:
        return getattr(self._local, "redis", None)

    @_redis.setter
    def _redis(self, value: aioredis.Redis | None) -> None:
        self._local.redis = value
        thread_id = threading.get_ident()
        if value is None:
            self._all_clients.pop(thread_id, None)
        else:
            self._all_clients[thread_id] = value

    def _cached_for_current_loop(self) -> aioredis.Redis | None:
        """Return the cached client if it belongs to the running loop.

        When the cached client was built on a loop that is gone, close its
        sockets here rather than leaving them to the garbage collector: a
        Celery worker that recycles loops would otherwise accumulate one leaked
        fd per recycle until it hit the process limit.
        """
        client = self._redis
        if client is None:
            return None

        cached_loop = getattr(self._local, "loop", None)
        current_loop = self._current_loop()
        if current_loop is None or cached_loop is None or cached_loop is current_loop:
            return client

        leaked = _force_close_sockets(client)
        logger.warning(
            "redis_client_rebuilt_for_new_event_loop",
            extra={"extra_fields": {"sockets_closed": leaked}},
        )
        self._redis = None
        self._local.loop = None
        return None

    async def _close_existing(self) -> None:
        """Close current redis connection (must NOT be called under _lock)."""
        redis_to_close = None
        with self._lock:
            if self._redis is not None:
                redis_to_close = self._redis
                self._redis = None
                self._local.loop = None

        if redis_to_close is not None:
            try:
                await redis_to_close.aclose()
            except RuntimeError:
                # The owning loop is already closed, so `aclose` cannot run.
                # Release the sockets synchronously instead of leaking them.
                _force_close_sockets(redis_to_close)
            except Exception as exc:
                logger.warning("Error closing Redis connection: %s", exc)

    async def get(self):
        if aioredis is None:
            return None

        # Fast path (no lock needed — reading is fine with Python GIL)
        cached = self._cached_for_current_loop()
        if cached is not None:
            return cached

        # Slow path — create a new connection. No await under the lock.
        with self._lock:
            # Double-check after acquiring lock
            cached = self._cached_for_current_loop()
            if cached is not None:
                return cached
            # Build client object synchronously (no IO here yet)
            self._redis = aioredis.from_url(
                utcms_config.REDIS_URL,
                **_build_redis_kwargs(),
            )
            self._local.loop = self._current_loop()

        return self._redis

    async def close(self) -> None:
        """Gracefully close the Redis connection."""
        await self._close_existing()

    def close_sync(self) -> int:
        """Drop every cached client and release its sockets without awaiting.

        For teardown paths that have no usable loop — the pytest fixture between
        tests, an interpreter shutdown hook. Covers clients cached on *all*
        threads, not just the caller's, because the loops that owned them are
        typically already gone. Returns the number of sockets closed.
        """
        with self._lock:
            clients = list(self._all_clients.values())
            self._all_clients.clear()
            self._local.redis = None
            self._local.loop = None
        return sum(_force_close_sockets(client) for client in clients)


redis_manager = RedisConnectionManager()
