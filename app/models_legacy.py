from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class BotStats(SQLModel, table=True):
    __tablename__ = "botstats"
    """مدل آمار روزانه عملکرد ربات"""

    id: Optional[int] = Field(default=None, primary_key=True)
    report_date: date = Field(index=True, unique=True)

    total_requests: int = Field(default=0)
    successful_waybills: int = Field(default=0)
    failed_attempts: int = Field(default=0)

    map_google: int = Field(default=0)
    map_openlayers: int = Field(default=0)
    map_leaflet: int = Field(default=0)
    map_mapbox: int = Field(default=0)
    map_unknown: int = Field(default=0)
    map_none: int = Field(default=0)


class WaybillTask(SQLModel, table=True):
    """وضعیت اجرای هر درخواست بارنامه در صف."""

    __tablename__ = "waybilltask"
    __table_args__ = (
        UniqueConstraint("task_id", name="uq_waybill_task_task_id"),
        UniqueConstraint("idempotency_key", name="uq_waybill_task_idempotency_key"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: str = Field(index=True)
    idempotency_key: str = Field(index=True)
    status: str = Field(default="queued", index=True)

    payload_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    result_json: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    last_error: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    error_category: Optional[str] = Field(default=None, index=True)

    attempt_count: int = Field(default=0)
    max_retries: int = Field(default=0)
    retryable: bool = Field(default=False)
    celery_task_id: Optional[str] = Field(default=None, index=True)
    worker_id: Optional[str] = Field(default=None, index=True)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )
    started_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=False), nullable=True),
    )
    finished_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=False), nullable=True),
    )
