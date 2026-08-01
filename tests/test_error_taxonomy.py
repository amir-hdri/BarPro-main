from app.core.error_taxonomy import ErrorCategory, classify_error_string


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
