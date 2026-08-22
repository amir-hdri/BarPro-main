import json
from enum import StrEnum


class JobStatus(StrEnum):
    PENDING = "pending"
    WAITING_AUTH = "waiting_auth"
    WAITING_RETRY = "waiting_retry"
    WAITING_SUBMISSION_WINDOW = "waiting_submission_window"
    OTP_BACKOFF = "otp_backoff"
    QUEUED = "queued"
    CLAIMED = "claimed"
    RUNNING = "running"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    DAILY_LIMIT_REACHED = "daily_limit_reached"
    NEEDS_REVIEW = "needs_review"
    DEAD_LETTER = "dead_letter"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"
    RECONCILING = "reconciling"


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending": {
        "queued",
        "waiting_auth",
        "waiting_retry",
        "waiting_submission_window",
        "cancelled",
        "in_progress",
        "daily_limit_reached",
    },
    "waiting_auth": {
        "queued",
        "pending",
        "waiting_submission_window",
        "cancelled",
        "in_progress",
        "unknown",
        "daily_limit_reached",
    },
    "waiting_retry": {
        "pending",
        "dead_letter",
        "cancelled",
        "in_progress",
        "queued",
        "waiting_submission_window",
        "unknown",
        "daily_limit_reached",
    },
    "waiting_submission_window": {
        "pending",
        "queued",
        "waiting_auth",
        "waiting_retry",
        "cancelled",
        "in_progress",
        "daily_limit_reached",
    },
    "otp_backoff": {
        "pending",
        "dead_letter",
        "cancelled",
        "in_progress",
        "queued",
        "waiting_submission_window",
        "unknown",
        "daily_limit_reached",
    },
    "queued": {
        "claimed",
        "waiting_retry",
        "waiting_submission_window",
        "cancelled",
        "in_progress",
        "unknown",
        "daily_limit_reached",
    },
    "claimed": {
        "running",
        "waiting_retry",
        "waiting_submission_window",
        "needs_review",
        "cancelled",
        "unknown",
        "daily_limit_reached",
    },
    "running": {
        "success",
        "failed",
        "needs_review",
        "waiting_retry",
        "waiting_submission_window",
        "otp_backoff",
        "unknown",
        "cancelled",
        "daily_limit_reached",
    },
    "in_progress": {
        "success",
        "failed",
        "needs_review",
        "waiting_retry",
        "waiting_submission_window",
        "otp_backoff",
        "unknown",
        "cancelled",
        "daily_limit_reached",
    },
    "needs_review": {"pending", "reconciling", "cancelled", "daily_limit_reached"},
    "failed": {"dead_letter", "daily_limit_reached", "pending", "cancelled"},
    "unknown": {"reconciling", "cancelled", "failed", "needs_review"},
    "reconciling": {"success", "failed", "needs_review", "cancelled", "unknown"},
    "dead_letter": set(),
    "cancelled": set(),
    "success": {"needs_review"},
    "daily_limit_reached": {"pending"},
}


class StateTransitionError(Exception):
    pass


class JobStateMachine:
    @classmethod
    def transition(cls, session, job, target: str, *, expected_from: set[str] | None = None, **fields):
        target_str = target.value if hasattr(target, "value") else str(target)
        if target_str == JobStatus.SUCCESS.value and hasattr(job, "mutation_status"):
            mutation_status = fields.get("mutation_status", getattr(job, "mutation_status", None))
            reconciled_at = fields.get("reconciled_at", getattr(job, "reconciled_at", None))
            result_json = fields.get("result_json", getattr(job, "result_json", None))
            if isinstance(result_json, str):
                try:
                    result_json = json.loads(result_json)
                except (TypeError, json.JSONDecodeError):
                    result_json = {}
            tracking_code = result_json.get("tracking_code") if isinstance(result_json, dict) else None
            if mutation_status != "confirmed" or reconciled_at is None or not tracking_code:
                raise StateTransitionError(
                    "Waybill SUCCESS requires confirmed mutation, reconciled_at, and UTCMS tracking_code"
                )
        if job.status == target_str:
            for key, value in fields.items():
                setattr(job, key, value)
            if session is not None:
                session.add(job)
            return job
        if expected_from is None:
            expected_from = {job.status}
        if job.status not in expected_from:
            raise StateTransitionError(f"current {job.status!r} not in {expected_from}")
        if target_str not in ALLOWED_TRANSITIONS.get(job.status, set()):
            raise StateTransitionError(f"{job.status!r} → {target_str!r} not allowed")
        for key, value in fields.items():
            setattr(job, key, value)
        job.status = target_str
        if session is not None:
            session.add(job)
        return job

    @classmethod
    def assert_allowed(cls, current: str, target: str) -> None:
        if target not in ALLOWED_TRANSITIONS.get(current, set()):
            raise StateTransitionError(f"{current!r} → {target!r} not allowed")


# Allowed status values for the FuelInquiry entity (transitions are
# intentionally permissive — pending → running → success/failed — because the
# FuelInquiry model is a separate aggregate from WaybillJob).
FUEL_INQUIRY_STATUSES: frozenset[str] = frozenset(
    {"pending", "processing", "running", "success", "failed", "stale", "cancelled"}
)


def set_fuel_inquiry_status(inquiry, target: str) -> None:
    """Bounded status setter for FuelInquiry rows.

    Centralises the single place in the codebase that decides which status
    strings FuelInquiry accepts, so individual call sites cannot introduce
    new values by accident (which historically caused inconsistent dashboard
    counters).
    """
    if target not in FUEL_INQUIRY_STATUSES:
        raise ValueError(f"Unknown FuelInquiry status: {target!r}")
    inquiry.status = target
