"""Structured error codes for UTCMS automation errors."""

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """Structured error codes for all UTCMS errors."""

    # Authentication errors (AUTH_*)
    AUTH_INVALID_CREDENTIALS = "AUTH_INVALID_CREDENTIALS"
    AUTH_SESSION_EXPIRED = "AUTH_SESSION_EXPIRED"
    AUTH_CAPTCHA_REQUIRED = "AUTH_CAPTCHA_REQUIRED"
    AUTH_CAPTCHA_INVALID = "AUTH_CAPTCHA_INVALID"
    AUTH_MISSING_CREDENTIALS = "AUTH_MISSING_CREDENTIALS"
    AUTH_SERVICE_UNAVAILABLE = "AUTH_SERVICE_UNAVAILABLE"

    # Network errors (NET_*)
    NET_TIMEOUT = "NET_TIMEOUT"
    NET_CONNECTION_REFUSED = "NET_CONNECTION_REFUSED"
    NET_DNS_FAILURE = "NET_DNS_FAILURE"
    NET_CONNECTION_RESET = "NET_CONNECTION_RESET"
    NET_SERVICE_UNAVAILABLE = "NET_SERVICE_UNAVAILABLE"

    # Waybill errors (WB_*)
    WB_VALIDATION_FAILED = "WB_VALIDATION_FAILED"
    WB_FORM_ERROR = "WB_FORM_ERROR"
    WB_MAP_INTERACTION_FAILED = "WB_MAP_INTERACTION_FAILED"
    WB_LOCATION_SELECTION_FAILED = "WB_LOCATION_SELECTION_FAILED"
    WB_SUBMISSION_REJECTED = "WB_SUBMISSION_REJECTED"
    WB_PERMISSION_DENIED = "WB_PERMISSION_DENIED"
    WB_DUPLICATE_ENTRY = "WB_DUPLICATE_ENTRY"

    # Queue errors (Q_*)
    Q_TASK_NOT_FOUND = "Q_TASK_NOT_FOUND"
    Q_TASK_ALREADY_EXISTS = "Q_TASK_ALREADY_EXISTS"
    Q_QUEUE_FULL = "Q_QUEUE_FULL"
    Q_TASK_TIMEOUT = "Q_TASK_TIMEOUT"
    Q_TASK_DEAD_LETTER = "Q_TASK_DEAD_LETTER"

    # Browser errors (BR_*)
    BR_LAUNCH_FAILED = "BR_LAUNCH_FAILED"
    BR_CONTEXT_CREATION_FAILED = "BR_CONTEXT_CREATION_FAILED"
    BR_PAGE_CREATION_FAILED = "BR_PAGE_CREATION_FAILED"
    BR_NAVIGATION_TIMEOUT = "BR_NAVIGATION_TIMEOUT"
    BR_CRASHED = "BR_CRASHED"

    # Rate limiting (RL_*)
    RL_RATE_LIMIT_EXCEEDED = "RL_RATE_LIMIT_EXCEEDED"
    RL_CONCURRENCY_LIMIT_EXCEEDED = "RL_CONCURRENCY_LIMIT_EXCEEDED"

    # Internal errors (INT_*)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    INTERNAL_CONFIG_ERROR = "INTERNAL_CONFIG_ERROR"
    INTERNAL_DATABASE_ERROR = "INTERNAL_DATABASE_ERROR"


class UTCMSException(Exception):
    """Base exception for UTCMS automation with structured error codes."""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        status_code: int = 500,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        self.retryable = retryable

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to structured dict."""
        return {
            "error": self.error_code.value,
            "message": str(self),
            "retryable": self.retryable,
            **self.details,
        }


class MapInteractionError(UTCMSException):
    """Raised when interaction with the map fails."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.WB_MAP_INTERACTION_FAILED,
            status_code=400,
            details=details,
        )


class LocationSelectionError(UTCMSException):
    """Raised when location selection fails (all methods)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.WB_LOCATION_SELECTION_FAILED,
            status_code=400,
            details=details,
        )


class WaybillError(UTCMSException):
    """Raised when waybill creation fails."""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.WB_FORM_ERROR,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
    ):
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=status_code,
            details=details,
            retryable=retryable,
        )


class AuthenticationError(UTCMSException):
    """Raised when authentication fails."""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.AUTH_INVALID_CREDENTIALS,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=401,
            details=details,
        )


class NetworkError(UTCMSException):
    """Raised when network operations fail."""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.NET_SERVICE_UNAVAILABLE,
        details: dict[str, Any] | None = None,
        retryable: bool = True,
    ):
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=503,
            details=details,
            retryable=retryable,
        )


class QueueError(UTCMSException):
    """Raised when queue operations fail."""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.Q_TASK_NOT_FOUND,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=404,
            details=details,
        )


class BrowserError(UTCMSException):
    """Raised when browser operations fail."""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.BR_LAUNCH_FAILED,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=500,
            details=details,
        )
