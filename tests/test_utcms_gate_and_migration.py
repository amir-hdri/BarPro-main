"""Tests for Phase 2: UTCMSSystemObservation, WaybillJob mutation safety fields, and state transitions."""

from datetime import UTC, datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models_multitenant import TaskStatus, WaybillJob
from app.models_rpa import GateStateValue, UTCMSSystemObservation
from app.orchestrator.state_machine import JobStateMachine, JobStatus, StateTransitionError


def test_utcms_system_observation_model():
    """Test SQLModel serialization and defaults for UTCMSSystemObservation."""
    obs = UTCMSSystemObservation(
        state=GateStateValue.OTP_FREE.value,
        source="passive_probe",
        worker_id="worker-1",
        evidence_json='{"is_otp_needed": false}',
    )
    assert obs.state == "otp_free"
    assert obs.source == "passive_probe"
    assert obs.worker_id == "worker-1"
    assert obs.evidence_json == '{"is_otp_needed": false}'
    assert obs.observed_at is not None


def test_waybill_job_mutation_fields():
    """Test that WaybillJob contains mutation safety fields."""
    job = WaybillJob(
        job_id="job_test_mutation_1",
        idempotency_key="idemp_test_1",
        client_id=1,
        driver_id=1,
        status=TaskStatus.WAITING_SUBMISSION_WINDOW.value,
        payload_json={"sample": "data"},
        request_digest="sha256_dummy_digest",
        document_id="doc_12345",
        mutation_status="intent_persisted",
        mutation_at=datetime.now(UTC).replace(tzinfo=None),
        reconciled_at=None,
    )
    assert job.request_digest == "sha256_dummy_digest"
    assert job.document_id == "doc_12345"
    assert job.mutation_status == "intent_persisted"
    assert job.status == "waiting_submission_window"
    assert job.mutation_at is not None
    assert job.reconciled_at is None


def test_state_machine_waiting_submission_window_transitions():
    """Test comprehensive transitions for WAITING_SUBMISSION_WINDOW."""
    job = WaybillJob(
        job_id="job_test_trans_1",
        idempotency_key="idemp_test_trans_1",
        client_id=1,
        driver_id=1,
        status=JobStatus.PENDING.value,
        payload_json={},
    )

    # pending -> waiting_submission_window
    JobStateMachine.transition(None, job, JobStatus.WAITING_SUBMISSION_WINDOW)
    assert job.status == JobStatus.WAITING_SUBMISSION_WINDOW.value

    # waiting_submission_window -> queued
    JobStateMachine.transition(None, job, JobStatus.QUEUED)
    assert job.status == JobStatus.QUEUED.value

    # queued -> claimed -> running -> waiting_submission_window
    JobStateMachine.transition(None, job, JobStatus.CLAIMED)
    JobStateMachine.transition(None, job, JobStatus.RUNNING)
    JobStateMachine.transition(None, job, JobStatus.WAITING_SUBMISSION_WINDOW)
    assert job.status == JobStatus.WAITING_SUBMISSION_WINDOW.value

    # running -> unknown -> reconciling -> success/failed
    JobStateMachine.transition(None, job, JobStatus.QUEUED)
    JobStateMachine.transition(None, job, JobStatus.CLAIMED)
    JobStateMachine.transition(None, job, JobStatus.RUNNING)
    JobStateMachine.transition(None, job, JobStatus.UNKNOWN)
    assert job.status == JobStatus.UNKNOWN.value

    JobStateMachine.transition(None, job, JobStatus.RECONCILING)
    assert job.status == JobStatus.RECONCILING.value

    JobStateMachine.transition(None, job, JobStatus.SUCCESS)
    assert job.status == JobStatus.SUCCESS.value


def test_sqlite_in_memory_table_creation():
    """Verify that tables with new columns and UTCMSSystemObservation can be created in DB."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        obs = UTCMSSystemObservation(
            state=GateStateValue.OTP_REQUIRED.value,
            source="scheduler_probe",
            worker_id="worker-node-1",
            evidence_json='{"status": 200, "is_otp_needed": true}',
            valid_until=datetime.now(UTC).replace(tzinfo=None),
        )
        session.add(obs)
        session.commit()
        session.refresh(obs)

        assert obs.id is not None
        assert obs.state == "otp_required"

        fetched = session.exec(select(UTCMSSystemObservation)).all()
        assert len(fetched) == 1
        assert fetched[0].worker_id == "worker-node-1"
