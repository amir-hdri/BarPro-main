import asyncio
import inspect
from typing import Any

_SHARED_EVENT_LOOP: asyncio.AbstractEventLoop | None = None


def get_shared_event_loop() -> asyncio.AbstractEventLoop:
    global _SHARED_EVENT_LOOP
    try:
        # Check if there is already a running event loop in this thread
        return asyncio.get_running_loop()
    except RuntimeError:
        pass

    if _SHARED_EVENT_LOOP is None or _SHARED_EVENT_LOOP.is_closed():
        _SHARED_EVENT_LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_SHARED_EVENT_LOOP)
    return _SHARED_EVENT_LOOP


def run_async(coro) -> Any:
    """Run an async coroutine synchronously on the shared event loop."""
    loop = get_shared_event_loop()
    try:
        return loop.run_until_complete(coro)
    except RuntimeError as e:
        if "already running" in str(e):
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
        raise


async def resolve_maybe_awaitable(value: Any) -> Any:
    """Resolve values that may be wrapped by AsyncMock/awaitable objects."""
    resolved = value
    for _ in range(3):
        if inspect.isawaitable(resolved):
            resolved = await resolved
            continue
        break
    return resolved
