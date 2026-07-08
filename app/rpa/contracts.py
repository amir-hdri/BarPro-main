"""Contracts for hybrid auth/submit orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class SubmitOutcome(StrEnum):
    SUCCESS = "success"
    AUTH_EXPIRED = "auth_expired"
    RATE_LIMITED = "rate_limited"
    TRANSIENT_FAILURE = "transient_failure"
    VALIDATION_ERROR = "validation_error"
    DUPLICATE = "duplicate"
    UNKNOWN_ERROR = "unknown_error"


@dataclass(slots=True)
class SessionBundle:
    cookies: list[dict[str, Any]] = field(default_factory=list)
    user_agent: str = ""
    csrf_token: str | None = None
    hidden_form_state: dict[str, str] = field(default_factory=dict)
    issued_at: str | None = None
    expires_at: str | None = None
    session_version: int = 0
    proxy_key: str | None = None


@dataclass(slots=True)
class SubmitClassification:
    outcome: SubmitOutcome
    reason_code: str
    retryable: bool
    http_status: int | None = None
    message: str | None = None
    response_excerpt: str | None = None


@dataclass(slots=True)
class SubmitExecutionResult:
    classification: SubmitClassification
    latency_ms: int
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AuthResult:
    ok: bool
    session_bundle: SessionBundle | None
    reason_code: str
    message: str | None = None
    expires_at: datetime | None = None


@dataclass(slots=True)
class SchedulerDecision:
    job_id: str
    driver_id: int
    client_id: int
    queue_name: str
    reason: str
    priority: int = 5


@dataclass(slots=True)
class RuntimeCounterSnapshot:
    business_date: str
    attempts: int
    successes: int
