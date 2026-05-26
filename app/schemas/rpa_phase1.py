"""Schemas for Phase 1 orchestration observability APIs."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DriverCounterSnapshotResponse(BaseModel):
    business_date: str
    attempts: int
    successes: int


class DriverRuntimeStateResponse(BaseModel):
    driver_id: int
    client_id: int
    state: str
    session_version: int
    last_auth_at: datetime | None = None
    session_expires_at: datetime | None = None
    next_retry_at: datetime | None = None
    paused_until: datetime | None = None
    proxy_key: str | None = None
    last_error_code: str | None = None
    counters: DriverCounterSnapshotResponse


class SchedulerDecisionResponse(BaseModel):
    job_id: str
    driver_id: int
    client_id: int
    queue_name: str
    reason: str
    priority: int


class Phase1OverviewResponse(BaseModel):
    scheduler_batch_size: int
    tenant_slice: int
    session_ttl_seconds: int
    retry_delay_seconds: int
    daily_success_cap: int
    daily_attempt_cap: int
    queues: dict[str, str]
