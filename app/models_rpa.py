"""Phase 1 operational models for multi-tenant RPA orchestration."""

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import Column, DateTime, Index, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class DriverRuntimeStateValue(StrEnum):
    ACTIVE = "active"
    AUTH_REQUIRED = "auth_required"
    AUTH_IN_PROGRESS = "auth_in_progress"
    READY = "ready"
    SUBMITTING = "submitting"
    WAITING_RETRY = "waiting_retry"
    RATE_LIMIT_COOLDOWN = "rate_limit_cooldown"
    DAILY_SUCCESS_LIMIT_REACHED = "daily_success_limit_reached"
    DAILY_ATTEMPT_LIMIT_REACHED = "daily_attempt_limit_reached"
    INVALID_CREDENTIALS = "invalid_credentials"
    DISABLED = "disabled"
    ERROR_REVIEW = "error_review"


class AttemptType(StrEnum):
    SUBMIT = "submit"
    AUTH = "auth"
    REFRESH = "refresh"


class AttemptResult(StrEnum):
    SUCCESS = "success"
    AUTH_EXPIRED = "auth_expired"
    RATE_LIMITED = "rate_limited"
    TRANSIENT_FAILURE = "transient_failure"
    VALIDATION_ERROR = "validation_error"
    DUPLICATE = "duplicate"
    INVALID_CREDENTIALS = "invalid_credentials"
    UNKNOWN_ERROR = "unknown_error"


class DriverRuntimeState(SQLModel, table=True):
    __tablename__ = "driver_runtime_states"
    __table_args__ = (
        UniqueConstraint("driver_id", name="uq_driver_runtime_states_driver_id"),
        Index("idx_driver_runtime_states_client_state", "client_id", "state"),
        Index("idx_driver_runtime_states_next_retry_at", "next_retry_at"),
    )

    id: int | None = Field(default=None, primary_key=True)
    client_id: int = Field(foreign_key="clients.id", index=True)
    driver_id: int = Field(foreign_key="drivers.id", index=True)
    state: str = Field(default=DriverRuntimeStateValue.ACTIVE.value, max_length=64, index=True)
    session_version: int = Field(default=0)
    last_auth_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))
    session_expires_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))
    next_retry_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))
    paused_until: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))
    proxy_key: str | None = Field(default=None, max_length=128, index=True)
    last_error_code: str | None = Field(default=None, max_length=64, index=True)
    last_error_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )


class DriverDailyCounter(SQLModel, table=True):
    __tablename__ = "driver_daily_counters"
    __table_args__ = (
        UniqueConstraint("business_date", "client_id", "driver_id", name="uq_driver_daily_counters_scope"),
        Index("idx_driver_daily_counters_client_date", "client_id", "business_date"),
    )

    id: int | None = Field(default=None, primary_key=True)
    business_date: str = Field(max_length=16, index=True)
    client_id: int = Field(foreign_key="clients.id", index=True)
    driver_id: int = Field(foreign_key="drivers.id", index=True)
    attempts: int = Field(default=0)
    successes: int = Field(default=0)
    last_attempt_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))
    last_success_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )


class DriverSessionMetadata(SQLModel, table=True):
    __tablename__ = "driver_session_metadata"
    __table_args__ = (
        UniqueConstraint("driver_id", name="uq_driver_session_metadata_driver_id"),
        Index("idx_driver_session_metadata_client_driver", "client_id", "driver_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    client_id: int = Field(foreign_key="clients.id", index=True)
    driver_id: int = Field(foreign_key="drivers.id", index=True)
    session_version: int = Field(default=0)
    auth_state_path: str | None = Field(default=None, max_length=512)
    user_agent: str | None = Field(default=None, max_length=512)
    csrf_token: str | None = Field(default=None, max_length=512)
    expires_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))
    last_auth_result: str | None = Field(default=None, max_length=64)
    last_auth_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))
    proxy_key: str | None = Field(default=None, max_length=128)
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )


class WaybillAttempt(SQLModel, table=True):
    __tablename__ = "waybill_attempts"
    __table_args__ = (
        UniqueConstraint("attempt_id", name="uq_waybill_attempts_attempt_id"),
        Index("idx_waybill_attempts_job_id", "job_id"),
        Index("idx_waybill_attempts_driver_id_created", "driver_id", "created_at"),
        Index("idx_waybill_attempts_result", "result"),
    )

    id: int | None = Field(default=None, primary_key=True)
    attempt_id: str = Field(max_length=64, index=True)
    job_id: str = Field(max_length=100, index=True)
    client_id: int = Field(foreign_key="clients.id", index=True)
    driver_id: int = Field(foreign_key="drivers.id", index=True)
    attempt_no: int = Field(default=1)
    attempt_type: str = Field(default=AttemptType.SUBMIT.value, max_length=32)
    result: str = Field(default=AttemptResult.UNKNOWN_ERROR.value, max_length=64, index=True)
    http_status: int | None = Field(default=None)
    reason_code: str | None = Field(default=None, max_length=64, index=True)
    latency_ms: int | None = Field(default=None)
    session_version: int = Field(default=0)
    proxy_key: str | None = Field(default=None, max_length=128)
    response_excerpt: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )


class DomainEvent(SQLModel, table=True):
    __tablename__ = "domain_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_domain_events_event_id"),
        Index("idx_domain_events_type_created", "event_type", "created_at"),
    )

    id: int | None = Field(default=None, primary_key=True)
    event_id: str = Field(max_length=64, index=True)
    event_type: str = Field(max_length=64, index=True)
    client_id: int = Field(foreign_key="clients.id", index=True)
    driver_id: int | None = Field(default=None, foreign_key="drivers.id", index=True)
    job_id: str | None = Field(default=None, max_length=100, index=True)
    payload_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )
    processed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))


class ProxyEndpoint(SQLModel, table=True):
    __tablename__ = "proxy_endpoints"
    __table_args__ = (
        UniqueConstraint("client_id", "proxy_key", name="uq_proxy_endpoints_scope"),
        Index("idx_proxy_endpoints_health", "client_id", "is_active", "is_healthy"),
    )

    id: int | None = Field(default=None, primary_key=True)
    client_id: int = Field(foreign_key="clients.id", index=True)
    proxy_key: str = Field(max_length=128, index=True)
    endpoint_url: str = Field(max_length=512)
    is_active: bool = Field(default=True)
    is_healthy: bool = Field(default=True)
    consecutive_failures: int = Field(default=0)
    last_success_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))
    last_failure_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))
    cooldown_until: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))
    notes: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )
