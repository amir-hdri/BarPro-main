import pytest

from app.core.error_taxonomy import (
    FUEL_INQUIRY_ERROR_CODE,
    ErrorCategory,
    classify_error_string,
    classify_exception,
    classify_fuel_inquiry_exception,
)
from app.core.network import (
    BROWSER_LIFECYCLE_MARKERS,
    EGRESS_FAILURE_MARKERS,
    is_egress_failure,
    is_retryable_network_error,
)


def test_submission_unconfirmed_hint_has_known_category() -> None:
    category = classify_error_string(
        error_msg="Portal success response did not include a tracking code",
        error_category_hint="submission_unconfirmed",
        status_hint="failed",
    )

    assert category is ErrorCategory.SUBMISSION_UNCONFIRMED
    assert category.value == "submission_unconfirmed"


def test_legacy_submission_unknown_hint_maps_to_unconfirmed() -> None:
    category = classify_error_string(
        error_msg="Submission outcome requires reconciliation",
        error_category_hint="submission_unknown",
        status_hint="needs_review",
    )

    assert category is ErrorCategory.SUBMISSION_UNCONFIRMED


# ---------------------------------------------------------------------------
# Classification matrix.
#
# Every row below is an error string measured coming out of the real workers
# against a degraded egress path. Before this table existed, five of the six
# transport failures were retried without the breaker ever removing the broken
# IP index from rotation, and four of them were reported to operators as the
# opaque Fuel Inquiry code "100".
#
# (error string, retryable, egress, classify_error_string category, fuel code)
# ---------------------------------------------------------------------------
CLASSIFICATION_MATRIX = [
    ("net::ERR_CONNECTION_CLOSED", True, True, ErrorCategory.TARGET_SITE_TIMEOUT, "103"),
    ("TLS handshake: EOF", True, True, ErrorCategory.TARGET_SITE_TIMEOUT, "102"),
    ("SSL: UNEXPECTED_EOF_WHILE_READING", True, True, ErrorCategory.TARGET_SITE_TIMEOUT, "102"),
    ("408 Request Timeout", True, False, ErrorCategory.TARGET_SITE_TIMEOUT, "103"),
    ("net::ERR_CONNECTION_RESET", True, True, ErrorCategory.TARGET_SITE_TIMEOUT, "103"),
    ("ERR_CONNECTION_CLOSED", True, True, ErrorCategory.TARGET_SITE_TIMEOUT, "103"),
    ("curl (56) Proxy CONNECT aborted", True, True, ErrorCategory.TARGET_SITE_TIMEOUT, "103"),
    ("Proxy CONNECT failed: connection refused", True, True, ErrorCategory.TARGET_SITE_TIMEOUT, "103"),
    # Worker-local faults: retryable, but never egress.
    (
        "Target page, context or browser has been closed",
        True,
        False,
        ErrorCategory.WORKER_RESOURCE_ERROR,
        "108",
    ),
    ("Page crashed", True, False, ErrorCategory.WORKER_RESOURCE_ERROR, "108"),
    # Genuinely non-network failures must stay out of both tables.
    # NOTE: "Invalid driver national code" is a user-data problem but neither
    # classifier recognises it as one — the USER_DATA branch keys off hints and
    # the word "incomplete", not "invalid". Pinned as measured rather than as
    # desired; fixing it means widening the USER_DATA keywords, which is a
    # separate change with its own false-positive risk.
    ("Invalid driver national code", False, False, ErrorCategory.UNKNOWN_AUTOMATION_ERROR, "100"),
    ("bot detected on page", False, False, ErrorCategory.BOT_DETECTED, "107"),
]


@pytest.mark.parametrize(
    ("error_msg", "retryable", "egress", "category", "fuel_code"),
    CLASSIFICATION_MATRIX,
)
def test_classification_matrix(error_msg, retryable, egress, category, fuel_code) -> None:
    assert is_retryable_network_error(error_msg) is retryable
    assert is_egress_failure(error_msg) is egress
    assert classify_error_string(error_msg) is category
    assert classify_fuel_inquiry_exception(Exception(error_msg))[1] == fuel_code


@pytest.mark.parametrize("marker", EGRESS_FAILURE_MARKERS)
def test_every_egress_failure_is_retryable(marker: str) -> None:
    """Structural invariant: EGRESS is a subset of RETRYABLE.

    Enforced by construction in ``network.py``; asserted here so a future edit
    that splits the tables apart again fails loudly instead of silently
    reintroducing "retried forever, never rotated out".
    """
    assert is_retryable_network_error(marker) is True


@pytest.mark.parametrize("marker", BROWSER_LIFECYCLE_MARKERS)
def test_browser_lifecycle_faults_are_never_egress(marker: str) -> None:
    """A worker-local crash must not evict a healthy IP index from rotation."""
    assert is_retryable_network_error(marker) is True
    assert is_egress_failure(marker) is False


def test_fuel_error_code_table_is_total() -> None:
    """No ErrorCategory may fall through to the "100" default.

    The table used to cover 5 of 10 categories, so bot detection, auth failure,
    a dead browser, a changed selector and an unconfirmed submission were all
    reported as "unknown error 100".
    """
    missing = [c.value for c in ErrorCategory if c not in FUEL_INQUIRY_ERROR_CODE]
    assert missing == []

    codes = list(FUEL_INQUIRY_ERROR_CODE.values())
    assert len(set(codes)) == len(codes), "duplicate user-facing error codes"


def test_only_genuinely_unknown_errors_get_code_100() -> None:
    category, code = classify_fuel_inquiry_exception(Exception("something entirely unparseable"))
    assert category is ErrorCategory.UNKNOWN_AUTOMATION_ERROR
    assert code == "100"


@pytest.mark.parametrize(("error_msg", "_r", "_e", "_c", "_f"), CLASSIFICATION_MATRIX)
def test_both_classifiers_agree_on_transport_vs_worker(error_msg, _r, _e, _c, _f) -> None:
    """``classify_exception`` and ``classify_error_string`` must not disagree.

    They are two entry points onto the same taxonomy — the exception path and
    the browser-result path — and they had drifted: the string path knew
    nothing about network markers and returned UNKNOWN for every net:: error.
    """
    assert classify_exception(Exception(error_msg))[0] is classify_error_string(error_msg)
