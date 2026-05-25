from enum import Enum
from typing import Tuple

from fastapi import HTTPException

from app.core.exceptions import UTCMSException, WaybillError
from app.core.network import is_retryable_network_error


class ErrorCategory(str, Enum):
    USER_DATA_ERROR = "USER_DATA_ERROR"
    AUTH_FAILURE = "AUTH_FAILURE"
    CAPTCHA_EXHAUSTION = "CAPTCHA_EXHAUSTION"
    TARGET_SITE_TIMEOUT = "TARGET_SITE_TIMEOUT"
    SELECTOR_CHANGED = "SELECTOR_CHANGED"
    BOT_DETECTED = "BOT_DETECTED"
    TRANSIENT_INFRA_ERROR = "TRANSIENT_INFRA_ERROR"
    WORKER_RESOURCE_ERROR = "WORKER_RESOURCE_ERROR"
    UNKNOWN_AUTOMATION_ERROR = "UNKNOWN_AUTOMATION_ERROR"


def classify_exception(error: Exception) -> Tuple[ErrorCategory, bool]:
    text = str(error).lower()

    if isinstance(error, HTTPException):
        if error.status_code == 422:
            return ErrorCategory.USER_DATA_ERROR, False
        if error.status_code in {401, 403}:
            return ErrorCategory.AUTH_FAILURE, False
        if error.status_code in {429, 503, 504}:
            return ErrorCategory.TARGET_SITE_TIMEOUT, True
        if error.status_code >= 500:
            return ErrorCategory.TRANSIENT_INFRA_ERROR, True

    if isinstance(error, UTCMSException):
        if "captcha" in text:
            return ErrorCategory.CAPTCHA_EXHAUSTION, error.retryable
        if "selector" in text:
            return ErrorCategory.SELECTOR_CHANGED, error.retryable
        if "auth" in text or "login" in text or "credential" in text:
            return ErrorCategory.AUTH_FAILURE, error.retryable
        if "timeout" in text or "network" in text:
            return ErrorCategory.TARGET_SITE_TIMEOUT, error.retryable
        if "field" in text or "validation" in text or "form" in text:
            return ErrorCategory.USER_DATA_ERROR, error.retryable

    if isinstance(error, WaybillError):
        if "captcha" in text:
            return ErrorCategory.CAPTCHA_EXHAUSTION, False
        if "selector" in text:
            return ErrorCategory.SELECTOR_CHANGED, False
        if "timeout" in text or is_retryable_network_error(error):
            return ErrorCategory.TARGET_SITE_TIMEOUT, True
        if "field" in text or "validation" in text or "form" in text:
            return ErrorCategory.USER_DATA_ERROR, False

    if "bot" in text or "automationcontrolled" in text or "suspicious" in text:
        return ErrorCategory.BOT_DETECTED, False
    if "selector" in text or "query_selector" in text:
        return ErrorCategory.SELECTOR_CHANGED, False
    if "captcha" in text:
        return ErrorCategory.CAPTCHA_EXHAUSTION, False
    if "memory" in text or "browser" in text or "context" in text or "playwright" in text:
        return ErrorCategory.WORKER_RESOURCE_ERROR, is_retryable_network_error(error)
    if "timeout" in text or is_retryable_network_error(error):
        return ErrorCategory.TARGET_SITE_TIMEOUT, True
    return ErrorCategory.UNKNOWN_AUTOMATION_ERROR, False

