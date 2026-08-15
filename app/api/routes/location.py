"""
مسیرهای API سرویس مکان‌ها، نقشه، پارس هوشمند آدرس و آدرس‌های محبوب
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth_multitenant import get_current_user_or_admin
from app.core.database import get_session
from app.core.iran_locations import (
    get_all_provinces,
    get_cities_by_province,
    parse_smart_address,
)
from app.models.location_favorite import LocationFavorite

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/locations", tags=["locations"])


class ParseAddressRequest(BaseModel):
    address_text: str = Field(..., description="متن کامل یا سرهم آدرس")


class FavoriteLocationCreate(BaseModel):
    title: str = Field(..., description="عنوان مکان مانند انبار مرکزی")
    province: str = Field(..., description="استان")
    city: str = Field(..., description="شهر")
    district: str | None = Field(default=None, description="ناحیه / منطقه")
    address: str = Field(..., description="آدرس دقیق")
    latitude: float | None = Field(default=None, description="عرض جغرافیایی")
    longitude: float | None = Field(default=None, description="طول جغرافیایی")
    is_origin: bool = Field(default=True, description="قابل استفاده به عنوان مبدا")
    is_destination: bool = Field(default=True, description="قابل استفاده به عنوان مقصد")


@router.get("/provinces")
async def list_provinces():
    """دریافت لیست کل ۳۱ استان ایران به همراه مرکز و مختصات"""
    return get_all_provinces()


@router.get("/cities")
async def list_cities(province: str = Query(..., description="نام استان")):
    """دریافت لیست شهرهای یک استان مشخص"""
    return get_cities_by_province(province)


@router.post("/parse-address")
async def parse_address_endpoint(request: ParseAddressRequest):
    """پارس هوشمند متون سرهم آدرس به استان، شهر، منطقه و آدرس مجزا"""
    return parse_smart_address(request.address_text)


@router.get("/reverse-geocode")
async def reverse_geocode_location(
    lat: float = Query(..., description="عرض جغرافیایی"),
    lng: float = Query(..., description="طول جغرافیایی"),
    user_context: dict[str, Any] = Depends(get_current_user_or_admin),
):
    """تبدیل مختصات جغرافیایی به استان، شهر و آدرس با کَش درون‌حافظه‌ای و حد فاصله فال‌بک"""
    from app.services.location_service import location_service

    return await location_service.reverse_geocode(lat, lng)


@router.get("/favorites", response_model=list[LocationFavorite])
async def list_favorites(
    user_context: dict[str, Any] = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    """دریافت لیست آدرس‌های محبوب مشتری"""
    client_id = user_context.get("client_id")
    if not client_id and isinstance(user_context.get("user"), object) and hasattr(user_context["user"], "id"):
        client_id = user_context["user"].id
    if not client_id:
        return []

    statement = select(LocationFavorite).where(LocationFavorite.client_id == client_id).order_by(LocationFavorite.title)
    results = await session.exec(statement)
    return list(results.all())


@router.post("/favorites", response_model=LocationFavorite, status_code=status.HTTP_201_CREATED)
async def create_favorite(
    payload: FavoriteLocationCreate,
    user_context: dict[str, Any] = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    """افزودن مکان منتخب جدید برای مشتری"""
    client_id = user_context.get("client_id")
    if not client_id and isinstance(user_context.get("user"), object) and hasattr(user_context["user"], "id"):
        client_id = user_context["user"].id
    if not client_id:
        raise HTTPException(status_code=403, detail="شناسه مشتری نامعتبر است")

    fav = LocationFavorite(
        client_id=client_id,
        title=payload.title,
        province=payload.province,
        city=payload.city,
        district=payload.district,
        address=payload.address,
        latitude=payload.latitude,
        longitude=payload.longitude,
        is_origin=payload.is_origin,
        is_destination=payload.is_destination,
    )
    session.add(fav)
    await session.commit()
    await session.refresh(fav)
    return fav


@router.delete("/favorites/{favorite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_favorite(
    favorite_id: int,
    user_context: dict[str, Any] = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    """حذف مکان منتخب"""
    client_id = user_context.get("client_id")
    if not client_id and isinstance(user_context.get("user"), object) and hasattr(user_context["user"], "id"):
        client_id = user_context["user"].id
    if not client_id:
        raise HTTPException(status_code=403, detail="دسترسی غیرمجاز")

    statement = select(LocationFavorite).where(
        LocationFavorite.id == favorite_id, LocationFavorite.client_id == client_id
    )
    res = await session.exec(statement)
    fav = res.first()
    if not fav:
        raise HTTPException(status_code=404, detail="مکان منتخب یافت نشد")

    await session.delete(fav)
    await session.commit()
    return None
