"""A multi-route batch: expands N route templates × target_count into waybill jobs."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Index, UniqueConstraint
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _default_progress() -> dict:
    return {"completed": 0, "failed": 0, "today": 0}


class WaybillBatch(SQLModel, table=True):
    __tablename__ = "waybill_batch"
    __table_args__ = (
        Index("idx_batch_client_driver", "client_id", "driver_id"),
        Index("idx_batch_status", "status"),
        # Idempotency is scoped per tenant: the same key may legitimately exist in
        # different clients, so uniqueness must be composite, not global.
        UniqueConstraint("client_id", "idempotency_key", name="uq_batch_client_idempotency"),
    )

    id: int | None = Field(default=None, primary_key=True)
    client_id: int = Field(foreign_key="clients.id")
    idempotency_key: str | None = Field(default=None, max_length=128)
    driver_id: int | None = Field(default=None, foreign_key="drivers.id")
    name: str | None = Field(default=None, max_length=255)

    route_template_ids: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    base_payload_json: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    target_count: int = Field(default=15)
    repeat_mode: str = Field(default="round_robin", max_length=20)  # round_robin | random | sequential
    interval_minutes: int = Field(default=40)
    status: str = Field(default="active", max_length=20)  # active | paused | completed | cancelled
    progress: dict = Field(default_factory=_default_progress, sa_column=Column(JSON, nullable=False))

    created_at: datetime = Field(default_factory=_utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))
    updated_at: datetime = Field(default_factory=_utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))
