"""
Multi-tenant database schema for UTCMS Automation SaaS.

This module defines the complete relational schema ensuring strict tenant isolation.
Each client has isolated access to their own drivers and waybill tasks.
"""

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import JSON, Boolean, Column, DateTime, Index, Integer, Text, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

# ==================== ENUMS ====================


class ClientStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    INACTIVE = "inactive"


class DriverStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    BLOCKED = "blocked"
    AUTH_REQUIRED = "auth_required"
    READY = "ready"
    WAITING_RETRY = "waiting_retry"
    RATE_LIMITED = "rate_limited"
    INVALID_CREDENTIALS = "invalid_credentials"
    DAILY_LIMIT_REACHED = "daily_limit_reached"


class TaskStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    CLAIMED = "claimed"
    RUNNING = "running"
    RETRYING = "retrying"
    WAITING_AUTH = "waiting_auth"
    WAITING_RETRY = "waiting_retry"
    WAITING_SUBMISSION_WINDOW = "waiting_submission_window"
    NEEDS_REVIEW = "needs_review"
    OTP_BACKOFF = "otp_backoff"
    SUCCESS = "success"
    FAILED = "failed"
    DAILY_LIMIT_REACHED = "daily_limit_reached"
    DEAD_LETTER = "dead_letter"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"
    RECONCILING = "reconciling"


class TaskSource(StrEnum):
    MANUAL = "manual"
    BULK_UPLOAD = "bulk_upload"
    API = "api"


class ScheduleFrequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    ONCE = "once"


class ErrorCategory(StrEnum):
    LOGIN_FAILED = "login_failed"
    CAPTCHA_FAILED = "captcha_failed"
    FORM_FILL_FAILED = "form_fill_failed"
    SUBMISSION_FAILED = "submission_failed"
    NETWORK_ERROR = "network_error"
    VALIDATION_ERROR = "validation_error"
    UNKNOWN = "unknown"


# ==================== MULTI-TENANT MODELS ====================


class Client(SQLModel, table=True):
    """
    Represents a tenant (مشتری) in the multi-tenant system.
    Each client has strictly isolated data and can only access their own resources.
    """

    __tablename__ = "clients"
    __table_args__ = (
        UniqueConstraint("client_code", name="uq_clients_client_code"),
        UniqueConstraint("email", name="uq_clients_email"),
        Index("idx_clients_status", "status"),
        Index("idx_clients_created_at", "created_at"),
    )

    id: int | None = Field(default=None, primary_key=True)
    client_code: str = Field(max_length=50, index=True, unique=True)
    name: str = Field(max_length=255)
    email: str = Field(max_length=255, index=True)
    phone: str | None = Field(default=None, max_length=20)
    hashed_password: str = Field(max_length=255)
    status: str = Field(default=ClientStatus.ACTIVE.value, max_length=20, index=True)
    access_level: str = Field(default="standard", max_length=50)

    # Legacy/DB mandatory columns (used by some auth/registration logic)
    # These columns exist in the DB schema and must be non-null.
    username: str = Field(max_length=255, sa_column=Column(Text, nullable=False))
    full_name: str = Field(max_length=255, sa_column=Column(Text, nullable=False))

    # Subscription & limits
    max_drivers: int = Field(default=10)
    max_plates: int = Field(default=20)
    max_concurrent_tasks: int = Field(default=2)
    max_daily_tasks: int = Field(default=100)

    # Metadata
    metadata_json: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    notes: str | None = Field(default=None, sa_column=Column(Text, nullable=True))

    # ORM relationships
    drivers: list["Driver"] = Relationship(back_populates="client")
    plates: list["DriverPlate"] = Relationship(back_populates="client")
    schedules: list["DriverSchedule"] = Relationship(back_populates="client")
    jobs: list["WaybillJob"] = Relationship(back_populates="client")
    task_logs: list["WaybillTaskLog"] = Relationship(back_populates="client")
    upload_batches: list["UploadBatch"] = Relationship(back_populates="client")
    fuel_inquiries: list["FuelInquiry"] = Relationship(back_populates="client")

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )
    last_login_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=False), nullable=True),
    )
    subscription_start_date: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=False), nullable=True),
    )
    subscription_end_date: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=False), nullable=True),
    )


