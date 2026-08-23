"""API for multi-route batches (create + progress)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth_multitenant import get_current_user_or_admin
from app.core.database import get_session
from app.models.waybill_batch import WaybillBatch
from app.schemas.multiroute import BatchCreate, BatchProgressResponse
from app.services.batch_service import batch_service

router = APIRouter(prefix="/api/v1/batches", tags=["batches"])


def _resolve_client_id(user_context: dict[str, Any]) -> int:
    client_id = user_context.get("client_id")
    if not client_id and isinstance(user_context.get("user"), object) and hasattr(user_context["user"], "id"):
        client_id = user_context["user"].id
    if not client_id:
        raise HTTPException(status_code=403, detail="شناسه مشتری نامعتبر است")
    return int(client_id)


@router.post("", response_model=WaybillBatch, status_code=status.HTTP_201_CREATED)
async def create_batch(
    payload: BatchCreate,
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    user_context: dict[str, Any] = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    return await batch_service.create_batch(session, _resolve_client_id(user_context), payload, idempotency_key)


@router.get("/{batch_id}/progress", response_model=BatchProgressResponse)
async def get_batch_progress(
    batch_id: int,
    user_context: dict[str, Any] = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    return await batch_service.get_progress(session, batch_id, _resolve_client_id(user_context))
