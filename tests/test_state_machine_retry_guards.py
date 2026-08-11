"""Regression tests for state machine transitions used by soft-cancel and retry guards."""

import pytest

from app.orchestrator.state_machine import ALLOWED_TRANSITIONS, JobStateMachine, StateTransitionError


class _FakeJob:
    status = "pending"


def test_soft_cancel_allows_all_active_statuses():
    for current in ("queued", "claimed", "running", "in_progress", "reconciling", "unknown"):
        assert "cancelled" in ALLOWED_TRANSITIONS[current], current


def test_soft_cancel_also_allowed_from_terminal_states():
    assert "cancelled" in ALLOWED_TRANSITIONS["failed"]
    assert "cancelled" in ALLOWED_TRANSITIONS["needs_review"]


def test_success_never_transitions_to_cancelled():
    assert "cancelled" not in ALLOWED_TRANSITIONS["success"]


def test_retry_guard_unknown_to_pending_is_rejected():
    """Unknown must not silently become pending via JobStateMachine; the
    service layer raises 409 before this point, and the machine must also
    refuse the direct transition."""
    job = _task_job("unknown")
    with pytest.raises(StateTransitionError):
        JobStateMachine.transition(None, job, "pending")


def test_unknown_to_reconciling_is_allowed():
    job = _FakeJob()
    job.status = "unknown"
    JobStateMachine.transition(None, job, "reconciling")
    assert job.status == "reconciling"


def _task_job(status: str) -> _FakeJob:
    job = _FakeJob()
    job.status = status
    return job
