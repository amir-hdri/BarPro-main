"""Tests for JobStateMachine.

Spec (Phase 1 acceptance criteria): ≥20 tests covering both allowed and
disallowed transitions across every job state defined in the roadmap
(pending, queued, claimed, running, in_progress, success, failed,
needs_review, waiting_auth, waiting_retry, otp_backoff, dead_letter,
cancelled, unknown, reconciling, daily_limit_reached).
"""

from unittest.mock import MagicMock

import pytest

from app.orchestrator.state_machine import (
    ALLOWED_TRANSITIONS,
    JobStateMachine,
    JobStatus,
    StateTransitionError,
    set_fuel_inquiry_status,
)


class MockJob:
    """Minimal stand-in for the SQLModel WaybillJob entity."""

    def __init__(self, status):
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "updated_fields", {})

    def __setattr__(self, name, value):
        if name in ("status", "updated_fields"):
            object.__setattr__(self, name, value)
        else:
            self.updated_fields[name] = value


@pytest.fixture
def session():
    return MagicMock()


# --- Happy path transitions ----------------------------------------------------


def test_pending_to_queued(session):
    job = MockJob(JobStatus.PENDING)
    JobStateMachine.transition(session, job, JobStatus.QUEUED)
    assert job.status == JobStatus.QUEUED
    session.add.assert_called_once_with(job)


def test_pending_to_waiting_auth(session):
    job = MockJob(JobStatus.PENDING)
    JobStateMachine.transition(session, job, JobStatus.WAITING_AUTH)
    assert job.status == JobStatus.WAITING_AUTH


def test_pending_to_waiting_retry(session):
    job = MockJob(JobStatus.PENDING)
    JobStateMachine.transition(session, job, JobStatus.WAITING_RETRY)
    assert job.status == JobStatus.WAITING_RETRY


def test_pending_to_waiting_submission_window(session):
    job = MockJob(JobStatus.PENDING)
    JobStateMachine.transition(session, job, JobStatus.WAITING_SUBMISSION_WINDOW)
    assert job.status == JobStatus.WAITING_SUBMISSION_WINDOW


def test_waiting_submission_window_to_queued(session):
    job = MockJob(JobStatus.WAITING_SUBMISSION_WINDOW)
    JobStateMachine.transition(session, job, JobStatus.QUEUED)
    assert job.status == JobStatus.QUEUED


def test_waiting_submission_window_to_pending(session):
    job = MockJob(JobStatus.WAITING_SUBMISSION_WINDOW)
    JobStateMachine.transition(session, job, JobStatus.PENDING)
    assert job.status == JobStatus.PENDING


def test_pending_to_cancelled(session):
    job = MockJob(JobStatus.PENDING)
    JobStateMachine.transition(session, job, JobStatus.CANCELLED)
    assert job.status == JobStatus.CANCELLED


def test_queued_to_claimed(session):
    job = MockJob(JobStatus.QUEUED)
    JobStateMachine.transition(session, job, JobStatus.CLAIMED)
    assert job.status == JobStatus.CLAIMED


def test_claimed_to_running(session):
    job = MockJob(JobStatus.CLAIMED)
    JobStateMachine.transition(session, job, JobStatus.RUNNING)
    assert job.status == JobStatus.RUNNING


def test_running_to_success(session):
    job = MockJob(JobStatus.RUNNING)
    JobStateMachine.transition(session, job, JobStatus.SUCCESS)
    assert job.status == JobStatus.SUCCESS


def test_running_to_failed(session):
    job = MockJob(JobStatus.RUNNING)
    JobStateMachine.transition(session, job, JobStatus.FAILED)
    assert job.status == JobStatus.FAILED


def test_running_to_needs_review(session):
    job = MockJob(JobStatus.RUNNING)
    JobStateMachine.transition(session, job, JobStatus.NEEDS_REVIEW)
    assert job.status == JobStatus.NEEDS_REVIEW


def test_claimed_to_needs_review(session):
    job = MockJob(JobStatus.CLAIMED)
    JobStateMachine.transition(session, job, JobStatus.NEEDS_REVIEW)
    assert job.status == JobStatus.NEEDS_REVIEW


def test_running_to_otp_backoff(session):
    job = MockJob(JobStatus.RUNNING)
    JobStateMachine.transition(session, job, JobStatus.OTP_BACKOFF)
    assert job.status == JobStatus.OTP_BACKOFF


def test_running_to_waiting_retry(session):
    job = MockJob(JobStatus.RUNNING)
    JobStateMachine.transition(session, job, JobStatus.WAITING_RETRY)
    assert job.status == JobStatus.WAITING_RETRY


def test_running_to_unknown(session):
    job = MockJob(JobStatus.RUNNING)
    JobStateMachine.transition(session, job, JobStatus.UNKNOWN)
    assert job.status == JobStatus.UNKNOWN


