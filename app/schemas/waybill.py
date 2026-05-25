from enum import Enum
from typing import Optional, Union

from pydantic import BaseModel, Field


class OperationMode(str, Enum):
    SAFE = "safe"
    FULL = "full"


class GeoCoordinateModel(BaseModel):
    lat: float = Field(..., description="عرض جغرافیایی")
    lng: float = Field(..., description="طول جغرافیایی")


class LocationModel(BaseModel):
    province: str
    city: str
    district: Optional[str] = None
    address: str
    coordinates: Optional[GeoCoordinateModel] = None


class SenderModel(BaseModel):
    name: str = Field(..., description="نام فرستنده")
    phone: str = Field(..., description="تلفن فرستنده")
    address: str = Field(..., description="آدرس فرستنده")
    national_code: str = Field(..., description="کد ملی فرستنده")


class ReceiverModel(BaseModel):
    name: str = Field(..., description="نام گیرنده")
    phone: str = Field(..., description="تلفن گیرنده")
    address: str = Field(..., description="آدرس گیرنده")
    national_code: Optional[str] = Field(None, description="کد ملی گیرنده")


class CargoModel(BaseModel):
    type: Optional[str] = Field(None, description="نوع کالا")
    weight: Union[str, int, float] = Field(..., description="وزن کالا")
    count: Union[str, int] = Field(default="1", description="تعداد کالا")
    description: Optional[str] = Field(None, description="توضیحات کالا")


class VehicleModel(BaseModel):
    driver_national_code: Optional[str] = Field(None, description="کد ملی راننده")
    driver_phone: Optional[str] = Field(None, description="تلفن راننده")
    plate: Optional[str] = Field(None, description="پلاک خودرو")
    type: Optional[str] = Field(None, description="نوع خودرو")


class FinancialModel(BaseModel):
    cost: Optional[Union[str, int, float]] = Field(None, description="هزینه حمل")
    payment_method: Optional[str] = Field(None, description="روش پرداخت")


class UTCMSLoginModel(BaseModel):
    username: str = Field(..., description="نام کاربری/کد ملی UTCMS")
    password: str = Field(..., description="رمز عبور UTCMS")
    login_url: str = Field(
        default="https://barname.utcms.ir/Barname/Account/Login",
        description="آدرس صفحه لاگین UTCMS",
    )


class ShippingOptionsModel(BaseModel):
    two_way: Optional[bool] = Field(default=False, description="ثبت دو طرفه (رفت و برگشت)")
    time_limit: Optional[int] = Field(default=None, description="محدودیت زمانی ثبت (دقیقه)")
    end_shipping: Optional[str] = Field(default=None, description="تاریخ/زمان پایان حمل")
    otp: Optional[str] = Field(default=None, description="کد OTP در صورت نیاز به احراز هویت دو مرحله‌ای")


class WaybillMapRequest(BaseModel):
    session_id: Optional[str] = None
    correlation_id: Optional[str] = None
    batch_id: Optional[str] = None
    priority: int = Field(default=5, ge=0, le=9)
    operation_mode: OperationMode = Field(default=OperationMode.SAFE)
    utcms_auth: Optional[UTCMSLoginModel] = Field(
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
    shipping_options: Optional[ShippingOptionsModel] = Field(default=None, description="گزینه‌های اضافی حمل")
