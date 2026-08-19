"""
Pydantic schemas for multi-tenant API requests and responses.
"""

import json
import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.waybill import (
    CargoModel,
    FinancialModel,
    LocationModel,
    ReceiverModel,
    SenderModel,
    ShippingOptionsModel,
    VehicleModel,
)

PERSIAN_PLATE_LETTERS = "اآبپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی"
PLATE_PATTERN = re.compile(rf"^\d{{2}}(الف|[{PERSIAN_PLATE_LETTERS}])\d{{3}}ایران\d{{2}}$")


def _coerce_json_field(value: Any) -> Any:
    """Safely coerce JSON strings or dicts for schema compatibility."""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            return None
        if (trimmed.startswith("{") and trimmed.endswith("}")) or (trimmed.startswith("[") and trimmed.endswith("]")):
            try:
                return json.loads(trimmed)
            except Exception:
                return value
    return value


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
    match = re.fullmatch(rf"(\d{{2}})(الف|[{PERSIAN_PLATE_LETTERS}])(\d{{3}})(\d{{2}})", compact)
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
    phone: str | None = Field(None, max_length=20)
    password: str = Field(..., min_length=8, max_length=100)
    max_drivers: int | None = Field(default=10, ge=1, le=10000)
    max_plates: int | None = Field(default=20, ge=1, le=20000)
    max_concurrent_tasks: int = Field(default=2, ge=1, le=20)
    max_daily_tasks: int = Field(default=100, ge=1, le=1000)
    access_level: str | None = Field(default="standard", max_length=50)
    status: str | None = Field(default="active", max_length=20)
    subscription_start_date: datetime | None = None
    subscription_end_date: datetime | None = None

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        return normalized or None

    @field_validator("access_level", mode="before")
    @classmethod
    def validate_access_level(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        return normalized or None


class ClientResponse(BaseModel):
    """Client profile response."""

    id: int
    client_code: str
    name: str
    email: str
    phone: str | None
    status: str
    access_level: str
    max_drivers: int
    max_plates: int
    max_concurrent_tasks: int
    max_daily_tasks: int

    # Usage counts (populated by service)
    drivers_count: int | None = 0
    plates_count: int | None = 0

    subscription_start_date: datetime | None = None
    subscription_end_date: datetime | None = None

    created_at: datetime
    last_login_at: datetime | None
    metadata_json: dict | list | str | Any | None = None

    @field_validator("metadata_json", mode="before")
    @classmethod
    def coerce_metadata_json(cls, v: Any) -> Any:
        return _coerce_json_field(v)

    model_config = ConfigDict(from_attributes=True)


class AdminClientUpdateRequest(BaseModel):
    """Master admin update request for tenant accounts."""

    client_code: str | None = Field(None, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str | None = Field(None, max_length=255)
    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=20)
    password: str | None = Field(None, min_length=8, max_length=100)
    status: str | None = Field(None, max_length=20)
    max_drivers: int | None = Field(None, ge=1, le=10000)
    max_plates: int | None = Field(None, ge=1, le=20000)
    max_concurrent_tasks: int | None = Field(None, ge=1, le=1000)
    max_daily_tasks: int | None = Field(None, ge=1, le=100000)
    access_level: str | None = Field(None, max_length=50)
    subscription_start_date: datetime | None = None
    subscription_end_date: datetime | None = None

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        return normalized or None

    @field_validator("access_level", mode="before")
    @classmethod
    def validate_access_level(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        return normalized or None


# ==================== DRIVER SCHEMAS ====================


class DriverCreateRequest(BaseModel):
    """Create a new driver."""

    driver_national_code: str = Field(..., max_length=10, pattern=r"^[0-9۰-۹]+$")
    full_name: str = Field(..., max_length=255)
    phone: str | None = Field(None, max_length=20)
    license_number: str | None = Field(None, max_length=50)
    utcms_username: str = Field(..., max_length=100)
    utcms_password: str = Field(..., min_length=4, max_length=100)
    plate_number: str | None = Field(None, max_length=50)
    vehicle_type: str | None = Field(None, max_length=50)
    default_payload: dict[str, Any] | None = Field(None)


class DriverUpdateRequest(BaseModel):
    """Update driver information."""

    driver_national_code: str | None = Field(None, max_length=10, pattern=r"^[0-9۰-۹]+$")
    full_name: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=20)
    license_number: str | None = Field(None, max_length=50)
    utcms_username: str | None = Field(None, max_length=100)
    utcms_password: str | None = Field(None, max_length=100)
    plate_number: str | None = Field(None, max_length=50)
    vehicle_type: str | None = Field(None, max_length=50)
    status: str | None = Field(None, max_length=20)
    default_payload: dict[str, Any] | None = Field(None)

    @field_validator("driver_national_code", "utcms_password", "phone", "license_number", "plate_number", mode="before")
    @classmethod
    def empty_str_to_none(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("utcms_password")
    @classmethod
    def validate_password_length(cls, v: str | None) -> str | None:
        if v is not None and len(v) < 4:
            raise ValueError("رمز عبور باید حداقل ۴ کاراکتر باشد")
        return v



class DriverResponse(BaseModel):
    """Driver response (never includes passwords)."""

    id: int
    client_id: int
    driver_national_code: str
    full_name: str
    phone: str | None
    license_number: str | None
    utcms_username: str
    status: str
    runtime_status: str | None = None
    last_auth_at: datetime | None = None
    last_session_expires_at: datetime | None = None
    last_error_code: str | None = None
    active_plate: str | None = None
    created_at: datetime
    updated_at: datetime
    default_payload_json: dict | list | str | Any | None = None
    metadata_json: dict | list | str | Any | None = None

    @field_validator("default_payload_json", "metadata_json", mode="before")
    @classmethod
    def coerce_json_fields(cls, v: Any) -> Any:
        return _coerce_json_field(v)

    model_config = ConfigDict(from_attributes=True)


class PlateCreateRequest(BaseModel):
    driver_id: int
    plate_number: str = Field(..., min_length=8, max_length=20)
    vehicle_type: str | None = Field(None, max_length=100)
    status: str = Field(default="active", max_length=20)
    notes: str | None = Field(None, max_length=2000)

    @field_validator("plate_number", mode="before")
    @classmethod
    def validate_plate_number(cls, value: str) -> str:
        normalized = _normalize_plate(str(value))
        if not PLATE_PATTERN.fullmatch(normalized):
            raise ValueError("فرمت پلاک باید به صورت ۱۲ب۳۴۵ایران۶۷ باشد")
        return normalized


class PlateUpdateRequest(BaseModel):
    plate_number: str | None = Field(None, min_length=8, max_length=20)
    vehicle_type: str | None = Field(None, max_length=100)
    status: str | None = Field(None, max_length=20)
    notes: str | None = Field(None, max_length=2000)

    @field_validator("plate_number", mode="before")
    @classmethod
    def validate_plate_number(cls, value: str | None) -> str | None:
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
    vehicle_type: str | None
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


def _normalize_persian_schedule_date(v: str | None) -> str | None:
    if not v:
        return None
    s = str(v).strip()
    if not s:
        return None
    persian_arabic_digits = {
        '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4', '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9',
        '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4', '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9',
    }
    for p, a in persian_arabic_digits.items():
        s = s.replace(p, a)
    s = re.sub(r"[\s_/\.\\]+", "-", s)
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)
    if m:
        y, mth, d = m.groups()
        return f"{y}-{int(mth):02d}-{int(d):02d}"
    return s


def _normalize_schedule_time(v: str | None) -> str | None:
    if not v:
        return None
    s = str(v).strip()
    persian_arabic_digits = {
        '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4', '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9',
        '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4', '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9',
    }
    for p, a in persian_arabic_digits.items():
        s = s.replace(p, a)
    s = re.sub(r"[\s_/\.\-]+", ":", s)
    m = re.match(r"^(\d{1,2}):(\d{1,2})$", s)
    if m:
        h, mn = m.groups()
        return f"{int(h):02d}:{int(mn):02d}"
    return s


class DriverScheduleCreateRequest(BaseModel):
    driver_id: int
    title: str = Field(..., min_length=2, max_length=255)
    frequency: str = Field(default="daily", max_length=20)
    run_time: str = Field(default="08:00")
    run_times: list[str] = Field(default_factory=list)
    weekdays: list[int] | None = Field(default=None)
    specific_dates: list[str] = Field(default_factory=list)
    start_date: str | None = Field(default=None)
    end_date: str | None = Field(default=None)
    timezone: str = Field(default="Asia/Tehran", max_length=64)
    payload_template: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def validate_dates(cls, v: Any) -> str | None:
        if v is None:
            return None
        norm = _normalize_persian_schedule_date(str(v))
        if norm and re.match(r"^\d{4}-\d{2}-\d{2}$", norm):
            return norm
        raise ValueError(f"فرمت تاریخ نامعتبر است ({v}). فرمت صحیح YYYY-MM-DD است.")

    @field_validator("specific_dates", mode="before")
    @classmethod
    def validate_specific_dates(cls, v: Any) -> list[str]:
        if not v:
            return []
        if isinstance(v, str):
            raw_list = [x.strip() for x in v.split(",") if x.strip()]
        elif isinstance(v, list):
            raw_list = v
        else:
            return []
        res = []
        for item in raw_list:
            norm = _normalize_persian_schedule_date(str(item))
            if norm and re.match(r"^\d{4}-\d{2}-\d{2}$", norm):
                res.append(norm)
            else:
                raise ValueError(f"فرمت تاریخ در لیست تاریخ‌های مشخص نامعتبر است ({item}). فرمت صحیح YYYY-MM-DD است.")
        return res

    @field_validator("run_time", mode="before")
    @classmethod
    def validate_run_time(cls, v: Any) -> str:
        norm = _normalize_schedule_time(str(v) if v else "08:00")
        if norm and re.match(r"^\d{2}:\d{2}$", norm):
            return norm
        raise ValueError(f"فرمت ساعت نامعتبر است ({v}). فرمت صحیح HH:MM است.")

    @field_validator("run_times", mode="before")
    @classmethod
    def validate_run_times(cls, v: Any) -> list[str]:
        if not v:
            return []
        if isinstance(v, str):
            raw_list = [x.strip() for x in v.split(",") if x.strip()]
        elif isinstance(v, list):
            raw_list = v
        else:
            return []
        res = []
        for item in raw_list:
            norm = _normalize_schedule_time(str(item))
            if norm and re.match(r"^\d{2}:\d{2}$", norm):
                res.append(norm)
            else:
                raise ValueError(f"فرمت ساعت نامعتبر است ({item}). فرمت صحیح HH:MM است.")
        return res


class DriverScheduleUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=2, max_length=255)
    frequency: str | None = Field(None, max_length=20)
    run_time: str | None = None
    run_times: list[str] | None = None
    weekdays: list[int] | None = None
    specific_dates: list[str] | None = None
    start_date: str | None = None
    end_date: str | None = None
    timezone: str | None = Field(None, max_length=64)
    payload_template: dict[str, Any] | None = None
    is_active: bool | None = None

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def validate_dates(cls, v: Any) -> str | None:
        if v is None:
            return None
        norm = _normalize_persian_schedule_date(str(v))
        if norm and re.match(r"^\d{4}-\d{2}-\d{2}$", norm):
            return norm
        raise ValueError(f"فرمت تاریخ نامعتبر است ({v}). فرمت صحیح YYYY-MM-DD است.")

    @field_validator("specific_dates", mode="before")
    @classmethod
    def validate_specific_dates(cls, v: Any) -> list[str] | None:
        if v is None:
            return None
        if isinstance(v, str):
            raw_list = [x.strip() for x in v.split(",") if x.strip()]
        elif isinstance(v, list):
            raw_list = v
        else:
            return None
        res = []
        for item in raw_list:
            norm = _normalize_persian_schedule_date(str(item))
            if norm and re.match(r"^\d{4}-\d{2}-\d{2}$", norm):
                res.append(norm)
            else:
                raise ValueError(f"فرمت تاریخ در لیست تاریخ‌های مشخص نامعتبر است ({item}). فرمت صحیح YYYY-MM-DD است.")
        return res

    @field_validator("run_time", mode="before")
    @classmethod
    def validate_run_time(cls, v: Any) -> str | None:
        if v is None:
            return None
        norm = _normalize_schedule_time(str(v))
        if norm and re.match(r"^\d{2}:\d{2}$", norm):
            return norm
        raise ValueError(f"فرمت ساعت نامعتبر است ({v}). فرمت صحیح HH:MM است.")

    @field_validator("run_times", mode="before")
    @classmethod
    def validate_run_times(cls, v: Any) -> list[str] | None:
        if v is None:
            return None
        if isinstance(v, str):
            raw_list = [x.strip() for x in v.split(",") if x.strip()]
        elif isinstance(v, list):
            raw_list = v
        else:
            return None
        res = []
        for item in raw_list:
            norm = _normalize_schedule_time(str(item))
            if norm and re.match(r"^\d{2}:\d{2}$", norm):
                res.append(norm)
            else:
                raise ValueError(f"فرمت ساعت نامعتبر است ({item}). فرمت صحیح HH:MM است.")
        return res


