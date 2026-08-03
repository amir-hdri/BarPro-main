"""Utilities for isolating a live RPA run from stale queue/lock state."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logging import monitoring_extra
from app.models_multitenant import TaskStatus, WaybillJob
from app.models_rpa import DriverRuntimeState, DriverRuntimeStateValue
from app.orchestrator.state_machine import JobStateMachine
from app.services.rpa_runtime_service import rpa_runtime

logger = logging.getLogger(__name__)


async def prepare_live_run_isolation(
    *,
    client_id: int,
    driver_id: int,
    session: AsyncSession | None = None,
    job: WaybillJob,
    runtime_state: DriverRuntimeState | None = None,
) -> dict[str, Any]:
    """Clear stale queue/lock markers before an inline/live submit run."""
    released_locks: list[str] = []
    # Get tokens from ContextVar to pass to force_release_lock for ownership verification
    lock_tokens = rpa_runtime._lock_tokens.get() or {}
    
    for lock_key in (
        rpa_runtime.auth_lock_key(client_id, driver_id),
        rpa_runtime.submit_lock_key(client_id, driver_id),
    ):
        # Pass the token if available for this lock key (ownership verification)
        token = lock_tokens.get(lock_key)
        await rpa_runtime.force_release_lock(lock_key, token)
        released_locks.append(lock_key)

    previous = {
        "job_status": job.status,
        "celery_task_id": job.celery_task_id,
        "worker_id": job.worker_id,
        "submit_after": job.submit_after.isoformat() if job.submit_after else None,
        "next_retry_at": job.next_retry_at.isoformat() if job.next_retry_at else None,
        "runtime_state": runtime_state.state if runtime_state else None,
    }

    now = datetime.now(UTC).replace(tzinfo=None)
    job.celery_task_id = None
    job.worker_id = None
    job.started_at = None
    job.finished_at = None
    job.submit_after = now
    job.next_retry_at = None
    job.updated_at = now
    if job.status in {
        TaskStatus.QUEUED.value,
        TaskStatus.IN_PROGRESS.value,
        TaskStatus.WAITING_AUTH.value,
        TaskStatus.WAITING_RETRY.value,
        TaskStatus.OTP_BACKOFF.value,
    }:
        JobStateMachine.transition(
            session,
            job,
            TaskStatus.PENDING.value,
            expected_from={
                TaskStatus.QUEUED.value,
                TaskStatus.IN_PROGRESS.value,
                TaskStatus.WAITING_AUTH.value,
                TaskStatus.WAITING_RETRY.value,
                TaskStatus.OTP_BACKOFF.value,
            },
        )

    if runtime_state is not None:
        runtime_state.next_retry_at = None
        runtime_state.updated_at = now
        if runtime_state.state in {
            DriverRuntimeStateValue.WAITING_RETRY.value,
            DriverRuntimeStateValue.AUTH_IN_PROGRESS.value,
            DriverRuntimeStateValue.SUBMITTING.value,
        }:
            runtime_state.state = DriverRuntimeStateValue.READY.value

    result = {
        "released_locks": released_locks,
        "previous": previous,
        "job_status": job.status,
        "runtime_state": runtime_state.state if runtime_state else None,
    }
    logger.info(
        "live_run_isolation_prepared",
        extra=monitoring_extra(
            "live_run_isolation_prepared",
            category="queue_isolation",
            payload=result,
            tags={"client_id": client_id, "driver_id": driver_id, "job_id": job.job_id},
            client_id=client_id,
            driver_id=driver_id,
            job_id=job.job_id,
            **result,
        ),
    )
    return result
