"""Resilient Playwright locator with selector fallback and retry support."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import wraps
from typing import Any, TypeVar, cast

from playwright.async_api import (
    Error as PlaywrightError,
)
from playwright.async_api import (
    Locator,
    Page,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class SmartLocatorError(RuntimeError):
    """Raised when no selector can be resolved to a stable interactable element."""


@dataclass(slots=True)
class RetryPolicy:
    """Retry settings for transient Playwright and navigation failures."""

    max_attempts: int = 3
    initial_delay_seconds: float = 0.35
    backoff_multiplier: float = 2.0


def auto_retry(
    *,
    max_attempts: int = 3,
    initial_delay_seconds: float = 0.35,
    backoff_multiplier: float = 2.0,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Retry async method on transient browser/page instability."""

    def decorator(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(fn)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> T:
            policy = getattr(self, "retry_policy", None)
            attempts = getattr(policy, "max_attempts", max_attempts)
            delay = max(0.05, getattr(policy, "initial_delay_seconds", initial_delay_seconds))
            multiplier = max(1.0, getattr(policy, "backoff_multiplier", backoff_multiplier))
            last_error: Exception | None = None

            for attempt in range(1, attempts + 1):
                try:
                    return await fn(self, *args, **kwargs)
                except Exception as exc:  # noqa: BLE001 - classification is done below
                    if not getattr(self, "_is_retryable_error", lambda _: False)(exc):
                        raise

                    last_error = exc
                    if attempt >= attempts:
                        break

                    self._logger.warning(
                        "smart_locator_retry",
                        extra={
                            "extra_fields": {
                                "attempt": attempt,
                                "max_attempts": attempts,
                                "delay_seconds": round(delay, 3),
                                "error": str(exc),
                            }
                        },
                    )
                    await asyncio.sleep(delay)
                    delay *= multiplier

            assert last_error is not None
            raise last_error

        return wrapper

    return decorator


class SmartLocator:
    """Fallback-first locator that returns only stable, interactable elements."""

    def __init__(
        self,
        *,
        retry_policy: RetryPolicy | None = None,
        stability_checks: int = 2,
        stability_interval_ms: int = 120,
        logger_instance: logging.Logger | None = None,
    ) -> None:
        self.retry_policy = retry_policy or RetryPolicy()
        self.stability_checks = max(1, stability_checks)
        self.stability_interval_ms = max(50, stability_interval_ms)
        self._logger = logger_instance or logger
        self._cache: dict[str, str] = {}  # Selector cache for performance

    @auto_retry()
    async def locate(self, page: Page, selectors: Sequence[str], timeout: int = 10_000) -> Locator:
        """
        Locate an element using multiple selector fallbacks with caching and smart recovery.
        """
        if not selectors:
            raise ValueError("selectors cannot be empty")

        # 1. Try cached successful selector first for speed (scoped by page instance ID)
        page_id = id(page)
        cache_key = f"{page_id}:{':'.join(selectors)}"
        if cache_key in self._cache:
            try:
                cached_selector = self._cache[cache_key]
                locator = await self._build_locator(page, cached_selector)
                await locator.wait_for(state="visible", timeout=2000)
                return locator
            except Exception:
                del self._cache[cache_key]

        deadline = asyncio.get_running_loop().time() + (max(1, timeout) / 1000)
        failures: list[dict[str, str]] = []

        # 2. Sequential fallback search
        for index, raw_selector in enumerate(selectors, start=1):
            remaining_ms = int((deadline - asyncio.get_running_loop().time()) * 1000)
            if remaining_ms <= 0:
                break

            selector = self._normalize_selector(raw_selector)
            per_selector_timeout = max(250, remaining_ms // max(1, len(selectors) - index + 1))

            try:
                locator = await self._build_locator(page, selector)
                await locator.wait_for(state="visible", timeout=per_selector_timeout)
                await self._ensure_interactable(locator, timeout=per_selector_timeout)

                # Update cache on success
                self._cache[cache_key] = raw_selector
                if index > 1:
                    self._logger.warning(
                        f"smart_locator_selector_fallback_success: {raw_selector} (index={index}). "
                        f"Primary selector failed. DOM layout might have changed."
                    )
                return locator
            except Exception as exc:
                failures.append({"selector": raw_selector, "error": str(exc)})
                self._logger.debug(f"Selector {index} failed: {raw_selector}")

        # 3. Smart Recovery: Fuzzy matching for text-based selectors
        text_selectors = [s for s in selectors if "text=" in s.lower() or ":" in s]
        if text_selectors:
            self._logger.info(f"smart_locator_attempting_fuzzy_recovery for selectors={selectors} (failures={failures})")
            for ts in text_selectors:
                try:
                    # Look for elements containing the text regardless of casing/exact match
                    clean_text = ts.split("=")[-1].strip("'\"") if "=" in ts else ts
                    fuzzy_selector = f"*:has-text('{clean_text}')"
                    locator = page.locator(fuzzy_selector).first
                    if await locator.is_visible(timeout=1000):
                        self._logger.info(f"smart_locator_fuzzy_recovered: {fuzzy_selector}")
                        return locator
                except Exception:
                    continue

        raise SmartLocatorError(f"No stable interactable element found for selectors after {len(failures)} failures")

    async def _ensure_interactable(self, locator: Locator, timeout: int) -> None:
        """Verify element is attached, visible, enabled, and stable in the DOM."""
        # Fast fail if detached before checks start.
        attached = await locator.evaluate("el => !!el && el.isConnected")
        if not attached:
            raise SmartLocatorError("Element is detached from DOM")

        if not await locator.is_visible():
            raise SmartLocatorError("Element is not visible")

        if not await locator.is_enabled():
            raise SmartLocatorError("Element is not enabled")

        box = await locator.bounding_box()
        if box is None:
            raise SmartLocatorError("Element has no bounding box")

        # Guard against stale/detached elements during layout shifts.
        remaining_checks = self.stability_checks
        while remaining_checks > 0:
            await locator.wait_for(state="attached", timeout=timeout)

            before = await locator.bounding_box()
            if before is None:
                raise SmartLocatorError("Element became non-interactable during stability check")

            await asyncio.sleep(self.stability_interval_ms / 1000)

            after = await locator.bounding_box()
            if after is None:
                raise SmartLocatorError("Element detached during stability check")

            connected = await locator.evaluate("el => !!el && el.isConnected")
            if not connected:
                raise SmartLocatorError("Element detached during stability check")

            if not self._boxes_close(before, after):
                raise SmartLocatorError("Element is unstable (moving/changing layout)")

            remaining_checks -= 1

        # Additional actionability check that catches many click/fill edge cases.
        await locator.scroll_into_view_if_needed(timeout=timeout)

    def _is_retryable_error(self, exc: Exception) -> bool:
        """Classify transient errors that should trigger automatic retries."""
        if isinstance(exc, PlaywrightTimeoutError | asyncio.TimeoutError):
            return True

        if isinstance(exc, PlaywrightError):
            text = str(exc).lower()
            retry_markers = (
                "execution context was destroyed",
                "navigation",
                "target page, context or browser has been closed",
                "element is not attached",
                "frame was detached",
                "net::",
                "timeout",
            )
            return any(marker in text for marker in retry_markers)

        text = str(exc).lower()
        return any(
            marker in text
            for marker in (
                "detached",
                "stale",
                "navigation",
                "connection reset",
                "temporarily unavailable",
            )
        )

    @staticmethod
    def _normalize_selector(selector: str) -> str:
        """Normalize selector shortcuts for XPath and text-based lookup."""
        cleaned = selector.strip()
        if cleaned.startswith("//"):
            return f"xpath={cleaned}"
        if cleaned.startswith("(") and "//" in cleaned:
            return f"xpath={cleaned}"
        if cleaned.lower().startswith("text=") or cleaned.lower().startswith("xpath="):
            return cleaned
        return cleaned

    @staticmethod
    async def _resolve_maybe_awaitable(value: Any) -> Any:
        resolved = value
        for _ in range(3):
            if inspect.isawaitable(resolved):
                resolved = await resolved
                continue
            break
        return resolved

    async def _build_locator(self, page: Page, selector: str) -> Locator:
        raw_locator = page.locator(selector)
        locator = await self._resolve_maybe_awaitable(raw_locator)
        first_candidate = getattr(locator, "first", locator)
        return cast("Locator", await self._resolve_maybe_awaitable(first_candidate))

    @staticmethod
    # Mapping[str, Any] rather than Mapping[str, float] because callers pass
    # Playwright's FloatRect TypedDict, which only widens to Mapping[str, object].
    def _boxes_close(before: Mapping[str, Any], after: Mapping[str, Any], tolerance: float = 0.5) -> bool:
        """Allow tiny layout jitter while rejecting meaningful movement/resizing."""
        keys = ("x", "y", "width", "height")
        return all(abs(float(before[key]) - float(after[key])) <= tolerance for key in keys)
