from enum import StrEnum

from pydantic import BaseModel, Field


class OperationMode(StrEnum):
    SAFE = "safe"
    FULL = "full"


class GeoCoordinateModel(BaseModel):
    lat: float = Field(..., description="عرض جغرافیایی")
    lng: float = Field(..., description="طول جغرافیایی")


class LocationModel(BaseModel):
    province: str
    city: str
    district: str | None = None
    address: str
    coordinates: GeoCoordinateModel | None = None


class SenderModel(BaseModel):
    name: str = Field(..., description="نام فرستنده")
    phone: str = Field(..., description="تلفن فرستنده")
    address: str = Field(..., description="آدرس فرستنده")
    national_code: str = Field(..., description="کد ملی فرستنده")


class ReceiverModel(BaseModel):
    name: str = Field(..., description="نام گیرنده")
    phone: str = Field(..., description="تلفن گیرنده")
    address: str = Field(..., description="آدرس گیرنده")
    national_code: str | None = Field(None, description="کد ملی گیرنده")


class CargoModel(BaseModel):
    type: str | None = Field(None, description="نوع کالا")
    weight: str | int | float = Field(..., description="وزن کالا")
    count: str | int = Field(default="1", description="تعداد کالا")
    description: str | None = Field(None, description="توضیحات کالا")


class VehicleModel(BaseModel):
    driver_national_code: str | None = Field(None, description="کد ملی راننده")
    driver_phone: str | None = Field(None, description="تلفن راننده")
    plate: str | None = Field(None, description="پلاک خودرو")
    type: str | None = Field(None, description="نوع خودرو")


class FinancialModel(BaseModel):
    cost: str | int | float | None = Field(None, description="هزینه حمل")
    payment_method: str | None = Field(None, description="روش پرداخت")


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
