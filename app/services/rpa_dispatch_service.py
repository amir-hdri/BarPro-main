"""Shared dispatch facade for manual retries and scheduler-driven queueing."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import utcms_config
from app.core.database import async_session_factory
from app.models_multitenant import TaskStatus, WaybillJob, WaybillTaskLog
from app.models_rpa import DomainEvent
from app.rpa.contracts import SchedulerDecision
from app.rpa.event_taxonomy import JOB_DISPATCH_FAILED, JOB_DISPATCH_SKIPPED, JOB_DISPATCHED
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


class RPADispatchService:
    async def dispatch_waybill_job_now(
        self,
        session: AsyncSession,
        job: WaybillJob,
        requested_at: datetime,
    ) -> str:
        if celery_app is None:
            await self._record_dispatch_state(
                session,
                job,
                JOB_DISPATCH_SKIPPED,
                "dispatch_skipped",
                "pending",
                "Celery is unavailable, job remains pending for scheduler pickup",
                {"requested_at": requested_at.isoformat(), "reason": "celery_unavailable"},
            )
            return "celery_unavailable"

        try:
            from app.core.circuit_breaker import get_routed_queue
            routed_queue = get_routed_queue("waybill_tasks")
            result = celery_app.send_task(
                "waybill.process_job",
                args=[job.job_id],
                queue=routed_queue,
            )
            job.status = TaskStatus.QUEUED.value
            job.submit_after = requested_at
            job.updated_at = datetime.now(UTC).replace(tzinfo=None)
            job.celery_task_id = getattr(result, "id", None)
            session.add(job)
            await self._record_dispatch_state(
                session,
                job,
                JOB_DISPATCHED,
                "dispatch_now",
                "queued",
                "Job dispatched to worker immediately",
                {
                    "requested_at": requested_at.isoformat(),
                    "queue": routed_queue,
                    "celery_task_id": job.celery_task_id,
                },
            )
            return "queued"
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "dispatch_waybill_job_now_failed", extra={"extra_fields": {"job_id": job.job_id, "error": str(exc)}}
            )
            await self._record_dispatch_state(
                session,
                job,
                JOB_DISPATCH_FAILED,
                "dispatch_failed",
                "pending",
                "Immediate worker dispatch failed; scheduler will retry pickup",
                {"requested_at": requested_at.isoformat(), "error": str(exc)},
            )
            return str(exc)

    async def dispatch_phase1_due_jobs(self) -> list[dict[str, Any]]:
        from app.services.rpa_scheduler_service import rpa_scheduler_service

        decisions = await rpa_scheduler_service.plan_due_jobs()
        return await self.dispatch_phase1_decisions(decisions)

    async def dispatch_phase1_decisions(
        self,
        decisions: Iterable[SchedulerDecision],
    ) -> list[dict[str, Any]]:
        session = async_session_factory()
        dispatched: list[dict[str, Any]] = []
        try:
            for decision in decisions:
                job = (
                    await session.exec(
                        select(WaybillJob).where(
                            WaybillJob.job_id == decision.job_id,
                            WaybillJob.client_id == decision.client_id,
                        )
                    )
                ).first()
                if job is None:
                    dispatched.append(
                        {
                            "job_id": decision.job_id,
                            "queue_name": decision.queue_name,
                            "status": "missing",
                        }
                    )
                    continue

                result = await self._dispatch_phase1_task(
                    session=session,
                    job=job,
                    queue_name=decision.queue_name,
                    requested_at=datetime.now(UTC).replace(tzinfo=None),
                    reason=decision.reason,
                    source="scheduler",
                )
                dispatched.append(result)
            return dispatched
        finally:
            await session.close()

    async def dispatch_phase1_submit_now(
        self,
        session: AsyncSession,
        job: WaybillJob,
        requested_at: datetime,
        reason: str,
    ) -> dict[str, Any]:
        return await self._dispatch_phase1_task(
            session=session,
            job=job,
            queue_name=utcms_config.RPA_SUBMIT_QUEUE,
            requested_at=requested_at,
            reason=reason,
            source="auth_followup",
        )

    async def _dispatch_phase1_task(
        self,
        session: AsyncSession,
        job: WaybillJob,
        queue_name: str,
        requested_at: datetime,
        reason: str,
        source: str,
    ) -> dict[str, Any]:
        task_name, args, step = self._phase1_task_spec(job, queue_name, reason)
        payload = {
            "requested_at": requested_at.isoformat(),
            "queue": queue_name,
            "task_name": task_name,
            "reason": reason,
            "source": source,
        }

        if celery_app is None:
            job.celery_task_id = None
            session.add(job)
            await self._record_dispatch_state(
                session,
                job,
                JOB_DISPATCH_SKIPPED,
                step,
                job.status,
                "Phase 1 dispatch skipped because Celery is unavailable",
                {**payload, "status": "skipped", "dispatch_reason": "celery_unavailable"},
            )
            return {"job_id": job.job_id, "queue_name": queue_name, "status": "skipped"}

        try:
            from app.core.circuit_breaker import get_routed_queue
            routed_queue = get_routed_queue(queue_name)
            result = celery_app.send_task(task_name, args=args, queue=routed_queue)
            job.celery_task_id = getattr(result, "id", None)
            job.updated_at = datetime.now(UTC).replace(tzinfo=None)
            session.add(job)
            await self._record_dispatch_state(
                session,
                job,
                JOB_DISPATCHED,
                step,
                "queued",
                "Phase 1 job dispatched",
                {**payload, "status": "queued", "queue": routed_queue, "celery_task_id": job.celery_task_id},
            )
            return {
                "job_id": job.job_id,
                "queue_name": routed_queue,
                "task_name": task_name,
                "status": "queued",
                "celery_task_id": job.celery_task_id,
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "dispatch_phase1_task_failed",
                extra={"extra_fields": {"job_id": job.job_id, "queue": queue_name, "error": str(exc)}},
            )
            job.celery_task_id = None
            session.add(job)
            await self._record_dispatch_state(
                session,
                job,
                JOB_DISPATCH_FAILED,
                step,
                job.status,
                "Phase 1 dispatch failed",
                {**payload, "status": "failed", "error": str(exc)},
            )
            return {
                "job_id": job.job_id,
                "queue_name": queue_name,
                "task_name": task_name,
                "status": "failed",
                "error": str(exc),
            }

    def _phase1_task_spec(self, job: WaybillJob, queue_name: str, reason: str) -> tuple[str, list[Any], str]:
        if queue_name == utcms_config.RPA_AUTH_QUEUE:
            return (
                "phase1.auth.process",
                [job.client_id, job.driver_id, reason, job.job_id],
                "queued_auth",
            )
        if queue_name == utcms_config.RPA_SUBMIT_QUEUE:
            return (
                "phase1.submit.process",
                [job.client_id, job.job_id],
                "queued_submit",
            )
        raise ValueError(f"Unsupported Phase 1 queue: {queue_name}")

    async def _record_dispatch_state(
        self,
        session: AsyncSession,
        job: WaybillJob,
        event_type: str,
        step: str,
        status: str,
        message: str,
        payload: dict,
    ) -> None:
        session.add(
            DomainEvent(
                event_id=f"evt_dispatch_{uuid.uuid4().hex[:24]}",
                event_type=event_type,
                client_id=job.client_id,
                driver_id=job.driver_id,
                job_id=job.job_id,
                payload_json=json.dumps(payload, ensure_ascii=False),
            )
        )
        session.add(
            WaybillTaskLog(
                job_id=job.job_id,
                client_id=job.client_id,
                step=step,
                status=status,
                message=message,
                details_json=json.dumps(payload, ensure_ascii=False),
            )
        )
        await session.commit()


rpa_dispatch_service = RPADispatchService()
