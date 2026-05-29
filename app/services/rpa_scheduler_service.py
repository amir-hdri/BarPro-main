"""Scheduler and orchestration helpers for Phase 1 multi-tenant RPA."""
from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlmodel import col, select

from app.core.business_time import business_date_str
from app.core.config import utcms_config
from app.core.database import async_session_factory
from app.models_multitenant import Driver, DriverStatus, TaskSource, TaskStatus, WaybillJob
from app.models_rpa import DomainEvent, DriverDailyCounter, DriverRuntimeState, DriverRuntimeStateValue
from app.rpa.contracts import SchedulerDecision
from app.rpa.event_taxonomy import DRIVER_LIMIT_REACHED, JOB_CREATED, JOB_QUEUED_AUTH, JOB_QUEUED_SUBMIT
from app.services.rpa_runtime_service import rpa_runtime
from app.services.rpa_submit_service import build_job_idempotency_key

logger = logging.getLogger(__name__)


def _utcnow_naive() -> datetime:
    """Return a naive UTC timestamp for database columns stored without timezone."""
    return datetime.now(UTC).replace(tzinfo=None)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    # Convert offset-aware to naive UTC for comparison
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


class RPASchedulerService:
    async def create_job(self, client_id: int, driver: Driver, payload: dict[str, Any], source: TaskSource, max_retries: int, priority: int = 5, correlation_id: str | None = None, idempotency_key: str | None = None) -> WaybillJob:
        session = async_session_factory()
        try:
            normalized_key = build_job_idempotency_key(client_id, driver.id, payload, supplied=idempotency_key)
            existing = (
                await session.exec(
                    select(WaybillJob).where(WaybillJob.client_id == client_id, WaybillJob.idempotency_key == normalized_key)
                )
            ).first()
            if existing:
                return existing

            job = WaybillJob(
                job_id=f"job_{uuid.uuid4().hex[:16]}",
                idempotency_key=normalized_key,
                client_id=client_id,
                driver_id=driver.id,
                status=TaskStatus.PENDING.value,
                source=source.value,
                payload_json=json.dumps(payload, ensure_ascii=False),
                max_retries=max_retries,
                correlation_id=(correlation_id or f"corr_{uuid.uuid4().hex[:16]}"),
                business_date=business_date_str(),
                priority=priority,
                submit_after=_utcnow_naive(),
            )
            session.add(job)
            await self._ensure_runtime_state(session, client_id, driver.id)
            await self._record_event(session, client_id, driver.id, job.job_id, JOB_CREATED, {"priority": priority, "source": source.value})
            await session.commit()
            await session.refresh(job)
            return job
        finally:
            await session.close()

    async def plan_due_jobs(self, *, persist: bool = True) -> list[SchedulerDecision]:
        session = async_session_factory()
        try:
            jobs = (
                await session.exec(
                    select(WaybillJob, Driver)
                    .join(Driver, Driver.id == WaybillJob.driver_id)
                    .where(col(WaybillJob.status).in_([
                        TaskStatus.PENDING.value,
                        TaskStatus.QUEUED.value,
                        TaskStatus.WAITING_RETRY.value,
                        TaskStatus.WAITING_AUTH.value,
                        TaskStatus.OTP_BACKOFF.value,
                    ]))
                    .order_by(col(WaybillJob.priority).desc(), col(WaybillJob.created_at).asc())
                )
            ).all()

            decisions: list[SchedulerDecision] = []
            tenant_counts: dict[int, int] = defaultdict(int)
            tenant_limit = max(1, utcms_config.RPA_SCHEDULER_TENANT_SLICE)
            batch_limit = max(1, utcms_config.RPA_SCHEDULER_BATCH_SIZE)
            now = datetime.now(UTC).replace(tzinfo=None)

            for job, driver in jobs:
                if len(decisions) >= batch_limit:
                    break
                if tenant_counts[job.client_id] >= tenant_limit:
                    continue
                if job.celery_task_id:
                    continue

                # ── OTP_BACKOFF: only eligible after next_retry_at has passed ──
                if job.status == TaskStatus.OTP_BACKOFF.value:
                    if job.next_retry_at is None:
                        continue  # no retry time set, skip
                    retry_at = _as_utc(job.next_retry_at)
                    if retry_at > now:
                        continue  # not yet due

                submit_after = _as_utc(job.submit_after)
                if submit_after and submit_after > now:
                    continue

                counter = await rpa_runtime.counter_snapshot(job.client_id, driver.id)
                if persist:
                    await self._upsert_counter_row(session, job.client_id, driver.id, counter.business_date, counter.attempts, counter.successes)
                if counter.successes >= utcms_config.DRIVER_DAILY_SUCCESS_CAP:
                    if persist:
                        await self._mark_driver_daily_limit(session, driver, job, "daily_success_limit_reached")
                    continue
                if counter.attempts >= utcms_config.DRIVER_DAILY_ATTEMPT_CAP:
                    if persist:
                        await self._mark_driver_daily_limit(session, driver, job, "daily_attempt_limit_reached")
                    continue
                if await rpa_runtime.cooldown_active("tenant", str(job.client_id)):
                    continue

                runtime_state = await self._ensure_runtime_state(session, job.client_id, driver.id)
                next_retry_at = _as_utc(runtime_state.next_retry_at)
                if next_retry_at and next_retry_at > now:
                    continue
                paused_until = _as_utc(runtime_state.paused_until)
                if paused_until and paused_until > now:
                    continue

                bundle = await rpa_runtime.get_session(job.client_id, driver.id)
                if bundle is None:
                    queue_name = utcms_config.RPA_AUTH_QUEUE
                    reason = "auth_required"
                    if persist:
                        driver.runtime_status = DriverStatus.AUTH_REQUIRED.value
                        runtime_state.state = DriverRuntimeStateValue.AUTH_REQUIRED.value
                        job.status = TaskStatus.WAITING_AUTH.value
                        await self._record_event(session, job.client_id, driver.id, job.job_id, JOB_QUEUED_AUTH, {"reason": reason, "queue": queue_name})
                else:
                    queue_name = utcms_config.RPA_SUBMIT_QUEUE
                    reason = "session_ready"
                    if persist:
                        driver.runtime_status = DriverStatus.READY.value
                        runtime_state.state = DriverRuntimeStateValue.READY.value
                        job.status = TaskStatus.QUEUED.value
                        await self._record_event(session, job.client_id, driver.id, job.job_id, JOB_QUEUED_SUBMIT, {"reason": reason, "queue": queue_name})

                tenant_counts[job.client_id] += 1
                if persist:
                    job.updated_at = _utcnow_naive()
                    runtime_state.updated_at = _utcnow_naive()
                    job.business_date = counter.business_date
                decisions.append(SchedulerDecision(job_id=job.job_id, driver_id=driver.id, client_id=job.client_id, queue_name=queue_name, reason=reason, priority=job.priority))

            if persist:
                await session.commit()
            return decisions
        finally:
            await session.close()

    async def _ensure_runtime_state(self, session, client_id: int, driver_id: int) -> DriverRuntimeState:
        state = (await session.exec(select(DriverRuntimeState).where(DriverRuntimeState.driver_id == driver_id))).first()
        if state is None:
            state = DriverRuntimeState(client_id=client_id, driver_id=driver_id)
            session.add(state)
            await session.flush()
        return state

    async def _mark_driver_daily_limit(self, session, driver: Driver, job: WaybillJob, reason: str) -> None:
        runtime_state = await self._ensure_runtime_state(session, job.client_id, driver.id)
        runtime_state.state = DriverRuntimeStateValue.DAILY_SUCCESS_LIMIT_REACHED.value if "success" in reason else DriverRuntimeStateValue.DAILY_ATTEMPT_LIMIT_REACHED.value
        runtime_state.updated_at = _utcnow_naive()
        driver.runtime_status = DriverStatus.DAILY_LIMIT_REACHED.value
        job.status = TaskStatus.DAILY_LIMIT_REACHED.value
        job.terminal_reason = reason
        job.finished_at = _utcnow_naive()
        await self._record_event(session, job.client_id, driver.id, job.job_id, DRIVER_LIMIT_REACHED, {"reason": reason})

    async def _upsert_counter_row(self, session, client_id: int, driver_id: int, business_date: str, attempts: int, successes: int) -> None:
        row = (
            await session.exec(
                select(DriverDailyCounter).where(
                    DriverDailyCounter.client_id == client_id,
                    DriverDailyCounter.driver_id == driver_id,
                    DriverDailyCounter.business_date == business_date,
                )
            )
        ).first()
        if row is None:
            row = DriverDailyCounter(client_id=client_id, driver_id=driver_id, business_date=business_date)
            session.add(row)
        row.attempts = attempts
        row.successes = successes
        row.updated_at = _utcnow_naive()

    async def _record_event(self, session, client_id: int, driver_id: int, job_id: str | None, event_type: str, payload: dict[str, Any]) -> None:
        session.add(
            DomainEvent(
                event_id=f"evt_{uuid.uuid4().hex[:24]}",
                event_type=event_type,
                client_id=client_id,
                driver_id=driver_id,
                job_id=job_id,
                payload_json=json.dumps(payload, ensure_ascii=False),
            )
        )


rpa_scheduler_service = RPASchedulerService()
