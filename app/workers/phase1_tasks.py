"""Celery tasks for Phase 1 hybrid auth/submit orchestration."""
from __future__ import annotations

import asyncio
import atexit
import logging

from app.services.rpa_auth_service import rpa_auth_service
from app.services.rpa_dispatch_service import rpa_dispatch_service
from app.services.rpa_submit_service import rpa_submit_service
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()


if celery_app is not None:
    @celery_app.task(name="phase1.scheduler.plan")
    def plan_phase1_jobs():
        return _run(rpa_dispatch_service.dispatch_phase1_due_jobs())


    @celery_app.task(name="phase1.scheduler.cleanup")
    def cleanup_phase1_jobs():
        from app.services.rpa_scheduler_service import rpa_scheduler_service
        return _run(rpa_scheduler_service.cleanup_stuck_jobs())


    @celery_app.task(name="phase1.auth.process")
    def process_phase1_auth(client_id: int, driver_id: int, reason: str, resume_job_id: str | None = None):
        result = _run(rpa_auth_service.authenticate_driver(client_id, driver_id, reason, resume_job_id=resume_job_id))
        return {
            "ok": result.ok,
            "reason_code": result.reason_code,
            "expires_at": result.expires_at.isoformat() if result.expires_at else None,
            "session_version": result.session_bundle.session_version if result.session_bundle else None,
        }


    @celery_app.task(name="phase1.submit.process")
    def process_phase1_submit(client_id: int, job_id: str):
        result = _run(rpa_submit_service.process_job(client_id, job_id))
        return {
            "outcome": result.classification.outcome.value,
            "reason_code": result.classification.reason_code,
            "http_status": result.classification.http_status,
            "latency_ms": result.latency_ms,
        }


# ==================== SCHEDULED WAYBILL EXECUTION TASKS ====================
from app.services.scheduled_waybill_executor import (
    clear_expired_waiting_jobs,
    evaluate_and_run_schedules,
    retry_failed_scheduled_jobs,
)

if celery_app is not None:
    @celery_app.task(
        name="scheduled.waybill.evaluate_and_run",
        queue="scheduled_tasks",
        soft_time_limit=300,
        time_limit=600,
    )
    def evaluate_and_run_scheduled_waybills():
        """Evaluate all active schedules and execute due ones."""
        try:
            result = _run(evaluate_and_run_schedules())
            logger.info(
                "scheduled_waybill_evaluation_complete",
                extra={"extra_fields": result},
            )
            return result
        except Exception:
            logger.exception("evaluate_and_run_scheduled_waybills_failed")
            raise

    @celery_app.task(
        name="scheduled.waybill.retry_failed",
        queue="scheduled_tasks",
        soft_time_limit=300,
        time_limit=600,
    )
    def retry_failed_scheduled_jobs_task():
        """Retry jobs stuck in WAITING_RETRY that are now eligible."""
        try:
            result = _run(retry_failed_scheduled_jobs())
            logger.info(
                "scheduled_waybill_retry_complete",
                extra={"extra_fields": result},
            )
            return result
        except Exception:
            logger.exception("retry_failed_scheduled_jobs_failed")
            raise

    @celery_app.task(
        name="scheduled.waybill.clear_expired",
        queue="scheduled_tasks",
        soft_time_limit=120,
        time_limit=300,
    )
    def clear_expired_waiting_jobs_task():
        """Mark stuck WAITING_RETRY jobs for review."""
        try:
            result = _run(clear_expired_waiting_jobs())
            logger.info(
                "scheduled_waybill_clear_expired_complete",
                extra={"extra_fields": result},
            )
            return result
        except Exception:
            logger.exception("clear_expired_waiting_jobs_failed")
            raise

    @celery_app.task(
        name="scheduled.waybill.run_job",
        queue="scheduled_tasks",
        soft_time_limit=300,
        time_limit=600,
    )
    def run_scheduled_job(job_id: int):
        """Execute a single scheduled waybill job on worker."""
        try:
            from app.services.scheduled_waybill_executor import execute_scheduled_job_by_id
            result = _run(execute_scheduled_job_by_id(job_id))
            logger.info(
                "scheduled_waybill_execution_complete",
                extra={"extra_fields": {"job_id": job_id, "result": result}},
            )
            return result
        except Exception:
            logger.exception(f"run_scheduled_job_failed_for_job_{job_id}")
            raise

