"""
Schemas for Client Panel API
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ==================== Driver Management Schemas ====================

class DriverCreateRequest(BaseModel):
    """Create new driver request"""
    driver_national_code: str = Field(min_length=10, max_length=10)
    full_name: str = Field(min_length=2, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=20)
    license_number: Optional[str] = Field(default=None, max_length=50)
    
    # Vehicle info
    vehicle_plate: str = Field(min_length=2, max_length=20)
    vehicle_type: Optional[str] = Field(default=None, max_length=50)
    vehicle_model: Optional[str] = Field(default=None, max_length=100)
    
    # UTCMS credentials
    utcms_username: str = Field(min_length=3, max_length=100)
    utcms_password: str = Field(min_length=3)


class DriverUpdateRequest(BaseModel):
    """Update driver request"""
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=20)
    license_number: Optional[str] = Field(default=None, max_length=50)
    
    # Vehicle info
    vehicle_plate: Optional[str] = Field(default=None, min_length=2, max_length=20)
    vehicle_type: Optional[str] = Field(default=None, max_length=50)
    vehicle_model: Optional[str] = Field(default=None, max_length=100)
    
    # UTCMS credentials
    utcms_username: Optional[str] = Field(default=None, min_length=3, max_length=100)
    utcms_password: Optional[str] = Field(default=None, min_length=3)
    
    # Status
    status: Optional[str] = Field(default=None, pattern="^(active|inactive|suspended)$")


class DriverResponse(BaseModel):
    """Driver response"""
    id: int
    client_id: int
    driver_national_code: str
    full_name: str
    phone: Optional[str] = None
    license_number: Optional[str] = None
    
    # Vehicle info
    vehicle_plate: str
    vehicle_type: Optional[str] = None
    vehicle_model: Optional[str] = None
    
    # UTCMS credentials (username only, no password)
    utcms_username: str
    
    # Status
    status: str
    runtime_status: str
    
    # Schedule
    auto_schedule_enabled: bool
    schedule_config: Optional[dict] = None
    
    # Stats
    total_waybills: int
    successful_waybills: int
    failed_waybills: int
    success_rate: float = 0.0
    last_waybill_at: Optional[datetime] = None
    
    # Auth info
    last_auth_at: Optional[datetime] = None
    last_error_message: Optional[str] = None
    
    created_at: datetime
    updated_at: datetime


class DriverListResponse(BaseModel):
    """Driver list item response"""
    id: int
    driver_national_code: str
    full_name: str
    vehicle_plate: str
    vehicle_type: Optional[str] = None
    status: str
    runtime_status: str
    auto_schedule_enabled: bool
    total_waybills: int
    successful_waybills: int
    success_rate: float = 0.0
    last_waybill_at: Optional[datetime] = None
    created_at: datetime


# ==================== Schedule Management Schemas ====================

class ScheduleCreateRequest(BaseModel):
    """Create schedule request"""
    schedule_type: str = Field(pattern="^(daily|weekly|monthly|custom)$")
    schedule_time: str = Field(pattern="^([0-1][0-9]|2[0-3]):[0-5][0-9]$")  # HH:MM
    schedule_days: Optional[list[str]] = None  # ["monday", "tuesday", ...]
    
    # Waybill template
    waybill_template: dict = Field(
        description="Template for waybill data",
        example={
            "sender_name": "شرکت حمل و نقل",
            "sender_phone": "09123456789",
            "receiver_name": "مقصد",
            "cargo_type": "کالای عمومی",
            "cargo_weight": "1000"
        }
    )


class ScheduleUpdateRequest(BaseModel):
    """Update schedule request"""
    schedule_type: Optional[str] = Field(default=None, pattern="^(daily|weekly|monthly|custom)$")
    schedule_time: Optional[str] = Field(default=None, pattern="^([0-1][0-9]|2[0-3]):[0-5][0-9]$")
    schedule_days: Optional[list[str]] = None
    waybill_template: Optional[dict] = None
    is_active: Optional[bool] = None


class ScheduleResponse(BaseModel):
    """Schedule response"""
    id: int
    driver_id: int
    schedule_type: str
    schedule_time: str
    schedule_days: Optional[list[str]] = None
    waybill_template: dict
    is_active: bool
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    total_runs: int
    successful_runs: int
    failed_runs: int
    success_rate: float = 0.0
    created_at: datetime
    updated_at: datetime


# ==================== Waybill Management Schemas ====================

class WaybillCreateRequest(BaseModel):
    """Create waybill request"""
    driver_id: int
    
    # Sender info
    sender_name: str
    sender_phone: str
    sender_address: str
    sender_national_code: Optional[str] = None
    
    # Receiver info
    receiver_name: str
    receiver_phone: str
    receiver_address: str
    receiver_national_code: Optional[str] = None
    
    # Origin
    origin_province: str
    origin_city: str
    origin_district: Optional[str] = None
    origin_address: str
    
    # Destination
    destination_province: str
    destination_city: str
    destination_district: Optional[str] = None
    destination_address: str
    
    # Cargo
    cargo_type: str
    cargo_weight: str
    cargo_count: str = "1"
    cargo_description: Optional[str] = None
    
    # Financial
    financial_cost: Optional[str] = None
    payment_method: Optional[str] = None
    
    # Options
    two_way: bool = False
    time_limit: Optional[str] = None
    notes: Optional[str] = None


class WaybillResponse(BaseModel):
    """Waybill response"""
    id: int
    job_id: str
    client_id: int
    driver_id: int
    status: str
    scheduled_by: str
    
    # Result
    waybill_number: Optional[str] = None
    result_json: Optional[dict] = None
    
    # Error info
    terminal_reason: Optional[str] = None
    last_error: Optional[str] = None
    
    # Timing
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None


class WaybillListResponse(BaseModel):
    """Waybill list item response"""
    id: int
    job_id: str
    driver_id: int
    driver_name: str
    vehicle_plate: str
    status: str
    scheduled_by: str
    waybill_number: Optional[str] = None
    terminal_reason: Optional[str] = None
    created_at: datetime
    finished_at: Optional[datetime] = None


# ==================== Dashboard Schemas ====================

class PanelDashboardStats(BaseModel):
    """Client panel dashboard statistics"""
    total_drivers: int
    active_drivers: int
    inactive_drivers: int
    
    total_waybills: int
    successful_waybills: int
    failed_waybills: int
    pending_waybills: int
    
    waybills_today: int
    successful_today: int
    failed_today: int
    
    waybills_this_week: int
    waybills_this_month: int
    
    success_rate: float
    avg_waybills_per_day: float
    
    # Limits
    max_drivers: int
    max_concurrent_tasks: int
    max_daily_tasks: int
    
    # Usage
    drivers_usage_percent: float
    daily_tasks_usage_percent: float


# ==================== Report Schemas ====================

class ReportFilter(BaseModel):
    """Report filter"""
    driver_id: Optional[int] = None
    status: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)


class DriverReport(BaseModel):
    """Driver performance report"""
    driver_id: int
    driver_name: str
    vehicle_plate: str
    total_waybills: int
    successful_waybills: int
    failed_waybills: int
    success_rate: float
    avg_duration_seconds: float
    last_waybill_at: Optional[datetime] = None


class WaybillsByDateReport(BaseModel):
    """Waybills grouped by date"""
    date: str
    total: int
    successful: int
    failed: int
    pending: int
    success_rate: float
