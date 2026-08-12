from enum import StrEnum

from fastapi import HTTPException

from app.core.exceptions import UTCMSException, WaybillError
from app.core.network import BROWSER_LIFECYCLE_MARKERS, is_egress_failure, is_retryable_network_error


class ErrorCategory(StrEnum):
    USER_DATA_ERROR = "USER_DATA_ERROR"
    AUTH_FAILURE = "AUTH_FAILURE"
    CAPTCHA_EXHAUSTION = "CAPTCHA_EXHAUSTION"
    TARGET_SITE_TIMEOUT = "TARGET_SITE_TIMEOUT"
    SELECTOR_CHANGED = "SELECTOR_CHANGED"
    BOT_DETECTED = "BOT_DETECTED"
    TRANSIENT_INFRA_ERROR = "TRANSIENT_INFRA_ERROR"
    WORKER_RESOURCE_ERROR = "WORKER_RESOURCE_ERROR"
    UNKNOWN_AUTOMATION_ERROR = "UNKNOWN_AUTOMATION_ERROR"
    SUBMISSION_UNCONFIRMED = "submission_unconfirmed"


def classify_exception(error: Exception) -> tuple[ErrorCategory, bool]:
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
    if "proxy" in text or "unreachable" in text or "squid" in text:
        return ErrorCategory.TRANSIENT_INFRA_ERROR, True
    if "selector" in text or "query_selector" in text:
        return ErrorCategory.SELECTOR_CHANGED, False
    if "captcha" in text:
        return ErrorCategory.CAPTCHA_EXHAUSTION, False
    # Transport evidence outranks the keyword heuristic below: a Playwright
    # message such as "playwright: net::ERR_CONNECTION_RESET" mentions the
    # browser but describes a broken route, and blaming the worker for it sends
    # the job down the wrong recovery path.
    if is_egress_failure(error):
        return ErrorCategory.TARGET_SITE_TIMEOUT, True
    if (
        "memory" in text
        or "browser" in text
        or "context" in text
        or "playwright" in text
        or any(marker in text for marker in BROWSER_LIFECYCLE_MARKERS)
    ):
        return ErrorCategory.WORKER_RESOURCE_ERROR, is_retryable_network_error(error)
    if "timeout" in text or is_retryable_network_error(error):
        return ErrorCategory.TARGET_SITE_TIMEOUT, True
    return ErrorCategory.UNKNOWN_AUTOMATION_ERROR, False


def classify_error_string(
    error_msg: str,
    error_category_hint: str | None = None,
    status_hint: str | None = None,
) -> ErrorCategory:
    """Classify an error message/hints from browser result into ErrorCategory."""
    text = (error_msg or "").lower()
    cat_hint = (error_category_hint or "").lower()
    st_hint = (status_hint or "").lower().replace("_", "").replace("-", "")

    if cat_hint in {"submission_unconfirmed", "submission_unknown"}:
        return ErrorCategory.SUBMISSION_UNCONFIRMED

    # CAPTCHA
    if "captcha" in text or "captcha" in cat_hint or st_hint in {"captchafailed", "captcha_failed"}:
        return ErrorCategory.CAPTCHA_EXHAUSTION

    # AUTH / LOGIN
    if (
        "login" in text
        or "auth" in text
        or "credential" in text
        or "login_failed" in cat_hint
        or "invalid_driver" in cat_hint
        or "driver_key_mismatch" in cat_hint
        or st_hint == "loginfailed"
    ):
        return ErrorCategory.AUTH_FAILURE

    # USER DATA / INCOMPLETE / FORM
    if (
        "form" in cat_hint
        or "validation" in cat_hint
        or "incomplete" in text
        or "incomplete_data" in cat_hint
        or "user_data" in cat_hint
    ):
        return ErrorCategory.USER_DATA_ERROR

    # TIMEOUT / TARGET SITE / NETWORK
    #
    # ``is_egress_failure`` is consulted here because the hint-based substring
    # checks below it only ever matched the literal words "network"/"timeout".
    # Every Chrome net:: error, TLS handshake abort and connection reset was
    # therefore classified UNKNOWN_AUTOMATION_ERROR by this function while
    # ``classify_exception`` classified the same text as TARGET_SITE_TIMEOUT —
    # and because the Fuel Inquiry code table has no entry for the categories
    # that UNKNOWN collapses into, real transport failures surfaced to users as
    # the opaque code "100".
    if (
        "network" in cat_hint
        or "timeout" in cat_hint
        or "system" in cat_hint
        or "target_site" in text
        or "network" in text
        or "timeout" in text
        or "system_error" in cat_hint
        or "destination_error" in cat_hint
        or "service" in cat_hint
        or "api" in cat_hint
        or is_egress_failure(text)
    ):
        return ErrorCategory.TARGET_SITE_TIMEOUT

    # SELECTOR / CHANGED
    if "selector" in text or "query_selector" in text or "selector_changed" in cat_hint:
        return ErrorCategory.SELECTOR_CHANGED

    # BOT DETECTED
    if "bot" in text or "automationcontrolled" in text or "suspicious" in text or "bot_detected" in cat_hint:
        return ErrorCategory.BOT_DETECTED

    # WORKER RESOURCE — the renderer or browser died on this worker. Kept below
    # the egress check so a broken route is never blamed on the worker, and
    # mirrors the WORKER_RESOURCE_ERROR branch in ``classify_exception``.
    if any(marker in text for marker in BROWSER_LIFECYCLE_MARKERS) or "memory" in text:
        return ErrorCategory.WORKER_RESOURCE_ERROR

    # Remaining transient network evidence that is not egress-specific
    # (e.g. a bare "408 Request Timeout" from the target).
    if is_retryable_network_error(text):
        return ErrorCategory.TARGET_SITE_TIMEOUT

    return ErrorCategory.UNKNOWN_AUTOMATION_ERROR


