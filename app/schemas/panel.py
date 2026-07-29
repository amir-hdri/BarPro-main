"""
Schemas for Client Panel API
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ==================== Driver Management Schemas ====================


class DriverCreateRequest(BaseModel):
    """Create new driver request"""

    driver_national_code: str = Field(min_length=10, max_length=10)
    full_name: str = Field(min_length=2, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    license_number: str | None = Field(default=None, max_length=50)

    # Vehicle info
    vehicle_plate: str = Field(min_length=2, max_length=20)
    vehicle_type: str | None = Field(default=None, max_length=50)
    vehicle_model: str | None = Field(default=None, max_length=100)

    # UTCMS credentials
    utcms_username: str = Field(min_length=3, max_length=100)
    utcms_password: str = Field(min_length=3)


class DriverUpdateRequest(BaseModel):
    """Update driver request"""

    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    license_number: str | None = Field(default=None, max_length=50)

    # Vehicle info
    vehicle_plate: str | None = Field(default=None, min_length=2, max_length=20)
    vehicle_type: str | None = Field(default=None, max_length=50)
    vehicle_model: str | None = Field(default=None, max_length=100)

    # UTCMS credentials
    utcms_username: str | None = Field(default=None, min_length=3, max_length=100)
    utcms_password: str | None = Field(default=None, min_length=3)

    # Status
    status: str | None = Field(default=None, pattern="^(active|inactive|suspended)$")


class DriverResponse(BaseModel):
    """Driver response"""

    id: int
    client_id: int
    driver_national_code: str
    full_name: str
    phone: str | None = None
    license_number: str | None = None

    # Vehicle info
    vehicle_plate: str
    vehicle_type: str | None = None
    vehicle_model: str | None = None

    # UTCMS credentials (username only, no password)
    utcms_username: str

    # Status
    status: str
    runtime_status: str

    # Schedule
    auto_schedule_enabled: bool
    schedule_config: dict | None = None

    # Stats
    total_waybills: int
    successful_waybills: int
    failed_waybills: int
    success_rate: float = 0.0
    last_waybill_at: datetime | None = None

    # Auth info
    last_auth_at: datetime | None = None
    last_error_message: str | None = None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DriverListResponse(BaseModel):
    """Driver list item response"""

    id: int
    driver_national_code: str
    full_name: str
    vehicle_plate: str
    vehicle_type: str | None = None
    status: str
    runtime_status: str
    auto_schedule_enabled: bool
    total_waybills: int
    successful_waybills: int
    success_rate: float = 0.0
    last_waybill_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==================== Schedule Management Schemas ====================


class ScheduleCreateRequest(BaseModel):
    """Create schedule request"""

    schedule_type: str = Field(pattern="^(daily|weekly|monthly|custom)$")
    schedule_time: str = Field(pattern="^([0-1][0-9]|2[0-3]):[0-5][0-9]$")  # HH:MM
    schedule_days: list[str] | None = None  # ["monday", "tuesday", ...]

    # Waybill template
    waybill_template: dict = Field(
        description="Template for waybill data",
        json_schema_extra={
            "example": {
                "sender_name": "شرکت حمل و نقل",
                "sender_phone": "09123456789",
                "receiver_name": "مقصد",
                "cargo_type": "کالای عمومی",
                "cargo_weight": "1000",
            }
        },
    )


class ScheduleUpdateRequest(BaseModel):
    """Update schedule request"""

    schedule_type: str | None = Field(default=None, pattern="^(daily|weekly|monthly|custom)$")
    schedule_time: str | None = Field(default=None, pattern="^([0-1][0-9]|2[0-3]):[0-5][0-9]$")
    schedule_days: list[str] | None = None
    waybill_template: dict | None = None
    is_active: bool | None = None


class ScheduleResponse(BaseModel):
    """Schedule response"""

    id: int
    driver_id: int
    schedule_type: str
    schedule_time: str
    schedule_days: list[str] | None = None
    waybill_template: dict
    is_active: bool
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    total_runs: int
    successful_runs: int
    failed_runs: int
    success_rate: float = 0.0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==================== Waybill Management Schemas ====================


class WaybillCreateRequest(BaseModel):
    """Create waybill request"""

    driver_id: int

    # Sender info
    sender_name: str
    sender_phone: str
    sender_address: str
    sender_national_code: str | None = None

    # Receiver info
    receiver_name: str
    receiver_phone: str
    receiver_address: str
    receiver_national_code: str | None = None

    # Origin
    origin_province: str
    origin_city: str
    origin_district: str | None = None
    origin_address: str

    # Destination
    destination_province: str
    destination_city: str
    destination_district: str | None = None
    destination_address: str

    # Cargo
    cargo_type: str
    cargo_weight: str
    cargo_count: str = "1"
    cargo_description: str | None = None

    # Financial
    financial_cost: str | None = None
    payment_method: str | None = None

    # Options
    two_way: bool = False
    time_limit: str | None = None
    notes: str | None = None


class WaybillResponse(BaseModel):
    """Waybill response"""

    id: int
    job_id: str
    client_id: int
    driver_id: int
    status: str
    scheduled_by: str

    # Result
    waybill_number: str | None = None
    payload_json: dict | list | str | Any | None = None
    result_json: dict | list | str | Any | None = None

    # Error info
    terminal_reason: str | None = None
    last_error: str | None = None

    # Timing
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float | None = None

    @field_validator("payload_json", "result_json", mode="before")
    @classmethod
    def coerce_json_fields(cls, v: Any) -> Any:
        if v is None:
            return v
        if isinstance(v, (dict, list)):
            return v
        if isinstance(v, str):
            import json

            try:
                return json.loads(v)
            except (ValueError, TypeError):
                return v
        return v

    model_config = ConfigDict(from_attributes=True)


class WaybillListResponse(BaseModel):
    """Waybill list item response"""

    id: int
    job_id: str
    driver_id: int
    driver_name: str
    vehicle_plate: str
    status: str
    scheduled_by: str
    waybill_number: str | None = None
    terminal_reason: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


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

    driver_id: int | None = None
    status: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
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
    last_waybill_at: datetime | None = None


class WaybillsByDateReport(BaseModel):
    """Waybills grouped by date"""

    date: str
    total: int
    successful: int
    failed: int
    pending: int
    success_rate: float
