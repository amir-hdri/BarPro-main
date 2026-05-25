import asyncio
import random
from contextlib import asynccontextmanager
from dataclasses import dataclass

from app.core.config import utcms_config


@dataclass
class TrafficSnapshot:
    active_requests: int
    queued_requests: int
    next_allowed_in_seconds: float
    blocked_for_seconds: float
    active_safe: int = 0
    active_full: int = 0
    queued_safe: int = 0
    queued_full: int = 0


class WaybillTrafficController:
    """Compliant load control: concurrency limit, pacing, and temporary backoff."""

    def __init__(self):
        self._semaphore = asyncio.Semaphore(max(1, utcms_config.WAYBILL_MAX_CONCURRENT))
        self._lock = asyncio.Lock()
        self._next_allowed_at = 0.0
        self._blocked_until = 0.0
        self._active_requests = 0
        self._queued_requests = 0
        self._active_by_mode = {"safe": 0, "full": 0}
        self._queued_by_mode = {"safe": 0, "full": 0}

    async def _wait_for_pacing(self):
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            wait_seconds = max(0.0, self._next_allowed_at - now, self._blocked_until - now)
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)

            jitter = random.uniform(0, max(0.0, utcms_config.WAYBILL_JITTER_SECONDS))
            gap = max(0.0, utcms_config.WAYBILL_MIN_GAP_SECONDS) + jitter
            self._next_allowed_at = loop.time() + gap

    async def acquire(self, mode: str = "safe"):
        normalized_mode = "full" if mode == "full" else "safe"
        self._queued_requests += 1
        self._queued_by_mode[normalized_mode] += 1

        await self._semaphore.acquire()

        self._queued_requests = max(0, self._queued_requests - 1)
        self._queued_by_mode[normalized_mode] = max(0, self._queued_by_mode[normalized_mode] - 1)
        self._active_requests += 1
        self._active_by_mode[normalized_mode] += 1

        try:
            await self._wait_for_pacing()
        except Exception:
            self._active_requests = max(0, self._active_requests - 1)
            self._active_by_mode[normalized_mode] = max(0, self._active_by_mode[normalized_mode] - 1)
            self._semaphore.release()
            raise

    def release(self, mode: str = "safe"):
        normalized_mode = "full" if mode == "full" else "safe"
        if self._active_requests > 0:
            self._active_requests -= 1
        self._active_by_mode[normalized_mode] = max(0, self._active_by_mode[normalized_mode] - 1)
        self._semaphore.release()

    async def mark_temporary_block(self, multiplier: float = 1.0):
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            base = max(0.0, utcms_config.WAYBILL_BLOCK_BACKOFF_SECONDS)
            max_backoff = max(base, utcms_config.WAYBILL_BLOCK_BACKOFF_MAX_SECONDS)
            backoff = min(max_backoff, base * max(1.0, multiplier))
            self._blocked_until = max(self._blocked_until, now + backoff)

    def snapshot(self) -> TrafficSnapshot:
        loop = asyncio.get_running_loop()
        now = loop.time()
        return TrafficSnapshot(
            active_requests=self._active_requests,
            queued_requests=self._queued_requests,
            next_allowed_in_seconds=max(0.0, self._next_allowed_at - now),
            blocked_for_seconds=max(0.0, self._blocked_until - now),
            active_safe=self._active_by_mode["safe"],
            active_full=self._active_by_mode["full"],
            queued_safe=self._queued_by_mode["safe"],
            queued_full=self._queued_by_mode["full"],
        )

    @asynccontextmanager
    async def slot(self, mode: str = "safe"):
        await self.acquire(mode=mode)
        try:
            yield
        finally:
            self.release(mode=mode)


waybill_traffic_controller = WaybillTrafficController()
