"""Schemas for Phase 1 orchestration observability APIs."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

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
    last_auth_at: Optional[datetime] = None
    session_expires_at: Optional[datetime] = None
    next_retry_at: Optional[datetime] = None
    paused_until: Optional[datetime] = None
    proxy_key: Optional[str] = None
    last_error_code: Optional[str] = None
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