class Driver(SQLModel, table=True):
    """
    Represents a driver (راننده) belonging to a specific client.
    Contains credentials for accessing the external UTCMS system.
    """

    __tablename__ = "drivers"
    __table_args__ = (
        UniqueConstraint("client_id", "driver_national_code", name="uq_driver_client_national_code"),
        Index("idx_drivers_client_id", "client_id"),
        Index("idx_drivers_status", "status"),
        Index("idx_drivers_national_code", "driver_national_code"),
    )

    id: int | None = Field(default=None, primary_key=True)
    client_id: int = Field(foreign_key="clients.id", index=True)

    # Driver identity
    driver_national_code: str = Field(max_length=10, index=True)
    full_name: str = Field(max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    license_number: str | None = Field(default=None, max_length=50)

    # UTCMS credentials (encrypted at rest)
    utcms_username: str = Field(max_length=100)
    utcms_password_encrypted: str = Field(sa_column=Column(Text, nullable=False))

    # Default waybill information (stored as JSON)
    default_payload_json: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))

    # Status & metadata
    status: str = Field(default=DriverStatus.ACTIVE.value, max_length=20, index=True)
    metadata_json: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    runtime_status: str = Field(default=DriverStatus.ACTIVE.value, max_length=40, index=True)
    last_auth_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=False), nullable=True),
    )
    last_session_expires_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=False), nullable=True),
    )
    last_error_code: str | None = Field(default=None, max_length=64, index=True)

    # ORM relationships
    client: Client | None = Relationship(back_populates="drivers")
    plates: list["DriverPlate"] = Relationship(back_populates="driver")
    schedules: list["DriverSchedule"] = Relationship(back_populates="driver")
    jobs: list["WaybillJob"] = Relationship(back_populates="driver")
    fuel_inquiries: list["FuelInquiry"] = Relationship(back_populates="driver")

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )


class DriverPlate(SQLModel, table=True):
    """Vehicle plate assigned to a driver under a tenant."""

    __tablename__ = "driver_plates"
    __table_args__ = (
        UniqueConstraint("client_id", "plate_number", name="uq_driver_plate_client_plate"),
        Index("idx_driver_plates_client_id", "client_id"),
        Index("idx_driver_plates_driver_id", "driver_id"),
        Index("idx_driver_plates_status", "status"),
    )

    id: int | None = Field(default=None, primary_key=True)
    client_id: int = Field(foreign_key="clients.id", index=True)
    driver_id: int = Field(foreign_key="drivers.id", index=True)
    plate_number: str = Field(max_length=20, index=True)
    vehicle_type: str | None = Field(default=None, max_length=100)
    status: str = Field(default=DriverStatus.ACTIVE.value, max_length=20, index=True)
    notes: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )

    # ORM relationships
    client: Client | None = Relationship(back_populates="plates")
    driver: Driver | None = Relationship(back_populates="plates")


class DriverSchedule(SQLModel, table=True):
    """Auto waybill schedule definition per driver."""

    __tablename__ = "driver_schedules"
    __table_args__ = (
        Index("idx_driver_schedules_client_id", "client_id"),
        Index("idx_driver_schedules_driver_id", "driver_id"),
        Index("idx_driver_schedules_is_active", "is_active"),
    )

    id: int | None = Field(default=None, primary_key=True)
    client_id: int = Field(foreign_key="clients.id", index=True)
    driver_id: int = Field(foreign_key="drivers.id", index=True)
    title: str = Field(max_length=255)
    frequency: str = Field(default=ScheduleFrequency.DAILY.value, max_length=20)
    run_time: str = Field(default="08:00", max_length=5)
    run_times_csv: str | None = Field(default=None, max_length=256)
    weekdays_csv: str | None = Field(default=None, max_length=32)
    specific_dates_csv: str | None = Field(default=None, max_length=1024)
    start_date: str | None = Field(default=None, max_length=10)
    end_date: str | None = Field(default=None, max_length=10)
    timezone: str = Field(default="Asia/Tehran", max_length=64)
    payload_template_json: dict = Field(sa_column=Column(JSON, nullable=False))
    is_active: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, default=True))
    last_run_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=False), nullable=True),
    )
    next_run_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=False), nullable=True),
    )
    last_run_signature: str | None = Field(default=None, max_length=64, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )

    # ORM relationships
    client: Client | None = Relationship(back_populates="schedules")
    driver: Driver | None = Relationship(back_populates="schedules")


