"""
مسیرهای API سرویس مکان‌ها، نقشه، پارس هوشمند آدرس و آدرس‌های محبوب
"""

import logging
from typing import Any

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth_multitenant import get_current_user_or_admin
from app.automation.proxy_rotator import get_proxy_rotator
from app.core.database import get_session
from app.core.iran_locations import (
    find_nearest_city_coords,
    get_all_provinces,
    get_cities_by_province,
    parse_smart_address,
)
from app.models.location_favorite import LocationFavorite
from app.models_multitenant import Client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/locations", tags=["locations"])


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
    provinces = get_all_provinces()
    return {"success": True, "data": provinces}


@router.get("/cities")
async def list_cities(province: str = Query(..., description="نام استان")):
    """دریافت لیست شهرهای یک استان مشخص"""
    cities = get_cities_by_province(province)
    return {"success": True, "province": province, "data": cities}


@router.post("/parse-address")
async def parse_address_endpoint(request: ParseAddressRequest):
    """پارس هوشمند متون سرهم آدرس به استان، شهر، منطقه و آدرس مجزا"""
    result = parse_smart_address(request.address_text)
    return {"success": True, "data": result}


@router.get("/reverse-geocode")
async def reverse_geocode_location(
    lat: float = Query(..., description="عرض جغرافیایی"),
    lng: float = Query(..., description="طول جغرافیایی"),
    user_context: dict[str, Any] = Depends(get_current_user_or_admin),
):
    """تبدیل مختصات جغرافیایی به استان، شهر و آدرس (با پشتیبانی هوشمند مستقیم + فال‌بک آنلاین/آفلاین)"""
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {
        "lat": lat,
        "lon": lng,
        "format": "json",
        "accept-language": "fa",
        "zoom": 12,
    }
    headers = {"User-Agent": "BarPro-Automation/1.0"}

    data = None

    # ۱. تلاش مستقیم برای Nominatim با زمان انتظار کوتاه (۲ ثانیه)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=2.0)) as resp:
                if resp.status == 200:
                    data = await resp.json()
    except Exception:
        logger.debug("direct_nominatim_failed_or_timed_out")

    # ۲. تلاش با پروکسی
    if data is None:
        try:
            proxy_info = await get_proxy_rotator().get_next()
            if proxy_info and proxy_info.protocol in ("http", "https"):
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url,
                        params=params,
                        headers=headers,
                        proxy=proxy_info.full_url,
                        timeout=aiohttp.ClientTimeout(total=3.0),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
        except Exception:
            logger.debug("proxy_nominatim_failed")

    if data and isinstance(data, dict):
        address = data.get("address", {})
        prov = address.get("state") or address.get("province") or address.get("county") or ""
        cit = address.get("city") or address.get("town") or address.get("village") or address.get("county") or ""
        dist = address.get("suburb") or address.get("district") or address.get("neighbourhood") or ""
        disp = data.get("display_name", "")
        return {
            "success": True,
            "province": prov,
            "city": cit,
            "district": dist,
            "address": disp,
            "source": "online_geocode",
        }

    # ۳. فال‌بک آفلاین: پیدا کردن نزدیک‌ترین شهر بر اساس دیتابیس شهرهای ایران
    offline_match = find_nearest_city_coords(lat, lng)
    if offline_match:
        return {
            "success": True,
            "province": offline_match["province"],
            "city": offline_match["city"],
            "district": "",
            "address": f"محدوده {offline_match['city']}، {offline_match['province']}",
            "source": "offline_dataset",
        }

    return {
        "success": False,
        "error": "مکان مورد نظر یافت نشد",
        "province": "",
        "city": "",
        "district": "",
        "address": "",
    }


@router.get("/favorites")
async def list_favorites(
    user_context: dict[str, Any] = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    """دریافت لیست آدرس‌های محبوب مشتری"""
    client_id = user_context.get("client_id")
    if not client_id:
        return {"success": True, "data": []}

    statement = select(LocationFavorite).where(LocationFavorite.client_id == client_id).order_by(LocationFavorite.title)
    results = await session.exec(statement)
    favorites = results.all()
    return {"success": True, "data": favorites}


@router.post("/favorites", status_code=status.HTTP_201_CREATED)
async def create_favorite(
    payload: FavoriteLocationCreate,
    user_context: dict[str, Any] = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    """افزودن مکان منتخب جدید برای مشتری"""
    client_id = user_context.get("client_id")
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
    return {"success": True, "data": fav}


@router.delete("/favorites/{favorite_id}")
async def delete_favorite(
    favorite_id: int,
    user_context: dict[str, Any] = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    """حذف مکان منتخب"""
    client_id = user_context.get("client_id")
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
    return {"success": True, "message": "مکان منتخب با موفقیت حذف شد"}
