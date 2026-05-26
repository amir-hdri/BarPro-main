"""
Models for Super Admin and related entities
"""
from datetime import UTC, datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class SuperAdmin(SQLModel, table=True):
    """Super Admin model - manages the entire system"""
    __tablename__ = "super_admins"

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(max_length=50, unique=True, index=True)
    email: str = Field(max_length=255, unique=True, index=True)
    hashed_password: str = Field(max_length=255)
    full_name: str | None = Field(default=None, max_length=255)
    is_active: bool = Field(default=True)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
    last_login_at: datetime | None = None


class SubscriptionPlan(SQLModel, table=True):
    """Subscription plans for clients"""
    __tablename__ = "subscription_plans"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=50)
    name_fa: str = Field(max_length=100)
    description: str | None = None

    # Pricing
    price_monthly: float | None = None
    price_yearly: float | None = None

    # Limits
    max_drivers: int
    max_concurrent_tasks: int
    max_daily_tasks: int

    # Features (JSON)
    features: dict | None = Field(default=None, sa_column=Column(JSON))

    # Status
    is_active: bool = Field(default=True)
    is_public: bool = Field(default=True)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


class AdminDriverSchedule(SQLModel, table=True):
    """Scheduled waybill jobs for drivers (admin legacy model - use models_multitenant.DriverSchedule for multi-tenant)"""
    __tablename__ = "admin_driver_schedules"

    id: int | None = Field(default=None, primary_key=True)
    driver_id: int = Field(foreign_key="drivers.id")

    # Schedule settings
    schedule_type: str = Field(max_length=20)  # daily, weekly, monthly, custom
    schedule_time: str  # HH:MM format
    schedule_days: dict | None = Field(default=None, sa_column=Column(JSON))

    # Waybill template
    waybill_template: dict = Field(sa_column=Column(JSON))

    # Status
    is_active: bool = Field(default=True)
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None

    # Stats
    total_runs: int = Field(default=0)
    successful_runs: int = Field(default=0)
    failed_runs: int = Field(default=0)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


class ActivityLog(SQLModel, table=True):
    """Activity logs for audit trail"""
    __tablename__ = "activity_logs"

    id: int | None = Field(default=None, primary_key=True)

    # User info
    user_type: str = Field(max_length=20)  # super_admin, client
    user_id: int

    # Action info
    action: str = Field(max_length=50)
    entity_type: str | None = Field(default=None, max_length=50)
    entity_id: int | None = None

    # Details
    description: str | None = None
    changes: dict | None = Field(default=None, sa_column=Column(JSON))

    # Metadata
    ip_address: str | None = Field(default=None, max_length=45)
    user_agent: str | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
