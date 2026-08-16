"""Scheduler and orchestration helpers for Phase 1 multi-tenant RPA."""

from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select

from app.core.business_time import business_date_str
from app.core.config import utcms_config
from app.core.database import async_session_factory
from app.core.error_taxonomy import ErrorCategory
from app.models_multitenant import Driver, DriverStatus, TaskSource, TaskStatus, WaybillJob
from app.models_rpa import DomainEvent, DriverDailyCounter, DriverRuntimeState, DriverRuntimeStateValue
from app.orchestrator.state_machine import JobStateMachine
from app.rpa.contracts import SchedulerDecision
from app.rpa.event_taxonomy import (
    DRIVER_LIMIT_REACHED,
    JOB_CREATED,
    JOB_QUEUED_AUTH,
    JOB_QUEUED_SUBMIT,
    JOB_WAITING_SUBMISSION_WINDOW,
)
from app.services.rpa_runtime_service import rpa_runtime
from app.services.night_submission_policy import clear_expired_night_attempts
from app.services.utcms_submission_gate import utcms_submission_gate
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
    async def create_job(
        self,
        client_id: int,
        driver: Driver,
        payload: dict[str, Any],
        source: TaskSource,
        max_retries: int,
        priority: int = 5,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> WaybillJob:
        async with async_session_factory() as session:
            normalized_key = build_job_idempotency_key(client_id, driver.id, payload, supplied=idempotency_key)
            existing = (
                await session.exec(
                    select(WaybillJob).where(
                        WaybillJob.client_id == client_id, WaybillJob.idempotency_key == normalized_key
                    )
                )
            ).first()
            if existing:
                logger.warning(
                    "duplicate_idempotency_key_rejected",
                    extra={"extra_fields": {"job_id": existing.job_id, "idempotency_key": normalized_key}},
                )
                return existing

            job = WaybillJob(
                job_id=f"job_{uuid.uuid4().hex[:16]}",
                idempotency_key=normalized_key,
                client_id=client_id,
                driver_id=driver.id,
                status=TaskStatus.PENDING.value,
                source=source.value,
                payload_json=payload,
                max_retries=max_retries,
                correlation_id=(correlation_id or f"corr_{uuid.uuid4().hex[:16]}"),
                business_date=business_date_str(),
                priority=priority,
                submit_after=_utcnow_naive(),
            )
            session.add(job)
            await self._ensure_runtime_state(session, client_id, driver.id)
            await self._record_event(
                session, client_id, driver.id, job.job_id, JOB_CREATED, {"priority": priority, "source": source.value}
            )
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                for attempt in range(5):
                    await asyncio.sleep(0.05 * (attempt + 1))
                    existing = (
                        await session.exec(
                            select(WaybillJob).where(
                                WaybillJob.client_id == client_id, WaybillJob.idempotency_key == normalized_key
                            )
                        )
                    ).first()
                    if existing:
                        logger.warning(
                            "concurrent_duplicate_idempotency_key_recovered",
                            extra={"extra_fields": {"job_id": existing.job_id, "idempotency_key": normalized_key}},
                        )
                        return existing
                raise
            await session.refresh(job)
            return job

    async def plan_due_jobs(self, *, persist: bool = True) -> list[SchedulerDecision]:
        async with async_session_factory() as session:
            # CRITICAL: Use SELECT FOR UPDATE SKIP LOCKED to prevent race conditions
            # when multiple scheduler instances (Beat + workers) run concurrently.
            # This ensures only one scheduler can pick up each job atomically.
            jobs = (
                await session.exec(
                    select(WaybillJob, Driver)
                    .join(Driver, Driver.id == WaybillJob.driver_id)
                    .where(
                        WaybillJob.schedule_id.is_(None),
                        col(WaybillJob.status).in_(
                            [
                                TaskStatus.PENDING.value,
                                TaskStatus.QUEUED.value,
                                TaskStatus.WAITING_RETRY.value,
                                TaskStatus.WAITING_AUTH.value,
                                TaskStatus.OTP_BACKOFF.value,
                                TaskStatus.WAITING_SUBMISSION_WINDOW.value,
                            ]
                        ),
                    )
                    .with_for_update(skip_locked=True)
                    .order_by(col(WaybillJob.priority).desc(), col(WaybillJob.created_at).asc())
                )
            ).all()

            decisions: list[SchedulerDecision] = []
            tenant_counts: dict[int, int] = defaultdict(int)
            tenant_limit = max(1, utcms_config.RPA_SCHEDULER_TENANT_SLICE)
            batch_limit = max(1, utcms_config.RPA_SCHEDULER_BATCH_SIZE)
            now = datetime.now(UTC).replace(tzinfo=None)

            # Check UTCMS Submission Gate state once per planning cycle
            is_gate_open = await utcms_submission_gate.is_submission_allowed()

            for job, driver in jobs:
                if len(decisions) >= batch_limit:
                    break
                if tenant_counts[job.client_id] >= tenant_limit:
                    continue
                if job.celery_task_id:
                    if job.status in {
                        TaskStatus.PENDING.value,
                        TaskStatus.WAITING_RETRY.value,
                        TaskStatus.OTP_BACKOFF.value,
                        TaskStatus.WAITING_SUBMISSION_WINDOW.value,
                    }:
                        job.celery_task_id = None
                    else:
                        continue

                try:
                    # ── OTP_BACKOFF / WAITING_SUBMISSION_WINDOW: only eligible after next_retry_at has passed ──
                    if job.status in {TaskStatus.OTP_BACKOFF.value, TaskStatus.WAITING_SUBMISSION_WINDOW.value}:
                        if job.next_retry_at is not None:
                            retry_at = _as_utc(job.next_retry_at)
                            if retry_at > now:
                                continue  # not yet due

                    submit_after = _as_utc(job.submit_after)
                    if submit_after and submit_after > now:
                        continue
                    if persist:
                        clear_expired_night_attempts(job)

                    counter = await rpa_runtime.counter_snapshot(job.client_id, driver.id)
                    if persist:
                        await self._upsert_counter_row(
                            session,
                            job.client_id,
                            driver.id,
                            counter.business_date,
                            counter.attempts,
                            counter.successes,
                        )
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
                            JobStateMachine.transition(
                                session,
                                job,
                                TaskStatus.WAITING_AUTH.value,
                                submit_after=now + timedelta(seconds=utcms_config.DRIVER_RETRY_DELAY_SECONDS),
                            )
                            session.add(driver)
                            session.add(runtime_state)
                            await self._record_event(
                                session,
                                job.client_id,
                                driver.id,
                                job.job_id,
                                JOB_QUEUED_AUTH,
                                {"reason": reason, "queue": queue_name},
                            )
                    else:
                        # Session is ready -> verify UTCMS Submission Gate before queuing for submit
                        if not is_gate_open:
                            if persist and job.status != TaskStatus.WAITING_SUBMISSION_WINDOW.value:
                                retry_at = now + timedelta(seconds=utcms_config.GATE_PROBE_INTERVAL_SECONDS)
                                driver.runtime_status = DriverStatus.READY.value
                                runtime_state.state = DriverRuntimeStateValue.WAITING_SUBMISSION_WINDOW.value
                                JobStateMachine.transition(
                                    session,
                                    job,
                                    TaskStatus.WAITING_SUBMISSION_WINDOW.value,
                                    submit_after=retry_at,
                                    next_retry_at=retry_at,
                                )
                                session.add(driver)
                                session.add(runtime_state)
                                await self._record_event(
                                    session,
                                    job.client_id,
                                    driver.id,
                                    job.job_id,
                                    JOB_WAITING_SUBMISSION_WINDOW,
                                    {"reason": "gate_closed_otp_active", "retry_at": retry_at.isoformat()},
                                )
                            continue

                        queue_name = utcms_config.RPA_SUBMIT_QUEUE
                        reason = "session_ready"
                        if persist:
                            driver.runtime_status = DriverStatus.READY.value
                            runtime_state.state = DriverRuntimeStateValue.READY.value
                            JobStateMachine.transition(session, job, TaskStatus.QUEUED.value)
                            session.add(driver)
                            session.add(runtime_state)
                            await self._record_event(
                                session,
                                job.client_id,
                                driver.id,
                                job.job_id,
                                JOB_QUEUED_SUBMIT,
                                {"reason": reason, "queue": queue_name},
                            )

                    tenant_counts[job.client_id] += 1
                    if persist:
                        job.updated_at = _utcnow_naive()
                        runtime_state.updated_at = _utcnow_naive()
                        job.business_date = counter.business_date
                    decisions.append(
                        SchedulerDecision(
                            job_id=job.job_id,
                            driver_id=driver.id,
                            client_id=job.client_id,
                            queue_name=queue_name,
                            reason=reason,
                            priority=job.priority,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.exception(
                        "plan_due_jobs_single_job_failed",
                        extra={"extra_fields": {"job_id": job.job_id, "error": str(exc)}},
                    )
                    continue

            if persist:
                await session.commit()
            return decisions

    async def cleanup_stuck_jobs(self) -> int:
        """Detect and recover jobs stuck in QUEUED, IN_PROGRESS, WAITING_AUTH, WAITING_RETRY, or OTP_BACKOFF status."""
        async with async_session_factory() as session:
            now = datetime.now(UTC).replace(tzinfo=None)
            queued_cutoff = now - timedelta(minutes=15)
            in_progress_cutoff = now - timedelta(minutes=30)
            waiting_auth_cutoff = now - timedelta(hours=1)
            waiting_retry_cutoff = now - timedelta(hours=1)
            otp_backoff_cutoff = now - timedelta(hours=2)

            # Find jobs stuck in various states with appropriate timeouts
            from sqlalchemy import or_

            stmt = select(WaybillJob).where(
                or_(
                    (WaybillJob.status == TaskStatus.QUEUED.value) & (WaybillJob.updated_at < queued_cutoff),
                    (WaybillJob.status == TaskStatus.IN_PROGRESS.value) & (WaybillJob.updated_at < in_progress_cutoff),
                    (WaybillJob.status == TaskStatus.WAITING_AUTH.value)
                    & (WaybillJob.updated_at < waiting_auth_cutoff),
                    (WaybillJob.status == TaskStatus.WAITING_RETRY.value)
                    & (WaybillJob.updated_at < waiting_retry_cutoff),
                    (WaybillJob.status == TaskStatus.OTP_BACKOFF.value) & (WaybillJob.updated_at < otp_backoff_cutoff),
                )
            )
            result = await session.exec(stmt)
            stuck_jobs = result.all()

            count = 0
            for job in stuck_jobs:
                # CRITICAL: Check if job was already successfully submitted to portal
                # by checking for tracking_code in result_json
                if job.result_json:
                    try:
                        result_data = job.result_json  # already deserialized by SQLAlchemy JSON/JSONB
                        if result_data.get("tracking_code"):
                            logger.warning(
                                "stuck_job_already_has_tracking_code_skipping_recovery",
                                extra={
                                    "extra_fields": {
                                        "job_id": job.job_id,
                                        "status": job.status,
                                        "tracking_code": result_data.get("tracking_code"),
                                    }
                                },
                            )
                            # Mark as SUCCESS to prevent future recovery attempts
                            JobStateMachine.transition(
                                session,
                                job,
                                TaskStatus.SUCCESS.value,
                                finished_at=_utcnow_naive(),
                                updated_at=_utcnow_naive(),
                            )
                            session.add(job)
                            continue
                    except json.JSONDecodeError as exc:
                        logger.debug(
                            "rpa_scheduler_result_json_corrupted",
                            extra={"extra_fields": {"job_id": job.job_id, "error": str(exc)}},
                        )

                old_status = job.status
                logger.warning(
                    "recovering_stuck_job",
                    extra={
                        "extra_fields": {
                            "job_id": job.job_id,
                            "old_status": old_status,
                            "last_updated": job.updated_at.isoformat(),
                        }
                    },
                )

                if old_status == TaskStatus.IN_PROGRESS.value:
                    # The worker may have failed after UTCMS accepted the submit.
                    # Never automatically resubmit an unknown external outcome.
                    JobStateMachine.transition(
                        session,
                        job,
                        TaskStatus.NEEDS_REVIEW.value,
                        error_category=ErrorCategory.SUBMISSION_UNCONFIRMED.value,
                        last_error="Worker lease expired; reconcile UTCMS before retrying",
                        finished_at=_utcnow_naive(),
                        updated_at=_utcnow_naive(),
                    )
                else:
                    JobStateMachine.transition(
                        session,
                        job,
                        TaskStatus.PENDING.value,
                        celery_task_id=None,
                        worker_id=None,
                    )
                    job.updated_at = _utcnow_naive()
                session.add(job)

                # Add log for visibility
                from app.models_multitenant import WaybillTaskLog

                session.add(
                    WaybillTaskLog(
                        job_id=job.job_id,
                        client_id=job.client_id,
                        step="recovery",
                        status=job.status,
                        message=(
                            "نتیجه ثبت در UTCMS نامشخص است؛ پیش از تلاش مجدد نیاز به بررسی دارد"
                            if job.status == TaskStatus.NEEDS_REVIEW.value
                            else f"تسک از وضعیت {old_status} بازیابی شد (عدم پاسخگویی کارگر/تایم‌اوت)"
                        ),
                    )
                )
                count += 1

            await session.commit()
            return count

    async def _ensure_runtime_state(self, session, client_id: int, driver_id: int) -> DriverRuntimeState:
        state = (
            await session.exec(select(DriverRuntimeState).where(DriverRuntimeState.driver_id == driver_id))
        ).first()
        if state is None:
            try:
                async with session.begin_nested():
                    state = DriverRuntimeState(client_id=client_id, driver_id=driver_id)
                    session.add(state)
                    await session.flush()
            except IntegrityError:
                state = (
                    await session.exec(select(DriverRuntimeState).where(DriverRuntimeState.driver_id == driver_id))
                ).first()
                if state is None:
                    raise
        elif state.client_id != client_id:
            # Self-heal: correct stale client_id that could have been written by an earlier bug
            logger.warning(
                "ensure_runtime_state_client_id_corrected",
                extra={
                    "extra_fields": {
                        "driver_id": driver_id,
                        "old_client_id": state.client_id,
                        "correct_client_id": client_id,
                    }
                },
            )
            state.client_id = client_id
            session.add(state)
            await session.flush()
        return state

    async def _mark_driver_daily_limit(self, session, driver: Driver, job: WaybillJob, reason: str) -> None:
        runtime_state = await self._ensure_runtime_state(session, job.client_id, driver.id)
        runtime_state.state = (
            DriverRuntimeStateValue.DAILY_SUCCESS_LIMIT_REACHED.value
            if "success" in reason
            else DriverRuntimeStateValue.DAILY_ATTEMPT_LIMIT_REACHED.value
        )
        runtime_state.updated_at = _utcnow_naive()
        driver.runtime_status = DriverStatus.DAILY_LIMIT_REACHED.value
        JobStateMachine.transition(
            session,
            job,
            TaskStatus.DAILY_LIMIT_REACHED.value,
            terminal_reason=reason,
            finished_at=_utcnow_naive(),
        )
        await self._record_event(
            session, job.client_id, driver.id, job.job_id, DRIVER_LIMIT_REACHED, {"reason": reason}
        )

    async def _upsert_counter_row(
        self, session, client_id: int, driver_id: int, business_date: str, attempts: int, successes: int
    ) -> None:
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

    async def _record_event(
        self, session, client_id: int, driver_id: int, job_id: str | None, event_type: str, payload: dict[str, Any]
    ) -> None:
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
