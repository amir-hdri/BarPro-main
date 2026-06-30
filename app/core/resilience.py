"""
Enterprise-Grade Resilient Error Handling & State Tracking System
==================================================================
Implements crash-proof workflows with exponential backoff, explicit waits,
step-by-step state tracking, and graceful degradation.
"""

import asyncio
import functools
import logging
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, TypeVar

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.core.exceptions import ErrorCode, UTCMSException
from app.core.network import is_retryable_network_error

logger = logging.getLogger(__name__)


# ============================================================================
# STEP STATE TRACKING
# ============================================================================


class StepStatus(str, Enum):
    """Status of a workflow step."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


class ErrorCategory(str, Enum):
    """Categorized error types for precise tracking."""

    AUTH_TIMEOUT = "AUTH_TIMEOUT"
    AUTH_INVALID = "AUTH_INVALID"
    AUTH_CAPTCHA_FAILED = "AUTH_CAPTCHA_FAILED"
    CAPTCHA_MAX_RETRY = "CAPTCHA_MAX_RETRY"
    CAPTCHA_SOLVER_ERROR = "CAPTCHA_SOLVER_ERROR"
    NAVIGATION_TIMEOUT = "NAVIGATION_TIMEOUT"
    ELEMENT_NOT_FOUND = "ELEMENT_NOT_FOUND"
    ELEMENT_NOT_INTERACTABLE = "ELEMENT_NOT_INTERACTABLE"
    FORM_VALIDATION_ERROR = "FORM_VALIDATION_ERROR"
    WAYBILL_FORM_CHANGED = "WAYBILL_FORM_CHANGED"
    WAYBILL_SUBMISSION_FAILED = "WAYBILL_SUBMISSION_FAILED"
    MAP_LOADING_TIMEOUT = "MAP_LOADING_TIMEOUT"
    MAP_INTERACTION_FAILED = "MAP_INTERACTION_FAILED"
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    NETWORK_CONNECTION_LOST = "NETWORK_CONNECTION_LOST"
    BROWSER_CRASHED = "BROWSER_CRASHED"
    BROWSER_CONTEXT_LOST = "BROWSER_CONTEXT_LOST"
    PORTAL_DOWN = "PORTAL_DOWN"
    PORTAL_MAINTENANCE = "PORTAL_MAINTENANCE"
    RATE_LIMITED = "RATE_LIMITED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"


@dataclass
class StepState:
    """Tracks the state of a single workflow step."""

    step_name: str
    step_id: str
    status: StepStatus = StepStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: float | None = None
    attempts: int = 0
    max_attempts: int = 3
    error_code: str | None = None
    error_message: str | None = None
    error_category: ErrorCategory | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def start(self) -> None:
        """Mark step as in progress."""
        self.status = StepStatus.IN_PROGRESS
        self.started_at = datetime.now(UTC).replace(tzinfo=None)
        self.attempts += 1

    def complete(self, metadata: dict[str, Any] | None = None) -> None:
        """Mark step as completed."""
        self.status = StepStatus.COMPLETED
        self.completed_at = datetime.now(UTC).replace(tzinfo=None)
        if self.started_at:
            self.duration_ms = (self.completed_at - self.started_at).total_seconds() * 1000
        if metadata:
            self.metadata.update(metadata)

    def fail(
        self,
        error_code: str,
        error_message: str,
        error_category: ErrorCategory | None = None,
        retryable: bool = False,
    ) -> None:
        """Mark step as failed."""
        self.error_code = error_code
        self.error_message = error_message
        self.error_category = error_category or ErrorCategory.UNEXPECTED_ERROR

        if retryable and self.attempts < self.max_attempts:
            self.status = StepStatus.RETRYING
        else:
            self.status = StepStatus.FAILED
            self.completed_at = datetime.now(UTC).replace(tzinfo=None)
            if self.started_at:
                self.duration_ms = (self.completed_at - self.started_at).total_seconds() * 1000

    def skip(self, reason: str = "") -> None:
        """Mark step as skipped."""
        self.status = StepStatus.SKIPPED
        self.completed_at = datetime.now(UTC).replace(tzinfo=None)
        self.metadata["skip_reason"] = reason

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "step_name": self.step_name,
            "step_id": self.step_id,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": round(self.duration_ms, 2) if self.duration_ms else None,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "error_category": self.error_category.value if self.error_category else None,
            "metadata": self.metadata,
        }


@dataclass
class WorkflowState:
    """Tracks the state of an entire workflow."""

    workflow_id: str
    workflow_name: str
    status: StepStatus = StepStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: float | None = None
    steps: list[StepState] = field(default_factory=list)
    current_step: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def start(self) -> None:
        """Start the workflow."""
        self.status = StepStatus.IN_PROGRESS
        self.started_at = datetime.now(UTC).replace(tzinfo=None)

    def complete(self) -> None:
        """Complete the workflow successfully."""
        self.status = StepStatus.COMPLETED
        self.completed_at = datetime.now(UTC).replace(tzinfo=None)
        if self.started_at:
            self.duration_ms = (self.completed_at - self.started_at).total_seconds() * 1000

    def fail(self, error_code: str, error_message: str) -> None:
        """Fail the workflow."""
        self.status = StepStatus.FAILED
        self.completed_at = datetime.now(UTC).replace(tzinfo=None)
        self.error_code = error_code
        self.error_message = error_message
        if self.started_at:
            self.duration_ms = (self.completed_at - self.started_at).total_seconds() * 1000

    def add_step(self, step_name: str, step_id: str | None = None, max_attempts: int = 3) -> StepState:
        """Add a new step to the workflow."""
        step = StepState(
            step_name=step_name,
            step_id=step_id or f"step_{len(self.steps) + 1}",
            max_attempts=max_attempts,
        )
        self.steps.append(step)
        return step

    def get_current_step(self) -> StepState | None:
        """Get the currently active step."""
        for step in reversed(self.steps):
            if step.status in (StepStatus.IN_PROGRESS, StepStatus.RETRYING):
                return step
        return None

    def get_failed_step(self) -> StepState | None:
        """Get the first failed step."""
        for step in self.steps:
            if step.status == StepStatus.FAILED:
                return step
        return None

    def get_progress(self) -> dict[str, Any]:
        """Get workflow progress summary."""
        total = len(self.steps)
        completed = sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)
        failed = sum(1 for s in self.steps if s.status == StepStatus.FAILED)
        pending = sum(1 for s in self.steps if s.status == StepStatus.PENDING)

        return {
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "status": self.status.value,
            "progress_percent": round((completed / max(1, total)) * 100, 2),
            "total_steps": total,
            "completed_steps": completed,
            "failed_steps": failed,
            "pending_steps": pending,
            "current_step": self.current_step,
            "duration_ms": round(self.duration_ms, 2) if self.duration_ms else None,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": round(self.duration_ms, 2) if self.duration_ms else None,
            "current_step": self.current_step,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "steps": [step.to_dict() for step in self.steps],
            "metadata": self.metadata,
        }


# ============================================================================
# EXPONENTIAL BACKOFF & RETRY ENGINE
# ============================================================================

T = TypeVar("T")


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retryable_exceptions: tuple | None = None,
        retryable_error_codes: tuple | None = None,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions or (PlaywrightTimeoutError, PlaywrightError)
        self.retryable_error_codes = retryable_error_codes or (
            ErrorCode.NET_TIMEOUT,
            ErrorCode.NET_CONNECTION_REFUSED,
            ErrorCode.BR_NAVIGATION_TIMEOUT,
        )


def calculate_backoff_delay(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
) -> float:
    """
    Calculate exponential backoff delay with optional jitter.

    Args:
        attempt: Current attempt number (0-indexed)
        base_delay: Base delay in seconds
        max_delay: Maximum delay cap
        exponential_base: Base for exponential calculation
        jitter: Add random jitter to prevent thundering herd

    Returns:
        Delay in seconds
    """
    # Exponential backoff
    delay = base_delay * (exponential_base**attempt)

    # Add jitter (randomize by ±25%)
    if jitter:
        jitter_range = delay * 0.25
        delay += asyncio.get_event_loop().time() % 1 * jitter_range * 2 - jitter_range

    # Cap at max delay
    delay = min(delay, max_delay)

    # Ensure minimum delay
    return max(0.1, delay)


async def retry_with_backoff(
    func: Callable, *args, retry_config: RetryConfig | None = None, on_retry: Callable | None = None, **kwargs
) -> Any:
    """
    Execute function with exponential backoff retry.

    Args:
        func: Async function to execute
        *args: Positional arguments for the function
        retry_config: Retry configuration
        on_retry: Callback function called on each retry
        **kwargs: Keyword arguments for the function

    Returns:
        Result of the function call

    Raises:
        Last exception if all retries exhausted
    """
    if retry_config is None:
        retry_config = RetryConfig()

    last_exception = None

    for attempt in range(retry_config.max_retries + 1):
        try:
            return await func(*args, **kwargs)

        except Exception as exc:
            last_exception = exc

            # Check if exception is retryable
            is_retryable = (
                isinstance(exc, retry_config.retryable_exceptions)
                or is_retryable_network_error(exc)
                or (hasattr(exc, "error_code") and exc.error_code in retry_config.retryable_error_codes)
            )

            if not is_retryable or attempt >= retry_config.max_retries:
                raise

            # Calculate delay
            delay = calculate_backoff_delay(
                attempt,
                retry_config.base_delay,
                retry_config.max_delay,
                retry_config.exponential_base,
                retry_config.jitter,
            )

            # Log retry attempt
            logger.warning(
                "retry_attempt",
                extra={
                    "extra_fields": {
                        "attempt": attempt + 1,
                        "max_retries": retry_config.max_retries,
                        "delay_seconds": round(delay, 2),
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    }
                },
            )

            # Call retry callback if provided
            if on_retry:
                await on_retry(attempt, exc, delay)

            # Wait before retry
            await asyncio.sleep(delay)

    if last_exception:
        raise last_exception


# ============================================================================
# EXPLICIT WAIT ENGINE
# ============================================================================


class ExplicitWaits:
    """Advanced explicit wait utilities (no hard sleeps)."""

    @staticmethod
    async def wait_for_element_stable(
        page: Page,
        selector: str,
        timeout: float = 10000,
        stable_time: float = 0.5,
        check_interval: float = 0.1,
    ) -> bool:
        """
        Wait for element to be present and stable (not changing).

        Args:
            page: Playwright page
            selector: Element selector
            timeout: Maximum wait time in milliseconds
            stable_time: Time element must remain unchanged
            check_interval: How often to check

        Returns:
            True if element is stable
        """
        start_time = time.time()
        timeout_seconds = timeout / 1000
        stable_start = None

        while time.time() - start_time < timeout_seconds:
            try:
                element = await page.query_selector(selector)
                if element and await element.is_visible():
                    if stable_start is None:
                        stable_start = time.time()
                    elif time.time() - stable_start >= stable_time:
                        return True
                else:
                    stable_start = None
            except Exception:
                stable_start = None

            await asyncio.sleep(check_interval)

        return False

    @staticmethod
    async def wait_for_url_change(
        page: Page,
        current_url: str,
        timeout: float = 15000,
    ) -> str:
        """
        Wait for page URL to change from current value.

        Args:
            page: Playwright page
            current_url: Current URL to wait away from
            timeout: Maximum wait time in milliseconds

        Returns:
            New URL
        """
        start_time = time.time()
        timeout_seconds = timeout / 1000

        while time.time() - start_time < timeout_seconds:
            new_url = await page.url()
            if new_url != current_url:
                return new_url
            await asyncio.sleep(0.1)

        raise TimeoutError(f"URL did not change from {current_url} within {timeout}ms")

    @staticmethod
    async def wait_for_network_idle_smart(
        page: Page,
        timeout: float = 10000,
        fallback_sleep: float = 2.0,
    ) -> None:
        """
        Wait for network idle with fallback to sleep.

        Args:
            page: Playwright page
            timeout: Maximum wait for networkidle
            fallback_sleep: Sleep duration if networkidle fails
        """
        try:
            await page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=max(2000, timeout / 2))
            except Exception:
                logger.warning("wait_for_load_state_fallback_failed", exc_info=True)
            await asyncio.sleep(max(0.5, fallback_sleep))


# ============================================================================
# RESILIENT WORKFLOW EXECUTOR
# ============================================================================


class ResilientWorkflow:
    """
    Executes workflows with comprehensive error handling, state tracking,
    and automatic evidence collection on failure.
    """

    def __init__(
        self,
        workflow_name: str,
        workflow_id: str,
        page: Page | None = None,
        max_retries: int = 3,
        capture_evidence_on_failure: bool = True,
    ):
        self.workflow_name = workflow_name
        self.workflow_id = workflow_id
        self.page = page
        self.max_retries = max_retries
        self.capture_evidence = capture_evidence_on_failure
        self.state = WorkflowState(
            workflow_id=workflow_id,
            workflow_name=workflow_name,
        )
        self._evidence_collected: list[dict[str, Any]] = []

    async def execute_step(
        self,
        step_name: str,
        step_func: Callable,
        max_retries: int = 3,
        retryable_exceptions: tuple | None = None,
        capture_evidence: bool = True,
        **kwargs,
    ) -> Any:
        """
        Execute a workflow step with retry logic and state tracking.

        Args:
            step_name: Human-readable step name
            step_func: Async function to execute
            max_retries: Maximum retry attempts for this step
            retryable_exceptions: Tuple of exceptions that trigger retry
            capture_evidence: Capture screenshot/HTML on failure
            **kwargs: Additional arguments for step_func

        Returns:
            Result of step_func
        """
        step = self.state.add_step(step_name, max_attempts=max_retries)
        self.state.current_step = step_name

        for attempt in range(max_retries):
            step.start()

            try:
                # Execute the step
                result = await step_func(**kwargs)

                # Mark as complete
                step.complete(metadata={"result_type": type(result).__name__})

                # Log success
                logger.info(
                    "workflow_step_completed",
                    extra={
                        "extra_fields": {
                            "workflow_id": self.workflow_id,
                            "step_name": step_name,
                            "attempt": attempt + 1,
                            "duration_ms": step.duration_ms,
                        }
                    },
                )

                return result

            except Exception as exc:
                # Categorize the error
                error_code, error_category, is_retryable = self._categorize_error(exc, retryable_exceptions)

                step.fail(
                    error_code=error_code,
                    error_message=str(exc),
                    error_category=error_category,
                    retryable=is_retryable and attempt < max_retries - 1,
                )

                # Log failure
                logger.error(
                    "workflow_step_failed",
                    extra={
                        "extra_fields": {
                            "workflow_id": self.workflow_id,
                            "step_name": step_name,
                            "attempt": attempt + 1,
                            "max_attempts": max_retries,
                            "error_code": error_code,
                            "error_category": error_category.value if error_category else None,
                            "error_message": str(exc),
                            "retryable": is_retryable,
                        }
                    },
                )

                # Capture evidence on final failure
                if capture_evidence and self.capture_evidence and not is_retryable:
                    await self._capture_evidence(step_name, error_code)

                # If not retryable or last attempt, re-raise
                if not is_retryable or attempt >= max_retries - 1:
                    raise

                # Calculate backoff delay
                delay = calculate_backoff_delay(attempt, base_delay=1.0, max_delay=15.0)
                await asyncio.sleep(delay)

        raise RuntimeError(f"Step '{step_name}' exhausted all {max_retries} retries")

    async def execute(self, workflow_func: Callable, **kwargs) -> dict[str, Any]:
        """
        Execute the entire workflow with top-level error handling.

        Args:
            workflow_func: Main workflow async function
            **kwargs: Arguments for workflow_func

        Returns:
            Workflow result with state tracking
        """
        self.state.start()

        try:
            result = await workflow_func(**kwargs)
            self.state.complete()

            logger.info(
                "workflow_completed",
                extra={
                    "extra_fields": {
                        "workflow_id": self.workflow_id,
                        "workflow_name": self.workflow_name,
                        "duration_ms": self.state.duration_ms,
                    }
                },
            )

            return {
                "success": True,
                "result": result,
                "workflow_state": self.state.to_dict(),
                "evidence": self._evidence_collected,
            }

        except Exception as exc:
            self.state.fail(
                error_code=getattr(exc, "error_code", "UNKNOWN_ERROR"),
                error_message=str(exc),
            )

            # Capture final evidence
            if self.capture_evidence and self.page:
                await self._capture_evidence("workflow_failure", self.state.error_code)

            logger.error(
                "workflow_failed",
                extra={
                    "extra_fields": {
                        "workflow_id": self.workflow_id,
                        "workflow_name": self.workflow_name,
                        "error_code": self.state.error_code,
                        "error_message": str(exc),
                        "duration_ms": self.state.duration_ms,
                        "traceback": traceback.format_exc(),
                    }
                },
            )

            return {
                "success": False,
                "error": str(exc),
                "error_code": self.state.error_code,
                "workflow_state": self.state.to_dict(),
                "evidence": self._evidence_collected,
            }

    def _categorize_error(
        self,
        exc: Exception,
        retryable_exceptions: tuple | None = None,
    ) -> tuple:
        """Categorize an exception into error code and category."""

        # Check if it's already a structured exception
        if isinstance(exc, UTCMSException):
            return exc.error_code.value, self._map_to_category(exc.error_code), exc.retryable

        # Playwright timeout
        if isinstance(exc, PlaywrightTimeoutError):
            return (
                ErrorCode.BR_NAVIGATION_TIMEOUT.value,
                ErrorCategory.NAVIGATION_TIMEOUT,
                True,
            )

        # Network errors
        if is_retryable_network_error(exc):
            return (
                ErrorCode.NET_TIMEOUT.value,
                ErrorCategory.NETWORK_TIMEOUT,
                True,
            )

        # Check retryable exceptions
        if retryable_exceptions and isinstance(exc, retryable_exceptions):
            return (
                ErrorCode.NET_SERVICE_UNAVAILABLE.value,
                ErrorCategory.NETWORK_TIMEOUT,
                True,
            )

        # Default: unexpected error
        return (
            ErrorCode.INTERNAL_ERROR.value,
            ErrorCategory.UNEXPECTED_ERROR,
            False,
        )

    @staticmethod
    def _map_to_category(error_code: ErrorCode) -> ErrorCategory:
        """Map error code to error category."""
        mapping = {
            ErrorCode.AUTH_INVALID_CREDENTIALS: ErrorCategory.AUTH_INVALID,
            ErrorCode.AUTH_CAPTCHA_INVALID: ErrorCategory.AUTH_CAPTCHA_FAILED,
            ErrorCode.NET_TIMEOUT: ErrorCategory.NETWORK_TIMEOUT,
            ErrorCode.NET_CONNECTION_REFUSED: ErrorCategory.NETWORK_CONNECTION_LOST,
            ErrorCode.BR_NAVIGATION_TIMEOUT: ErrorCategory.NAVIGATION_TIMEOUT,
            ErrorCode.WB_FORM_ERROR: ErrorCategory.WAYBILL_FORM_CHANGED,
            ErrorCode.WB_SUBMISSION_REJECTED: ErrorCategory.WAYBILL_SUBMISSION_FAILED,
            ErrorCode.WB_MAP_INTERACTION_FAILED: ErrorCategory.MAP_INTERACTION_FAILED,
        }
        return mapping.get(error_code, ErrorCategory.UNEXPECTED_ERROR)

    async def _capture_evidence(self, step_name: str, error_code: str) -> None:
        """Capture screenshot and HTML dump on failure."""
        if not self.page:
            return

        try:
            timestamp = datetime.now(UTC).replace(tzinfo=None).strftime("%Y%m%d_%H%M%S")
            evidence_id = f"{self.workflow_id}_{step_name}_{timestamp}"

            evidence = {
                "evidence_id": evidence_id,
                "step_name": step_name,
                "error_code": error_code,
                "timestamp": timestamp,
                "url": await self.page.url(),
                "title": await self.page.title(),
            }

            # Capture full-page screenshot
            try:
                screenshot_path = f"evidence/screenshot_{evidence_id}.png"
                await self.page.screenshot(path=screenshot_path, full_page=True)
                evidence["screenshot_path"] = screenshot_path
            except Exception as e:
                evidence["screenshot_error"] = str(e)

            # Capture HTML DOM
            try:
                html_path = f"evidence/dom_{evidence_id}.html"
                html_content = await self.page.content()

                def _write_html():
                    with open(html_path, "w", encoding="utf-8") as f:
                        f.write(html_content)

                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, _write_html)

                evidence["html_path"] = html_path
            except Exception as e:
                evidence["html_error"] = str(e)

            self._evidence_collected.append(evidence)

        except Exception as e:
            logger.warning("evidence_capture_failed", extra={"extra_fields": {"step_name": step_name, "error": str(e)}})

    def get_state(self) -> WorkflowState:
        """Get current workflow state."""
        return self.state


# ============================================================================
# DECORATOR-BASED RESILIENCE
# ============================================================================


def resilient_step(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    capture_evidence: bool = True,
    error_code: str | None = None,
):
    """
    Decorator to make any async function resilient with retry and error handling.

    Usage:
        @resilient_step(max_retries=3, error_code="AUTH_TIMEOUT")
        async def login(username, password):
            ...
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)

                except Exception as exc:
                    last_exception = exc
                    is_retryable = is_retryable_network_error(exc)

                    if not is_retryable or attempt >= max_retries:
                        # Log final failure
                        logger.error(
                            "resilient_step_failed",
                            extra={
                                "extra_fields": {
                                    "function": func.__name__,
                                    "attempt": attempt + 1,
                                    "max_retries": max_retries,
                                    "error": str(exc),
                                    "error_code": error_code or type(exc).__name__,
                                }
                            },
                        )
                        raise

                    # Calculate delay
                    delay = calculate_backoff_delay(attempt, base_delay, max_delay)

                    logger.warning(
                        "resilient_step_retrying",
                        extra={
                            "extra_fields": {
                                "function": func.__name__,
                                "attempt": attempt + 1,
                                "delay_seconds": round(delay, 2),
                                "error": str(exc),
                            }
                        },
                    )

                    await asyncio.sleep(delay)

            if last_exception:
                raise last_exception

        return wrapper

    return decorator


