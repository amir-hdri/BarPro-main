from typing import Any

from pydantic import BaseModel, Field

from app.schemas.waybill import WaybillMapRequest


class ManagedCustomerUpsertRequest(BaseModel):
    source_system: str = Field(default="local")
    external_key: str
    full_name: str
    wallet: str | None = None
    driver_limit: int | None = None
    bot_running: bool | None = None
    bot_running_barname: bool | None = None
    auto_stop: bool | None = None
    two_way: bool | None = None
    remaining_duration: float | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class ManagedRouteUpsertRequest(BaseModel):
    source_system: str = Field(default="local")
    route_key: str
    name: str | None = None
    origin_label: str | None = None
    origin_province: str | None = None
    origin_city: str | None = None
    origin_address: str | None = None
    origin_lat: float | None = None
    origin_lng: float | None = None
    destination_label: str | None = None
    destination_province: str | None = None
    destination_city: str | None = None
    destination_address: str | None = None
    destination_lat: float | None = None
    destination_lng: float | None = None
    distance_km: float | None = None
    duration_minutes: float | None = None
    same_province: bool | None = None
    recommended: bool | None = None
    enabled: bool = True
    raw: dict[str, Any] = Field(default_factory=dict)


class ManagedAccountUpsertRequest(BaseModel):
    source_system: str = Field(default="local")
    external_name: str
    bot_owner: str | None = None
    title: str | None = None
    phone_number: str | None = None
    national_code: str | None = None
    platform: str | None = None
    status: str | None = None
    route_key: str | None = None
    otp_needed: bool | None = None
    has_account_is_enabled: bool | None = None
    has_driver_data: bool | None = None
    has_truck_data: bool | None = None
    has_valid_location: bool | None = None
    start_shipping: bool | None = None
    two_way: bool | None = None
    custom_current_submit: int | None = None
    custom_target_submit: int | None = None
    time_interval: int | None = None
    last_success: str | None = None
    source_details_json: str | None = None
    destination_detail_json: str | None = None
    mobile_info_json: str | None = None
    payment_details_json: str | None = None
    flags: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


class ManagedQueueCreateRequest(BaseModel):
    source_system: str = Field(default="local")
    account_external_name: str | None = None
    route_key: str | None = None
    bot_owner: str | None = None
    operation_mode: str = Field(default="safe")
    priority: int = Field(default=100)
    metadata: dict[str, Any] = Field(default_factory=dict)
    waybill_payload: WaybillMapRequest | None = None


class ManagedQueueDispatchRequest(BaseModel):
    idempotency_key: str | None = None
    warm_session_first: bool = True
    allow_otp_pending: bool = False


class ManagementBootstrapRequest(BaseModel):
    source_system: str = Field(default="local")
    customer_external_key: str | None = None
    customer_name: str | None = None
    bot_owner: str | None = None
    wallet: str | None = None
    driver_limit: int | None = None
    account_external_name: str | None = None
    account_title: str | None = None
    account_phone_number: str | None = None
    account_national_code: str | None = None
    platform: str = Field(default="Barname")
    status: str | None = Field(default="Ready")
    otp_needed: bool | None = None
    start_shipping: bool = True
    two_way: bool | None = None
    custom_current_submit: int | None = None
    custom_target_submit: int | None = None
    time_interval: int | None = None
    priority: int = Field(default=100)
    create_queue: bool = True
    waybill_payload: WaybillMapRequest


class ManagementExcelImportOptions(BaseModel):
    source_system: str = Field(default="local")
    customer_external_key: str | None = Field(default="excel-import")
    customer_name: str | None = Field(default="Excel Import")
    bot_owner: str | None = None
    wallet: str | None = None
    driver_limit: int | None = None
    platform: str = Field(default="Barname")
    operation_mode: str = Field(default="safe")
    login_url: str = Field(default="https://barname.utcms.ir/Barname/Account/Login")
    include_auth: bool = True
    create_queue: bool = True
    reverse_geo_enabled: bool = False
    default_province: str = Field(default="تهران")
    default_city: str = Field(default="تهران")
    priority: int = Field(default=100)
    time_interval: int | None = None