def test_in_progress_path(session):
    # in_progress follows the same downstream rules as running
    job = MockJob(JobStatus.IN_PROGRESS)
    JobStateMachine.transition(session, job, JobStatus.SUCCESS)
    assert job.status == JobStatus.SUCCESS


def test_unknown_to_reconciling(session):
    job = MockJob(JobStatus.UNKNOWN)
    JobStateMachine.transition(session, job, JobStatus.RECONCILING)
    assert job.status == JobStatus.RECONCILING


def test_reconciling_outcomes(session):
    for target in (JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.NEEDS_REVIEW):
        job = MockJob(JobStatus.RECONCILING)
        JobStateMachine.transition(session, job, target)
        assert job.status == target


def test_failed_to_dead_letter(session):
    job = MockJob(JobStatus.FAILED)
    JobStateMachine.transition(session, job, JobStatus.DEAD_LETTER)
    assert job.status == JobStatus.DEAD_LETTER


def test_terminal_states_no_outgoing():
    # dead_letter, cancelled are terminal — no outgoing transitions exist
    assert ALLOWED_TRANSITIONS[JobStatus.DEAD_LETTER.value] == set()
    assert ALLOWED_TRANSITIONS[JobStatus.CANCELLED.value] == set()
    # success has only needs_review as outgoing
    assert ALLOWED_TRANSITIONS[JobStatus.SUCCESS.value] == {JobStatus.NEEDS_REVIEW.value}


# --- Field updates -------------------------------------------------------------


def test_transition_persists_extra_fields(session):
    job = MockJob(JobStatus.PENDING)
    JobStateMachine.transition(
        session,
        job,
        JobStatus.QUEUED,
        submit_after="2026-01-01T00:00:00",
        priority=5,
    )
    assert job.status == JobStatus.QUEUED
    assert job.updated_fields["submit_after"] == "2026-01-01T00:00:00"
    assert job.updated_fields["priority"] == 5


def test_transition_expected_from_set(session):
    job = MockJob(JobStatus.PENDING)
    JobStateMachine.transition(
        session,
        job,
        JobStatus.QUEUED,
        expected_from={JobStatus.PENDING},
    )
    assert job.status == JobStatus.QUEUED


# --- Disallowed transitions ----------------------------------------------------


def test_success_to_running_disallowed(session):
    job = MockJob(JobStatus.SUCCESS)
    with pytest.raises(StateTransitionError):
        JobStateMachine.transition(session, job, JobStatus.RUNNING)


def test_pending_to_success_disallowed(session):
    job = MockJob(JobStatus.PENDING)
    with pytest.raises(StateTransitionError):
        JobStateMachine.transition(session, job, JobStatus.SUCCESS)


def test_pending_to_claimed_disallowed(session):
    job = MockJob(JobStatus.PENDING)
    with pytest.raises(StateTransitionError):
        JobStateMachine.transition(session, job, JobStatus.CLAIMED)


def test_running_to_queued_disallowed(session):
    job = MockJob(JobStatus.RUNNING)
    with pytest.raises(StateTransitionError):
        JobStateMachine.transition(session, job, JobStatus.QUEUED)


def test_cancelled_to_anything_disallowed(session):
    job = MockJob(JobStatus.CANCELLED)
    for target in (JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.PENDING):
        with pytest.raises(StateTransitionError):
            JobStateMachine.transition(session, job, target)


def test_dead_letter_to_anything_disallowed(session):
    job = MockJob(JobStatus.DEAD_LETTER)
    for target in (JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.PENDING):
        with pytest.raises(StateTransitionError):
            JobStateMachine.transition(session, job, target)


def test_expected_from_mismatch(session):
    job = MockJob(JobStatus.PENDING)
    with pytest.raises(StateTransitionError):
        JobStateMachine.transition(
            session,
            job,
            JobStatus.QUEUED,
            expected_from={JobStatus.RUNNING},
        )


# --- Fuel inquiry bounded setter (helper, not full state machine) ----------------


class MockFuelInquiry:
    def __init__(self):
        self.status = None


def test_set_fuel_inquiry_status_known_value():
    inquiry = MockFuelInquiry()
    set_fuel_inquiry_status(inquiry, "success")
    assert inquiry.status == "success"


def test_set_fuel_inquiry_status_unknown_value():
    inquiry = MockFuelInquiry()
    with pytest.raises(ValueError):
        set_fuel_inquiry_status(inquiry, "bogus_state")


# --- Assert-allowed helper -----------------------------------------------------


def test_assert_allowed_accepts():
    JobStateMachine.assert_allowed(JobStatus.PENDING, JobStatus.QUEUED)


def test_assert_allowed_rejects():
    with pytest.raises(StateTransitionError):
        JobStateMachine.assert_allowed(JobStatus.SUCCESS, JobStatus.QUEUED)
