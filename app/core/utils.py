import asyncio
import inspect
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

# One event-loop per OS thread (Celery prefork workers each have their own thread)
_THREAD_LOCAL = threading.local()

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


def close_thread_event_loop() -> None:
    """Close the async bridge loop owned by the current OS thread."""
    loop: asyncio.AbstractEventLoop | None = getattr(_THREAD_LOCAL, "loop", None)
    if loop is not None and not loop.is_running() and not loop.is_closed():
        loop.close()
    if hasattr(_THREAD_LOCAL, "loop"):
        delattr(_THREAD_LOCAL, "loop")


def shutdown_async_bridge() -> None:
    """Release the process-local pool and the current thread's bridge loop."""
    global _SHARED_POOL
    with _SHARED_POOL_LOCK:
        pool, _SHARED_POOL = _SHARED_POOL, None
    if pool is not None:
        pool.shutdown(wait=True, cancel_futures=True)
    close_thread_event_loop()


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
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _THREAD_LOCAL.loop = loop
    return loop


def run_async(coro) -> Any:
    """Run an async coroutine synchronously.

    Strategy:
    1. If a loop is already running in the current thread (e.g. inside an async context),
       delegate execution safely via a persistent thread pool to avoid blocking the running loop.
    2. Otherwise use the thread-local event loop, which persists for the lifetime
       of this process thread.
    """
    try:
        running_loop = asyncio.get_running_loop()
        if running_loop.is_running():
            pool = _get_shared_pool()
            future = pool.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        # No running loop — use the persistent thread-local loop
        pass

    loop = get_shared_event_loop()
    return loop.run_until_complete(coro)


async def resolve_maybe_awaitable(value: Any) -> Any:
    """Resolve values that may be wrapped by AsyncMock/awaitable objects."""
    resolved = value
    for _ in range(3):
        if inspect.isawaitable(resolved):
            resolved = await resolved
            continue
        break
    return resolved