class DriverScheduleResponse(BaseModel):
    id: int
    client_id: int
    driver_id: int
    title: str
    frequency: str
    run_time: str
    run_times: list[str] = Field(default_factory=list)
    weekdays: list[int] = Field(default_factory=list)
    specific_dates: list[str] = Field(default_factory=list)
    start_date: str | None = None
    end_date: str | None = None
    timezone: str
    payload_template: dict[str, Any] = Field(default_factory=dict)
    is_active: bool
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==================== WAYBILL JOB SCHEMAS ====================


class WaybillPayload(BaseModel):
    """Waybill data for a single job (Flat/Compact version)."""

    # Driver info
    driver_national_code: str = Field(..., max_length=10)

    # Route info
    origin: str = Field(..., max_length=500, description="Origin city/location (text only, no map)")
    destination: str = Field(..., max_length=500, description="Destination city/location (text only, no map)")
    route_source: str = Field(default="user_text", description="منبع مسیر: user_text")
    location_mode: str = Field(default="user_text", description="حالت مکان: user_text")

    # Waybill details
    waybill_number: str | None = Field(default=None, max_length=100)
    cargo_type: str = Field(..., min_length=1, max_length=100)
    cargo_weight: float = Field(..., gt=0)
    cargo_description: str | None = Field(default=None, max_length=1000)
    cargo_value: str | None = Field(None, max_length=50)

    # Additional fields
    vehicle_type: str = Field(..., min_length=1, max_length=100)
    plate_number: str = Field(..., min_length=1, max_length=20)
    driver_phone: str = Field(..., min_length=11, max_length=20)

    # Metadata
    notes: str | None = Field(default=None, max_length=500)
    metadata_json: dict | None = Field(None)

    @staticmethod
    def _validate_iran_national_code(code: str) -> bool:
        if not re.fullmatch(r"\d{10}", code):
            return False
        if code in {
            "0000000000",
            "1111111111",
            "2222222222",
            "3333333333",
            "4444444444",
            "5555555555",
            "6666666666",
            "7777777777",
            "8888888888",
            "9999999999",
        }:
            return False
        checksum = sum(int(code[i]) * (10 - i) for i in range(9))
        remainder = checksum % 11
        control = int(code[9])
        return control == remainder if remainder < 2 else control == 11 - remainder

    @field_validator("driver_national_code", mode="before")
    @classmethod
    def validate_driver_national_code(cls, value: str) -> str:
        normalized = _normalize_national_code(str(value))
        if not cls._validate_iran_national_code(normalized):
            raise ValueError("کد ملی راننده معتبر نیست (checksum نامعتبر)")
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


