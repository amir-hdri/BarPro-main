"""Captcha interception + solver integration with circuit breaker protection."""
from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence

import aiohttp
from playwright.async_api import Locator, Page

from app.automation.selectors import AuthSelectors
from app.bot.core.smart_locator import SmartLocator, SmartLocatorError
from app.core.logging import monitoring_extra

logger = logging.getLogger(__name__)


class CaptchaSolveStatus(str, Enum):
    NOT_FOUND = "not_found"
    SOLVED = "solved"
    FAILED = "failed"
    CIRCUIT_OPEN = "circuit_open"


@dataclass(slots=True)
class CaptchaSolveResult:
    status: CaptchaSolveStatus
    solution: Optional[str] = None
    provider: str = "mock_solver"
    error: Optional[str] = None
    selector_used: Optional[str] = None


@dataclass(slots=True)
class CircuitBreakerConfig:
    failure_threshold: int = 3
    recovery_timeout_seconds: int = 60


class SolverCircuitBreaker:
    """Simple circuit breaker for external solver reliability control."""

    def __init__(self, config: CircuitBreakerConfig | None = None) -> None:
        self._config = config or CircuitBreakerConfig()
        self._failure_count = 0
        self._opened_at_monotonic: Optional[float] = None

    def allow_request(self) -> bool:
        if self._opened_at_monotonic is None:
            return True
        elapsed = time.monotonic() - self._opened_at_monotonic
        if elapsed >= self._config.recovery_timeout_seconds:
            # Half-open: allow one trial request.
            self._opened_at_monotonic = None
            self._failure_count = 0
            return True
        return False

    def record_success(self) -> None:
        self._failure_count = 0
        self._opened_at_monotonic = None

    def record_failure(self) -> None:
        self._failure_count += 1
        if self._failure_count >= self._config.failure_threshold:
            self._opened_at_monotonic = time.monotonic()

    @property
    def is_open(self) -> bool:
        return not self.allow_request()

    @property
    def failure_count(self) -> int:
        return self._failure_count


