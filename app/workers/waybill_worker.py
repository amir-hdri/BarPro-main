"""
Celery worker for processing waybill jobs in the multi-tenant system.

This worker:
1. Picks up pending waybill jobs from the queue
2. Executes the RPA bot for each job
3. Updates job status and logs in real-time
4. Handles retries and error categorization (including OTP_BACKOFF)
"""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from celery import Task
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth_multitenant import decrypt_driver_password
from app.automation.browser import browser_manager, managed_browser_session
from app.automation.waybill_bot_multitenant import WaybillAutomationBot
from app.automation.worker_proxy import get_playwright_proxy
from app.core.config import utcms_config
from app.core.database import async_session_factory
from app.core.utils import run_async as _run
from app.models_multitenant import (
    Driver,
    TaskStatus,
    WaybillJob,
    WaybillTaskLog,
)
from app.models_rpa import DomainEvent, DriverRuntimeState, DriverRuntimeStateValue
from app.rpa.event_taxonomy import (
    JOB_EXECUTION_FAILED,
    JOB_EXECUTION_STARTED,
    JOB_EXECUTION_SUCCEEDED,
    JOB_RETRY_SCHEDULED,
    OTP_DETECTED,
)
from app.services.rpa_runtime_service import rpa_runtime
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _utcnow_naive() -> datetime:
    """Return a naive UTC timestamp for database columns stored without timezone."""
    return datetime.now(UTC).replace(tzinfo=None)


