from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class OperationMode(StrEnum):
    SAFE = "safe"
    FULL = "full"


def _normalize_digits(value: str) -> str:
    result = value or ""
    for index, digit in enumerate("۰۱۲۳۴۵۶۷۸۹"):
        result = result.replace(digit, str(index))
    for index, digit in enumerate("٠١٢٣٤٥٦٧٨٩"):
        result = result.replace(digit, str(index))
    return result


class GeoCoordinateModel(BaseModel):
    lat: float = Field(..., description="عرض جغرافیایی")
    lng: float = Field(..., description="طول جغرافیایی")


class LocationModel(BaseModel):
    province: str = Field(..., min_length=1, description="استان")
    city: str = Field(..., min_length=1, description="شهر")
    district: str | None = Field(default=None, description="منطقه (در صورت وجود)")
    address: str = Field(..., min_length=1, description="آدرس متنی")
    coordinates: GeoCoordinateModel | None = Field(
        default=None, description="مختصات جغرافیایی (اختیاری، در user_text نادیده گرفته می‌شود)"
    )
    location_mode: str = Field(default="user_text", description="حالت مکان: پیش‌فرض user_text")
    route_source: str = Field(default="user_text", description="منبع مسیر: پیش‌فرض user_text")


class SenderModel(BaseModel):
    name: str = Field(..., description="نام فرستنده")
    phone: str | None = Field(None, description="موبایل فرستنده (در ثبت زنده UTCMS الزامی است)")
    address: str | None = Field(None, description="آدرس فرستنده (در مرحله مبدا ثبت می‌شود)")
    national_code: str | None = Field(None, description="کد ملی فرستنده (اختیاری در UTCMS)")
    entity_type: str = Field(default="individual", description="individual یا company")

    @model_validator(mode="before")
    @classmethod
    def _normalize_sender_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            d = dict(data)
            if "national_id" in d and "national_code" not in d:
                d["national_code"] = d["national_id"]
            return d
        return data


class ReceiverModel(BaseModel):
    name: str = Field(..., description="نام گیرنده")
    phone: str | None = Field(None, description="موبایل گیرنده (در ثبت زنده UTCMS الزامی است)")
    address: str | None = Field(None, description="آدرس گیرنده (در مرحله مقصد ثبت می‌شود)")
    national_code: str | None = Field(None, description="کد ملی گیرنده")
    entity_type: str = Field(default="individual", description="individual یا company")

    @model_validator(mode="before")
    @classmethod
    def _normalize_receiver_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            d = dict(data)
            if "national_id" in d and "national_code" not in d:
                d["national_code"] = d["national_id"]
            return d
        return data


class CargoModel(BaseModel):
    type: str = Field(..., min_length=1, description="نوع کالا")
    weight: str | int | float = Field(..., description="وزن کالا")
    count: str | int = Field(default="1", description="تعداد کالا")
    description: str | None = Field(None, description="توضیحات کالا")
    packaging: str | None = Field(None, description="نوع بسته‌بندی UTCMS مانند فله یا کیسه")
    value: str | int | float | None = Field(None, description="ارزش تقریبی بار به ریال")

    @model_validator(mode="before")
    @classmethod
    def _normalize_cargo_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            d = dict(data)
            if "cargo_title" in d and "type" not in d:
                d["type"] = d["cargo_title"]
            if "cargo_weight" in d and "weight" not in d:
                d["weight"] = d["cargo_weight"]
            if "packaging_title" in d and "packaging" not in d:
                d["packaging"] = d["packaging_title"]
            if "cargo_value" in d and "value" not in d:
                d["value"] = d["cargo_value"]
            return d
        return data

    @field_validator("weight", mode="before")
    @classmethod
    def validate_cargo_weight(cls, value: Any) -> float:
        if value is None:
            raise ValueError("وزن بار الزامی است")
        norm = _normalize_digits(str(value)).replace(",", "").strip()
        try:
            val = float(norm)
        except Exception:
            raise ValueError("وزن بار باید عددی معتبر باشد") from None
        if val <= 0:
            raise ValueError("وزن بار باید بزرگ‌تر از صفر باشد")
        return val


class VehicleModel(BaseModel):
    driver_national_code: str | None = Field(None, description="کد ملی راننده")
    driver_phone: str | None = Field(None, description="تلفن راننده")
    plate: str | None = Field(None, description="پلاک خودرو")
    type: str | None = Field(None, description="نوع خودرو")

    @model_validator(mode="before")
    @classmethod
    def _normalize_vehicle_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            d = dict(data)
            if "plate_number" in d and "plate" not in d:
                d["plate"] = d["plate_number"]
            if "vehicle_type" in d and "type" not in d:
                d["type"] = d["vehicle_type"]
            return d
        return data


class FinancialModel(BaseModel):
    cost: str | int | float | None = Field(None, description="هزینه حمل")
    payment_method: str | None = Field(None, description="روش پرداخت")

    @model_validator(mode="before")
    @classmethod
    def _normalize_financial_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            d = dict(data)
            if "fare_amount" in d and "cost" not in d:
                d["cost"] = d["fare_amount"]
            if "shipping_cost" in d and "cost" not in d:
                d["cost"] = d["shipping_cost"]
            if "fare" in d and "cost" not in d:
                d["cost"] = d["fare"]
            if "rent" in d and "cost" not in d:
                d["cost"] = d["rent"]
            if "fare_type" in d and "payment_method" not in d:
                d["payment_method"] = d["fare_type"]
            return d
        return data


class UTCMSLoginModel(BaseModel):
    username: str = Field(..., description="نام کاربری/کد ملی UTCMS")
    password: str = Field(..., description="رمز عبور UTCMS")
    login_url: str = Field(
        default="https://barname.utcms.ir/Barname/Account/Login",
        description="آدرس صفحه لاگین UTCMS",
    )


class ShippingOptionsModel(BaseModel):
    two_way: bool | None = Field(default=False, description="ثبت دو طرفه (رفت و برگشت)")
    time_limit: int | None = Field(default=None, description="محدودیت زمانی ثبت (دقیقه)")
    end_shipping: str | None = Field(default=None, description="تاریخ/زمان پایان حمل")
    otp: str | None = Field(default=None, description="کد OTP در صورت نیاز به احراز هویت دو مرحله‌ای")


class WaybillMapRequest(BaseModel):
    session_id: str | None = None
    correlation_id: str | None = None
    batch_id: str | None = None
    priority: int = Field(default=5, ge=0, le=9)
    operation_mode: OperationMode = Field(default=OperationMode.SAFE)
    route_source: str = Field(default="user_text", description="منبع مسیر (پیش‌فرض user_text)")
    location_mode: str = Field(default="user_text", description="حالت مکان‌یابی (پیش‌فرض user_text)")
    utcms_auth: UTCMSLoginModel | None = Field(
        default=None,
        description="در صورت ارسال، لاگین با اطلاعات همین درخواست انجام می‌شود",
    )
    sender: SenderModel
    receiver: ReceiverModel
    origin: LocationModel
    destination: LocationModel
    cargo: CargoModel
    vehicle: VehicleModel
    financial: FinancialModel
    shipping_options: ShippingOptionsModel | None = Field(default=None, description="گزینه‌های اضافی حمل")
