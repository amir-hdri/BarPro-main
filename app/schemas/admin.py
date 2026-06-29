"""
Schemas for Super Admin API
"""

from datetime import datetime

from pydantic import BaseModel, Field

# ==================== Super Admin Schemas ====================


class SuperAdminLogin(BaseModel):
    """Super Admin login request"""

    username: str
    password: str


class SuperAdminResponse(BaseModel):
    """Super Admin response"""

    id: int
    username: str
    email: str
    full_name: str | None = None
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


# ==================== Client Management Schemas ====================


class ClientCreateRequest(BaseModel):
    """Create new client request (by Super Admin)"""

    username: str = Field(min_length=3, max_length=50)
    email: str
    password: str = Field(min_length=6)
    full_name: str = Field(min_length=2, max_length=255)
    company_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    national_code: str | None = Field(default=None, max_length=10)

    # Limits
    max_drivers: int = Field(default=10, ge=1, le=1000)
    max_concurrent_tasks: int = Field(default=2, ge=1, le=50)
    max_daily_tasks: int = Field(default=100, ge=1, le=10000)

    # Subscription
    subscription_plan_id: int | None = None

    notes: str | None = None


class ClientUpdateRequest(BaseModel):
    """Update client request (by Super Admin)"""

    email: str | None = None
    password: str | None = Field(default=None, min_length=6)
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    company_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    national_code: str | None = Field(default=None, max_length=10)

    # Limits
    max_drivers: int | None = Field(default=None, ge=1, le=1000)
    max_concurrent_tasks: int | None = Field(default=None, ge=1, le=50)
    max_daily_tasks: int | None = Field(default=None, ge=1, le=10000)

    # Subscription
    subscription_plan_id: int | None = None

    # Status
    status: str | None = Field(default=None, pattern="^(active|suspended|inactive)$")

    notes: str | None = None


class ClientStatusUpdate(BaseModel):
    """Update client status"""

    status: str = Field(pattern="^(active|suspended|inactive)$")
    reason: str | None = None


class ClientDetailResponse(BaseModel):
    """Detailed client response"""

    id: int
    client_code: str
    username: str
    email: str
    full_name: str
    company_name: str | None = None
    phone: str | None = None
    national_code: str | None = None
    status: str
    is_active: bool

    # Limits
    max_drivers: int
    max_concurrent_tasks: int
    max_daily_tasks: int

    # Subscription
    subscription_plan_id: int | None = None
    subscription_plan_name: str | None = None
    subscription_start_date: datetime | None = None
    subscription_end_date: datetime | None = None

    # Stats
    total_drivers: int = 0
    active_drivers: int = 0
    total_waybills: int = 0
    successful_waybills: int = 0
    failed_waybills: int = 0

    # Metadata
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None
    created_by_admin_id: int | None = None


class ClientListResponse(BaseModel):
    """Client list item response"""

    id: int
    client_code: str
    username: str
    email: str
    full_name: str
    company_name: str | None = None
    status: str
    is_active: bool
    max_drivers: int
    total_drivers: int = 0
    active_drivers: int = 0
    subscription_plan_name: str | None = None
    created_at: datetime
    last_login_at: datetime | None = None


# ==================== Dashboard Schemas ====================


class AdminDashboardStats(BaseModel):
    """Super Admin dashboard statistics"""

    total_clients: int
    active_clients: int
    suspended_clients: int
    inactive_clients: int

    total_drivers: int
    active_drivers: int

    total_waybills_today: int
    successful_waybills_today: int
    failed_waybills_today: int

    total_waybills_month: int
    successful_waybills_month: int
    failed_waybills_month: int

    system_health: str  # healthy, warning, critical


# ==================== Subscription Plan Schemas ====================


class SubscriptionPlanResponse(BaseModel):
    """Subscription plan response"""

    id: int
    name: str
    name_fa: str
    description: str | None = None
    price_monthly: float | None = None
    price_yearly: float | None = None
    max_drivers: int
    max_concurrent_tasks: int
    max_daily_tasks: int
    features: dict | None = None
    is_active: bool
    is_public: bool


# ==================== Activity Log Schemas ====================


class ActivityLogResponse(BaseModel):
    """Activity log response"""

    id: int
    user_type: str
    user_id: int
    user_name: str | None = None
    action: str
    entity_type: str | None = None
    entity_id: int | None = None
    description: str | None = None
    changes: dict | None = None
    ip_address: str | None = None
    created_at: datetime


class ActivityLogFilter(BaseModel):
    """Activity log filter"""

    user_type: str | None = None
    user_id: int | None = None
    action: str | None = None
    entity_type: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)


# ==================== Analytics Schemas ====================


class ClientAnalytics(BaseModel):
    """Client analytics data"""

    client_id: int
    client_name: str
    total_drivers: int
    active_drivers: int
    total_waybills: int
    successful_waybills: int
    failed_waybills: int
    success_rate: float
    avg_waybills_per_day: float


class DriverReportFilter(BaseModel):
    """Filter parameters for driver reports"""

    client_id: int | None = Field(default=None, description="Filter by client")
    driver_id: int | None = Field(default=None, description="Filter by driver")
    plate_id: int | None = Field(default=None, description="Filter by plate (uses driver_id)")
    status: str | None = Field(default=None, description="Filter by job status")
    date_from: str | None = Field(default=None, description="Start date (YYYY-MM-DD)")
    date_to: str | None = Field(default=None, description="End date (YYYY-MM-DD)")
    operation_type: str | None = Field(default=None, description="Filter by source (manual, api, bulk_upload)")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


class SystemAnalytics(BaseModel):
    """System-wide analytics"""

    total_clients: int
    total_drivers: int
    total_waybills: int
    success_rate: float
    top_clients: list[ClientAnalytics]
    waybills_by_day: list[dict]  # [{"date": "2025-05-01", "total": 100, "successful": 95}]
    waybills_by_status: dict  # {"pending": 10, "in_progress": 5, "completed": 85}
