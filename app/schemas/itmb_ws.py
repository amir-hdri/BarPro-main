from typing import Any, Dict, List, Optional

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
    Description: Optional[str] = None
    Image: Optional[bytes] = None


class BOLCnt(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    PlaqueID: str = Field(..., min_length=7, max_length=7)
    PlaqueSN: int = Field(..., ge=10, le=99)
    PlaqueType: str
    DriverNationalCode: str = Field(..., min_length=10, max_length=10)
    SecondDriverNationalCode: Optional[str] = Field(default=None, min_length=10, max_length=10)
    OWNERNATIONALID: str

    SenderType: int = Field(..., ge=1, le=2)
    SenderName: str
    SenderLastName: Optional[str] = None
    SenderNationalID: Optional[str] = Field(default=None, min_length=10, max_length=10)
    SenderMobile: Optional[str] = None
    SenderPhoneNo: Optional[str] = None
    SenderPostalCode: Optional[str] = None
    SenderCityCode: Optional[str] = None
    SenderAddress: str

    RecieverType: int = Field(..., ge=1, le=2)
    RecieverName: str
    RecieverLastName: Optional[str] = None
    RecieverNationalID: Optional[str] = Field(default=None, min_length=10, max_length=10)
    RecieverMobile: Optional[str] = None
    RecieverPhoneNo: Optional[str] = None
    RecieverPostalCode: Optional[str] = None
    RecieverCityCode: Optional[str] = None
    RecieverAddress: str

    Freightage: int = Field(default=0, ge=0)
    PreFreightage: int = Field(default=0, ge=0)
    FreightageTax: int = Field(default=0, ge=0)
    CompanyCommission: int = Field(default=0, ge=0)
    ITServiceCost: int = Field(default=0, ge=0)
    InfoServiceCost: int = Field(default=0, ge=0)
    TotalAmountPayment: int = Field(..., ge=0)
    InsuranceCosts: int = Field(default=0, ge=0)

    Description: Optional[str] = None
    SerialNo: int = Field(..., gt=0)
    IssuerNaCode: str = Field(..., min_length=10, max_length=10)
    IssuerMobile: Optional[str] = None
    IssueDate: int = Field(..., ge=0, description="Unix timestamp")

    LoadingPlacePostalCode: Optional[str] = None
    LoadingPlaceCityCode: Optional[str] = None
    LoadingPlaceAddress: str
    OffLoadingPlacePostalCode: Optional[str] = None
    OffLoadingPlaceCityCode: Optional[str] = None
    OffLoadingPlaceAddress: str
    LoadingPlaceCountieCode: Optional[str] = None
    OffLoadingPlaceCountieCode: Optional[str] = None
    OriginLattitude: Optional[float] = None
    OriginLongitude: Optional[float] = None
    DestinationLattitude: Optional[float] = None
    DestinationLongitude: Optional[float] = None

    Goods: List[BOLGoodCnt] = Field(..., min_length=1)

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
    def validate_national_codes(cls, value: Optional[str]) -> Optional[str]:
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
    def validate_postal_codes(cls, value: Optional[str]) -> Optional[str]:
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

    CompanyCode: Optional[str] = None
    ServicePassword: Optional[str] = None
    Salt: Optional[int] = None
    HashedValue: Optional[str] = None
    bol: BOLCnt
    InsertTime: Optional[int] = Field(default=None, ge=0, description="Unix timestamp")
    InsertPosition: GPSCnt

    @field_validator("HashedValue")
    @classmethod
    def validate_hashed_value(cls, value: Optional[str]) -> Optional[str]:
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
    baseinfo_validation: Dict[str, Any] = Field(default_factory=dict)
