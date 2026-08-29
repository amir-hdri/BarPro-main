"""CRUD + favorite toggle for saved route templates (multi-route feature)."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.waybill_route_template import WaybillRouteTemplate
from app.services.distance_service import get_route_distance


def _validate_route_fields(
    *,
    origin_province: Any,
    origin_city: Any,
    origin_address: Any,
    dest_province: Any,
    dest_city: Any,
    dest_address: Any,
) -> None:
    """Reject incomplete route templates before they can enter a batch."""
    missing: list[str] = []
    for label, value in (
        ("استان مبدأ", origin_province),
        ("شهر مبدأ", origin_city),
        ("آدرس مبدأ", origin_address),
        ("استان مقصد", dest_province),
        ("شهر مقصد", dest_city),
        ("آدرس مقصد", dest_address),
    ):
        if len(str(value or "").strip()) < 2:
            missing.append(label)
    if missing:
        raise HTTPException(status_code=422, detail="فیلدهای مسیر الزامی هستند: " + "، ".join(missing))


async def _compute_distance(
    origin_lat: float | None,
    origin_lng: float | None,
    dest_lat: float | None,
    dest_lng: float | None,
) -> tuple[float | None, float | None]:
    if origin_lat is None or origin_lng is None or dest_lat is None or dest_lng is None:
        return None, None
    try:
        data = await get_route_distance(origin_lat, origin_lng, dest_lat, dest_lng)
        return data.get("distance_km"), data.get("duration_min")
    except Exception:  # noqa: BLE001 — distance is best-effort on template save
        return None, None


class RouteTemplateService:
    async def create(self, session: AsyncSession, client_id: int, payload: Any) -> WaybillRouteTemplate:
        _validate_route_fields(
            origin_province=payload.origin_province,
            origin_city=payload.origin_city,
            origin_address=payload.origin_address,
            dest_province=payload.dest_province,
            dest_city=payload.dest_city,
            dest_address=payload.dest_address,
        )
        distance_km, duration_min = await _compute_distance(
            payload.origin_lat, payload.origin_lng, payload.dest_lat, payload.dest_lng
        )
        template = WaybillRouteTemplate(
            client_id=client_id,
            name=payload.name,
            origin_province=payload.origin_province,
            origin_city=payload.origin_city,
            origin_address=payload.origin_address,
            origin_lat=payload.origin_lat,
            origin_lng=payload.origin_lng,
            dest_province=payload.dest_province,
            dest_city=payload.dest_city,
            dest_address=payload.dest_address,
            dest_lat=payload.dest_lat,
            dest_lng=payload.dest_lng,
            distance_km=distance_km,
            duration_min=duration_min,
            is_favorite=True if payload.is_favorite is None else payload.is_favorite,
        )
        session.add(template)
        await session.commit()
        await session.refresh(template)
        return template

    async def list(self, session: AsyncSession, client_id: int) -> list[WaybillRouteTemplate]:
        statement = (
            select(WaybillRouteTemplate)
            .where(WaybillRouteTemplate.client_id == client_id)
            .order_by(WaybillRouteTemplate.id.desc())
        )
        return list((await session.exec(statement)).all())

    async def get(self, session: AsyncSession, template_id: int, client_id: int) -> WaybillRouteTemplate | None:
        template = await session.get(WaybillRouteTemplate, template_id)
        if template is None or template.client_id != client_id:
            return None
        return template

    async def update(
        self, session: AsyncSession, template_id: int, client_id: int, payload: Any
    ) -> WaybillRouteTemplate | None:
        template = await self.get(session, template_id, client_id)
        if template is None:
            return None
        data = payload.model_dump(exclude_unset=True)
        _non_nullable = {"name", "is_favorite"}
        _skip = {"distance_km", "duration_min", "client_id", "id", "created_at", "updated_at"}
        for field_name, value in data.items():
            if field_name in _skip:
                continue
            if value is None and field_name in _non_nullable:
                continue  # non-nullable columns must not be nulled
            setattr(template, field_name, value)
        _validate_route_fields(
            origin_province=template.origin_province,
            origin_city=template.origin_city,
            origin_address=template.origin_address,
            dest_province=template.dest_province,
            dest_city=template.dest_city,
            dest_address=template.dest_address,
        )
        # Recompute distance/duration when either endpoint's coordinates changed.
        if any(k in data for k in ("origin_lat", "origin_lng", "dest_lat", "dest_lng")):
            distance_km, duration_min = await _compute_distance(
                template.origin_lat, template.origin_lng, template.dest_lat, template.dest_lng
            )
            template.distance_km = distance_km
            template.duration_min = duration_min
        session.add(template)
        await session.commit()
        await session.refresh(template)
        return template

    async def delete(self, session: AsyncSession, template_id: int, client_id: int) -> bool:
        template = await self.get(session, template_id, client_id)
        if template is None:
            return False
        await session.delete(template)
        await session.commit()
        return True

    async def toggle_favorite(
        self, session: AsyncSession, template_id: int, client_id: int
    ) -> WaybillRouteTemplate | None:
        template = await self.get(session, template_id, client_id)
        if template is None:
            return None
        template.is_favorite = not template.is_favorite
        session.add(template)
        await session.commit()
        await session.refresh(template)
        return template


route_template_service = RouteTemplateService()
