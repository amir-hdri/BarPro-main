from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Integer, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class ManagedCustomer(SQLModel, table=True):
    __tablename__ = "managed_customers"
    __table_args__ = (UniqueConstraint("source_system", "external_key", name="uq_managed_customer_source_external"),)

    id: int | None = Field(default=None, primary_key=True)
    source_system: str = Field(default="local", index=True)
    external_key: str = Field(index=True)
    full_name: str = Field(index=True)

    wallet: str | None = Field(default=None)
    driver_limit: int | None = Field(default=None)
    bot_running: bool | None = Field(default=None)
    bot_running_barname: bool | None = Field(default=None)
    auto_stop: bool | None = Field(default=None)
    two_way: bool | None = Field(default=None)
    remaining_duration: float | None = Field(default=None)

    raw_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    synced_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )


class ManagedRoute(SQLModel, table=True):
    __tablename__ = "managed_routes"
    __table_args__ = (UniqueConstraint("source_system", "route_key", name="uq_managed_route_source_key"),)

    id: int | None = Field(default=None, primary_key=True)
    source_system: str = Field(default="local", index=True)
    route_key: str = Field(index=True)
    name: str | None = Field(default=None, index=True)

    origin_label: str | None = Field(default=None)
    origin_province: str | None = Field(default=None, index=True)
    origin_city: str | None = Field(default=None, index=True)
    origin_address: str | None = Field(default=None)
    origin_lat: float | None = Field(default=None)
    origin_lng: float | None = Field(default=None)

    destination_label: str | None = Field(default=None)
    destination_province: str | None = Field(default=None, index=True)
    destination_city: str | None = Field(default=None, index=True)
    destination_address: str | None = Field(default=None)
    destination_lat: float | None = Field(default=None)
    destination_lng: float | None = Field(default=None)

    distance_km: float | None = Field(default=None)
    duration_minutes: float | None = Field(default=None)
    same_province: bool | None = Field(default=None)
    recommended: bool | None = Field(default=None)
    enabled: bool = Field(default=True)

    raw_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    synced_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )


class ManagedAccount(SQLModel, table=True):
    __tablename__ = "managed_accounts"
    __table_args__ = (UniqueConstraint("source_system", "external_name", name="uq_managed_account_source_external"),)

    id: int | None = Field(default=None, primary_key=True)
    source_system: str = Field(default="local", index=True)
    external_name: str = Field(index=True)
    bot_owner: str | None = Field(default=None, index=True)
    title: str | None = Field(default=None, index=True)
    phone_number: str | None = Field(default=None, index=True)
    national_code: str | None = Field(default=None, index=True)
    platform: str | None = Field(default=None, index=True)
    status: str | None = Field(default=None, index=True)
    route_key: str | None = Field(default=None, index=True)

    otp_needed: bool | None = Field(default=None)
    has_account_is_enabled: bool | None = Field(default=None)
    has_driver_data: bool | None = Field(default=None)
    has_truck_data: bool | None = Field(default=None)
    has_valid_location: bool | None = Field(default=None)
    start_shipping: bool | None = Field(default=None)
    two_way: bool | None = Field(default=None)

    custom_current_submit: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    custom_target_submit: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    time_interval: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    last_success: str | None = Field(default=None)

    source_details_json: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    destination_detail_json: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    mobile_info_json: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    payment_details_json: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    flags_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    raw_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    synced_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )


class ManagedQueueItem(SQLModel, table=True):
    __tablename__ = "managed_queue_items"
    __table_args__ = (UniqueConstraint("source_system", "external_key", name="uq_managed_queue_source_external"),)

    id: int | None = Field(default=None, primary_key=True)
    queue_item_id: str = Field(index=True)
    source_system: str = Field(default="local", index=True)
    external_key: str = Field(index=True)
    account_external_name: str | None = Field(default=None, index=True)
    route_key: str | None = Field(default=None, index=True)
    bot_owner: str | None = Field(default=None, index=True)
    status: str = Field(default="queued", index=True)
    operation_mode: str = Field(default="safe", index=True)
    priority: int = Field(default=100, index=True)
    origin: str = Field(default="local")

    payload_json: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    result_json: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    metadata_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    last_error: str | None = Field(default=None, sa_column=Column(Text, nullable=True))

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )
    dispatched_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=False), nullable=True),
    )
    finished_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=False), nullable=True),
    )


class ManagedSyncLog(SQLModel, table=True):
    __tablename__ = "managed_sync_logs"
    id: int | None = Field(default=None, primary_key=True)
    source_system: str = Field(default="local", index=True)
    sync_type: str = Field(default="audit", index=True)
    status: str = Field(default="completed", index=True)
    summary_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    error_text: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )
