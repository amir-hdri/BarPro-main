import asyncio
import time
from dataclasses import dataclass


class CircuitOpenError(Exception):
    def __init__(self, retry_after_seconds: float):
        super().__init__("circuit_open")
        self.retry_after_seconds = retry_after_seconds


@dataclass
class CircuitSnapshot:
    state: str
    failure_count: int
    retry_after_seconds: float


class AsyncCircuitBreaker:
    def __init__(
        self,
        enabled: bool = True,
        failure_threshold: int = 5,
        recovery_seconds: int = 30,
        half_open_max_calls: int = 1,
    ):
        self._enabled = enabled
        self._failure_threshold = max(1, failure_threshold)
        self._recovery_seconds = max(1, recovery_seconds)
        self._half_open_max_calls = max(1, half_open_max_calls)

        self._state = "closed"
        self._failure_count = 0
        self._opened_at: float | None = None
        self._half_open_inflight = 0
        self._lock = asyncio.Lock()

    async def allow_request(self) -> None:
        if not self._enabled:
            return

        async with self._lock:
            self._move_open_to_half_open_if_ready()

            if self._state == "open":
                raise CircuitOpenError(retry_after_seconds=self._remaining_open_seconds())

            if self._state == "half_open":
                if self._half_open_inflight >= self._half_open_max_calls:
                    raise CircuitOpenError(retry_after_seconds=self._remaining_open_seconds())
                self._half_open_inflight += 1

    async def record_success(self) -> None:
        if not self._enabled:
            return

        async with self._lock:
            self._state = "closed"
            self._failure_count = 0
            self._opened_at = None
            self._half_open_inflight = 0

    async def record_failure(self) -> None:
        if not self._enabled:
            return

        async with self._lock:
            if self._state == "half_open":
                self._state = "open"
                self._opened_at = time.monotonic()
                self._half_open_inflight = 0
                self._failure_count = self._failure_threshold
                return

            self._failure_count += 1
            if self._failure_count >= self._failure_threshold:
                self._state = "open"
                self._opened_at = time.monotonic()
                self._half_open_inflight = 0

    async def snapshot(self) -> CircuitSnapshot:
        async with self._lock:
            self._move_open_to_half_open_if_ready()
            return CircuitSnapshot(
                state=self._state,
                failure_count=self._failure_count,
                retry_after_seconds=self._remaining_open_seconds(),
            )

    def _remaining_open_seconds(self) -> float:
        if self._state != "open" or self._opened_at is None:
            return 0.0
        elapsed = time.monotonic() - self._opened_at
        return max(0.0, self._recovery_seconds - elapsed)

    def _move_open_to_half_open_if_ready(self) -> None:
        if self._state != "open" or self._opened_at is None:
            return
        if (time.monotonic() - self._opened_at) >= self._recovery_seconds:
            self._state = "half_open"
            self._half_open_inflight = 0