def _safe_json(raw: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def _close_page_quickly(page) -> None:
    try:
        await asyncio.wait_for(page.close(), timeout=2.5)
    except Exception as exc:
        logger.warning("worker_page_close_skipped", extra={"extra_fields": {"error": str(exc)}})


class WaybillTask(Task):
    """Base task for waybill processing with common utilities."""

    autoretry_for = (ConnectionError, TimeoutError, OSError, IOError)
    max_retries = utcms_config.CELERY_MAX_RETRIES
    retry_backoff = True
    retry_backoff_max = 300
    retry_jitter = True

    async def get_async_session(self) -> AsyncSession:
        """Get async database session."""
        return async_session_factory()


@celery_app.task(
    bind=True,
    base=WaybillTask,
    name="waybill.process_job",
    queue="waybill_tasks",
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_waybill_job(self, job_id: str):
    """
    Process a single waybill job.

    Uses a persistent event loop per worker process.
    This eliminates the 'Future attached to a different loop' error by reusing
    the same event loop for all tasks executed in this worker process.
    """
    try:
        result = _run(_execute_job(self, job_id))
        return result
    except Exception as e:
        logger.error(f"Job {job_id} failed with exception: {e}", exc_info=True)
        from app.core.circuit_breaker import check_and_report_failure

        try:
            _run(check_and_report_failure(str(e)))
        except Exception as cb_err:
            logger.warning("circuit_breaker_report_failed", extra={"extra_fields": {"error": str(cb_err)}})
        try:
            _run(_update_job_status(job_id, TaskStatus.NEEDS_REVIEW.value, str(e), "submission_unknown"))
        except Exception as db_err:
            logger.error("update_job_status_failed", extra={"extra_fields": {"error": str(db_err)}})
        raise


async def _execute_job(task, job_id: str) -> dict[str, Any]:
    """Execute a waybill job with full lifecycle management."""
    session = async_session_factory()
    job: WaybillJob | None = None
    driver_lock_acquired = False

    try:
        statement = select(WaybillJob).where(WaybillJob.job_id == job_id).with_for_update()
        result = await session.exec(statement)
        job = result.first()

        if not job:
            logger.error(f"Job {job_id} not found in database")
            return {"status": "failed", "error": "Job not found"}

        existing_result = _safe_json(job.result_json)
        if existing_result.get("tracking_code"):
            logger.info("Skipping already completed waybill job %s", job_id)
            return {"status": TaskStatus.SUCCESS.value, "result": existing_result, "reused": True}
        if job.status == TaskStatus.SUCCESS.value:
            job.status = TaskStatus.NEEDS_REVIEW.value
            job.error_category = "submission_unconfirmed"
            job.last_error = "Success state has no UTCMS tracking code"
            job.updated_at = _utcnow_naive()
            await session.commit()
            logger.warning("Waybill job %s has success status without tracking code", job_id)
            return {"status": TaskStatus.NEEDS_REVIEW.value, "skipped": True}
        allowed_statuses = {
            TaskStatus.PENDING.value,
            TaskStatus.QUEUED.value,
            TaskStatus.WAITING_RETRY.value,
            TaskStatus.RETRYING.value,
            TaskStatus.OTP_BACKOFF.value,
        }
        if job.status not in allowed_statuses:
            # Allow reclaiming IN_PROGRESS jobs if stuck for > 5 minutes (worker lost/requeued)
            stale_threshold = _utcnow_naive() - timedelta(minutes=5)
            if job.status == TaskStatus.IN_PROGRESS.value and job.updated_at and job.updated_at < stale_threshold:
                logger.warning(f"Reclaiming stuck IN_PROGRESS job {job_id} (last updated {job.updated_at.isoformat()})")
            else:
                logger.info("Skipping waybill job %s in non-claimable status %s", job_id, job.status)
                return {"status": job.status, "skipped": True}

        runtime_state = await _get_or_create_runtime_state(session, job.client_id, job.driver_id)

        job.status = TaskStatus.IN_PROGRESS.value
        job.started_at = _utcnow_naive()
        job.attempt_count += 1
        job.worker_id = task.request.hostname
        job.updated_at = _utcnow_naive()
        job.submit_after = None
        runtime_state.state = DriverRuntimeStateValue.SUBMITTING.value
        runtime_state.updated_at = datetime.now(UTC).replace(tzinfo=None)
        await session.commit()

        await _add_job_log(
            session=session,
            job_id=job_id,
            client_id=job.client_id,
            step="start",
            status="success",
            message=f"Job started, attempt {job.attempt_count}",
        )
        await _record_event(
            session=session,
            client_id=job.client_id,
            driver_id=job.driver_id,
            job_id=job.job_id,
            event_type=JOB_EXECUTION_STARTED,
            payload={"attempt": job.attempt_count, "worker_id": job.worker_id},
        )

        driver = await session.get(Driver, job.driver_id)
        if not driver or driver.client_id != job.client_id:
            raise ValueError(f"Driver {job.driver_id} not found")

        driver_lock_key = rpa_runtime.submit_lock_key(job.client_id, driver.id)
        driver_lock_acquired = await rpa_runtime.acquire_lock(driver_lock_key, utcms_config.RPA_LOCK_TTL_SECONDS)
        if not driver_lock_acquired:
            retry_at = _utcnow_naive() + timedelta(seconds=utcms_config.DRIVER_RETRY_DELAY_SECONDS)
            job.status = TaskStatus.WAITING_RETRY.value
            job.celery_task_id = None
            job.retryable = True
            job.next_retry_at = retry_at
            job.submit_after = retry_at
            job.last_error = "Another waybill submission is already running for this driver"
            job.error_category = "driver_submission_in_progress"
            job.updated_at = _utcnow_naive()
            await session.commit()
            return {"status": TaskStatus.WAITING_RETRY.value, "next_retry_at": retry_at.isoformat()}

        username = driver.utcms_username
        password = decrypt_driver_password(driver.utcms_password_encrypted)
        payload = json.loads(job.payload_json)

        from app.services.session_vault import session_vault

        auth_state_path = session_vault.auth_state_path_for_account(
            username=username,
            national_code=driver.driver_national_code,
            fallback=username,
            scope=f"client-{job.client_id}-driver-{driver.id}",
        )
        # Use simple worker proxy helper — bypasses proxy_rotator's cooldown/geo-check
        # that could return None, leaving Chromium without proxy → navigation timeout.
        proxy_dict = get_playwright_proxy()
        async with managed_browser_session(auth_state_path=auth_state_path, proxy_dict=proxy_dict) as (
            _session_id,
            context,
        ):
            page = await browser_manager.new_page(context)

            try:
                bot = WaybillAutomationBot(page, context)
                job_timeout = getattr(utcms_config, "JOB_TIMEOUT_SECONDS", 240)
                try:
                    result = await asyncio.wait_for(
                        bot.execute_waybill_job(
                            username=username,
                            password=password,
                            payload=payload,
                            job_id=job_id,
                            client_id=job.client_id,
                            auth_state_path=auth_state_path,
                        ),
                        timeout=float(job_timeout),
                    )
                except TimeoutError:
                    logger.warning(f"Job {job_id} automation execution timed out after {job_timeout} seconds")
                    result = {
                        "status": "failed",
                        "error": f"Execution timed out after {job_timeout}s",
                        "error_category": "system_error",
                    }

                result_status = str(result.get("status", "")).strip().lower()
                now = _utcnow_naive()

                if result_status == "otp_backoff":
                    retry_minutes = int(result.get("next_retry_at_minutes_add", 60))
                    retry_at = now + timedelta(minutes=retry_minutes)
                    job.status = TaskStatus.OTP_BACKOFF.value
                    job.celery_task_id = None
                    job.next_retry_at = retry_at
                    job.submit_after = retry_at
                    job.last_error = result.get("message", "OTP challenge detected")
                    job.error_category = "otp_required"
                    job.finished_at = now
                    runtime_state.state = DriverRuntimeStateValue.WAITING_RETRY.value
                    runtime_state.next_retry_at = retry_at
                    runtime_state.updated_at = datetime.now(UTC).replace(tzinfo=None)
                    await session.commit()

                    await _add_job_log(
                        session=session,
                        job_id=job_id,
                        client_id=job.client_id,
                        step="otp_backoff",
                        status="waiting_retry",
                        message=f"OTP detected. Retrying in {retry_minutes} minutes.",
                        details_json=json.dumps(result, ensure_ascii=False),
                    )
                    await _record_event(
                        session=session,
                        client_id=job.client_id,
                        driver_id=job.driver_id,
                        job_id=job.job_id,
                        event_type=OTP_DETECTED,
                        payload={"retry_at": retry_at.isoformat(), "message": job.last_error},
                    )

                    logger.info(f"Job {job_id} entered OTP_BACKOFF, retry at {job.next_retry_at}")
                    return result

                if result_status == TaskStatus.SUCCESS.value:
                    result_payload = result.get("result")
                    tracking_code = result_payload.get("tracking_code") if isinstance(result_payload, dict) else None
                    if not tracking_code:
                        result_status = TaskStatus.FAILED.value
                        result["status"] = TaskStatus.FAILED.value
                        result["error"] = "Portal success response did not include a tracking code"
                        result["error_category"] = "submission_unconfirmed"
                    else:
                        job.status = TaskStatus.SUCCESS.value
                        job.result_json = json.dumps(result_payload, ensure_ascii=False)
                        job.finished_at = now
                        job.last_error = None
                        job.error_category = None
                        job.retryable = False
                        job.next_retry_at = None
                        runtime_state.state = DriverRuntimeStateValue.READY.value
                        runtime_state.next_retry_at = None
                        runtime_state.updated_at = datetime.now(UTC).replace(tzinfo=None)
                        await session.commit()

                        await _add_job_log(
                            session=session,
                            job_id=job_id,
                            client_id=job.client_id,
                            step="complete",
                            status="success",
                            message="Waybill registered successfully",
                            details_json=json.dumps(result_payload, ensure_ascii=False),
                        )
                        await _record_event(
                            session=session,
                            client_id=job.client_id,
                            driver_id=job.driver_id,
                            job_id=job.job_id,
                            event_type=JOB_EXECUTION_SUCCEEDED,
                            payload={"attempt": job.attempt_count, "tracking_code": tracking_code},
                        )

                        logger.info(f"Job {job_id} completed successfully")
                        await browser_manager.record_success_for_recycle()
                        return result

                job.last_error = result.get("error", "Unknown error")
                status_hint = str(result.get("status", "")).strip().lower()
                error_cat_raw = str(result.get("error_category", "")).lower()
                error_msg_raw = job.last_error.lower()

                if "login" in error_cat_raw or "login" in error_msg_raw or "auth" in error_cat_raw:
                    job.error_category = "login_failed"
                elif "driver" in error_cat_raw or "driver" in error_msg_raw:
                    job.error_category = "invalid_driver"
                elif "form" in error_cat_raw or "validation" in error_cat_raw or "incomplete" in error_msg_raw:
                    job.error_category = "incomplete_data"
                elif "network" in error_cat_raw or "timeout" in error_cat_raw or "system" in error_cat_raw:
                    job.error_category = "system_error"
                elif "service" in error_cat_raw or "api" in error_cat_raw or "destination" in error_msg_raw:
                    job.error_category = "destination_error"
                elif status_hint in {"captcha_failed", "captcha-failed", "captchafailed"}:
                    job.error_category = "captcha_failed"
                else:
                    job.error_category = result.get("error_category", "unknown")

                if job.attempt_count < job.max_retries and _is_retryable(result):
                    retry_at = now + timedelta(seconds=utcms_config.DRIVER_RETRY_DELAY_SECONDS)
                    job.status = TaskStatus.WAITING_RETRY.value
                    job.celery_task_id = None
                    job.retryable = True
                    job.next_retry_at = retry_at
                    job.submit_after = retry_at
                    job.finished_at = None
                    runtime_state.state = DriverRuntimeStateValue.WAITING_RETRY.value
                    runtime_state.next_retry_at = retry_at
                    runtime_state.updated_at = datetime.now(UTC).replace(tzinfo=None)
                    await session.commit()

                    await _add_job_log(
                        session=session,
                        job_id=job_id,
                        client_id=job.client_id,
                        step="retry_scheduled",
                        status="waiting_retry",
                        message=f"Retry scheduled for {retry_at.isoformat()} (attempt {job.attempt_count}/{job.max_retries})",
                        details_json=json.dumps(result, ensure_ascii=False),
                    )
                    await _record_event(
                        session=session,
                        client_id=job.client_id,
                        driver_id=job.driver_id,
                        job_id=job.job_id,
                        event_type=JOB_RETRY_SCHEDULED,
                        payload={
                            "retry_at": retry_at.isoformat(),
                            "attempt": job.attempt_count,
                            "max_retries": job.max_retries,
                            "error_category": job.error_category,
                        },
                    )

                    logger.info(f"Job {job_id} moved to WAITING_RETRY until {retry_at.isoformat()}")
                    return {
                        **result,
                        "status": TaskStatus.WAITING_RETRY.value,
                        "next_retry_at": retry_at.isoformat(),
                    }

                if job.error_category in {
                    "invalid_driver",
                    "incomplete_data",
                    "destination_error",
                    "submission_unconfirmed",
                }:
                    job.status = TaskStatus.NEEDS_REVIEW.value
                else:
                    job.status = TaskStatus.FAILED.value
                job.retryable = False
                job.finished_at = now
                job.next_retry_at = None
                runtime_state.state = DriverRuntimeStateValue.READY.value
                runtime_state.next_retry_at = None
                runtime_state.updated_at = datetime.now(UTC).replace(tzinfo=None)
                await session.commit()

                await _add_job_log(
                    session=session,
                    job_id=job_id,
                    client_id=job.client_id,
                    step="failed",
                    status="failed",
                    message=result.get("error", "Failed"),
                    details_json=json.dumps(result.get("steps", []), ensure_ascii=False),
                )
                await _record_event(
                    session=session,
                    client_id=job.client_id,
                    driver_id=job.driver_id,
                    job_id=job.job_id,
                    event_type=JOB_EXECUTION_FAILED,
                    payload={"error": job.last_error, "error_category": job.error_category},
                )

                logger.warning(f"Job {job_id} failed permanently: {result.get('error')}")
                from app.core.circuit_breaker import check_and_report_failure

                await check_and_report_failure(result.get("error", "Unknown error"))
                return result
            finally:
                await _close_page_quickly(page)

    except Exception as e:
        logger.error(f"Job {job_id} execution error: {e}", exc_info=True)
        from app.core.circuit_breaker import check_and_report_failure

        await check_and_report_failure(str(e))

        try:
            if job is not None:
                await session.rollback()
                runtime_state = await _get_or_create_runtime_state(session, job.client_id, job.driver_id)
                job.status = TaskStatus.NEEDS_REVIEW.value
                job.last_error = str(e)
                job.error_category = "submission_unknown"
                job.finished_at = _utcnow_naive()
                runtime_state.state = DriverRuntimeStateValue.ERROR_REVIEW.value
                runtime_state.updated_at = datetime.now(UTC).replace(tzinfo=None)
                await session.commit()
                await _record_event(
                    session=session,
                    client_id=job.client_id,
                    driver_id=job.driver_id,
                    job_id=job.job_id,
                    event_type="worker.exception",
                    payload={"error": str(e)},
                )
        except Exception as persist_err:
            logger.warning("job_failed_state_persist_error", extra={"extra_fields": {"error": str(persist_err)}})

        raise
    finally:
        if driver_lock_acquired and job is not None and job.driver_id is not None:
            await rpa_runtime.release_lock(rpa_runtime.submit_lock_key(job.client_id, job.driver_id))
        await session.close()


def _is_retryable(result: dict[str, Any]) -> bool:
    """Determine if a failed job should be retried."""
    error_category = str(result.get("error_category", "")).strip().lower()
    status_hint = str(result.get("status", "")).strip().lower().replace("_", "").replace("-", "")
    retryable_categories = {
        "login_failed",
        "captcha_failed",
        "network_error",
        "system_error",
    }
    if status_hint == "captchafailed":
        return True
    return error_category in retryable_categories


async def _get_or_create_runtime_state(
    session: AsyncSession,
    client_id: int,
    driver_id: int | None,
) -> DriverRuntimeState:
    if driver_id is None:
        raise ValueError("driver_id is required for runtime state")
    statement = select(DriverRuntimeState).where(DriverRuntimeState.driver_id == driver_id)
    result = await session.exec(statement)
    state = result.first()
    if state is None:
        state = DriverRuntimeState(client_id=client_id, driver_id=driver_id)
        session.add(state)
        await session.flush()
    return state


async def _update_job_status(
    job_id: str,
    status: str,
    error: str | None = None,
    error_category: str | None = None,
):
    """Update job status in database."""
    session = async_session_factory()
    try:
        statement = select(WaybillJob).where(WaybillJob.job_id == job_id)
        result = await session.exec(statement)
        job = result.first()

        if job:
            job.status = status
            if error:
                job.last_error = error
            if error_category:
                job.error_category = error_category
            if status in [TaskStatus.SUCCESS.value, TaskStatus.FAILED.value, TaskStatus.DEAD_LETTER.value]:
                job.finished_at = _utcnow_naive()
            await session.commit()
    finally:
        await session.close()


async def _record_event(
    session: AsyncSession,
    client_id: int,
    driver_id: int | None,
    job_id: str | None,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    if driver_id is None:
        return
    event = DomainEvent(
        event_id=f"evt_{datetime.now(UTC).replace(tzinfo=None).timestamp():.6f}_{driver_id}_{event_type.replace('.', '_')}",
        event_type=event_type,
        client_id=client_id,
        driver_id=driver_id,
        job_id=job_id,
        payload_json=json.dumps(payload, ensure_ascii=False),
    )
    session.add(event)
    await session.commit()


async def _add_job_log(
    session: AsyncSession,
    job_id: str,
    client_id: int,
    step: str,
    status: str,
    message: str | None = None,
    details_json: str | None = None,
):
    """Add a log entry for a job."""
    log = WaybillTaskLog(
        job_id=job_id,
        client_id=client_id,
        step=step,
        status=status,
        message=message,
        details_json=details_json,
    )
    session.add(log)
    await session.commit()