# Error categories that are safe to retry from terminal states (FAILED/NEEDS_REVIEW).
# These represent transient/infrastructure issues, NOT data integrity or submission confirmation issues.
RETRYABLE_TERMINAL_CATEGORIES: frozenset[ErrorCategory] = frozenset(
    {
        ErrorCategory.TARGET_SITE_TIMEOUT,
        ErrorCategory.TRANSIENT_INFRA_ERROR,
        ErrorCategory.WORKER_RESOURCE_ERROR,
        ErrorCategory.CAPTCHA_EXHAUSTION,
    }
)

# Error categories that should NEVER be retried directly from terminal states.
# These require reconciliation, admin review, or data correction.
NON_RETRYABLE_TERMINAL_CATEGORIES: frozenset[ErrorCategory] = frozenset(
    {
        ErrorCategory.SUBMISSION_UNCONFIRMED,
        ErrorCategory.USER_DATA_ERROR,
        ErrorCategory.AUTH_FAILURE,
        ErrorCategory.SELECTOR_CHANGED,
        ErrorCategory.BOT_DETECTED,
        ErrorCategory.UNKNOWN_AUTOMATION_ERROR,
    }
)


def is_retryable_terminal_category(category: str | ErrorCategory | None) -> bool:
    """Check if a terminal error category allows direct retry to PENDING.

    Unknown/legacy category strings (e.g. ``system_error``,
    ``driver_submission_in_progress``) are treated conservatively: retry is
    denied so the job flows to reconciliation/admin review instead of looping.
    """
    if category is None:
        return False
    try:
        cat = category.value if isinstance(category, ErrorCategory) else ErrorCategory(category)
    except ValueError:
        return False
    return cat in RETRYABLE_TERMINAL_CATEGORIES


# User-facing error codes used by the Fuel Inquiry feature.
#
# ``fuel_inquiry_service`` stores the code itself in ``inquiry.error_message``,
# so whatever appears here is what the operator ends up reading.
#
# This table MUST stay total over ErrorCategory. It previously listed only five
# of the ten categories and the lookup fell back to "100", so a correctly
# detected bot block, an auth failure, a dead browser and an unconfirmed
# submission were all reported as the same "unknown error 100" — which is why
# code 100 dominated the failure logs while nothing was actually unknown.
# ``test_error_taxonomy.py`` asserts totality so the fallback can never again
# absorb a category silently.
FUEL_INQUIRY_ERROR_CODE = {
    ErrorCategory.UNKNOWN_AUTOMATION_ERROR: "100",
    ErrorCategory.CAPTCHA_EXHAUSTION: "101",
    ErrorCategory.TARGET_SITE_TIMEOUT: "102",
    ErrorCategory.TRANSIENT_INFRA_ERROR: "103",
    ErrorCategory.USER_DATA_ERROR: "104",
    ErrorCategory.AUTH_FAILURE: "105",
    ErrorCategory.SELECTOR_CHANGED: "106",
    ErrorCategory.BOT_DETECTED: "107",
    ErrorCategory.WORKER_RESOURCE_ERROR: "108",
    ErrorCategory.SUBMISSION_UNCONFIRMED: "109",
}


def classify_fuel_inquiry_exception(error: Exception) -> tuple[ErrorCategory, str]:
    """Classify a fuel inquiry exception into (ErrorCategory, user code).

    Returns a tuple so call sites can store both fields without re-running
    the classifier. The returned code is one of the strings in
    FUEL_INQUIRY_ERROR_CODE so the frontend's error map stays stable.

    Persian/English domain keywords (پلاک/راننده/credentials/plate) are
    explicitly checked because legacy error messages from
    `fuel_inquiry_service` used these substrings before the error taxonomy
    was centralised.
    """
    text = str(error).lower()
    # Legacy substring keywords (kept because the original code hardcoded
    # Persian phrases; removing them would change the user-visible behaviour).
    plate_keywords = ("plate", "credentials", "invalid_driver", "پلاک", "راننده")
    system_keywords = ("خطا در سامانه", "system error")
    network_keywords = ("timeout", "connection", "network", "proxy")
    captcha_keywords = ("captcha", "کپچا")

    if any(k in text for k in plate_keywords):
        return ErrorCategory.USER_DATA_ERROR, FUEL_INQUIRY_ERROR_CODE[ErrorCategory.USER_DATA_ERROR]
    if any(k in text for k in system_keywords):
        return ErrorCategory.TARGET_SITE_TIMEOUT, FUEL_INQUIRY_ERROR_CODE[ErrorCategory.TARGET_SITE_TIMEOUT]
    if any(k in text for k in network_keywords):
        return ErrorCategory.TRANSIENT_INFRA_ERROR, FUEL_INQUIRY_ERROR_CODE[ErrorCategory.TRANSIENT_INFRA_ERROR]
    if any(k in text for k in captcha_keywords):
        return ErrorCategory.CAPTCHA_EXHAUSTION, FUEL_INQUIRY_ERROR_CODE[ErrorCategory.CAPTCHA_EXHAUSTION]

    category, _ = classify_exception(error)
    code = FUEL_INQUIRY_ERROR_CODE.get(category, "100")
    return category, code
