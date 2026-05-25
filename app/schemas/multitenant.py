"""
Pydantic schemas for multi-tenant API requests and responses.
"""
import re
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


PERSIAN_PLATE_LETTERS = "اآبپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی"
PLATE_PATTERN = re.compile(rf"^\d{{2}}[{PERSIAN_PLATE_LETTERS}]\d{{3}}ایران\d{{2}}$")


def _normalize_digits(value: str) -> str:
    result = value or ""
    for index, digit in enumerate("۰۱۲۳۴۵۶۷۸۹"):
        result = result.replace(digit, str(index))
    for index, digit in enumerate("٠١٢٣٤٥٦٧٨٩"):
        result = result.replace(digit, str(index))
    return result


def _normalize_text(value: str) -> str:
    return (value or "").strip().replace("ي", "ی").replace("ك", "ک").replace("ايران", "ایران")


def _normalize_phone(value: str) -> str:
    return re.sub(r"\D", "", _normalize_digits(value))


def _normalize_national_code(value: str) -> str:
    return re.sub(r"\D", "", _normalize_digits(value))


def _normalize_plate(value: str) -> str:
    compact = re.sub(r"[\s\-]+", "", _normalize_text(_normalize_digits(value)))
    compact = compact.replace("ایران", "")
    match = re.fullmatch(rf"(\d{{2}})([{PERSIAN_PLATE_LETTERS}])(\d{{3}})(\d{{2}})", compact)
    if not match:
        raise ValueError("فرمت پلاک باید به صورت ۱۲ب۳۴۵ایران۶۷ باشد")
    return f"{match.group(1)}{match.group(2)}{match.group(3)}ایران{match.group(4)}"


# ==================== AUTH SCHEMAS ====================

class ClientLoginRequest(BaseModel):
    """Client login request."""
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=6, max_length=100)


class AdminLoginRequest(BaseModel):
    """Master admin login request."""
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=3, max_length=100)


