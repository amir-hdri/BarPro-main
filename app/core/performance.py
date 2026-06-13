"""Performance monitoring and optimization utilities."""
import asyncio
import functools
import logging
import time
from collections.abc import Callable
from contextlib import asynccontextmanager, contextmanager
from typing import Any

logger = logging.getLogger(__name__)


@contextmanager
def timer(operation_name: str, log_level: int = logging.INFO):
    """
    Context manager to time operations.

    Usage:
        with timer("database_query"):
            result = db.query(...)
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = (time.perf_counter() - start) * 1000  # Convert to ms
        logger.log(
            log_level,
            f"{operation_name} completed",
            extra={"extra_fields": {"operation": operation_name, "duration_ms": round(elapsed, 2)}},
        )


@asynccontextmanager
async def async_timer(operation_name: str, log_level: int = logging.INFO):
    """
    Async context manager to time operations.

    Usage:
        async with async_timer("api_call"):
            result = await api.fetch(...)
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = (time.perf_counter() - start) * 1000  # Convert to ms
        logger.log(
            log_level,
            f"{operation_name} completed",
            extra={"extra_fields": {"operation": operation_name, "duration_ms": round(elapsed, 2)}},
        )


def measure_time(func: Callable | None = None, *, operation_name: str | None = None):
    """
    Decorator to measure function execution time.

    Usage:
        @measure_time
        def my_function():
            ...

        @measure_time(operation_name="custom_name")
        def another_function():
            ...
    """
    def decorator(f: Callable) -> Callable:
        name = operation_name or f.__name__

        @functools.wraps(f)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with timer(name):
                return f(*args, **kwargs)

        return wrapper

    if func is None:
        return decorator
    return decorator(func)


def measure_async_time(func: Callable | None = None, *, operation_name: str | None = None):
    """
    Decorator to measure async function execution time.

    Usage:
        @measure_async_time
        async def my_async_function():
            ...
    """
    def decorator(f: Callable) -> Callable:
        name = operation_name or f.__name__

        @functools.wraps(f)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            async with async_timer(name):
                return await f(*args, **kwargs)

        return wrapper

    if func is None:
        return decorator
    return decorator(func)


class PerformanceMonitor:
    """Monitor and track performance metrics."""

    def __init__(self):
        self._metrics = {}
        self._lock = asyncio.Lock()

    async def record_metric(self, name: str, value: float, tags: dict | None = None):
        """Record a performance metric."""
        async with self._lock:
            if name not in self._metrics:
                self._metrics[name] = {
                    "count": 0,
                    "total": 0.0,
                    "min": float("inf"),
                    "max": float("-inf"),
                    "avg": 0.0,
                }

            metric = self._metrics[name]
            metric["count"] += 1
            metric["total"] += value
            metric["min"] = min(metric["min"], value)
            metric["max"] = max(metric["max"], value)
            metric["avg"] = metric["total"] / metric["count"]

    async def get_metrics(self) -> dict:
        """Get all recorded metrics."""
        async with self._lock:
            return dict(self._metrics)

    async def reset_metrics(self):
        """Reset all metrics."""
        async with self._lock:
            self._metrics.clear()


# Global performance monitor instance
performance_monitor = PerformanceMonitor()


def log_slow_operation(threshold_ms: float = 1000):
    """
    Decorator to log operations that exceed a time threshold.

    Args:
        threshold_ms: Threshold in milliseconds
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            result = await func(*args, **kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000

            if elapsed_ms > threshold_ms:
                logger.warning(
                    f"Slow operation detected: {func.__name__}",
                    extra={
                        "extra_fields": {
                            "function": func.__name__,
                            "duration_ms": round(elapsed_ms, 2),
                            "threshold_ms": threshold_ms,
                        }
                    },
                )

            await performance_monitor.record_metric(func.__name__, elapsed_ms)
            return result

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            result = func(*args, **kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000

            if elapsed_ms > threshold_ms:
                logger.warning(
                    f"Slow operation detected: {func.__name__}",
                    extra={
                        "extra_fields": {
                            "function": func.__name__,
                            "duration_ms": round(elapsed_ms, 2),
                            "threshold_ms": threshold_ms,
                        }
                    },
                )

            return result

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
