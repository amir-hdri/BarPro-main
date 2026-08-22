"""Regression tests for the deep-review fixes (2026-08-22).

Guards the code-level fixes so they cannot silently regress:
  1. ``JobStatus`` must declare ``daily_limit_reached`` (was missing while the
     transition matrix already referenced it).
  2. Every key and target in ``ALLOWED_TRANSITIONS`` must be a declared
     ``JobStatus`` member (catches enum/matrix divergence).
  3. ``JOB_TIMEOUT_SECONDS`` must stay below ``CELERY_TASK_TIME_LIMIT`` so the
     graceful ``asyncio.wait_for`` fires before Celery's hard SIGKILL.
"""
from app.core.config import utcms_config
from app.orchestrator.state_machine import ALLOWED_TRANSITIONS, JobStatus


def test_job_status_declares_daily_limit_reached():
    assert JobStatus.DAILY_LIMIT_REACHED.value == "daily_limit_reached"


def test_allowed_transitions_keys_are_job_statuses():
    valid = {s.value for s in JobStatus}
    missing = set(ALLOWED_TRANSITIONS) - valid
    assert not missing, f"transition keys not in JobStatus: {sorted(missing)}"


def test_allowed_transitions_targets_are_job_statuses():
    valid = {s.value for s in JobStatus}
    targets = {t for ts in ALLOWED_TRANSITIONS.values() for t in ts}
    missing = targets - valid
    assert not missing, f"transition targets not in JobStatus: {sorted(missing)}"


def test_job_timeout_below_celery_hard_limit():
    assert utcms_config.JOB_TIMEOUT_SECONDS < utcms_config.CELERY_TASK_TIME_LIMIT, (
        f"JOB_TIMEOUT_SECONDS={utcms_config.JOB_TIMEOUT_SECONDS} must be < "
        f"CELERY_TASK_TIME_LIMIT={utcms_config.CELERY_TASK_TIME_LIMIT}"
    )
