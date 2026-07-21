import asyncio
import inspect
import threading
from typing import Any

# One event-loop per OS thread (Celery prefork workers each have their own thread)
_THREAD_LOCAL = threading.local()


def get_shared_event_loop() -> asyncio.AbstractEventLoop:
    """Return the running loop if one exists, otherwise the thread-local loop."""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
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
    1. If a loop is *already running* (e.g. nested call inside async context),
       use asyncio.get_event_loop().run_until_complete — but this is unusual for
       Celery workers.  We detect and raise clearly instead of silently creating
       orphan tasks on a second loop.
    2. Otherwise use the thread-local event loop, which persists for the lifetime
       of this Celery worker process-fork.  This prevents the
       'Future attached to a different loop' error that occurred when a new loop
       was created per-task while asyncpg connections were bound to the old loop.
    """
    try:
        # If there is already a running loop we MUST NOT call run_until_complete on it.
        running = asyncio.get_running_loop()
        # We are inside an async context — schedule and wait via a thread
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
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
