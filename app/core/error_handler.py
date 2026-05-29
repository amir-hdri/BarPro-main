"""Enhanced error handling utilities."""
import logging
import traceback
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from app.core.alerts import alert_manager
from app.core.error_taxonomy import ErrorCategory, classify_exception

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ErrorReporter:
    """Centralized error reporting and alerting system."""

    @classmethod
    def report(cls, exception: Exception, context: dict[str, Any] | None = None, severity: str = "error"):
        category, retryable = classify_exception(exception)

        error_data = {
            "error_type": type(exception).__name__,
            "error_message": str(exception),
            "category": category.value,
            "retryable": retryable,
            "traceback": traceback.format_exc(),
        }
        if context:
            error_data.update(context)

        # Log to centralized logging
        logger.log(
            logging.ERROR if severity == "error" else logging.CRITICAL,
            f"Centralized Error Report: {category.value} - {str(exception)}",
            extra={"extra_fields": error_data},
            exc_info=True
        )

        # Critical errors trigger alerts
        critical_categories = {
            ErrorCategory.BOT_DETECTED,
            ErrorCategory.AUTH_FAILURE,
            ErrorCategory.WORKER_RESOURCE_ERROR
        }

        if severity == "critical" or category in critical_categories:
            alert_manager.emit(
                severity="critical" if severity == "critical" else "high",
                title=f"Critical Automation Error: {category.value}",
                payload=error_data
            )


def safe_execute(
    func: Callable[..., T],
    *args: Any,
    default: T | None = None,
    log_error: bool = True,
    error_message: str | None = None,
    **kwargs: Any,
) -> T | None:
    """
    Safely execute a function and return default value on error.
    
    Args:
        func: Function to execute
        *args: Positional arguments for func
        default: Default value to return on error
        log_error: Whether to log errors
        error_message: Custom error message
        **kwargs: Keyword arguments for func
    
    Returns:
        Function result or default value
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if log_error:
            msg = error_message or f"Error executing {func.__name__}"
            logger.error(
                msg,
                extra={
                    "extra_fields": {
                        "function": func.__name__,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                },
                exc_info=True,
            )
        return default


def retry_on_exception(
    max_attempts: int = 3,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    delay: float = 1.0,
    backoff: float = 2.0,
    log_attempts: bool = True,
) -> Callable:
    """
    Decorator to retry function on specific exceptions.
    
    Args:
        max_attempts: Maximum number of attempts
        exceptions: Tuple of exception types to catch
        delay: Initial delay between retries (seconds)
        backoff: Multiplier for delay after each retry
        log_attempts: Whether to log retry attempts
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            import time

            current_delay = delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_attempts:
                        if log_attempts:
                            logger.error(
                                f"Function {func.__name__} failed after {max_attempts} attempts",
                                extra={
                                    "extra_fields": {
                                        "function": func.__name__,
                                        "attempts": max_attempts,
                                        "error": str(e),
                                    }
                                },
                                exc_info=True,
                            )
                        raise

                    if log_attempts:
                        logger.warning(
                            f"Attempt {attempt}/{max_attempts} failed for {func.__name__}, retrying in {current_delay}s",
                            extra={
                                "extra_fields": {
                                    "function": func.__name__,
                                    "attempt": attempt,
                                    "max_attempts": max_attempts,
                                    "delay": current_delay,
                                    "error": str(e),
                                }
                            },
                        )

                    time.sleep(current_delay)
                    current_delay *= backoff

            raise last_exception

        return wrapper
    return decorator


async def async_retry_on_exception(
    max_attempts: int = 3,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    delay: float = 1.0,
    backoff: float = 2.0,
    log_attempts: bool = True,
) -> Callable:
    """
    Async decorator to retry function on specific exceptions.
    
    Args:
        max_attempts: Maximum number of attempts
        exceptions: Tuple of exception types to catch
        delay: Initial delay between retries (seconds)
        backoff: Multiplier for delay after each retry
        log_attempts: Whether to log retry attempts
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            import asyncio

            current_delay = delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_attempts:
                        if log_attempts:
                            logger.error(
                                f"Async function {func.__name__} failed after {max_attempts} attempts",
                                extra={
                                    "extra_fields": {
                                        "function": func.__name__,
                                        "attempts": max_attempts,
                                        "error": str(e),
                                    }
                                },
                                exc_info=True,
                            )
                        raise

                    if log_attempts:
                        logger.warning(
                            f"Attempt {attempt}/{max_attempts} failed for {func.__name__}, retrying in {current_delay}s",
                            extra={
                                "extra_fields": {
                                    "function": func.__name__,
                                    "attempt": attempt,
                                    "max_attempts": max_attempts,
                                    "delay": current_delay,
                                    "error": str(e),
                                }
                            },
                        )

                    await asyncio.sleep(current_delay)
                    current_delay *= backoff

            raise last_exception

        return wrapper
    return decorator


def log_exception_context(
    logger_instance: logging.Logger,
    message: str,
    exception: Exception,
    extra_context: dict | None = None,
) -> None:
    """
    Log exception with full context and traceback, and report via centralized system.
    
    Args:
        logger_instance: Logger to use
        message: Error message
        exception: Exception that occurred
        extra_context: Additional context to log
    """
    context = {
        "error_type": type(exception).__name__,
        "error_message": str(exception),
        "traceback": traceback.format_exc(),
    }

    if extra_context:
        context.update(extra_context)

    # Use the centralized error reporter
    ErrorReporter.report(exception, context=context)