class WaybillNestedPayload(BaseModel):
    """Rich nested waybill data matching the frontend and WaybillMapRequest."""

    route_source: str = Field(default="user_text", description="منبع مسیر: user_text")
    location_mode: str = Field(default="user_text", description="حالت مکان: user_text")
    sender: SenderModel
    receiver: ReceiverModel
    origin: LocationModel
    destination: LocationModel
    cargo: CargoModel
    vehicle: VehicleModel
    financial: FinancialModel
    shipping_options: ShippingOptionsModel | None = None


class WaybillJobCreateRequest(BaseModel):
    """Create a single waybill job (manual form)."""

    driver_national_code: str = Field(..., max_length=10)
    payload: WaybillPayload | WaybillNestedPayload
    max_retries: int = Field(default=3, ge=0, le=10)
    idempotency_key: str | None = Field(default=None, max_length=200)
    correlation_id: str | None = Field(default=None, max_length=128)
    priority: int = Field(default=5, ge=0, le=9)

    @field_validator("driver_national_code", mode="before")
    @classmethod
    def validate_driver_national_code(cls, value: str) -> str:
        normalized = _normalize_national_code(str(value))
        if not WaybillPayload._validate_iran_national_code(normalized):
            raise ValueError("کد ملی راننده معتبر نیست (checksum نامعتبر)")
        return normalized


