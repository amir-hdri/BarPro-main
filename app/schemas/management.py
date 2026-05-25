from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from app.schemas.waybill import WaybillMapRequest



class ManagedCustomerUpsertRequest(BaseModel):
    source_system: str = Field(default="local")
    external_key: str
    full_name: str
    wallet: Optional[str] = None
    driver_limit: Optional[int] = None
    bot_running: Optional[bool] = None
    bot_running_barname: Optional[bool] = None
    auto_stop: Optional[bool] = None
    two_way: Optional[bool] = None
    remaining_duration: Optional[float] = None
    raw: Dict[str, Any] = Field(default_factory=dict)


class ManagedRouteUpsertRequest(BaseModel):
    source_system: str = Field(default="local")
    route_key: str
    name: Optional[str] = None
    origin_label: Optional[str] = None
    origin_province: Optional[str] = None
    origin_city: Optional[str] = None
    origin_address: Optional[str] = None
    origin_lat: Optional[float] = None
    origin_lng: Optional[float] = None
    destination_label: Optional[str] = None
    destination_province: Optional[str] = None
    destination_city: Optional[str] = None
    destination_address: Optional[str] = None
    destination_lat: Optional[float] = None
    destination_lng: Optional[float] = None
    distance_km: Optional[float] = None
    duration_minutes: Optional[float] = None
    same_province: Optional[bool] = None
    recommended: Optional[bool] = None
    enabled: bool = True
    raw: Dict[str, Any] = Field(default_factory=dict)


class ManagedAccountUpsertRequest(BaseModel):
    source_system: str = Field(default="local")
    external_name: str
    bot_owner: Optional[str] = None
    title: Optional[str] = None
    phone_number: Optional[str] = None
    national_code: Optional[str] = None
    platform: Optional[str] = None
    status: Optional[str] = None
    route_key: Optional[str] = None
    otp_needed: Optional[bool] = None
    has_account_is_enabled: Optional[bool] = None
    has_driver_data: Optional[bool] = None
    has_truck_data: Optional[bool] = None
    has_valid_location: Optional[bool] = None
    start_shipping: Optional[bool] = None
    two_way: Optional[bool] = None
    custom_current_submit: Optional[int] = None
    custom_target_submit: Optional[int] = None
    time_interval: Optional[int] = None
    last_success: Optional[str] = None
    source_details_json: Optional[str] = None
    destination_detail_json: Optional[str] = None
    mobile_info_json: Optional[str] = None
    payment_details_json: Optional[str] = None
    flags: Dict[str, Any] = Field(default_factory=dict)
    raw: Dict[str, Any] = Field(default_factory=dict)


class ManagedQueueCreateRequest(BaseModel):
    source_system: str = Field(default="local")
    account_external_name: Optional[str] = None
    route_key: Optional[str] = None
    bot_owner: Optional[str] = None
    operation_mode: str = Field(default="safe")
    priority: int = Field(default=100)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    waybill_payload: Optional[WaybillMapRequest] = None


class ManagedQueueDispatchRequest(BaseModel):
    idempotency_key: Optional[str] = None
    warm_session_first: bool = True
    allow_otp_pending: bool = False


class ManagementBootstrapRequest(BaseModel):
    source_system: str = Field(default="local")
    customer_external_key: Optional[str] = None
    customer_name: Optional[str] = None
    bot_owner: Optional[str] = None
    wallet: Optional[str] = None
    driver_limit: Optional[int] = None
    account_external_name: Optional[str] = None
    account_title: Optional[str] = None
    account_phone_number: Optional[str] = None
    account_national_code: Optional[str] = None
    platform: str = Field(default="Barname")
    status: Optional[str] = Field(default="Ready")
    otp_needed: Optional[bool] = None
    start_shipping: bool = True
    two_way: Optional[bool] = None
    custom_current_submit: Optional[int] = None
    custom_target_submit: Optional[int] = None
    time_interval: Optional[int] = None
    priority: int = Field(default=100)
    create_queue: bool = True
    waybill_payload: WaybillMapRequest


class ManagementExcelImportOptions(BaseModel):
    source_system: str = Field(default="local")
    customer_external_key: Optional[str] = Field(default="excel-import")
    customer_name: Optional[str] = Field(default="Excel Import")
    bot_owner: Optional[str] = None
    wallet: Optional[str] = None
    driver_limit: Optional[int] = None
    platform: str = Field(default="Barname")
    operation_mode: str = Field(default="safe")
    login_url: str = Field(default="https://barname.utcms.ir/Barname/Account/Login")
    include_auth: bool = True
    create_queue: bool = True
    reverse_geo_enabled: bool = False
    default_province: str = Field(default="تهران")
    default_city: str = Field(default="تهران")
    priority: int = Field(default=100)
    time_interval: Optional[int] = None
