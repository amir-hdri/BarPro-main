"""Enhanced error handling utilities."""

import logging
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

logger = logging.getLogger(__name__)

T = TypeVar("T")


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

            assert last_exception is not None  # set on every caught attempt above
            # cast() is a runtime no-op; it guards the raise against contexts where
            # the assert above does not narrow the type for the checker.
            raise cast(BaseException, last_exception)

        return wrapper

    return decorator
