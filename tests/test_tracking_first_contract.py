"""Tracking-first acknowledgement contract tests (implementation plan Task 1).

Contract under test:
- A non-empty UTCMS tracking code is an immediate operator acknowledgement.
  It is persisted in ``result_json`` and shown to the operator at once. It is
  NOT final database success — the three-witness rule (confirmed mutation +
  ``reconciled_at`` + persisted code) still gates ``status=success``.
- A success-shaped response without a tracking code crossed the mutation
  boundary and requires read-only UTCMS History reconciliation only. Never a
  resubmission.
"""

import pytest

from app.schemas.task import (
    TRACKING_MISSING_HISTORY_REQUIRED,
    TRACKING_RECEIVED,
    build_missing_tracking_result,
    build_tracking_received_result,
)


def test_tracking_received_is_an_operator_ack_not_final_success():
    result = build_tracking_received_result("UTC-123")
    assert result["operator_acknowledged"] is True
    assert result["confirmation_status"] == "tracking_received"
    assert result["tracking_code"] == "UTC-123"
    assert result["requires_resubmission"] is False
    assert result["requires_reconciliation"] is False


def test_tracking_received_normalizes_whitespace():
    result = build_tracking_received_result("  UTC-123  ")
    assert result["tracking_code"] == "UTC-123"


def test_tracking_received_preserves_extra_details():
    result = build_tracking_received_result("UTC-123", url="https://utcms.example/x", document_id="214")
    assert result["url"] == "https://utcms.example/x"
    assert result["document_id"] == "214"
    assert result["tracking_code"] == "UTC-123"
    assert result["operator_acknowledged"] is True


def test_tracking_received_rejects_empty_code():
    with pytest.raises(ValueError):
        build_tracking_received_result("   ")


def test_missing_tracking_code_requires_read_only_reconciliation():
    result = build_missing_tracking_result(document_id="214000001")
    assert result["requires_reconciliation"] is True
    assert result["reconciliation_mode"] == "history_only"
    assert result["requires_resubmission"] is False
    assert result["confirmation_status"] == "tracking_missing_history_required"
    assert result["operator_acknowledged"] is False
    assert result["document_id"] == "214000001"


def test_missing_tracking_code_allows_absent_document_id():
    result = build_missing_tracking_result(document_id=None)
    assert result["document_id"] is None
    assert result["requires_reconciliation"] is True


def test_contract_constants_are_stable():
    assert TRACKING_RECEIVED == "tracking_received"
    assert TRACKING_MISSING_HISTORY_REQUIRED == "tracking_missing_history_required"
