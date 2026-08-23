"""Saved origin→destination route template with precomputed distance/duration."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Index, Text
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class WaybillRouteTemplate(SQLModel, table=True):
    __tablename__ = "waybill_route_template"
    __table_args__ = (
        Index("idx_rt_client_id", "client_id"),
        Index("idx_rt_client_favorite", "client_id", "is_favorite"),
    )

    id: int | None = Field(default=None, primary_key=True)
    client_id: int = Field(foreign_key="clients.id")
    name: str = Field(default="", max_length=255)

    origin_province: str | None = Field(default=None, max_length=100)
    origin_city: str | None = Field(default=None, max_length=100)
    origin_address: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    origin_lat: float | None = Field(default=None)
    origin_lng: float | None = Field(default=None)

    dest_province: str | None = Field(default=None, max_length=100)
    dest_city: str | None = Field(default=None, max_length=100)
    dest_address: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    dest_lat: float | None = Field(default=None)
    dest_lng: float | None = Field(default=None)

    distance_km: float | None = Field(default=None)
    duration_min: float | None = Field(default=None)

    is_favorite: bool = Field(default=True)

    created_at: datetime = Field(default_factory=_utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))
    updated_at: datetime = Field(default_factory=_utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))
