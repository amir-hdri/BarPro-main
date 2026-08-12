import asyncio
import inspect
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

# One event-loop per OS thread (Celery prefork workers each have their own thread)
_THREAD_LOCAL = threading.local()

# Every bridge loop this process has created, so shutdown can close all of them
# and not just the calling thread's. The pool threads below own a loop each and
# never run `shutdown_async_bridge` themselves, so without this registry their
# loops (and the selector sockets registered on them) survive until process exit.
_BRIDGE_LOOPS: set[asyncio.AbstractEventLoop] = set()
_BRIDGE_LOOPS_LOCK = threading.Lock()

# Persistent thread pool for offloading coroutines from an already-running event loop.
# Created once and reused for the lifetime of the process to avoid thread churn.
_SHARED_POOL: ThreadPoolExecutor | None = None
_SHARED_POOL_LOCK = threading.Lock()


def _get_shared_pool() -> ThreadPoolExecutor:
    global _SHARED_POOL
    if _SHARED_POOL is None or _SHARED_POOL._shutdown:
        with _SHARED_POOL_LOCK:
            if _SHARED_POOL is None or _SHARED_POOL._shutdown:
                _SHARED_POOL = ThreadPoolExecutor(
                    max_workers=2,
                    thread_name_prefix="barpro-async-bridge",
                )
    return _SHARED_POOL


def _close_loop(loop: asyncio.AbstractEventLoop) -> None:
    if not loop.is_running() and not loop.is_closed():
        loop.close()


def close_thread_event_loop() -> None:
    """Close the async bridge loop owned by the current OS thread."""
    loop: asyncio.AbstractEventLoop | None = getattr(_THREAD_LOCAL, "loop", None)
    if loop is not None:
        _close_loop(loop)
        with _BRIDGE_LOOPS_LOCK:
            _BRIDGE_LOOPS.discard(loop)
    if hasattr(_THREAD_LOCAL, "loop"):
        delattr(_THREAD_LOCAL, "loop")


def shutdown_async_bridge() -> None:
    """Release the process-local pool and every bridge loop this process created."""
    global _SHARED_POOL
    with _SHARED_POOL_LOCK:
        pool, _SHARED_POOL = _SHARED_POOL, None
    # Shut the pool down first: its worker threads own bridge loops, and a loop
    # must not be closed while a task is still running on it.
    if pool is not None:
        pool.shutdown(wait=True, cancel_futures=True)

    close_thread_event_loop()

    with _BRIDGE_LOOPS_LOCK:
        loops = list(_BRIDGE_LOOPS)
        _BRIDGE_LOOPS.clear()
    for loop in loops:
        _close_loop(loop)


def get_shared_event_loop() -> asyncio.AbstractEventLoop:
    """Return the running loop if one exists, otherwise the thread-local loop."""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        # Standard asyncio idiom: `get_running_loop` raises `RuntimeError`
        # when no loop is bound to the current thread. The fallback below
        # creates and caches a thread-local loop, so swallowing this error
        # is intentional (rather than masking a real bug).
        pass

    loop: asyncio.AbstractEventLoop | None = getattr(_THREAD_LOCAL, "loop", None)
    if loop is None or loop.is_closed():
        if loop is not None:
            with _BRIDGE_LOOPS_LOCK:
                _BRIDGE_LOOPS.discard(loop)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _THREAD_LOCAL.loop = loop
        with _BRIDGE_LOOPS_LOCK:
            _BRIDGE_LOOPS.add(loop)
    return loop


def _run_on_thread_local_loop(coro) -> Any:
    """Run ``coro`` to completion on the calling thread's persistent loop."""
    return get_shared_event_loop().run_until_complete(coro)


def run_async(coro) -> Any:
    """Run an async coroutine synchronously.

    Strategy:
    1. If a loop is already running in the current thread (e.g. inside an async context),
       delegate execution safely via a persistent thread pool to avoid blocking the running loop.
    2. Otherwise use the thread-local event loop, which persists for the lifetime
       of this process thread.

    Both branches run on a *persistent* loop. The pool branch used to call
    `asyncio.run`, which creates a fresh loop per call and closes it on return.
    That silently broke every long-lived object bound to a loop — most visibly
    the shared Redis client, whose pooled connections are asyncio transports.
    The client was cached per thread but its sockets belonged to the loop that
    `asyncio.run` had already destroyed, so the *second* and every subsequent
    call from the same pool thread raised `RuntimeError: Event loop is closed`
    and leaked the socket. Reusing the thread's loop keeps those connections
    valid for the life of the process.

    Note the `try` covers only `get_running_loop()`. It previously wrapped
    `future.result()` as well, so a `RuntimeError` raised by `coro` itself was
    caught here and the already-consumed coroutine was re-submitted to the
    running loop — turning the real error into a misleading
    `RuntimeError: This event loop is already running`.
    """
    try:
        running_loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
    except RuntimeError:
        # No loop bound to this thread — use the persistent thread-local loop.
        running_loop = None

    if running_loop is not None and running_loop.is_running():
        pool = _get_shared_pool()
        future = pool.submit(_run_on_thread_local_loop, coro)
        return future.result()

    return get_shared_event_loop().run_until_complete(coro)


async def resolve_maybe_awaitable(value: Any) -> Any:
    """Resolve values that may be wrapped by AsyncMock/awaitable objects."""
    resolved = value
    for _ in range(3):
        if inspect.isawaitable(resolved):
            resolved = await resolved
            continue
        break
    return resolved
