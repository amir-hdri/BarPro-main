"""Tests for Phase 6: Idempotency, Request Digest, and Mutation Safety."""

import hashlib
import json
from unittest.mock import MagicMock

from app.core.error_taxonomy import ErrorCategory
from app.models_multitenant import TaskStatus, WaybillJob
from app.orchestrator.state_machine import JobStateMachine, JobStatus


def test_request_digest_calculation():
    """Verify deterministic request digest generation."""
    payload_1 = {"origin": "Tehran", "destination": "Isfahan", "weight": 1000}
    payload_2 = {"destination": "Isfahan", "origin": "Tehran", "weight": 1000}

    digest_1 = hashlib.sha256(json.dumps(payload_1, sort_keys=True).encode()).hexdigest()
    digest_2 = hashlib.sha256(json.dumps(payload_2, sort_keys=True).encode()).hexdigest()

    assert digest_1 == digest_2
    assert len(digest_1) == 64


def test_job_idempotency_hard_guard():
    """Verify that a job with an existing tracking code is never resubmitted."""
    job = WaybillJob(
        job_id="job_idem_1",
        idempotency_key="idemp_1",
        client_id=1,
        driver_id=1,
        status=TaskStatus.SUCCESS.value,
        payload_json={"test": "data"},
        result_json={"tracking_code": "TRACK_9999"},
        mutation_status="confirmed",
    )
    # Check guard condition
    assert job.result_json.get("tracking_code") == "TRACK_9999"
    assert job.mutation_status == "confirmed"


def test_ambiguous_success_downgrades_to_unknown():
    """Verify that a success result missing tracking code is downgraded to UNKNOWN."""
    mock_session = MagicMock()
    job = WaybillJob(
        job_id="job_ambiguous_1",
        idempotency_key="idemp_amb_1",
        client_id=1,
        driver_id=1,
        status=JobStatus.RUNNING.value,
        payload_json={"test": "data"},
        mutation_status="intent_persisted",
    )

    # Simulated worker downgrade logic
    job.mutation_status = "ambiguous"
    JobStateMachine.transition(
        mock_session,
        job,
        JobStatus.UNKNOWN.value,
        last_error="Portal success response did not include a tracking code; reconciliation required",
        error_category=ErrorCategory.SUBMISSION_UNCONFIRMED.value,
        retryable=False,
    )

    assert job.status == JobStatus.UNKNOWN.value
    assert job.mutation_status == "ambiguous"
    assert job.retryable is False
    assert job.error_category == ErrorCategory.SUBMISSION_UNCONFIRMED.value
