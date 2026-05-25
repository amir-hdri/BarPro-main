from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime, Integer, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class ManagedCustomer(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("source_system", "external_key", name="uq_managed_customer_source_external"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    source_system: str = Field(default="local", index=True)
    external_key: str = Field(index=True)
    full_name: str = Field(index=True)

    wallet: Optional[str] = Field(default=None)
    driver_limit: Optional[int] = Field(default=None)
    bot_running: Optional[bool] = Field(default=None)
    bot_running_barname: Optional[bool] = Field(default=None)
    auto_stop: Optional[bool] = Field(default=None)
    two_way: Optional[bool] = Field(default=None)
    remaining_duration: Optional[float] = Field(default=None)

    raw_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    synced_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )


class ManagedRoute(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("source_system", "route_key", name="uq_managed_route_source_key"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    source_system: str = Field(default="local", index=True)
    route_key: str = Field(index=True)
    name: Optional[str] = Field(default=None, index=True)

    origin_label: Optional[str] = Field(default=None)
    origin_province: Optional[str] = Field(default=None, index=True)
    origin_city: Optional[str] = Field(default=None, index=True)
    origin_address: Optional[str] = Field(default=None)
    origin_lat: Optional[float] = Field(default=None)
    origin_lng: Optional[float] = Field(default=None)

    destination_label: Optional[str] = Field(default=None)
    destination_province: Optional[str] = Field(default=None, index=True)
    destination_city: Optional[str] = Field(default=None, index=True)
    destination_address: Optional[str] = Field(default=None)
    destination_lat: Optional[float] = Field(default=None)
    destination_lng: Optional[float] = Field(default=None)

    distance_km: Optional[float] = Field(default=None)
    duration_minutes: Optional[float] = Field(default=None)
    same_province: Optional[bool] = Field(default=None)
    recommended: Optional[bool] = Field(default=None)
    enabled: bool = Field(default=True)

    raw_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    synced_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )


class ManagedAccount(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("source_system", "external_name", name="uq_managed_account_source_external"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    source_system: str = Field(default="local", index=True)
    external_name: str = Field(index=True)
    bot_owner: Optional[str] = Field(default=None, index=True)
    title: Optional[str] = Field(default=None, index=True)
    phone_number: Optional[str] = Field(default=None, index=True)
    national_code: Optional[str] = Field(default=None, index=True)
    platform: Optional[str] = Field(default=None, index=True)
    status: Optional[str] = Field(default=None, index=True)
    route_key: Optional[str] = Field(default=None, index=True)

    otp_needed: Optional[bool] = Field(default=None)
    has_account_is_enabled: Optional[bool] = Field(default=None)
    has_driver_data: Optional[bool] = Field(default=None)
    has_truck_data: Optional[bool] = Field(default=None)
    has_valid_location: Optional[bool] = Field(default=None)
    start_shipping: Optional[bool] = Field(default=None)
    two_way: Optional[bool] = Field(default=None)

    custom_current_submit: Optional[int] = Field(default=None, sa_column=Column(Integer, nullable=True))
    custom_target_submit: Optional[int] = Field(default=None, sa_column=Column(Integer, nullable=True))
    time_interval: Optional[int] = Field(default=None, sa_column=Column(Integer, nullable=True))
    last_success: Optional[str] = Field(default=None)

    source_details_json: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    destination_detail_json: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    mobile_info_json: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    payment_details_json: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    flags_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    raw_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    synced_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )


class ManagedQueueItem(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("source_system", "external_key", name="uq_managed_queue_source_external"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    queue_item_id: str = Field(index=True)
    source_system: str = Field(default="local", index=True)
    external_key: str = Field(index=True)
    account_external_name: Optional[str] = Field(default=None, index=True)
    route_key: Optional[str] = Field(default=None, index=True)
    bot_owner: Optional[str] = Field(default=None, index=True)
    status: str = Field(default="queued", index=True)
    operation_mode: str = Field(default="safe", index=True)
    priority: int = Field(default=100, index=True)
    origin: str = Field(default="local")

    payload_json: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    result_json: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    metadata_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    last_error: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )
    dispatched_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=False), nullable=True),
    )
    finished_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=False), nullable=True),
    )


class ManagedSyncLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    source_system: str = Field(default="local", index=True)
    sync_type: str = Field(default="audit", index=True)
    status: str = Field(default="completed", index=True)
    summary_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    error_text: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )
