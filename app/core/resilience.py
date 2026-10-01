"""
Enterprise-Grade Resilient Error Handling & State Tracking System
==================================================================
Implements crash-proof workflows with exponential backoff, explicit waits,
step-by-step state tracking, and graceful degradation.
"""

import asyncio
import functools
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, TypeVar

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.core.exceptions import ErrorCode
from app.core.network import is_retryable_network_error

logger = logging.getLogger(__name__)


# ============================================================================
# STEP STATE TRACKING
# ============================================================================


class StepStatus(StrEnum):
    """Status of a workflow step."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


class ErrorCategory(StrEnum):
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
