from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    RETRYING = "retrying"
    OTP_BACKOFF = "otp_backoff"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class EnqueueWaybillResponse(BaseModel):
    task_id: str
    idempotency_key: str
    correlation_id: str
    priority: int = 5
    status: TaskStatus
    queued: bool = True
    reused: bool = False
    celery_task_id: Optional[str] = None


class WaybillTaskStatusResponse(BaseModel):
    task_id: str
    idempotency_key: str
    correlation_id: str = "-"
    priority: int = 5
    status: TaskStatus
    attempt_count: int = 0
    max_retries: int = 0
    retryable: bool = False
    celery_task_id: Optional[str] = None
    worker_id: Optional[str] = None
    error_category: Optional[str] = None
    last_error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    next_retry_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class QueueSnapshotResponse(BaseModel):
    queued: int = Field(default=0)
    processing: int = Field(default=0)
    retrying: int = Field(default=0)
    otp_backoff: int = Field(default=0)
    dead_letter: int = Field(default=0)
    succeeded: int = Field(default=0)
    failed: int = Field(default=0)
