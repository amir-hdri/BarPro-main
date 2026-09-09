from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ── Tracking-first acknowledgement contract ─────────────────────────────────
#
# Stable result-level values for the waybill acknowledgement decision tree.
# ``tracking_received``  : UTCMS returned a non-empty tracking code. The code is
#                         persisted and acknowledged to the operator at once.
#                         This is an acknowledgement, NOT final DB success — the
#                         three-witness rule still gates ``status=success``.
# ``tracking_missing_history_required``: the response was success-shaped but no
#                         tracking code came back. The mutation boundary was
#                         crossed, so only read-only UTCMS History reconciliation
#                         may confirm it — never a resubmission.

TRACKING_RECEIVED = "tracking_received"
TRACKING_MISSING_HISTORY_REQUIRED = "tracking_missing_history_required"


def _normalize_tracking_code(tracking_code: str) -> str:
    code = str(tracking_code or "").strip()
    if not code:
        raise ValueError("tracking_code must be non-empty")
    return code


def build_tracking_received_result(tracking_code: str, **details: object) -> dict[str, Any]:
    """Build the immediate operator acknowledgement result for a tracking code.

    Whitespace is normalized; the code must be non-empty. Extra details
    (screenshot, url, document_id, ...) are preserved verbatim.
    """
    code = _normalize_tracking_code(tracking_code)
    return {
        **details,
        "tracking_code": code,
        "confirmation_status": TRACKING_RECEIVED,
        "operator_acknowledged": True,
        "requires_reconciliation": False,
        "requires_resubmission": False,
    }


def build_missing_tracking_result(*, document_id: str | None) -> dict[str, Any]:
    """Build the result contract for a success-shaped response without a code.

    The mutation boundary was crossed, so the job must go through read-only
    UTCMS History reconciliation. Resubmission is never implied by this result.
    """
    return {
        "document_id": document_id,
        "confirmation_status": TRACKING_MISSING_HISTORY_REQUIRED,
        "operator_acknowledged": False,
        "requires_reconciliation": True,
        "reconciliation_mode": "history_only",
        "requires_resubmission": False,
    }



class TaskStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    IN_PROGRESS = "in_progress"
    CLAIMED = "claimed"
    RUNNING = "running"
    RETRYING = "retrying"
    WAITING_AUTH = "waiting_auth"
    WAITING_RETRY = "waiting_retry"
    WAITING_SUBMISSION_WINDOW = "waiting_submission_window"
    NEEDS_REVIEW = "needs_review"
    OTP_BACKOFF = "otp_backoff"
    SUCCEEDED = "succeeded"
    SUCCESS = "success"
    FAILED = "failed"
    DAILY_LIMIT_REACHED = "daily_limit_reached"
    DEAD_LETTER = "dead_letter"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"
    RECONCILING = "reconciling"


class EnqueueWaybillResponse(BaseModel):
    task_id: str
    idempotency_key: str
    correlation_id: str
    priority: int = 5
    status: TaskStatus
    queued: bool = True
    reused: bool = False
    celery_task_id: str | None = None


class WaybillTaskStatusResponse(BaseModel):
    task_id: str
    idempotency_key: str
    correlation_id: str = "-"
    priority: int = 5
    status: TaskStatus
    attempt_count: int = 0
    max_retries: int = 0
    retryable: bool = False
    celery_task_id: str | None = None
    worker_id: str | None = None
    error_category: str | None = None
    last_error: str | None = None
    result: dict[str, Any] | None = None
    next_retry_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class QueueSnapshotResponse(BaseModel):
    queued: int = Field(default=0)
    processing: int = Field(default=0)
    retrying: int = Field(default=0)
    otp_backoff: int = Field(default=0)
    waiting_submission_window: int = Field(default=0)
    dead_letter: int = Field(default=0)
    succeeded: int = Field(default=0)
    failed: int = Field(default=0)
