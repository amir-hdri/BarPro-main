"""Pydantic schemas for the multi-route + distance/time feature."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DistanceRequest(BaseModel):
    origin_lat: float = Field(..., ge=-90, le=90, description="عرض جغرافیایی مبدأ")
    origin_lng: float = Field(..., ge=-180, le=180, description="طول جغرافیایی مبدأ")
    dest_lat: float = Field(..., ge=-90, le=90, description="عرض جغرافیایی مقصد")
    dest_lng: float = Field(..., ge=-180, le=180, description="طول جغرافیایی مقصد")


class DistanceResponse(BaseModel):
    distance_km: float
    duration_min: int
    distance_text: str
    duration_text: str
    source: str


class RouteTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    origin_province: str | None = None
    origin_city: str | None = None
    origin_address: str | None = None
    origin_lat: float | None = Field(default=None, ge=-90, le=90)
    origin_lng: float | None = Field(default=None, ge=-180, le=180)
    dest_province: str | None = None
    dest_city: str | None = None
    dest_address: str | None = None
    dest_lat: float | None = Field(default=None, ge=-90, le=90)
    dest_lng: float | None = Field(default=None, ge=-180, le=180)
    is_favorite: bool = True


class RouteTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    origin_province: str | None = None
    origin_city: str | None = None
    origin_address: str | None = None
    origin_lat: float | None = Field(default=None, ge=-90, le=90)
    origin_lng: float | None = Field(default=None, ge=-180, le=180)
    dest_province: str | None = None
    dest_city: str | None = None
    dest_address: str | None = None
    dest_lat: float | None = Field(default=None, ge=-90, le=90)
    dest_lng: float | None = Field(default=None, ge=-180, le=180)
    is_favorite: bool | None = None


class BatchCreate(BaseModel):
    driver_id: int = Field(..., ge=1, description="شناسه راننده (اجباری)")
    name: str | None = None
    route_template_ids: list[int] = Field(..., min_length=1)
    base_payload_json: dict = Field(
        ...,
        description="بارنامه پایه (اجباری: sender/receiver/cargo/vehicle) که مبدأ/مقصد از مسیر override می‌شود",
    )
    target_count: int = Field(default=15, ge=1, le=1000)
    repeat_mode: Literal["round_robin", "random", "sequential"] = "round_robin"
    interval_minutes: int = Field(default=40, ge=0, le=1440)
    # 0-9: must match WaybillJobUpdateRequest and CELERY_MAX_PRIORITY —
    # values above 9 were silently clipped by the broker, creating drift.
    priority: int = Field(default=5, ge=0, le=9)


class BatchProgressResponse(BaseModel):
    batch_id: int
    target: int
    completed: int
    failed: int
    today: int
    progress_percent: int
    status: str
