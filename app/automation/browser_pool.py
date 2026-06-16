import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import Browser, BrowserContext

from app.automation.proxy_rotator import get_proxy_rotator

logger = logging.getLogger(__name__)


@dataclass
class BrowserHealthStatus:
    """Health status of a browser context."""

    context_id: str
    is_healthy: bool
    last_used_at: float | None = None
    error_count: int = 0
    success_count: int = 0
    pages_open: int = 0


@dataclass
class BrowserPoolHealth:
    """Overall health status of the browser pool."""

    total_contexts: int
    healthy_contexts: int
    unhealthy_contexts: int
    available_contexts: int
    total_errors: int
    total_successes: int
    pool_utilization: float
    context_details: list[BrowserHealthStatus] = field(default_factory=list)


class BrowserPool:
    def __init__(self, size: int = 8):
        self.size = max(1, int(size))
        self._queue: asyncio.Queue[BrowserContext] = asyncio.Queue()
        self._started = False
        self._context_health: dict[str, BrowserHealthStatus] = {}
        self._context_counter = 0
        self._health_check_interval = 60  # seconds
        self._last_health_check = 0
        self._lock = asyncio.Lock()

    async def start(self, browser: Browser, context_args: dict[str, Any] | None = None) -> None:
        if self._started:
            return
        context_args = context_args or {}
        for _ in range(self.size):
            # Fetch and apply proxy dynamically per context
            proxy_info = await get_proxy_rotator().get_next()
            ctx_args_copy = context_args.copy()
            if proxy_info:
                ctx_args_copy["proxy"] = proxy_info.to_playwright_proxy()

            context = await browser.new_context(**ctx_args_copy)
            self._context_counter += 1
            context_id = f"ctx_{self._context_counter}"
            self._context_health[context_id] = BrowserHealthStatus(
                context_id=context_id,
                is_healthy=True,
            )
            # Store context ID as metadata
            context._pool_context_id = context_id
            await self._queue.put(context)
        self._started = True
        logger.info(
            "browser_pool_started",
            extra={"extra_fields": {"size": self.size}},
        )

    async def acquire(self) -> BrowserContext:
        context = await self._queue.get()
        context_id = getattr(context, "_pool_context_id", None)
        if context_id and context_id in self._context_health:
            self._context_health[context_id].last_used_at = time.time()
        return context

    async def release(self, context: BrowserContext) -> None:
        context_id = getattr(context, "_pool_context_id", None)

        try:
            for page in context.pages:
                if page.is_closed():
                    continue
                await page.close()
        except Exception as exc:
            logger.warning(
                "browser_pool_page_close_failed",
                extra={"extra_fields": {"context_id": context_id, "error": str(exc)}},
            )

        # Update health on release
        if context_id and context_id in self._context_health:
            self._context_health[context_id].pages_open = 0

        await self._queue.put(context)

    async def close(self) -> None:
        while not self._queue.empty():
            context = await self._queue.get()
            try:
                await context.close()
            except Exception:
                pass
        self._context_health.clear()
        self._started = False
        logger.info("browser_pool_closed")

    async def check_health(self) -> BrowserPoolHealth:
        """Comprehensive health check for the browser pool."""
        async with self._lock:
            self._last_health_check = time.time()
            healthy_count = 0
            unhealthy_count = 0
            total_errors = 0
            total_successes = 0
            context_details = []

            # Check available contexts in queue
            available = self._queue.qsize()

            for _context_id, health in self._context_health.items():
                total_errors += health.error_count
                total_successes += health.success_count

                if health.is_healthy:
                    healthy_count += 1
                else:
                    unhealthy_count += 1

                context_details.append(health)

            total_contexts = len(self._context_health)
            utilization = ((total_contexts - available) / total_contexts * 100) if total_contexts > 0 else 0

            return BrowserPoolHealth(
                total_contexts=total_contexts,
                healthy_contexts=healthy_count,
                unhealthy_contexts=unhealthy_count,
                available_contexts=available,
                total_errors=total_errors,
                total_successes=total_successes,
                pool_utilization=round(utilization, 2),
                context_details=context_details,
            )

    def record_success(self, context: BrowserContext) -> None:
        """Record a successful operation for a context."""
        context_id = getattr(context, "_pool_context_id", None)
        if context_id and context_id in self._context_health:
            self._context_health[context_id].success_count += 1
            self._context_health[context_id].is_healthy = True
            self._context_health[context_id].error_count = max(0, self._context_health[context_id].error_count - 1)

    def record_failure(self, context: BrowserContext, error: str) -> None:
        """Record a failure for a context."""
        context_id = getattr(context, "_pool_context_id", None)
        if context_id and context_id in self._context_health:
            self._context_health[context_id].error_count += 1
            self._context_health[context_id].pages_open = len(context.pages)

            # Mark as unhealthy if error count exceeds threshold
            if self._context_health[context_id].error_count >= 3:
                self._context_health[context_id].is_healthy = False
                logger.warning(
                    "browser_context_marked_unhealthy",
                    extra={"extra_fields": {"context_id": context_id, "error": error}},
                )

    async def heal_unhealthy_contexts(self, browser: Browser, context_args: dict[str, Any] | None = None) -> int:
        """Recreate unhealthy browser contexts."""
        healed_count = 0
        context_args = context_args or {}

        unhealthy_ids = [ctx_id for ctx_id, health in self._context_health.items() if not health.is_healthy]

        for ctx_id in unhealthy_ids:
            try:
                # Create new context with new proxy
                proxy_info = await get_proxy_rotator().get_next()
                ctx_args_copy = context_args.copy()
                if proxy_info:
                    ctx_args_copy["proxy"] = proxy_info.to_playwright_proxy()
                new_context = await browser.new_context(**ctx_args_copy)
                self._context_counter += 1
                new_id = f"ctx_{self._context_counter}"

                # Update health tracking
                del self._context_health[ctx_id]
                self._context_health[new_id] = BrowserHealthStatus(
                    context_id=new_id,
                    is_healthy=True,
                )
                new_context._pool_context_id = new_id

                # Add to queue
                await self._queue.put(new_context)
                healed_count += 1

                logger.info(
                    "browser_context_healed",
                    extra={"extra_fields": {"old_id": ctx_id, "new_id": new_id}},
                )
            except Exception as exc:
                logger.error(
                    "browser_context_heal_failed",
                    extra={"extra_fields": {"old_id": ctx_id, "error": str(exc)}},
                )

        return healed_count

    def get_health_status(self) -> dict[str, Any]:
        """Get health status as a dictionary for API responses."""
        return {
            "pool_size": self.size,
            "available": self._queue.qsize(),
            "total_tracked": len(self._context_health),
            "last_health_check": self._last_health_check,
            "contexts": [
                {
                    "context_id": h.context_id,
                    "is_healthy": h.is_healthy,
                    "error_count": h.error_count,
                    "success_count": h.success_count,
                    "last_used_at": h.last_used_at,
                }
                for h in self._context_health.values()
            ],
        }
