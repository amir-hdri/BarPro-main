from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class GPSCnt(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    Latitude: float
    Longitude: float
    Altitude: float = 0
    Bearing: float = 0
    NumberOfSatellite: int = Field(default=0, ge=0, le=255)
    PDOP: int = Field(default=0, ge=0, le=255)
    GPSSpeed: int = Field(default=0, ge=0, le=255)
    GPSMaxSpeed: int = Field(default=0, ge=0, le=255)
    GPSTotalTraveledDistance: int = Field(default=0, ge=0)

    @field_validator("Latitude")
    @classmethod
    def validate_latitude(cls, value: float) -> float:
        if value < -90 or value > 90:
            raise ValueError("Latitude باید بین 90- و 90 باشد")
        return value

    @field_validator("Longitude")
    @classmethod
    def validate_longitude(cls, value: float) -> float:
        if value < -180 or value > 180:
            raise ValueError("Longitude باید بین 180- و 180 باشد")
        return value


class BOLGoodCnt(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    GoodID: int = Field(..., gt=0)
    WeightKg: float = Field(..., gt=0)
    Value: float = Field(..., gt=0)
    PackingTypeID: int = Field(..., gt=0)
    GoodtypeID: int = Field(..., gt=0)
    Description: str | None = None
    Image: bytes | None = None


class BOLCnt(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    PlaqueID: str = Field(..., min_length=7, max_length=7)
    PlaqueSN: int = Field(..., ge=10, le=99)
    PlaqueType: str
    DriverNationalCode: str = Field(..., min_length=10, max_length=10)
    SecondDriverNationalCode: str | None = Field(default=None, min_length=10, max_length=10)
    OWNERNATIONALID: str

    SenderType: int = Field(..., ge=1, le=2)
    SenderName: str
    SenderLastName: str | None = None
    SenderNationalID: str | None = Field(default=None, min_length=10, max_length=10)
    SenderMobile: str | None = None
    SenderPhoneNo: str | None = None
    SenderPostalCode: str | None = None
    SenderCityCode: str | None = None
    SenderAddress: str

    RecieverType: int = Field(..., ge=1, le=2)
    RecieverName: str
    RecieverLastName: str | None = None
    RecieverNationalID: str | None = Field(default=None, min_length=10, max_length=10)
    RecieverMobile: str | None = None
    RecieverPhoneNo: str | None = None
    RecieverPostalCode: str | None = None
    RecieverCityCode: str | None = None
    RecieverAddress: str

    Freightage: int = Field(default=0, ge=0)
    PreFreightage: int = Field(default=0, ge=0)
    FreightageTax: int = Field(default=0, ge=0)
    CompanyCommission: int = Field(default=0, ge=0)
    ITServiceCost: int = Field(default=0, ge=0)
    InfoServiceCost: int = Field(default=0, ge=0)
    TotalAmountPayment: int = Field(..., ge=0)
    InsuranceCosts: int = Field(default=0, ge=0)

    Description: str | None = None
    SerialNo: int = Field(..., gt=0)
    IssuerNaCode: str = Field(..., min_length=10, max_length=10)
    IssuerMobile: str | None = None
    IssueDate: int = Field(..., ge=0, description="Unix timestamp")

    LoadingPlacePostalCode: str | None = None
    LoadingPlaceCityCode: str | None = None
    LoadingPlaceAddress: str
    OffLoadingPlacePostalCode: str | None = None
    OffLoadingPlaceCityCode: str | None = None
    OffLoadingPlaceAddress: str
    LoadingPlaceCountieCode: str | None = None
    OffLoadingPlaceCountieCode: str | None = None
    OriginLattitude: float | None = None
    OriginLongitude: float | None = None
    DestinationLattitude: float | None = None
    DestinationLongitude: float | None = None

    Goods: list[BOLGoodCnt] = Field(..., min_length=1)

    @field_validator("PlaqueID")
    @classmethod
    def validate_plaque_id(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("PlaqueID باید فقط عدد باشد")
        return value

    @field_validator(
        "DriverNationalCode",
        "SecondDriverNationalCode",
        "SenderNationalID",
        "RecieverNationalID",
        "IssuerNaCode",
        mode="before",
    )
    @classmethod
    def validate_national_codes(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.isdigit() or len(value) != 10:
            raise ValueError("کد ملی باید 10 رقم عددی باشد")
        return value

    @field_validator(
        "SenderPostalCode",
        "RecieverPostalCode",
        "LoadingPlacePostalCode",
        "OffLoadingPlacePostalCode",
        mode="before",
    )
    @classmethod
    def validate_postal_codes(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if not value.isdigit() or len(value) != 10:
            raise ValueError("کد پستی باید 10 رقم عددی باشد")
        return value

    @model_validator(mode="after")
    def validate_people_fields(self):
        if self.SenderType == 1:
            if not self.SenderLastName:
                raise ValueError("SenderLastName برای شخص حقیقی الزامی است")
            if not self.SenderNationalID:
                raise ValueError("SenderNationalID برای شخص حقیقی الزامی است")
        if self.RecieverType == 1:
            if not self.RecieverLastName:
                raise ValueError("RecieverLastName برای شخص حقیقی الزامی است")
            if not self.RecieverNationalID:
                raise ValueError("RecieverNationalID برای شخص حقیقی الزامی است")
        return self

    @model_validator(mode="after")
    def validate_financial_total(self):
        calculated_total = (
            self.Freightage
            + self.PreFreightage
            + self.FreightageTax
            + self.CompanyCommission
            + self.ITServiceCost
            + self.InfoServiceCost
            + self.InsuranceCosts
        )
        if self.TotalAmountPayment != calculated_total:
            raise ValueError("TotalAmountPayment باید برابر مجموع هزینه‌ها باشد")
        return self


class WS01InsertBOLRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    CompanyCode: str | None = None
    ServicePassword: str | None = None
    Salt: int | None = None
    HashedValue: str | None = None
    bol: BOLCnt
    InsertTime: int | None = Field(default=None, ge=0, description="Unix timestamp")
    InsertPosition: GPSCnt

    @field_validator("HashedValue")
    @classmethod
    def validate_hashed_value(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if cleaned == "":
            return None
        if len(cleaned) != 128:
            raise ValueError("HashedValue باید خروجی کامل SHA512 باشد")
        return cleaned.upper()


class WS01InsertBOLResponse(BaseModel):
    success: bool
    bol_trace_code: str
    used_salt: int
    baseinfo_validation: dict[str, Any] = Field(default_factory=dict)


class WS03StartBOLRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    CompanyCode: str | None = None
    ServicePassword: str | None = None
    Salt: int | None = None
    HashedValue: str | None = None
    BOLTraceCode: str = Field(..., min_length=1)
    StartTime: int | None = Field(default=None, ge=0, description="Unix timestamp")
    StartPosition: GPSCnt


class WS03StartBOLResponse(BaseModel):
    success: bool
    bol_trace_code: str
    result_code: int = 200
    message: str = "سفر با موفقیت آغاز شد"


class WS04EndBOLRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    CompanyCode: str | None = None
    ServicePassword: str | None = None
    Salt: int | None = None
    HashedValue: str | None = None
    BOLTraceCode: str = Field(..., min_length=1)
    EndTime: int | None = Field(default=None, ge=0, description="Unix timestamp")
    EndPosition: GPSCnt


class WS04EndBOLResponse(BaseModel):
    success: bool
    bol_trace_code: str
    result_code: int = 200
    message: str = "سفر با موفقیت پایان یافت"


class WS06InsertBOLTrackRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    CompanyCode: str | None = None
    ServicePassword: str | None = None
    Salt: int | None = None
    HashedValue: str | None = None
    BOLTraceCode: str = Field(..., min_length=1)
    TrackTime: int | None = Field(default=None, ge=0, description="Unix timestamp")
    TrackPosition: GPSCnt


class WS06InsertBOLTrackResponse(BaseModel):
    success: bool
    bol_trace_code: str
    result_code: int = 200
    message: str = "موقعیت با موفقیت ثبت شد"