class WaybillJob(SQLModel, table=True):
    """
    Represents a waybill registration job queued for RPA processing.
    Each job belongs to a client and optionally to a driver.
    """

    __tablename__ = "waybill_jobs"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_waybill_jobs_job_id"),
        UniqueConstraint("idempotency_key", name="uq_waybill_jobs_idempotency_key"),
        Index("idx_waybill_jobs_client_id", "client_id"),
        Index("idx_waybill_jobs_driver_id", "driver_id"),
        Index("idx_waybill_jobs_status", "status"),
        Index("idx_waybill_jobs_created_at", "created_at"),
        Index("idx_waybill_jobs_celery_task_id", "celery_task_id"),
        # Composite index for queue ordering: status, priority DESC, created_at ASC
        # Note: For PostgreSQL, create via migration with:
        # CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_wj_status_priority_created
        # ON waybill_jobs (status, priority DESC, created_at ASC);
    )

    id: int | None = Field(default=None, primary_key=True)
    job_id: str = Field(max_length=100, index=True, unique=True)
    idempotency_key: str = Field(max_length=100, index=True, unique=True)

    # Tenant isolation
    client_id: int = Field(foreign_key="clients.id", index=True)
    driver_id: int | None = Field(default=None, foreign_key="drivers.id", index=True)

    # Task metadata
    status: str = Field(default=TaskStatus.PENDING.value, max_length=20, index=True)
    source: str = Field(default=TaskSource.MANUAL.value, max_length=20)

    # Waybill data (JSON payload)
    payload_json: dict = Field(sa_column=Column(JSON, nullable=False))
    result_json: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    correlation_id: str | None = Field(default=None, max_length=128, index=True)
    business_date: str | None = Field(default=None, max_length=16, index=True)
    priority: int = Field(default=5, index=True)
    next_retry_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=False), nullable=True),
    )
    submit_after: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=False), nullable=True),
    )
    terminal_reason: str | None = Field(default=None, max_length=64, index=True)

    # Schedule tracking
    schedule_id: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    scheduled_by: str = Field(default="manual", max_length=20)

    # Error tracking
    last_error: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    error_category: str | None = Field(default=None, max_length=50, index=True)
    submission_fingerprint: str | None = Field(default=None, max_length=128, index=True)

    # Mutation & Idempotency tracking
    request_digest: str | None = Field(default=None, max_length=128, index=True)
    document_id: str | None = Field(default=None, max_length=64, index=True)
    mutation_status: str | None = Field(default=None, max_length=32, index=True)
    mutation_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=False), nullable=True),
    )
    reconciled_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=False), nullable=True),
    )

    # Retry logic
    attempt_count: int = Field(default=0)
    max_retries: int = Field(default=3)
    retryable: bool = Field(default=False)
    night_attempt_count: int = Field(default=0)
    night_attempt_window: str | None = Field(default=None, max_length=10, index=True)
    celery_task_id: str | None = Field(default=None, max_length=100, index=True)
    worker_id: str | None = Field(default=None, max_length=100)

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )
    started_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=False), nullable=True),
    )
    finished_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=False), nullable=True),
    )

    # ORM relationships
    client: Client | None = Relationship(back_populates="jobs")
    driver: Driver | None = Relationship(back_populates="jobs")


class WaybillTaskLog(SQLModel, table=True):
    """
    Detailed execution log for each waybill job.
    Tracks every step of the RPA bot for audit purposes.
    """

    __tablename__ = "waybill_task_logs"
    __table_args__ = (
        Index("idx_waybill_task_logs_job_id", "job_id"),
        Index("idx_waybill_task_logs_created_at", "created_at"),
    )

    id: int | None = Field(default=None, primary_key=True)
    job_id: str = Field(max_length=100, index=True)
    client_id: int = Field(foreign_key="clients.id", index=True)

    # Log entry
    step: str = Field(max_length=100)  # e.g., "login", "captcha", "form_fill", "submit"
    status: str = Field(max_length=20)  # "success", "failed", "retry"
    message: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    details_json: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))

    # ORM relationship
    client: Client | None = Relationship(back_populates="task_logs")

    # Timestamp
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )


class UploadBatch(SQLModel, table=True):
    """
    Tracks bulk Excel upload batches for reporting and auditing.
    """

    __tablename__ = "upload_batches"
    __table_args__ = (
        UniqueConstraint("batch_id", name="uq_upload_batches_batch_id"),
        Index("idx_upload_batches_client_id", "client_id"),
        Index("idx_upload_batches_created_at", "created_at"),
    )

    id: int | None = Field(default=None, primary_key=True)
    batch_id: str = Field(max_length=100, index=True, unique=True)
    client_id: int = Field(foreign_key="clients.id", index=True)

    # Upload metadata
    original_filename: str = Field(max_length=255)
    total_rows: int = Field(default=0)
    valid_rows: int = Field(default=0)
    invalid_rows: int = Field(default=0)

    # Processing status
    status: str = Field(default="processing", max_length=20)
    errors_json: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))

    # ORM relationship
    client: Client | None = Relationship(back_populates="upload_batches")

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )
    completed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=False), nullable=True),
    )


class FuelInquiry(SQLModel, table=True):
    """
    Represents a fuel inquiry (استعلام سهمیه سوخت) made for a driver.
    """

    __tablename__ = "fuel_inquiries"
    __table_args__ = (
        Index("idx_fuel_inquiries_client_id", "client_id"),
        Index("idx_fuel_inquiries_driver_id", "driver_id"),
        Index("idx_fuel_inquiries_status", "status"),
    )

    id: int | None = Field(default=None, primary_key=True)
    client_id: int = Field(foreign_key="clients.id", index=True)
    driver_id: int = Field(foreign_key="drivers.id", index=True)

    # Status of the inquiry (pending, processing, success, failed)
    status: str = Field(default="pending", max_length=20, index=True)
    error_message: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    error_category: str | None = Field(default=None, max_length=50, index=True)

    # Quota details (stored as a JSON string)
    quota_data_json: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))

    # ORM relationships
    client: Client | None = Relationship(back_populates="fuel_inquiries")
    driver: Driver | None = Relationship(back_populates="fuel_inquiries")

    # Path or URL to screenshot of the fuel quota page
    screenshot_url: str | None = Field(default=None, sa_column=Column(Text, nullable=True))

    # Jalali Year and Month for custom period inquiry
    year: int | None = Field(default=None, nullable=True)
    month: int | None = Field(default=None, nullable=True)

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )


# Ensure UTCMSSystemObservation table is included in SQLModel metadata
from app.models_rpa import UTCMSSystemObservation  # noqa: E402, F401