class CaptchaInterceptor:
    """Detect, capture and solve captcha with safe-failure behavior."""

    def __init__(
        self,
        solver_url: str,
        *,
        smart_locator: SmartLocator | None = None,
        request_timeout_seconds: float = 8.0,
        solver_retries: int = 3,
        circuit_breaker: SolverCircuitBreaker | None = None,
    ) -> None:
        self.solver_url = solver_url
        self.smart_locator = smart_locator or SmartLocator()
        self.request_timeout_seconds = max(1.0, request_timeout_seconds)
        self.solver_retries = max(1, solver_retries)
        self.circuit_breaker = circuit_breaker or SolverCircuitBreaker()

    async def detect_captcha(
        self,
        page: Page,
        *,
        image_selectors: Sequence[str] = AuthSelectors.CAPTCHA_IMAGE_SELECTORS,
        timeout_ms: int = 1500,
    ) -> Optional[Locator]:
        """Return captcha image locator if present, otherwise None."""
        try:
            locator = await self.smart_locator.locate(page, list(image_selectors), timeout=timeout_ms)
            return locator
        except Exception:
            return None

    async def capture_captcha_base64(self, page: Page, captcha_locator: Locator) -> Optional[str]:
        """Capture captcha without depending on full-page screenshot/font loading."""
        overall_started_at = time.perf_counter()
        try:
            capture_started_at = time.perf_counter()
            raw_base64 = await captcha_locator.evaluate(
                """async el => {
                    if (!el) return null;
                    const tag = (el.tagName || '').toLowerCase();

                    if (tag === 'img') {
                        const img = el;
                        const src = img.currentSrc || img.src || '';
                        if (src.startsWith('data:image/')) {
                            return {
                                source: 'img-src',
                                data: src.split(',')[1] || null,
                            };
                        }
                        if (img.complete && img.naturalWidth > 0) {
                            const canvas = document.createElement('canvas');
                            canvas.width = img.naturalWidth;
                            canvas.height = img.naturalHeight;
                            const ctx = canvas.getContext('2d');
                            ctx.drawImage(img, 0, 0);
                            const dataUrl = canvas.toDataURL('image/png');
                            return {
                                source: 'canvas',
                                data: dataUrl.split(',')[1] || null,
                            };
                        }
                    }

                    const canvasLike = tag === 'canvas' ? el : el.querySelector('canvas');
                    if (canvasLike && typeof canvasLike.toDataURL === 'function') {
                        const dataUrl = canvasLike.toDataURL('image/png');
                        return {
                            source: 'canvas',
                            data: dataUrl.split(',')[1] || null,
                        };
                    }

                    return null;
                }"""
            )
            elapsed_ms = round((time.perf_counter() - capture_started_at) * 1000, 2)
            if isinstance(raw_base64, dict):
                source = str(raw_base64.get("source") or "unknown")
                value = raw_base64.get("data")
                logger.info(
                    "captcha_capture_attempt",
                    extra=monitoring_extra(
                        "captcha_capture_attempt",
                        category="captcha",
                        payload={
                            "source": source,
                            "duration_ms": elapsed_ms,
                            "success": bool(value),
                        },
                        tags={"component": "captcha_interceptor"},
                        source=source,
                        duration_ms=elapsed_ms,
                        success=bool(value),
                    ),
                )
                if value:
                    logger.info(
                        "captcha_capture_completed",
                        extra=monitoring_extra(
                            "captcha_capture_completed",
                            category="captcha",
                            payload={
                                "source": source,
                                "duration_ms": round((time.perf_counter() - overall_started_at) * 1000, 2),
                            },
                            tags={"component": "captcha_interceptor"},
                            source=source,
                            duration_ms=round((time.perf_counter() - overall_started_at) * 1000, 2),
                        ),
                    )
                    return str(value)
            elif raw_base64:
                logger.info(
                    "captcha_capture_attempt",
                    extra=monitoring_extra(
                        "captcha_capture_attempt",
                        category="captcha",
                        payload={"source": "canvas", "duration_ms": elapsed_ms, "success": True},
                        tags={"component": "captcha_interceptor"},
                        source="canvas",
                        duration_ms=elapsed_ms,
                        success=True,
                    ),
                )
                return str(raw_base64)
        except Exception as exc:
            logger.info(
                "captcha_capture_attempt",
                extra=monitoring_extra(
                    "captcha_capture_attempt",
                    category="captcha",
                    payload={
                        "source": "canvas",
                        "duration_ms": round((time.perf_counter() - overall_started_at) * 1000, 2),
                        "success": False,
                        "error": str(exc),
                    },
                    tags={"component": "captcha_interceptor"},
                    source="canvas",
                    duration_ms=round((time.perf_counter() - overall_started_at) * 1000, 2),
                    success=False,
                    error=str(exc),
                ),
            )

        try:
            capture_started_at = time.perf_counter()
            image_bytes = await captcha_locator.screenshot(timeout=5000)
            if isinstance(image_bytes, (bytes, bytearray)):
                logger.info(
                    "captcha_capture_attempt",
                    extra=monitoring_extra(
                        "captcha_capture_attempt",
                        category="captcha",
                        payload={
                            "source": "locator.screenshot",
                            "duration_ms": round((time.perf_counter() - capture_started_at) * 1000, 2),
                            "success": True,
                        },
                        tags={"component": "captcha_interceptor"},
                        source="locator.screenshot",
                        duration_ms=round((time.perf_counter() - capture_started_at) * 1000, 2),
                        success=True,
                    ),
                )
                return base64.b64encode(bytes(image_bytes)).decode("utf-8")
        except Exception as exc:
            logger.info(
                "captcha_capture_attempt",
                extra=monitoring_extra(
                    "captcha_capture_attempt",
                    category="captcha",
                    payload={
                        "source": "locator.screenshot",
                        "duration_ms": round((time.perf_counter() - overall_started_at) * 1000, 2),
                        "success": False,
                        "error": str(exc),
                    },
                    tags={"component": "captcha_interceptor"},
                    source="locator.screenshot",
                    duration_ms=round((time.perf_counter() - overall_started_at) * 1000, 2),
                    success=False,
                    error=str(exc),
                ),
            )

        bbox = await captcha_locator.bounding_box()
        if bbox is None:
            return None

        clip = {
            "x": max(0, float(bbox["x"])),
            "y": max(0, float(bbox["y"])),
            "width": max(1.0, float(bbox["width"])),
            "height": max(1.0, float(bbox["height"])),
        }
        capture_started_at = time.perf_counter()
        image_bytes = await page.screenshot(clip=clip, timeout=5000)
        logger.info(
            "captcha_capture_attempt",
            extra=monitoring_extra(
                "captcha_capture_attempt",
                category="captcha",
                payload={
                    "source": "page.screenshot",
                    "duration_ms": round((time.perf_counter() - capture_started_at) * 1000, 2),
                    "success": isinstance(image_bytes, (bytes, bytearray)),
                },
                tags={"component": "captcha_interceptor"},
                source="page.screenshot",
                duration_ms=round((time.perf_counter() - capture_started_at) * 1000, 2),
                success=isinstance(image_bytes, (bytes, bytearray)),
            ),
        )
        if not isinstance(image_bytes, (bytes, bytearray)):
            return None
        return base64.b64encode(bytes(image_bytes)).decode("utf-8")

    async def solve_captcha(self, page: Page) -> CaptchaSolveResult:
        """Detect and solve captcha; fail fast if circuit is open."""
        captcha_locator = await self.detect_captcha(page)
        if captcha_locator is None:
            return CaptchaSolveResult(status=CaptchaSolveStatus.NOT_FOUND)

        image_base64 = await self.capture_captcha_base64(page, captcha_locator)
        if not image_base64:
            return CaptchaSolveResult(
                status=CaptchaSolveStatus.FAILED,
                error="captcha_capture_failed",
            )

        if not self.circuit_breaker.allow_request():
            logger.warning("captcha_solver_circuit_open")
            return CaptchaSolveResult(
                status=CaptchaSolveStatus.CIRCUIT_OPEN,
                error="solver_circuit_open",
            )

        try:
            solution = await self._request_solver(image_base64)
            self.circuit_breaker.record_success()
            return CaptchaSolveResult(
                status=CaptchaSolveStatus.SOLVED,
                solution=solution,
            )
        except Exception as exc:  # noqa: BLE001
            self.circuit_breaker.record_failure()
            logger.warning(
                "captcha_solver_failed",
                extra={"extra_fields": {"error": str(exc), "failure_count": self.circuit_breaker.failure_count}},
            )
            if not self.circuit_breaker.allow_request():
                return CaptchaSolveResult(
                    status=CaptchaSolveStatus.CIRCUIT_OPEN,
                    error=str(exc),
                )
            return CaptchaSolveResult(
                status=CaptchaSolveStatus.FAILED,
                error=str(exc),
            )

    async def _request_solver(self, image_base64: str) -> str:
        """Call external mock solver with retries and strict timeout."""
        timeout = aiohttp.ClientTimeout(total=self.request_timeout_seconds)
        last_error: Optional[Exception] = None

        for attempt in range(1, self.solver_retries + 1):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        self.solver_url,
                        json={"image_base64": image_base64},
                    ) as response:
                        payload = await response.json(content_type=None)
                        if response.status >= 400:
                            raise RuntimeError(f"solver_http_{response.status}: {payload}")

                        text = str(payload.get("text") or payload.get("solution") or "").strip()
                        if not text:
                            raise RuntimeError(f"solver_empty_solution: {payload}")

                        logger.info(
                            "captcha_solver_success",
                            extra={
                                "extra_fields": {
                                    "attempt": attempt,
                                    "solver_url": self.solver_url,
                                }
                            },
                        )
                        return text
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "captcha_solver_attempt_failed",
                    extra={
                        "extra_fields": {
                            "attempt": attempt,
                            "max_attempts": self.solver_retries,
                            "error": str(exc),
                        }
                    },
                )

        raise RuntimeError(f"solver_unavailable_after_retries: {last_error}")

    async def solve_and_fill(
        self,
        page: Page,
        captcha_input_selectors: Sequence[str] = AuthSelectors.CAPTCHA_SELECTORS,
        timeout_ms: int = 2500,
    ) -> CaptchaSolveResult:
        """Solve captcha and fill its input field if available."""
        try:
            input_locator = await self.smart_locator.locate(page, list(captcha_input_selectors), timeout=timeout_ms)
        except SmartLocatorError:
            return CaptchaSolveResult(status=CaptchaSolveStatus.NOT_FOUND)

        solve_result = await self.solve_captcha(page)
        if solve_result.status != CaptchaSolveStatus.SOLVED or not solve_result.solution:
            return solve_result

        await input_locator.fill("")
        await input_locator.fill(solve_result.solution)
        return solve_result
