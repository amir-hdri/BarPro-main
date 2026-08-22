"""API for saved route templates (multi-route feature)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth_multitenant import get_current_user_or_admin
from app.core.database import get_session
from app.models.waybill_route_template import WaybillRouteTemplate
from app.schemas.multiroute import RouteTemplateCreate, RouteTemplateUpdate
from app.services.route_template_service import route_template_service

router = APIRouter(prefix="/api/v1/route-templates", tags=["route-templates"])


def _resolve_client_id(user_context: dict[str, Any]) -> int:
    client_id = user_context.get("client_id")
    if not client_id and isinstance(user_context.get("user"), object) and hasattr(user_context["user"], "id"):
        client_id = user_context["user"].id
    if not client_id:
        raise HTTPException(status_code=403, detail="شناسه مشتری نامعتبر است")
    return int(client_id)


@router.post("", response_model=WaybillRouteTemplate, status_code=status.HTTP_201_CREATED)
async def create_route_template(
    payload: RouteTemplateCreate,
    user_context: dict[str, Any] = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    return await route_template_service.create(session, _resolve_client_id(user_context), payload)


@router.get("", response_model=list[WaybillRouteTemplate])
async def list_route_templates(
    user_context: dict[str, Any] = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    return await route_template_service.list(session, _resolve_client_id(user_context))


@router.get("/{template_id}", response_model=WaybillRouteTemplate)
async def get_route_template(
    template_id: int,
    user_context: dict[str, Any] = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    template = await route_template_service.get(session, template_id, _resolve_client_id(user_context))
    if template is None:
        raise HTTPException(status_code=404, detail="مسیر یافت نشد")
    return template


@router.put("/{template_id}", response_model=WaybillRouteTemplate)
async def update_route_template(
    template_id: int,
    payload: RouteTemplateUpdate,
    user_context: dict[str, Any] = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    template = await route_template_service.update(session, template_id, _resolve_client_id(user_context), payload)
    if template is None:
        raise HTTPException(status_code=404, detail="مسیر یافت نشد")
    return template


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_route_template(
    template_id: int,
    user_context: dict[str, Any] = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    deleted = await route_template_service.delete(session, template_id, _resolve_client_id(user_context))
    if not deleted:
        raise HTTPException(status_code=404, detail="مسیر یافت نشد")


@router.post("/{template_id}/favorite", response_model=WaybillRouteTemplate)
async def toggle_favorite(
    template_id: int,
    user_context: dict[str, Any] = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    template = await route_template_service.toggle_favorite(session, template_id, _resolve_client_id(user_context))
    if template is None:
        raise HTTPException(status_code=404, detail="مسیر یافت نشد")
    return template
