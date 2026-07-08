"""Tests for error handling utilities."""

import pytest

from app.core.error_handler import retry_on_exception, safe_execute


class TestErrorHandler:
    """Test error handling utilities."""

    def test_safe_execute_success(self):
        """Test safe_execute with successful function."""

        def success_func():
            return "success"

        result = safe_execute(success_func)
        assert result == "success"

    def test_safe_execute_with_error(self):
        """Test safe_execute with failing function."""

        def failing_func():
            raise ValueError("test error")

        result = safe_execute(failing_func, default="default_value", log_error=False)
        assert result == "default_value"

    def test_safe_execute_with_args(self):
        """Test safe_execute with function arguments."""

        def add(a, b):
            return a + b

        result = safe_execute(add, 2, 3)
        assert result == 5

    def test_retry_on_exception_success_first_try(self):
        """Test retry decorator succeeds on first try."""
        call_count = 0

        @retry_on_exception(max_attempts=3, log_attempts=False)
        def success_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = success_func()
        assert result == "success"
        assert call_count == 1

    def test_retry_on_exception_success_after_retries(self):
        """Test retry decorator succeeds after retries."""
        call_count = 0

        @retry_on_exception(max_attempts=3, delay=0.01, log_attempts=False)
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("temporary error")
            return "success"

        result = flaky_func()
        assert result == "success"
        assert call_count == 3

    def test_retry_on_exception_max_attempts_exceeded(self):
        """Test retry decorator fails after max attempts."""
        call_count = 0

        @retry_on_exception(max_attempts=3, delay=0.01, log_attempts=False)
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ValueError("permanent error")

        with pytest.raises(ValueError, match="permanent error"):
            always_fails()

        assert call_count == 3