class ClientRegisterRequest(BaseModel):
    """Client registration request."""
    client_code: str = Field(..., max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(..., max_length=255)
    email: str = Field(..., max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    password: str = Field(..., min_length=8, max_length=100)
    max_drivers: Optional[int] = Field(default=10, ge=1, le=10000)
    max_plates: Optional[int] = Field(default=20, ge=1, le=20000)
    access_level: Optional[str] = Field(default="standard", max_length=50)


class ClientResponse(BaseModel):
    """Client profile response."""
    id: int
    client_code: str
    name: str
    email: str
    phone: Optional[str]
    status: str
    access_level: str
    max_drivers: int
    max_plates: int
    max_concurrent_tasks: int
    max_daily_tasks: int
    
    # Usage counts (populated by service)
    drivers_count: Optional[int] = 0
    plates_count: Optional[int] = 0
    
    created_at: datetime
    last_login_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class AdminClientUpdateRequest(BaseModel):
    """Master admin update request for tenant accounts."""
    client_code: Optional[str] = Field(None, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    name: Optional[str] = Field(None, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    password: Optional[str] = Field(None, min_length=8, max_length=100)
    status: Optional[str] = Field(None, max_length=20)
    max_drivers: Optional[int] = Field(None, ge=1, le=10000)
    max_plates: Optional[int] = Field(None, ge=1, le=20000)
    max_concurrent_tasks: Optional[int] = Field(None, ge=1, le=1000)
    max_daily_tasks: Optional[int] = Field(None, ge=1, le=100000)
    access_level: Optional[str] = Field(None, max_length=50)


# ==================== DRIVER SCHEMAS ====================

class DriverCreateRequest(BaseModel):
    """Create a new driver."""
    driver_national_code: str = Field(..., max_length=10, pattern=r"^[0-9۰-۹]+$")
    full_name: str = Field(..., max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    license_number: Optional[str] = Field(None, max_length=50)
    utcms_username: str = Field(..., max_length=100)
    utcms_password: str = Field(..., min_length=4, max_length=100)
    default_payload: Optional[dict[str, Any]] = Field(None)


class DriverUpdateRequest(BaseModel):
    """Update driver information."""
    full_name: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    license_number: Optional[str] = Field(None, max_length=50)
    utcms_username: Optional[str] = Field(None, max_length=100)
    utcms_password: Optional[str] = Field(None, min_length=4, max_length=100)
    status: Optional[str] = Field(None, max_length=20)
    default_payload: Optional[dict[str, Any]] = Field(None)


class DriverResponse(BaseModel):
    """Driver response (never includes passwords)."""
    id: int
    client_id: int
    driver_national_code: str
    full_name: str
    phone: Optional[str]
    license_number: Optional[str]
    utcms_username: str
    status: str
    runtime_status: Optional[str] = None
    last_auth_at: Optional[datetime] = None
    last_session_expires_at: Optional[datetime] = None
    last_error_code: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PlateCreateRequest(BaseModel):
    driver_id: int
    plate_number: str = Field(..., min_length=8, max_length=20)
    vehicle_type: Optional[str] = Field(None, max_length=100)
    status: str = Field(default="active", max_length=20)
    notes: Optional[str] = Field(None, max_length=2000)

    @field_validator("plate_number", mode="before")
    @classmethod
    def validate_plate_number(cls, value: str) -> str:
        normalized = _normalize_plate(str(value))
        if not PLATE_PATTERN.fullmatch(normalized):
            raise ValueError("فرمت پلاک باید به صورت ۱۲ب۳۴۵ایران۶۷ باشد")
        return normalized


class PlateUpdateRequest(BaseModel):
    plate_number: Optional[str] = Field(None, min_length=8, max_length=20)
    vehicle_type: Optional[str] = Field(None, max_length=100)
    status: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = Field(None, max_length=2000)

    @field_validator("plate_number", mode="before")
    @classmethod
    def validate_plate_number(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = _normalize_plate(str(value))
        if not PLATE_PATTERN.fullmatch(normalized):
            raise ValueError("فرمت پلاک باید به صورت ۱۲ب۳۴۵ایران۶۷ باشد")
        return normalized


class PlateResponse(BaseModel):
    id: int
    client_id: int
    driver_id: int
    plate_number: str
    vehicle_type: Optional[str]
    status: str
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DriverScheduleCreateRequest(BaseModel):
    driver_id: int
    title: str = Field(..., min_length=2, max_length=255)
    frequency: str = Field(default="daily", max_length=20)
    run_time: str = Field(default="08:00", pattern=r"^\d{2}:\d{2}$")
    run_times: List[str] = Field(default_factory=list)
    weekdays: Optional[List[int]] = Field(default=None)
    specific_dates: List[str] = Field(default_factory=list)
    start_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    timezone: str = Field(default="Asia/Tehran", max_length=64)
    payload_template: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class DriverScheduleUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=255)
    frequency: Optional[str] = Field(None, max_length=20)
    run_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    run_times: Optional[List[str]] = None
    weekdays: Optional[List[int]] = None
    specific_dates: Optional[List[str]] = None
    start_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    timezone: Optional[str] = Field(None, max_length=64)
    payload_template: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None


class DriverScheduleResponse(BaseModel):
    id: int
    client_id: int
    driver_id: int
    title: str
    frequency: str
    run_time: str
    run_times: List[str] = Field(default_factory=list)
    weekdays: List[int] = Field(default_factory=list)
    specific_dates: List[str] = Field(default_factory=list)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    timezone: str
    payload_template: dict[str, Any] = Field(default_factory=dict)
    is_active: bool
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==================== WAYBILL JOB SCHEMAS ====================

class WaybillPayload(BaseModel):
    """Waybill data for a single job."""
    # Driver info
    driver_national_code: str = Field(..., max_length=10)
    
    # Route info
    origin: str = Field(..., max_length=500, description="Origin city/location (text only, no map)")
    destination: str = Field(..., max_length=500, description="Destination city/location (text only, no map)")
    
    # Waybill details
    waybill_number: str = Field(..., min_length=1, max_length=100)
    cargo_type: str = Field(..., min_length=1, max_length=100)
    cargo_weight: float = Field(..., gt=0)
    cargo_description: str = Field(..., min_length=1, max_length=1000)
    cargo_value: Optional[str] = Field(None, max_length=50)
    
    # Additional fields
    vehicle_type: str = Field(..., min_length=1, max_length=100)
    plate_number: str = Field(..., min_length=1, max_length=20)
    driver_phone: str = Field(..., min_length=11, max_length=20)
    
    # Metadata
    notes: str = Field(..., min_length=1, max_length=500)
    metadata_json: Optional[dict] = Field(None)

    @field_validator("driver_national_code", mode="before")
    @classmethod
    def validate_driver_national_code(cls, value: str) -> str:
        normalized = _normalize_national_code(str(value))
        if not re.fullmatch(r"\d{10}", normalized):
            raise ValueError("کد ملی راننده باید دقیقاً ۱۰ رقم باشد")
        return normalized

    @field_validator("driver_phone", mode="before")
    @classmethod
    def validate_driver_phone(cls, value: str) -> str:
        normalized = _normalize_phone(str(value))
        if not re.fullmatch(r"09\d{9}", normalized):
            raise ValueError("تلفن راننده باید با ۰۹ شروع شود و ۱۱ رقم باشد")
        return normalized

    @field_validator("plate_number", mode="before")
    @classmethod
    def validate_plate_number(cls, value: str) -> str:
        normalized = _normalize_plate(str(value))
        if not PLATE_PATTERN.fullmatch(normalized):
            raise ValueError("فرمت پلاک باید به صورت ۱۲ب۳۴۵ایران۶۷ باشد")
        return normalized


class WaybillJobCreateRequest(BaseModel):
    """Create a single waybill job (manual form)."""
    driver_national_code: str = Field(..., max_length=10)
    payload: WaybillPayload
    max_retries: int = Field(default=3, ge=0, le=10)
    idempotency_key: Optional[str] = Field(default=None, max_length=200)
    correlation_id: Optional[str] = Field(default=None, max_length=128)
    priority: int = Field(default=5, ge=0, le=9)

    @field_validator("driver_national_code", mode="before")
    @classmethod
    def validate_driver_national_code(cls, value: str) -> str:
        normalized = _normalize_national_code(str(value))
        if not re.fullmatch(r"\d{10}", normalized):
            raise ValueError("کد ملی راننده باید دقیقاً ۱۰ رقم باشد")
        return normalized


class WaybillRetryRequest(BaseModel):
    """Manual retry controls for an existing job."""
    force_auth_refresh: bool = False
    retry_with_overrides: Optional[dict[str, Any]] = None
    dispatch_now: bool = True


class WaybillJobResponse(BaseModel):
    """Waybill job status response."""
    id: int
    job_id: str
    client_id: int
    driver_id: Optional[int]
    status: str
    source: str
    correlation_id: Optional[str]
    business_date: Optional[str]
    priority: int
    last_error: Optional[str]
    error_category: Optional[str]
    next_retry_at: Optional[datetime]
    submit_after: Optional[datetime]
    terminal_reason: Optional[str]
    attempt_count: int
    max_retries: int
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


# ==================== BULK UPLOAD SCHEMAS ====================

class BulkUploadResponse(BaseModel):
    """Response for bulk Excel upload."""
    batch_id: str
    client_id: int
    original_filename: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    status: str
    jobs_created: List[WaybillJobResponse] = Field(default_factory=list)
    errors: List[dict] = Field(default_factory=list)


class BatchStatusResponse(BaseModel):
    """Batch processing status."""
    batch_id: str
    status: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    jobs_created: int
    jobs_completed: int
    errors: List[dict] = Field(default_factory=list)
    created_at: datetime
    completed_at: Optional[datetime]


# ==================== REPORT SCHEMAS ====================

class TaskFilterRequest(BaseModel):
    """Filter tasks by various criteria."""
    status: Optional[str] = None
    driver_id: Optional[int] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class TaskListResponse(BaseModel):
    """Paginated task list."""
    tasks: List[WaybillJobResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ClientStatsResponse(BaseModel):
    """Client dashboard statistics."""
    client_id: int
    total_drivers: int
    active_drivers: int
    total_jobs: int
    pending_jobs: int
    in_progress_jobs: int
    success_jobs: int
    failed_jobs: int
    today_jobs: int
    today_success: int
    today_failed: int
    success_rate: float
    created_at: datetime


# ==================== TASK LOG SCHEMAS ====================

class TaskLogEntry(BaseModel):
    """Single task log entry."""
    id: int
    job_id: str
    step: str
    status: str
    message: Optional[str]
    details_json: Optional[dict]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskLogsResponse(BaseModel):
    """Task logs response."""
    job_id: str
    logs: List[TaskLogEntry]


class TaskTimelineEntry(BaseModel):
    """Unified timeline entry sourced from domain events or task logs."""
    entry_id: str
    job_id: str
    source: str
    event_type: str
    phase: Optional[str] = None
    title: str
    status: Optional[str] = None
    message: Optional[str] = None
    payload: Optional[dict] = None
    created_at: datetime


class TaskTimelineQuery(BaseModel):
    """Server-side timeline filtering and pagination."""
    phase: Optional[str] = None
    event_type: Optional[str] = None
    source: Optional[str] = None
    q: Optional[str] = None
    include_payload: bool = True
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


class TaskTimelineResponse(BaseModel):
    """Merged timeline for a single job."""
    job_id: str
    total: int
    page: int
    page_size: int
    entries: List[TaskTimelineEntry]