class WaybillRetryRequest(BaseModel):
    """Manual retry controls for an existing job."""

    force_auth_refresh: bool = False
    retry_with_overrides: dict[str, Any] | None = None


class WaybillJobUpdateRequest(BaseModel):
    """Update request for an existing waybill job."""

    priority: int | None = Field(default=None, ge=0, le=9, description="اولویت کار (0-9)")
    max_retries: int | None = Field(default=None, ge=0, le=10, description="حداکثر تلاش مجدد")
    terminal_reason: str | None = Field(default=None, max_length=64, description="دلیل پایان کار")
    notes: str | None = Field(default=None, max_length=500, description="یادداشت‌ها")
    business_date: str | None = Field(default=None, max_length=16, description="تاریخ تجاری")
    correlation_id: str | None = Field(default=None, max_length=128, description="شناسه همبستگی")

    @field_validator("terminal_reason", "notes", "business_date", "correlation_id", mode="before")
    @classmethod
    def empty_str_to_none(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v



class WaybillJobResponse(BaseModel):
    """Waybill job status response."""

    id: int
    job_id: str
    client_id: int
    driver_id: int | None
    status: str
    source: str
    correlation_id: str | None
    business_date: str | None
    priority: int
    last_error: str | None
    error_category: str | None
    next_retry_at: datetime | None
    submit_after: datetime | None
    terminal_reason: str | None
    attempt_count: int
    max_retries: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    payload_json: dict | list | str | Any | None = None
    result_json: dict | list | str | Any | None = None
    client_name: str | None = None
    client_code: str | None = None
    request_digest: str | None = None
    document_id: str | None = None
    mutation_status: str | None = None
    mutation_at: datetime | None = None
    reconciled_at: datetime | None = None
    night_attempt_count: int = 0
    night_attempt_window: str | None = None

    @field_validator("payload_json", "result_json", mode="before")
    @classmethod
    def coerce_json_fields(cls, v: Any) -> Any:
        return _coerce_json_field(v)

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
    jobs_created: list[WaybillJobResponse] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)


