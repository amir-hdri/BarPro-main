"""Operational APIs for the Phase 1 hybrid multi-tenant RPA backend."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth_multitenant import get_current_client
from app.core.config import utcms_config
from app.core.database import get_session
from app.models_multitenant import Client, Driver
from app.models_rpa import DriverRuntimeState
from app.schemas.rpa_phase1 import (
    DriverCounterSnapshotResponse,
    DriverRuntimeStateResponse,
    Phase1OverviewResponse,
    SchedulerDecisionResponse,
)
from app.services.rpa_runtime_service import rpa_runtime
from app.services.rpa_scheduler_service import rpa_scheduler_service

router = APIRouter(prefix="/api/v1/rpa/phase1", tags=["multi-tenant-rpa-phase1"])


@router.get("/overview", response_model=Phase1OverviewResponse)
async def phase1_overview(client: Client = Depends(get_current_client)):
    return Phase1OverviewResponse(
        scheduler_batch_size=utcms_config.RPA_SCHEDULER_BATCH_SIZE,
        tenant_slice=utcms_config.RPA_SCHEDULER_TENANT_SLICE,
        session_ttl_seconds=utcms_config.RPA_SESSION_TTL_SECONDS,
        retry_delay_seconds=utcms_config.DRIVER_RETRY_DELAY_SECONDS,
        daily_success_cap=utcms_config.DRIVER_DAILY_SUCCESS_CAP,
        daily_attempt_cap=utcms_config.DRIVER_DAILY_ATTEMPT_CAP,
        queues={
            "auth": utcms_config.RPA_AUTH_QUEUE,
            "submit": utcms_config.RPA_SUBMIT_QUEUE,
            "refresh": utcms_config.RPA_REFRESH_QUEUE,
            "deadletter": utcms_config.RPA_DEADLETTER_QUEUE,
            "scheduler": utcms_config.RPA_SCHEDULER_QUEUE,
        },
    )


@router.get("/drivers/{driver_id}/runtime", response_model=DriverRuntimeStateResponse)
async def get_driver_runtime_state(
    driver_id: int,
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    driver = await session.get(Driver, driver_id)
    if driver is None or driver.client_id != client.id:
        raise HTTPException(status_code=404, detail="Driver not found")
    runtime_state = (
        await session.exec(
            select(DriverRuntimeState).where(DriverRuntimeState.client_id == client.id, DriverRuntimeState.driver_id == driver_id)
        )
    ).first()
    if runtime_state is None:
        raise HTTPException(status_code=404, detail="Driver runtime state not found")
    counters = await rpa_runtime.counter_snapshot(client.id, driver_id)
    return DriverRuntimeStateResponse(
        driver_id=driver_id,
        client_id=client.id,
        state=runtime_state.state,
        session_version=runtime_state.session_version,
        last_auth_at=runtime_state.last_auth_at,
        session_expires_at=runtime_state.session_expires_at,
        next_retry_at=runtime_state.next_retry_at,
        paused_until=runtime_state.paused_until,
        proxy_key=runtime_state.proxy_key,
        last_error_code=runtime_state.last_error_code,
        counters=DriverCounterSnapshotResponse(**counters.__dict__),
    )


@router.get("/scheduler/plan", response_model=list[SchedulerDecisionResponse])
async def get_scheduler_plan(client: Client = Depends(get_current_client)):
    decisions = await rpa_scheduler_service.plan_due_jobs(persist=False)
    return [SchedulerDecisionResponse(**decision.__dict__) for decision in decisions if decision.client_id == client.id]
