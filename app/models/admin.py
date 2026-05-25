"""
Models for Super Admin and related entities
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


class SuperAdmin(SQLModel, table=True):
    """Super Admin model - manages the entire system"""
    __tablename__ = "super_admins"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(max_length=50, unique=True, index=True)
    email: str = Field(max_length=255, unique=True, index=True)
    hashed_password: str = Field(max_length=255)
    full_name: Optional[str] = Field(default=None, max_length=255)
    is_active: bool = Field(default=True)
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    last_login_at: Optional[datetime] = None


class SubscriptionPlan(SQLModel, table=True):
    """Subscription plans for clients"""
    __tablename__ = "subscription_plans"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=50)
    name_fa: str = Field(max_length=100)
    description: Optional[str] = None
    
    # Pricing
    price_monthly: Optional[float] = None
    price_yearly: Optional[float] = None
    
    # Limits
    max_drivers: int
    max_concurrent_tasks: int
    max_daily_tasks: int
    
    # Features (JSON)
    features: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    
    # Status
    is_active: bool = Field(default=True)
    is_public: bool = Field(default=True)
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class AdminDriverSchedule(SQLModel, table=True):
    """Scheduled waybill jobs for drivers (admin legacy model - use models_multitenant.DriverSchedule for multi-tenant)"""
    __tablename__ = "admin_driver_schedules"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    driver_id: int = Field(foreign_key="drivers.id")
    
    # Schedule settings
    schedule_type: str = Field(max_length=20)  # daily, weekly, monthly, custom
    schedule_time: str  # HH:MM format
    schedule_days: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    
    # Waybill template
    waybill_template: dict = Field(sa_column=Column(JSON))
    
    # Status
    is_active: bool = Field(default=True)
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    
    # Stats
    total_runs: int = Field(default=0)
    successful_runs: int = Field(default=0)
    failed_runs: int = Field(default=0)
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class ActivityLog(SQLModel, table=True):
    """Activity logs for audit trail"""
    __tablename__ = "activity_logs"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # User info
    user_type: str = Field(max_length=20)  # super_admin, client
    user_id: int
    
    # Action info
    action: str = Field(max_length=50)
    entity_type: Optional[str] = Field(default=None, max_length=50)
    entity_id: Optional[int] = None
    
    # Details
    description: Optional[str] = None
    changes: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    
    # Metadata
    ip_address: Optional[str] = Field(default=None, max_length=45)
    user_agent: Optional[str] = None
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