class BatchStatusResponse(BaseModel):
    """Batch processing status."""

    batch_id: str
    status: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    jobs_created: int
    jobs_completed: int
    errors: list[dict] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime | None


# ==================== REPORT SCHEMAS ====================


class TaskFilterRequest(BaseModel):
    """Filter tasks by various criteria."""

    status: str | None = None
    driver_id: int | None = None
    driver_name: str | None = None
    plate_number: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=1000)


class TaskListResponse(BaseModel):
    """Paginated task list."""

    tasks: list[WaybillJobResponse]
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
    message: str | None
    details_json: dict | list | str | Any | None = None
    created_at: datetime

    @field_validator("details_json", mode="before")
    @classmethod
    def coerce_details_json(cls, v: Any) -> Any:
        return _coerce_json_field(v)

    model_config = ConfigDict(from_attributes=True)


class TaskLogsResponse(BaseModel):
    """Task logs response."""

    job_id: str
    logs: list[TaskLogEntry]


class TaskTimelineEntry(BaseModel):
    """Unified timeline entry sourced from domain events or task logs."""

    entry_id: str
    job_id: str
    source: str
    event_type: str
    phase: str | None = None
    title: str
    status: str | None = None
    message: str | None = None
    payload: dict | None = None
    created_at: datetime


class TaskTimelineQuery(BaseModel):
    """Server-side timeline filtering and pagination."""

    phase: str | None = None
    event_type: str | None = None
    source: str | None = None
    q: str | None = None
    include_payload: bool = True
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


class TaskTimelineResponse(BaseModel):
    """Merged timeline for a single job."""

    job_id: str
    total: int
    page: int
    page_size: int
    entries: list[TaskTimelineEntry]
    progress_percent: int | None = None


# ==================== FUEL INQUIRY SCHEMAS ====================


class FuelInquiryCreateRequest(BaseModel):
    """Request to trigger a fuel inquiry."""

    driver_id: int = Field(gt=0)
    year: int | None = Field(default=None, ge=1300, le=1600)
    month: int | None = Field(default=None, ge=1, le=12)
    force_retry: bool = Field(default=False)
    plate_number: str | None = Field(default=None)


class FuelInquiryResponse(BaseModel):
    """Response representing a fuel inquiry.

    The ``quota_data`` field maps the ORM column ``quota_data_json`` so that:
    - model_validate(orm_obj) reads from orm_obj.quota_data_json  (validation_alias)
    - JSON serialisation outputs the key as ``quota_data``          (field name)
    - The frontend never sees ``quota_data_json`` in the response
    """

    id: int
    client_id: int
    driver_id: int
    driver_name: str | None = None
    status: str
    error_message: str | None = None
    # Maps ORM column quota_data_json → response key quota_data
    quota_data: dict | list | str | Any | None = Field(
        default=None,
        validation_alias="quota_data_json",
    )
    screenshot_url: str | None = None
    created_at: datetime
    updated_at: datetime
    year: int | None = None
    month: int | None = None
    plate_number: str | None = None
    client_name: str | None = None
    client_code: str | None = None

    @field_validator("quota_data", mode="before")
    @classmethod
    def coerce_quota_data(cls, v: Any) -> Any:
        return _coerce_json_field(v)

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class FuelInquiryListResponse(BaseModel):
    """Paginated list of fuel inquiries."""

    items: list[FuelInquiryResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
