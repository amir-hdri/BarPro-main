"""
SQLModel table for Client Favorite Locations (آدرس‌های محبوب مشتریان)
"""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Index
from sqlmodel import Field, SQLModel


class LocationFavorite(SQLModel, table=True):
    """جدول ذخیره آدرس‌های محبوب و منتخب مشتریان"""

    __tablename__ = "location_favorites"
    __table_args__ = (
        Index("idx_loc_fav_client_id", "client_id"),
        Index("idx_loc_fav_title", "client_id", "title"),
    )

    id: int | None = Field(default=None, primary_key=True)
    client_id: int = Field(foreign_key="clients.id", index=True)
    title: str = Field(index=True, description="عنوان مکان، مثل انبار مرکزی یا کارخانه")
    province: str = Field(description="استان")
    city: str = Field(description="شهر")
    district: str | None = Field(default=None, description="ناحیه / منطقه")
    address: str = Field(description="آدرس دقیق")
    latitude: float | None = Field(default=None, description="عرض جغرافیایی")
    longitude: float | None = Field(default=None, description="طول جغرافیایی")
    is_origin: bool = Field(default=True, description="قابل استفاده به عنوان مبدا")
    is_destination: bool = Field(default=True, description="قابل استفاده به عنوان مقصد")

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
