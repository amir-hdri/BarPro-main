"""
Standalone scheduled waybill executor with retry, logging, and duplicate prevention.

This service:
- Evaluates all active schedules across all tenants
- Creates jobs for due schedules
- Executes jobs with retry logic
- Maintains execution logs
- Prevents duplicate execution via slot signatures
- Reports results back to the database
"""
import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth_multitenant import decrypt_driver_password
from app.automation.browser import browser_manager, managed_browser_session
from app.automation.multitenant_payload_adapter import build_enhanced_waybill_payload
from app.automation.proxy_rotator import get_proxy_rotator
from app.automation.waybill_bot_multitenant import WaybillAutomationBot
from app.core.config import utcms_config
from app.core.database import async_session_factory
from app.models_multitenant import (
    Client,
    Driver,
    DriverSchedule,
    ScheduleFrequency,
    TaskSource,
    TaskStatus,
    WaybillJob,
    WaybillTaskLog,
)
from app.models_rpa import DomainEvent
from app.rpa.event_taxonomy import (
    JOB_CREATED,
    JOB_EXECUTION_FAILED,
    JOB_EXECUTION_SUCCEEDED,
    JOB_RETRY_SCHEDULED,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BASE_DELAY = 5  # seconds
RETRY_MAX_DELAY = 120  # seconds


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _resolve_run_times(schedule: DriverSchedule) -> list[str]:
    if schedule.run_times_csv:
        parts = [p.strip() for p in schedule.run_times_csv.split(",") if p.strip()]
        if parts:
            return sorted(parts)
    return [schedule.run_time] if schedule.run_time else ["08:00"]


def _parse_weekdays_csv(raw: str | None) -> list[int]:
    if not raw:
        return []
    result: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if token.isdigit():
            val = int(token)
            if 0 <= val <= 6:
                result.append(val)
    return sorted(set(result))


def _parse_csv_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def _safe_json(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


async def _add_log(
    session: AsyncSession,
    job_id: str,
    client_id: int,
    step: str,
    status: str,
    message: str = None,
    details: dict = None,
) -> None:
    log = WaybillTaskLog(
        job_id=job_id,
        client_id=client_id,
        step=step,
        status=status,
        message=message,
        details_json=json.dumps(details, ensure_ascii=False) if details else None,
    )
    session.add(log)
    await session.commit()


async def _record_event(
    session: AsyncSession,
    client_id: int,
    driver_id: int,
    job_id: str,
    event_type: str,
    payload: dict,
) -> None:
    event = DomainEvent(
        event_id=f"evt_sched_{uuid.uuid4().hex[:12]}",
        event_type=event_type,
        client_id=client_id,
        driver_id=driver_id,
        job_id=job_id,
        payload_json=json.dumps(payload, ensure_ascii=False),
    )
    session.add(event)
    await session.commit()


async def _execute_single_job(
    client: Client,
    driver: Driver,
    job: WaybillJob,
    session: AsyncSession,
    attempt: int = 1,
) -> dict[str, Any]:
    """Execute a single waybill job with retry logic."""
    payload_data = _safe_json(job.payload_json)
    normalized = build_enhanced_waybill_payload(payload_data)
    username = driver.utcms_username
    password = decrypt_driver_password(driver.utcms_password_encrypted)
    job_id = job.job_id

    proxy_info = await get_proxy_rotator().get_next()
    proxy_dict = proxy_info.to_playwright_proxy() if proxy_info else None

    async with managed_browser_session(proxy_dict=proxy_dict) as (_session_id, context):
        page = await browser_manager.new_page(context)
        try:
            bot = WaybillAutomationBot(page, context)
            result = await bot.execute_waybill_job(
                username=username,
                password=password,
                payload=normalized,
                job_id=job_id,
                client_id=client.id,
            )
            status_str = str(result.get("status", "")).strip().lower()

            if status_str == "success":
                await _add_log(session, job_id, client.id, "submit", "success", "Waybill submitted successfully")
                await _record_event(session, client.id, driver.id, job_id, JOB_EXECUTION_SUCCEEDED, {
                    "attempt": attempt,
                    "steps": result.get("steps", []),
                })
                return result
            elif status_str == "otp_backoff":
                retry_minutes = int(result.get("next_retry_at_minutes_add", 60))
                retry_at = _utcnow() + timedelta(minutes=retry_minutes)
                job.status = TaskStatus.WAITING_RETRY.value
                job.next_retry_at = retry_at
                job.submit_after = retry_at
                job.last_error = result.get("message", "OTP challenge detected")
                job.error_category = "otp_required"
                job.attempt_count += 1
                await session.commit()
                await _add_log(session, job_id, client.id, "retry_scheduled", "success",
                               f"Retry scheduled in {retry_minutes} minutes")
                await _record_event(session, client.id, driver.id, job_id, JOB_RETRY_SCHEDULED, {
                    "retry_at": retry_at.isoformat(),
                    "attempt": attempt,
                })
                return {**result, "status": TaskStatus.WAITING_RETRY.value}
            else:
                await _add_log(session, job_id, client.id, "submit", "failed", result.get("error", "Unknown error"))
                await _record_event(session, client.id, driver.id, job_id, JOB_EXECUTION_FAILED, {
                    "error": result.get("error"),
                    "attempt": attempt,
                })

                if _is_retryable(result) and attempt < MAX_RETRIES:
                    delay = min(RETRY_BASE_DELAY * (2 ** (attempt - 1)), RETRY_MAX_DELAY)
                    await asyncio.sleep(delay)
                    logger.info(f"Retrying job {job_id}, attempt {attempt + 1}/{MAX_RETRIES} after {delay}s")
                    return await _execute_single_job(client, driver, job, session, attempt + 1)

                job.status = TaskStatus.FAILED.value
                job.finished_at = _utcnow()
                job.last_error = result.get("error", "Execution failed")
                job.error_category = result.get("error_category", "unknown")
                job.retryable = False
                job.attempt_count += 1
                await session.commit()
                return result

        finally:
            try:
                await asyncio.wait_for(page.close(), timeout=3)
            except Exception:
                pass


def _is_retryable(result: dict[str, Any]) -> bool:
    error_cat = str(result.get("error_category", "")).strip().lower()
    return error_cat in ("login_failed", "captcha_failed", "network_error", "system_or_network_error", "auth_expired")


async def evaluate_and_run_schedules() -> dict[str, Any]:
    """
    Main entry point: evaluate all active schedules across all tenants
    and execute due ones.

    Returns a summary of what was executed, skipped, and failed.
    """
    session = async_session_factory()
    summary = {
        "started_at": _utcnow().isoformat(),
        "schedules_evaluated": 0,
        "schedules_skipped": 0,
        "schedules_executed": 0,
        "jobs_created": 0,
        "jobs_success": 0,
        "jobs_failed": 0,
        "errors": [],
        "ended_at": None,
    }
    try:
        stmt = select(DriverSchedule).where(
            DriverSchedule.is_active.is_(True)
        ).order_by(col(DriverSchedule.created_at).asc())
        result = await session.exec(stmt)
        schedules = result.all()

        summary["schedules_evaluated"] = len(schedules)

        for schedule in schedules:
            try:
                exec_summary = await _evaluate_single_schedule(session, schedule)
                summary["schedules_executed"] += exec_summary.get("jobs_created", 0)
                summary["jobs_created"] += exec_summary.get("jobs_created", 0)
                summary["jobs_success"] += exec_summary.get("jobs_success", 0)
                summary["jobs_failed"] += exec_summary.get("jobs_failed", 0)
            except Exception as exc:
                summary["schedules_skipped"] += 1
                error_entry = {
                    "schedule_id": schedule.id,
                    "error": str(exc),
                    "driver_id": schedule.driver_id,
                }
                summary["errors"].append(error_entry)
                logger.exception(f"Schedule {schedule.id} failed: {exc}")

    except Exception as exc:
        summary["errors"].append({"error": str(exc), "phase": "main_loop"})
        logger.exception(f"Scheduled executor main loop failed: {exc}")
    finally:
        summary["ended_at"] = _utcnow().isoformat()
        await session.close()

    return summary


async def _evaluate_single_schedule(session: AsyncSession, schedule: DriverSchedule) -> dict[str, Any]:
    """Evaluate a single schedule and create/execute jobs for due timeslots."""
    now = _utcnow()
    today = now.date()
    current_hhmm = now.strftime("%H:%M")

    # Check date range
    if schedule.start_date and today < datetime.fromisoformat(schedule.start_date).date():
        return {"jobs_created": 0, "jobs_success": 0, "jobs_failed": 0, "skipped": True}
    if schedule.end_date and today > datetime.fromisoformat(schedule.end_date).date():
        return {"jobs_created": 0, "jobs_success": 0, "jobs_failed": 0, "skipped": True}

    # Check specific dates
    specific_dates = _parse_csv_list(schedule.specific_dates_csv)
    if specific_dates and today.isoformat() not in specific_dates:
        return {"jobs_created": 0, "jobs_success": 0, "jobs_failed": 0, "skipped": True}

    # Check weekdays for weekly schedules
    if schedule.frequency == ScheduleFrequency.WEEKLY.value:
        allowed = _parse_weekdays_csv(schedule.weekdays_csv)
        if allowed and now.weekday() not in allowed:
            return {"jobs_created": 0, "jobs_success": 0, "jobs_failed": 0, "skipped": True}

    # Determine due timeslots
    run_times = _resolve_run_times(schedule)
    due_times = [t for t in run_times if t <= current_hhmm]
    if not due_times:
        return {"jobs_created": 0, "jobs_success": 0, "jobs_failed": 0, "skipped": True}

    target_slot = due_times[-1]
    slot_signature = f"{today.isoformat()}@{target_slot}"

    # Prevent duplicate execution
    if schedule.last_run_signature == slot_signature:
        return {"jobs_created": 0, "jobs_success": 0, "jobs_failed": 0, "skipped": True}

    # Fetch client and driver
    client = await session.get(Client, schedule.client_id)
    if not client or client.status != "active":
        return {"jobs_created": 0, "jobs_success": 0, "jobs_failed": 0, "skipped": True, "reason": "inactive_client"}

    driver = await session.get(Driver, schedule.driver_id)
    if not driver or driver.client_id != schedule.client_id:
        return {"jobs_created": 0, "jobs_success": 0, "jobs_failed": 0, "skipped": True, "reason": "driver_not_found"}
    if driver.status not in ("active", "ready"):
        return {"jobs_created": 0, "jobs_success": 0, "jobs_failed": 0, "skipped": True, "reason": "inactive_driver"}

    # Build payload
    payload = _safe_json(schedule.payload_template_json)
    if "driver_national_code" not in payload:
        payload["driver_national_code"] = driver.driver_national_code

    # Create job with idempotency key
    idempotency_key = f"schedule:{schedule.id}:{slot_signature}"

    # Check for existing job with same idempotency key
    existing_stmt = select(WaybillJob).where(
        WaybillJob.client_id == schedule.client_id,
        WaybillJob.idempotency_key == idempotency_key,
    )
    existing = (await session.exec(existing_stmt)).first()
    if existing:
        return {"jobs_created": 0, "jobs_success": 0, "jobs_failed": 0, "skipped": True, "reason": "duplicate_idempotency"}

    new_job = WaybillJob(
        job_id=f"job_{uuid.uuid4().hex[:16]}",
        idempotency_key=idempotency_key,
        client_id=schedule.client_id,
        driver_id=driver.id,
        status=TaskStatus.PENDING.value,
        source=TaskSource.API.value,
        payload_json=json.dumps(payload, ensure_ascii=False),
        max_retries=3,
        correlation_id=f"schedule:{schedule.id}",
        business_date=utcms_config.BUSINESS_DATE_PROVIDER() if hasattr(utcms_config, 'BUSINESS_DATE_PROVIDER') and callable(utcms_config.BUSINESS_DATE_PROVIDER) else _utcnow().strftime("%Y-%m-%d"),
        priority=5,
        schedule_id=schedule.id,
    )
    session.add(new_job)
    await session.flush()

    await _record_event(session, schedule.client_id, driver.id, new_job.job_id, JOB_CREATED, {
        "source": "scheduled",
        "schedule_id": schedule.id,
        "timeslot": target_slot,
    })

    # Execute the job immediately
    success_count = 0
    failed_count = 0

    try:
        result = await _execute_single_job(client, driver, new_job, session, attempt=1)
        result_status = str(result.get("status", "")).strip().lower()

        if result_status == "success":
            new_job.status = TaskStatus.SUCCESS.value
            new_job.finished_at = _utcnow()
            success_count = 1
        elif result_status == TaskStatus.WAITING_RETRY.value:
            new_job.status = TaskStatus.WAITING_RETRY.value
            new_job.started_at = _utcnow()
            success_count = 0
            failed_count = 0
        else:
            new_job.status = TaskStatus.FAILED.value
            new_job.finished_at = _utcnow()
            failed_count = 1

        await session.commit()
    except Exception as exc:
        logger.exception(f"Job execution failed: {exc}")
        new_job.status = TaskStatus.FAILED.value
        new_job.last_error = str(exc)
        new_job.error_category = "execution_error"
        new_job.finished_at = _utcnow()
        new_job.retryable = False
        failed_count = 1
        await session.commit()

    # Update schedule timestamps
    schedule.last_run_at = _utcnow()
    schedule.last_run_signature = slot_signature

    freq_days = 1 if schedule.frequency == ScheduleFrequency.DAILY.value else 7
    schedule.next_run_at = _utcnow() + timedelta(days=freq_days)
    schedule.updated_at = _utcnow()
    session.add(schedule)
    await session.commit()

    return {
        "jobs_created": 1,
        "jobs_success": success_count,
        "jobs_failed": failed_count,
        "job_id": new_job.job_id,
        "timeslot": target_slot,
    }


async def retry_failed_scheduled_jobs() -> dict[str, Any]:
    """
    Retry scheduled jobs that are in WAITING_RETRY or have retryable failures.

    This is called periodically to check if jobs are eligible for retry.
    """
    session = async_session_factory()
    summary = {
        "started_at": _utcnow().isoformat(),
        "jobs_checked": 0,
        "jobs_retried": 0,
        "errors": [],
        "ended_at": None,
    }
    try:
        now = _utcnow()

        stmt = select(WaybillJob).where(
            col(WaybillJob.status).in_([
                TaskStatus.WAITING_RETRY.value,
                TaskStatus.RETRYING.value,
            ]),
            WaybillJob.schedule_id.is_not(None),
            (col(WaybillJob.next_retry_at).is_(None)) | (col(WaybillJob.next_retry_at) <= now),
        ).order_by(col(WaybillJob.priority).desc())

        result = await session.exec(stmt)
        retryable_jobs = result.all()
        summary["jobs_checked"] = len(retryable_jobs)

        for job in retryable_jobs:
            try:
                if job.attempt_count >= job.max_retries:
                    job.status = TaskStatus.DEAD_LETTER.value
                    job.terminal_reason = "max_retries_exceeded"
                    job.finished_at = _utcnow()
                    job.retryable = False
                    await session.commit()
                    summary["jobs_retried"] += 0
                    continue

                job.status = TaskStatus.RETRYING.value
                job.attempt_count += 1
                job.next_retry_at = None
                job.started_at = _utcnow()
                await session.commit()

                client = await session.get(Client, job.client_id)
                driver = await session.get(Driver, job.driver_id) if job.driver_id else None

                if client and driver:
                    result = await _execute_single_job(client, driver, job, session, attempt=job.attempt_count)
                    result_status = str(result.get("status", "")).strip().lower()

                    if result_status == "success":
                        job.status = TaskStatus.SUCCESS.value
                        job.finished_at = _utcnow()
                    elif result_status == TaskStatus.WAITING_RETRY.value:
                        job.status = TaskStatus.WAITING_RETRY.value
                    else:
                        job.status = TaskStatus.FAILED.value
                        job.finished_at = _utcnow()
                        job.retryable = False

                    await session.commit()
                    summary["jobs_retried"] += 1
                else:
                    job.status = TaskStatus.FAILED.value
                    job.last_error = "Client or driver not found"
                    job.finished_at = _utcnow()
                    job.retryable = False
                    await session.commit()
            except Exception as exc:
                summary["errors"].append({"job_id": job.job_id, "error": str(exc)})
                logger.exception(f"Retry job {job.job_id} failed: {exc}")

    except Exception as exc:
        summary["errors"].append({"error": str(exc), "phase": "retry_main_loop"})
        logger.exception(f"Retry service failed: {exc}")
    finally:
        summary["ended_at"] = _utcnow().isoformat()
        await session.close()

    return summary


async def clear_expired_waiting_jobs() -> dict[str, Any]:
    """
    Clear jobs that have been WAITING_RETRY for too long (e.g., > 24 hours)
    without making progress. Mark them for review.
    """
    session = async_session_factory()
    summary = {
        "cleared": 0,
        "errors": [],
        "ended_at": _utcnow().isoformat(),
    }
    try:
        cutoff = _utcnow() - timedelta(hours=24)

        stmt = select(WaybillJob).where(
            WaybillJob.status == TaskStatus.WAITING_RETRY.value,
            col(WaybillJob.updated_at) < cutoff,
            WaybillJob.schedule_id.is_not(None),
        )
        result = await session.exec(stmt)
        stuck_jobs = result.all()

        for job in stuck_jobs:
            try:
                job.status = TaskStatus.NEEDS_REVIEW.value
                job.terminal_reason = "stuck_waiting_retry"
                job.last_error = "Job stuck in WAITING_RETRY for > 24 hours"
                await session.commit()
                summary["cleared"] += 1
            except Exception as exc:
                summary["errors"].append({"job_id": job.job_id, "error": str(exc)})

    except Exception as exc:
        summary["errors"].append({"error": str(exc), "phase": "clear_expired"})
        logger.exception(f"Clear expired failed: {exc}")
    finally:
        await session.close()

    return summary


# Module-level convenience functions
scheduled_waybill_executor = {
    "evaluate_and_run_schedules": evaluate_and_run_schedules,
    "retry_failed_scheduled_jobs": retry_failed_scheduled_jobs,
    "clear_expired_waiting_jobs": clear_expired_waiting_jobs,
}