# ============================================================================
# GRACEFUL DEGRADATION ENGINE
# ============================================================================


class GracefulDegradation:
    """Handles graceful degradation when external services are unavailable."""

    def __init__(self, max_consecutive_failures: int = 5, pause_duration: float = 300.0):
        self.max_consecutive_failures = max_consecutive_failures
        self.pause_duration = pause_duration
        self.consecutive_failures = 0
        self.last_failure_time: float | None = None
        self.is_paused = False

    async def record_success(self) -> None:
        """Record a successful operation."""
        self.consecutive_failures = 0
        self.is_paused = False

    async def record_failure(self, error_code: str = "") -> bool:
        """
        Record a failed operation.

        Returns:
            True if system should pause (too many consecutive failures)
        """
        self.consecutive_failures += 1
        self.last_failure_time = time.time()

        if self.consecutive_failures >= self.max_consecutive_failures:
            self.is_paused = True
            logger.critical(
                "graceful_degradation_pausing",
                extra={
                    "extra_fields": {
                        "consecutive_failures": self.consecutive_failures,
                        "pause_duration_seconds": self.pause_duration,
                        "error_code": error_code,
                    }
                },
            )
            return True

        return False

    async def check_and_resume(self) -> bool:
        """
        Check if paused system should resume.

        Returns:
            True if system can resume
        """
        if not self.is_paused:
            return True

        if self.last_failure_time is None:
            self.is_paused = False
            return True

        elapsed = time.time() - self.last_failure_time
        if elapsed >= self.pause_duration:
            self.is_paused = False
            self.consecutive_failures = 0
            logger.info("graceful_degradation_resumed")
            return True

        return False

    def get_status(self) -> dict[str, Any]:
        """Get degradation status."""
        return {
            "is_paused": self.is_paused,
            "consecutive_failures": self.consecutive_failures,
            "max_consecutive_failures": self.max_consecutive_failures,
            "last_failure_time": self.last_failure_time,
            "resume_in_seconds": max(0, self.pause_duration - (time.time() - self.last_failure_time))
            if self.is_paused and self.last_failure_time
            else 0,
        }
