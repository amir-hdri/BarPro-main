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
import os
import socket
import threading
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from celery import Task
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth_multitenant import DriverPasswordDecryptError, decrypt_driver_password
from app.automation.browser import browser_manager, managed_browser_session
from app.automation.waybill_bot_multitenant import WaybillAutomationBot
from app.automation.worker_proxy import get_playwright_proxy
from app.core.config import utcms_config
from app.core.database import async_session_factory
from app.core.error_taxonomy import ErrorCategory, classify_error_string, classify_exception
from app.core.utils import close_thread_event_loop
from app.core.utils import run_async as _run
from app.models_multitenant import (
    Driver,
    TaskStatus,
    WaybillJob,
    WaybillTaskLog,
)
from app.models_rpa import DispatchIntent, DomainEvent, DriverRuntimeState, DriverRuntimeStateValue, Execution
from app.orchestrator.driver_slot import release_driver_execution_slot
from app.orchestrator.state_machine import JobStateMachine, StateTransitionError
from app.rpa.event_taxonomy import (
    JOB_EXECUTION_FAILED,
    JOB_EXECUTION_STARTED,
    JOB_RETRY_SCHEDULED,
    OTP_DETECTED,
)
from app.services.night_submission_policy import register_safe_night_failure
from app.services.rpa_runtime_service import rpa_runtime
from app.services.utcms_submission_gate import utcms_submission_gate
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _utcnow_naive() -> datetime:
    """Return a naive UTC timestamp for database columns stored without timezone."""
    return datetime.now(UTC).replace(tzinfo=None)


def generate_submission_fingerprint(payload: dict[str, Any]) -> str:
    """
    Generate a deterministic fingerprint from the waybill payload for reconciliation.

    Uses the key fields that uniquely identify a waybill submission:
    - driver_national_code
    - plate_number (vehicle.plate_number or vehicle.driver_plate or flat root)
    - origin (city + address)
    - destination (city + address)
    - cargo_weight
    - business_date
    - sender/receiver identifiers if available

    Both nested and flat payload layouts are supported (see
    ``extract_reconciliation_identity``). Returns a SHA256 hash truncated to
    32 chars for storage efficiency. The hash is an audit helper — the
    authoritative verification is the multi-field matching done by the
    reconciliation scraper against the UTCMS portal rows.
    """
    import hashlib

    from app.core.submission_identity import extract_reconciliation_identity, identity_fields_for_fingerprint

    identity = extract_reconciliation_identity(payload)

    sender = payload.get("sender", {}) if isinstance(payload.get("sender"), dict) else {}
    receiver = payload.get("receiver", {}) if isinstance(payload.get("receiver"), dict) else {}

    fingerprint_parts = identity_fields_for_fingerprint(identity) + [
        str(sender.get("national_code", "") or "").strip(),
        str(receiver.get("national_code", "") or "").strip(),
    ]

    fingerprint_string = "|".join(fingerprint_parts)
    return hashlib.sha256(fingerprint_string.encode("utf-8")).hexdigest()[:32]


def _safe_json(raw: str | dict | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    parsed: Any = raw
    for _ in range(2):
        if not isinstance(parsed, str):
            break
        try:
            parsed = json.loads(parsed or "{}")
        except (TypeError, json.JSONDecodeError):
            return {}
    return parsed if isinstance(parsed, dict) else {}


async def _close_page_quickly(page: Any) -> None:
    try:
        await asyncio.wait_for(page.close(), timeout=2.5)
    except Exception as exc:
        logger.warning("worker_page_close_skipped", extra={"extra_fields": {"error": str(exc)}})


async def _evict_unhealthy_proxy(proxy_url: str) -> None:
    """Remove the proxy that failed preflight before the next dispatch.

    A clean-pool endpoint can pass a login probe and fail immediately after
    the session starts.  Reporting a synthetic CONNECT failure here preserves
    the endpoint identity, so the circuit breaker evicts that exact proxy
    instead of allowing it to remain cached until the next pool refresh.
    """
    if not proxy_url:
        return
    try:
        from app.automation.worker_proxy import get_current_egress_context
        from app.core.circuit_breaker import check_and_report_failure

        source, cached_url = get_current_egress_context()
        await check_and_report_failure(
            "proxy connect failed during preflight health check",
            egress_source=source,
            proxy_url=cached_url or proxy_url,
        )
    except Exception as exc:
        logger.warning(
            "unhealthy_proxy_eviction_failed",
            extra={"extra_fields": {"proxy": proxy_url, "error": str(exc)[:240]}},
        )


class WaybillTask(Task):
    """Base task for waybill processing with common utilities."""

    autoretry_for = (ConnectionError, TimeoutError, asyncio.TimeoutError)
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
    name="barpro.waybill.execute",
    queue="waybill_tasks",
    acks_late=True,
    reject_on_worker_lost=True,
)
def execute_dispatched_intent(self, intent_id: str):
    """
    Claim and execute a dispatched intent.
    """
    try:
        result = _run(_claim_and_execute(self, intent_id))
        return result
    except Exception as e:
        logger.error(f"Intent {intent_id} failed with exception: {e}", exc_info=True)
        from app.core.circuit_breaker import check_and_report_failure

        try:
            _run(check_and_report_failure(str(e)))
        except Exception as cb_err:
            logger.warning("circuit_breaker_report_failed", extra={"extra_fields": {"error": str(cb_err)}})
        raise


@celery_app.task(
    bind=True,
    base=WaybillTask,
    name="barpro.waybill.reconcile",
    queue="reconciliation_tasks",
    acks_late=True,
    reject_on_worker_lost=True,
)
def reconcile_dispatched_intent(self, intent_id: str):
    """
    Claim and execute a dispatched reconciliation intent.
    """
    try:
        result = _run(_claim_and_reconcile(self, intent_id))
        return result
    except Exception as e:
        logger.error(f"Reconciliation intent {intent_id} failed with exception: {e}", exc_info=True)
        from app.core.circuit_breaker import check_and_report_failure

        try:
            _run(check_and_report_failure(str(e)))
        except Exception as cb_err:
            logger.warning("circuit_breaker_report_failed", extra={"extra_fields": {"error": str(cb_err)}})
        raise


async def _assert_still_valid(execution_id: str, fencing_token: int) -> None:
    async with async_session_factory() as session:
        stmt = select(Execution).where(Execution.execution_id == execution_id).with_for_update()
        res = await session.exec(stmt)
        exec_row = res.first()
        if not exec_row:
            raise StateTransitionError(f"Execution {execution_id} not found in database")
        if exec_row.fencing_token != fencing_token or exec_row.status != "running":
            raise StateTransitionError(
                f"Fencing token/status mismatch or ownership lost for execution {execution_id}. "
                f"DB fencing_token: {exec_row.fencing_token} (expected {fencing_token}), status: {exec_row.status}"
            )


async def _claim_and_execute(task: Any, intent_id: str):
    import os
    import socket

    worker_id = os.environ.get("WORKER_ID", socket.gethostname())

    from app.automation.worker_proxy import (
        ProxyUnavailableError,
        check_proxy_health,
        drain_worker_consumers,
        get_worker_proxy_url,
        is_worker_draining,
    )

    async with async_session_factory() as session:
        try:
            # Get and lock intent first
            statement = select(DispatchIntent).where(DispatchIntent.intent_id == intent_id).with_for_update()
            res = await session.exec(statement)
            intent = res.first()

            if intent is None:
                raise ValueError(f"Intent {intent_id} not found")

            if intent.status != "claimed":
                logger.warning(f"Intent {intent_id} has invalid status {intent.status}, skipping")
                return {"status": "skipped", "reason": f"invalid_intent_status_{intent.status}"}

            # Reject incomplete submissions before consuming a proxy, browser,
            # execution lease, or retry budget. Historical jobs may contain a
            # JSON string inside the JSON column, so normalize both encodings.
            job_statement = select(WaybillJob).where(WaybillJob.job_id == intent.job_id).with_for_update()
            job_result = await session.exec(job_statement)
            job = job_result.first()
            if not job:
                raise ValueError(f"Job {intent.job_id} not found for intent {intent_id}")

            from app.automation.multitenant_payload_adapter import (
                build_enhanced_waybill_payload,
                validate_live_waybill_payload,
            )

            normalized_payload = build_enhanced_waybill_payload(_safe_json(job.payload_json))
            vehicle = normalized_payload.get("vehicle") if isinstance(normalized_payload.get("vehicle"), dict) else {}
            payload_errors = validate_live_waybill_payload(
                normalized_payload,
                expected_driver_mobile=vehicle.get("driver_phone"),
            )
            if payload_errors:
                error_message = "اطلاعات اجباری بارنامه ناقص است: " + "، ".join(payload_errors)
                intent.status = "failed"
                intent.updated_at = _utcnow_naive()
                session.add(intent)
                JobStateMachine.transition(
                    session,
                    job,
                    TaskStatus.NEEDS_REVIEW.value,
                    last_error=error_message,
                    error_category="payload_validation_failed",
                    terminal_reason="payload_validation_failed",
                    retryable=False,
                    celery_task_id=None,
                    finished_at=_utcnow_naive(),
                    updated_at=_utcnow_naive(),
                )
                if job.driver_id:
                    await release_driver_execution_slot(
                        session,
                        driver_id=job.driver_id,
                        expected_intent_id=intent_id,
                    )
                await session.commit()
                logger.warning(
                    "worker_payload_preflight_failed",
                    extra={
                        "extra_fields": {
                            "intent_id": intent_id,
                            "job_id": job.job_id,
                            "missing_fields": payload_errors,
                        }
                    },
                )
                return {
                    "status": TaskStatus.NEEDS_REVIEW.value,
                    "error_category": "payload_validation_failed",
                    "validation_errors": payload_errors,
                }

            # Pre-flight draining check
            if await is_worker_draining(worker_id):
                logger.warning(f"Worker {worker_id} is draining, refusing to execute intent {intent_id}")
                drain_worker_consumers(task)

                # Move job to waiting_retry and intent to failed
                intent.status = "failed"
                intent.updated_at = datetime.now(UTC).replace(tzinfo=None)
                session.add(intent)

                job_statement = select(WaybillJob).where(WaybillJob.job_id == intent.job_id).with_for_update()
                job_res = await session.exec(job_statement)
                job = job_res.first()
                if job:
                    JobStateMachine.transition(
                        session,
                        job,
                        TaskStatus.WAITING_RETRY.value,
                        last_error=f"Worker {worker_id} is draining",
                        error_category=ErrorCategory.TRANSIENT_INFRA_ERROR.value,
                        next_retry_at=datetime.now(UTC).replace(tzinfo=None),
                        submit_after=datetime.now(UTC).replace(tzinfo=None),
                    )
                # Drain is a pre-execution failure: no Execution exists yet, so
                # the driver slot must be released or the job stays stuck in
                # WAITING_RETRY forever (the scheduler skips non-null slots).
                if job and job.driver_id:
                    await release_driver_execution_slot(session, driver_id=job.driver_id, expected_intent_id=intent_id)
                await session.commit()
                raise ConnectionError(f"Worker {worker_id} is currently draining")

            # Pre-flight proxy check (fail-closed: ProxyUnavailableError
            # moves the job to WAITING_RETRY instead of running direct)
            try:
                proxy_url = get_worker_proxy_url()
            except ProxyUnavailableError as proxy_exc:
                logger.error(f"{proxy_exc} (worker_id={worker_id})")
                intent.status = "failed"
                intent.updated_at = datetime.now(UTC).replace(tzinfo=None)
                session.add(intent)

                job_statement = select(WaybillJob).where(WaybillJob.job_id == intent.job_id).with_for_update()
                job_res = await session.exec(job_statement)
                job = job_res.first()
                if job:
                    JobStateMachine.transition(
                        session,
                        job,
                        TaskStatus.WAITING_RETRY.value,
                        last_error=f"Proxy unavailable: {proxy_exc}",
                        error_category=ErrorCategory.TRANSIENT_INFRA_ERROR.value,
                        next_retry_at=datetime.now(UTC).replace(tzinfo=None),
                        submit_after=datetime.now(UTC).replace(tzinfo=None),
                    )
                # Proxy failure is pre-execution: no Execution exists, release
                # the driver slot so the scheduler can re-dispatch this job.
                if job and job.driver_id:
                    await release_driver_execution_slot(session, driver_id=job.driver_id, expected_intent_id=intent_id)
                await session.commit()
                raise ConnectionError(f"Proxy unavailable: {proxy_exc}") from proxy_exc
            if proxy_url:
                is_healthy = await check_proxy_health(proxy_url)
                if not is_healthy:
                    logger.error(f"Proxy health check failed for {proxy_url}. Incrementing failures.")
                    await _evict_unhealthy_proxy(proxy_url)
                    # Do not permanently cancel Celery consumers for an egress
                    # outage.  The circuit breaker temporarily removes this IP
                    # from routing and automatically retries after its TTL.

                    # Move job to waiting_retry and intent to failed
                    intent.status = "failed"
                    intent.updated_at = datetime.now(UTC).replace(tzinfo=None)
                    session.add(intent)

                    job_statement = select(WaybillJob).where(WaybillJob.job_id == intent.job_id).with_for_update()
                    job_res = await session.exec(job_statement)
                    job = job_res.first()
                    if job:
                        JobStateMachine.transition(
                            session,
                            job,
                            TaskStatus.WAITING_RETRY.value,
                            last_error=f"Proxy {proxy_url} is unhealthy",
                            error_category=ErrorCategory.TRANSIENT_INFRA_ERROR.value,
                            next_retry_at=datetime.now(UTC).replace(tzinfo=None),
                            submit_after=datetime.now(UTC).replace(tzinfo=None),
                        )
                    # Proxy unhealthy is a pre-execution failure: no Execution
                    # exists, so release the driver slot to avoid a stuck job.
                    if job and job.driver_id:
                        await release_driver_execution_slot(
                            session, driver_id=job.driver_id, expected_intent_id=intent_id
                        )
                    await session.commit()
                    raise ConnectionError(f"Proxy {proxy_url} is unhealthy")
            # Transition intent status to running
            intent.status = "running"
            intent.updated_at = datetime.now(UTC).replace(tzinfo=None)
            session.add(intent)

            # Create unique execution ID
            execution_id = str(uuid.uuid4())

            # Create Execution lease slot
            lease_duration = getattr(utcms_config, "WORKER_STALL_TIMEOUT_SECONDS", 90)
            lease_expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=lease_duration)

            execution = Execution(
                execution_id=execution_id,
                intent_id=intent_id,
                job_id=intent.job_id,
                attempt_no=intent.attempt_no,
                operation=intent.operation,
                worker_id=worker_id,
                fencing_token=intent.fencing_token,
                lease_expires_at=lease_expires_at,
                status="running",
            )
            session.add(execution)

            # Transition job status to running.
            # updated_at MUST be bumped here: orphan_detector sweeps RUNNING jobs
            # with stale updated_at, and a job that waited in the queue can enter
            # RUNNING with an hours-old timestamp. Without this bump the sweep
            # kills the job seconds after it starts (C1).
            JobStateMachine.transition(
                session,
                job,
                TaskStatus.RUNNING.value,
                started_at=datetime.now(UTC).replace(tzinfo=None),
                attempt_count=job.attempt_count + 1,
                worker_id=worker_id,
                updated_at=_utcnow_naive(),
            )
            await session.commit()

        except Exception as e:
            logger.error(f"Error claiming intent {intent_id}: {e}", exc_info=True)
            await session.rollback()
            raise

    # Lease renewal loop
    main_loop = asyncio.get_running_loop()
    stop_event = threading.Event()
    driver_lock_holder = _DriverLockHolder()
    renewal_thread = threading.Thread(
        target=_renew_lease_sync_loop,
        args=(execution_id, intent.fencing_token, stop_event, main_loop, driver_lock_holder),
        daemon=True,
    )
    renewal_thread.start()

    try:
        # Run original execute job
        result = await _execute_job(
            task,
            intent.job_id,
            execution_id=execution_id,
            fencing_token=intent.fencing_token,
            stop_event=stop_event,
            lock_holder=driver_lock_holder,
        )
        await _assert_still_valid(execution_id, intent.fencing_token)
        status_str = "completed"
        await _finalize_execution(execution_id, intent_id, status_str, result)
        return result
    except Exception as err:
        logger.error(f"Execution failed for job {intent.job_id}: {err}", exc_info=True)
        try:
            await _assert_still_valid(execution_id, intent.fencing_token)
            await _finalize_execution(execution_id, intent_id, "failed", {"error": str(err)})
        except Exception as final_err:
            logger.warning(f"Skipping finalize as failed for execution {execution_id}: {final_err}")
        raise
    finally:
        stop_event.set()
        renewal_thread.join(timeout=5)


async def _claim_and_reconcile(task: Any, intent_id: str):
    import os
    import socket

    worker_id = os.environ.get("WORKER_ID", socket.gethostname())

    from app.automation.worker_proxy import (
        ProxyUnavailableError,
        check_proxy_health,
        drain_worker_consumers,
        get_worker_proxy_url,
        is_worker_draining,
    )

    async with async_session_factory() as session:
        try:
            # Get and lock intent first
            statement = select(DispatchIntent).where(DispatchIntent.intent_id == intent_id).with_for_update()
            res = await session.exec(statement)
            intent = res.first()

            if intent is None:
                raise ValueError(f"Intent {intent_id} not found")

            if intent.status != "claimed":
                logger.warning(f"Intent {intent_id} has invalid status {intent.status}, skipping")
                return {"status": "skipped", "reason": f"invalid_intent_status_{intent.status}"}

            # Pre-flight draining check
            if await is_worker_draining(worker_id):
                logger.warning(f"Worker {worker_id} is draining, refusing to reconcile intent {intent_id}")
                drain_worker_consumers(task)

                # Move job to unknown and intent to failed
                intent.status = "failed"
                intent.updated_at = datetime.now(UTC).replace(tzinfo=None)
                session.add(intent)

                job_statement = select(WaybillJob).where(WaybillJob.job_id == intent.job_id).with_for_update()
                job_res = await session.exec(job_statement)
                job = job_res.first()
                if job:
                    JobStateMachine.transition(
                        session,
                        job,
                        TaskStatus.UNKNOWN.value,
                        expected_from={TaskStatus.CLAIMED.value},
                        last_error=f"Worker {worker_id} is draining during reconciliation",
                        error_category=ErrorCategory.TRANSIENT_INFRA_ERROR.value,
                    )
                # Pre-execution failure (no Execution yet): free the driver slot
                # so reconciliation can be re-driven later via a fresh intent.
                if job and job.driver_id:
                    await release_driver_execution_slot(session, driver_id=job.driver_id, expected_intent_id=intent_id)
                await session.commit()
                raise ConnectionError(f"Worker {worker_id} is currently draining")

            # Pre-flight proxy check (fail-closed: ProxyUnavailableError
            # moves the job to UNKNOWN for later reconciliation)
            try:
                proxy_url = get_worker_proxy_url()
            except ProxyUnavailableError as proxy_exc:
                logger.error(f"{proxy_exc} (worker_id={worker_id})")
                intent.status = "failed"
                intent.updated_at = datetime.now(UTC).replace(tzinfo=None)
                session.add(intent)

                job_statement = select(WaybillJob).where(WaybillJob.job_id == intent.job_id).with_for_update()
                job_res = await session.exec(job_statement)
                job = job_res.first()
                if job:
                    JobStateMachine.transition(
                        session,
                        job,
                        TaskStatus.UNKNOWN.value,
                        expected_from={TaskStatus.CLAIMED.value},
                        last_error=f"Proxy unavailable during reconciliation: {proxy_exc}",
                        error_category=ErrorCategory.TRANSIENT_INFRA_ERROR.value,
                    )
                # Pre-execution failure: free the driver slot for re-reconciliation.
                if job and job.driver_id:
                    await release_driver_execution_slot(session, driver_id=job.driver_id, expected_intent_id=intent_id)
                await session.commit()
                raise ConnectionError(f"Proxy unavailable: {proxy_exc}") from proxy_exc
            if proxy_url:
                is_healthy = await check_proxy_health(proxy_url)
                if not is_healthy:
                    logger.error(f"Proxy health check failed for {proxy_url}. Incrementing failures.")
                    await _evict_unhealthy_proxy(proxy_url)
                    # Keep consumers alive; circuit-breaker routing handles a
                    # temporarily unavailable egress path and self-recovers.

                    # Move job to unknown and intent to failed
                    intent.status = "failed"
                    intent.updated_at = datetime.now(UTC).replace(tzinfo=None)
                    session.add(intent)

                    job_statement = select(WaybillJob).where(WaybillJob.job_id == intent.job_id).with_for_update()
                    job_res = await session.exec(job_statement)
                    job = job_res.first()
                    if job:
                        JobStateMachine.transition(
                            session,
                            job,
                            TaskStatus.UNKNOWN.value,
                            expected_from={TaskStatus.CLAIMED.value},
                            last_error=f"Proxy {proxy_url} is unhealthy during reconciliation",
                            error_category=ErrorCategory.TRANSIENT_INFRA_ERROR.value,
                        )
                    # Pre-execution failure: free the driver slot for re-reconciliation.
                    if job and job.driver_id:
                        await release_driver_execution_slot(
                            session, driver_id=job.driver_id, expected_intent_id=intent_id
                        )
                    await session.commit()
                    raise ConnectionError(f"Proxy {proxy_url} is unhealthy")

            # Transition intent status to running
            intent.status = "running"
            intent.updated_at = datetime.now(UTC).replace(tzinfo=None)
            session.add(intent)

            # Get job
            job_statement = select(WaybillJob).where(WaybillJob.job_id == intent.job_id).with_for_update()
            job_res = await session.exec(job_statement)
            job = job_res.first()
            if not job:
                raise ValueError(f"Job {intent.job_id} not found for intent {intent_id}")

            # Create unique execution ID
            execution_id = str(uuid.uuid4())

            # Create Execution lease slot
            lease_duration = getattr(utcms_config, "WORKER_STALL_TIMEOUT_SECONDS", 90)
            lease_expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=lease_duration)

            execution = Execution(
                execution_id=execution_id,
                intent_id=intent_id,
                job_id=intent.job_id,
                attempt_no=intent.attempt_no,
                operation=intent.operation,
                worker_id=worker_id,
                fencing_token=intent.fencing_token,
                lease_expires_at=lease_expires_at,
                status="running",
            )
            session.add(execution)

            # Transition job status to RECONCILING
            from app.orchestrator.state_machine import JobStatus

            JobStateMachine.transition(
                session,
                job,
                JobStatus.RECONCILING.value,
                worker_id=worker_id,
                updated_at=_utcnow_naive(),
            )
            await session.commit()

        except Exception as e:
            logger.error(f"Error claiming reconciliation intent {intent_id}: {e}", exc_info=True)
            await session.rollback()
            raise

    # Lease renewal loop
    main_loop = asyncio.get_running_loop()
    stop_event = threading.Event()
    renewal_thread = threading.Thread(
        target=_renew_lease_sync_loop, args=(execution_id, intent.fencing_token, stop_event, main_loop), daemon=True
    )
    renewal_thread.start()

    try:
        # Run reconciliation service
        from app.orchestrator.reconciliation_service import reconciliation_service

        async with async_session_factory() as run_session:
            reconciled_job = await reconciliation_service.reconcile_job(
                session=run_session,
                job_id=job.id,
            )
            if reconciled_job:
                result = {
                    "status": reconciled_job.status,
                    "last_error": reconciled_job.last_error,
                    "result_json": reconciled_job.result_json,
                }
            else:
                result = {"status": "unknown", "error": "Reconciliation returned None"}

        await _assert_still_valid(execution_id, intent.fencing_token)
        status_str = "completed"
        await _finalize_execution(execution_id, intent_id, status_str, result)
        return result
    except Exception as err:
        logger.error(f"Reconciliation failed for job {intent.job_id}: {err}", exc_info=True)
        try:
            await _assert_still_valid(execution_id, intent.fencing_token)
            await _finalize_execution(execution_id, intent_id, "failed", {"error": str(err)})
        except Exception as final_err:
            logger.warning(f"Skipping finalize as failed for reconciliation execution {execution_id}: {final_err}")
        raise
    finally:
        stop_event.set()
        renewal_thread.join(timeout=5)


async def _finalize_execution(execution_id: str, intent_id: str, status: str, result: Any):
    async with async_session_factory() as session:
        try:
            # Update execution
            exec_statement = select(Execution).where(Execution.execution_id == execution_id).with_for_update()
            exec_res = await session.exec(exec_statement)
            exec_row = exec_res.first()
            if not exec_row or exec_row.status != "running":
                logger.warning(
                    f"Aborting execution finalization. Execution {execution_id} "
                    f"status is '{exec_row.status if exec_row else 'not found'}' (expected 'running')."
                )
                return

            exec_row.status = status
            try:
                res_str = json.dumps(result, ensure_ascii=False)
            except Exception:
                res_str = str(result)
            exec_row.result_json = res_str
            exec_row.updated_at = datetime.now(UTC).replace(tzinfo=None)
            session.add(exec_row)

            # Clear active execution slot on completion. The execution row was
            # already moved to a terminal status above, so it is no longer a
            # live execution and the slot may be safely released.
            job_stmt = select(WaybillJob).where(WaybillJob.job_id == exec_row.job_id)
            job_res = await session.exec(job_stmt)
            job = job_res.first()
            if job and job.driver_id:
                await release_driver_execution_slot(session, driver_id=job.driver_id, expected_intent_id=intent_id)

            # Update intent
            intent_statement = select(DispatchIntent).where(DispatchIntent.intent_id == intent_id).with_for_update()
            intent_res = await session.exec(intent_statement)
            intent_row = intent_res.first()
            if intent_row:
                intent_row.status = status
                intent_row.updated_at = datetime.now(UTC).replace(tzinfo=None)
                session.add(intent_row)

            await session.commit()
        except Exception as e:
            logger.error(f"Failed to finalize execution {execution_id}: {e}", exc_info=True)
            await session.rollback()


class _DriverLockHolder:
    """Thread-safe registry of driver-lock keys held by the current execution.

    The lease-renewal thread runs in a separate OS thread and renews every key
    registered here (C3): Redis driver locks are acquired BEFORE the browser
    launches and must outlive the whole bot window, so they need periodic TTL
    extension just like the Execution DB lease.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._keys: list[str] = []

    def register(self, key: str) -> None:
        with self._lock:
            if key not in self._keys:
                self._keys.append(key)

    def clear(self) -> None:
        with self._lock:
            self._keys.clear()

    def snapshot(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._keys)


def _renew_lease_sync_loop(
    execution_id: str,
    fencing_token: int,
    stop_event: threading.Event,
    main_loop: asyncio.AbstractEventLoop | None = None,
    lock_holder: _DriverLockHolder | None = None,
):
    """Runs in a separate thread, updates lease_expires_at using asyncio.run_coroutine_threadsafe on main_loop.

    Renew every WORKER_STALL_TIMEOUT_SECONDS/3 (min 10s) so a single missed
    renewal never exceeds the stall window and orphans an in-flight job
    (X10). Also re-extends the TTL of any driver lock registered in
    ``lock_holder`` so the Redis submit/auth locks never expire mid-run (C3).
    """
    lease_duration = getattr(utcms_config, "WORKER_STALL_TIMEOUT_SECONDS", 90)
    renew_interval = max(10.0, lease_duration / 3.0)
    lock_ttl = getattr(utcms_config, "RPA_LOCK_TTL_SECONDS", 360)

    while not stop_event.wait(timeout=renew_interval):
        try:

            async def _update():
                # DB lease renewal is best-effort and MUST NOT abort driver-lock
                # renewal below: a transient DB error would otherwise skip lock
                # extension for that cycle (discovered by regression test).
                try:
                    async with async_session_factory() as session:
                        stmt = select(Execution).where(Execution.execution_id == execution_id).with_for_update()
                        res = await session.exec(stmt)
                        exec_row = res.first()
                        if exec_row:
                            if exec_row.fencing_token != fencing_token or exec_row.status != "running":
                                logger.warning(
                                    f"Fencing token/status mismatch or ownership lost for execution {execution_id}. "
                                    f"Fencing token: {exec_row.fencing_token} (expected {fencing_token}), status: {exec_row.status}. Stopping renewal."
                                )
                                stop_event.set()
                                return
                            exec_row.lease_expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                                seconds=lease_duration
                            )
                            exec_row.updated_at = datetime.now(UTC).replace(tzinfo=None)
                            session.add(exec_row)
                            await session.commit()
                            logger.debug(f"Lease renewed for execution {execution_id}")
                except Exception as lease_err:
                    logger.warning(f"Lease renewal DB error for execution {execution_id}: {lease_err}")

                # C3: extend driver submit/auth locks owned by this execution.
                # Ownership is proven inside renew_lock via compare-and-expire;
                # a False return means the lock is gone/foreign — log loudly so
                # parallel-submission risk is observable.
                if lock_holder is not None:
                    for lock_key in lock_holder.snapshot():
                        try:
                            renewed = await rpa_runtime.renew_lock(lock_key, lock_ttl)
                            if not renewed:
                                logger.warning(
                                    "driver_lock_renew_missed",
                                    extra={"extra_fields": {"key": lock_key, "execution_id": execution_id}},
                                )
                        except Exception:
                            logger.warning(
                                "driver_lock_renew_error",
                                exc_info=True,
                                extra={"extra_fields": {"key": lock_key, "execution_id": execution_id}},
                            )

            if main_loop is not None and main_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(_update(), main_loop)
                future.result(timeout=10.0)
            else:
                _run(_update())
        except Exception as e:
            logger.warning(f"Failed to renew lease for execution {execution_id}: {e}")

    # The renewal thread owns a thread-local loop; release its selector sockets
    # as soon as the lease is no longer active.
    close_thread_event_loop()


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
            _run(_update_job_status(job_id, TaskStatus.NEEDS_REVIEW.value, str(e), classify_exception(e)[0].value))
        except Exception as db_err:
            logger.error("update_job_status_failed", extra={"extra_fields": {"error": str(db_err)}})
        raise


async def _execute_job(
    task,
    job_id: str,
    execution_id: str | None = None,
    fencing_token: int | None = None,
    stop_event: threading.Event | None = None,
    lock_holder: "_DriverLockHolder | None" = None,
) -> dict[str, Any]:
    """Execute a waybill job with full lifecycle management."""
    job: WaybillJob | None = None
    driver_lock_acquired = False
    auth_lock_acquired = False
    page = None
    worker_id = str(getattr(task.request, "hostname", None) or os.environ.get("WORKER_ID") or socket.gethostname())

    async with async_session_factory() as session:
        try:
            statement = select(WaybillJob).where(WaybillJob.job_id == job_id).with_for_update()
            result = await session.exec(statement)
            job = result.first()

            if not job:
                logger.error(f"Job {job_id} not found in database")
                return {"status": "failed", "error": "Job not found"}

            # Cache client_id and driver_id to avoid MissingGreenlet error in finally block
            # These are accessed multiple times and need to be loaded before session closes
            cached_client_id = job.client_id
            cached_driver_id = job.driver_id

            existing_result = _safe_json(job.result_json)
            if existing_result.get("tracking_code"):
                logger.info("Skipping already completed waybill job %s", job_id)
                return {"status": TaskStatus.SUCCESS.value, "result": existing_result, "reused": True}
            if job.status == TaskStatus.SUCCESS.value:
                JobStateMachine.transition(
                    session,
                    job,
                    TaskStatus.NEEDS_REVIEW.value,
                    error_category=ErrorCategory.SUBMISSION_UNCONFIRMED.value,
                    last_error="Success state has no UTCMS tracking code",
                    updated_at=_utcnow_naive(),
                )
                await session.commit()
                logger.warning("Waybill job %s has success status without tracking code", job_id)
                return {"status": TaskStatus.NEEDS_REVIEW.value, "skipped": True}
            is_running_path = job.status == TaskStatus.RUNNING.value

            if not is_running_path:
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
                    if (
                        job.status == TaskStatus.IN_PROGRESS.value
                        and job.updated_at
                        and job.updated_at < stale_threshold
                    ):
                        logger.warning(
                            f"Reclaiming stuck IN_PROGRESS job {job_id} (last updated {job.updated_at.isoformat()})"
                        )
                    else:
                        logger.info("Skipping waybill job %s in non-claimable status %s", job_id, job.status)
                        return {"status": job.status, "skipped": True}

            runtime_state = await _get_or_create_runtime_state(session, cached_client_id, cached_driver_id)

            if not is_running_path:
                JobStateMachine.transition(
                    session,
                    job,
                    TaskStatus.IN_PROGRESS.value,
                    started_at=_utcnow_naive(),
                    attempt_count=job.attempt_count + 1,
                    worker_id=task.request.hostname,
                    updated_at=_utcnow_naive(),
                    submit_after=None,
                )
                # Generate and store submission fingerprint for reconciliation
                if isinstance(job.payload_json, dict):
                    payload = job.payload_json
                elif isinstance(job.payload_json, str):
                    payload = json.loads(job.payload_json)
                else:
                    payload = {}
                if payload and not job.submission_fingerprint:
                    job.submission_fingerprint = generate_submission_fingerprint(payload)
                    session.add(job)
                await session.commit()
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

            username = driver.utcms_username
            # ─── Decrypt BEFORE acquiring the driver lock ────────────────────────────
            # Doing this first prevents a zombie lock when the key is mismatched:
            # if decrypt fails we set NEEDS_REVIEW immediately and return without
            # ever touching Redis, so subsequent jobs for the same driver are free.
            try:
                password = decrypt_driver_password(driver.utcms_password_encrypted)
            except DriverPasswordDecryptError as exc:
                logger.error(
                    "worker_driver_key_mismatch",
                    extra={"extra_fields": {"driver_id": driver.id, "job_id": job_id}},
                )
                JobStateMachine.transition(
                    session,
                    job,
                    TaskStatus.NEEDS_REVIEW.value,
                    last_error=str(exc),
                    error_category="driver_key_mismatch",
                    finished_at=_utcnow_naive(),
                    updated_at=_utcnow_naive(),
                )
                await session.commit()
                return {"status": TaskStatus.NEEDS_REVIEW.value, "error_category": "driver_key_mismatch"}
            # ────────────────────────────────────────────────────────────────────────

            auth_lock_key = rpa_runtime.auth_lock_key(job.client_id, driver.id)
            auth_lock_acquired = await rpa_runtime.acquire_lock(auth_lock_key, utcms_config.RPA_LOCK_TTL_SECONDS)
            if not auth_lock_acquired:
                retry_at = _utcnow_naive() + timedelta(seconds=utcms_config.DRIVER_RETRY_DELAY_SECONDS)
                JobStateMachine.transition(
                    session,
                    job,
                    TaskStatus.WAITING_RETRY.value,
                    celery_task_id=None,
                    retryable=True,
                    next_retry_at=retry_at,
                    submit_after=retry_at,
                    last_error="Another authorization is already running for this driver",
                    error_category="driver_submission_in_progress",
                    updated_at=_utcnow_naive(),
                )
                await session.commit()
                return {"status": TaskStatus.WAITING_RETRY.value, "next_retry_at": retry_at.isoformat()}

            # Persist ownership of the auth lock in DB
            runtime_state = await _get_or_create_runtime_state(session, cached_client_id, cached_driver_id)
            runtime_state.auth_lock_owner = task.request.id or "worker"
            runtime_state.auth_lock_acquired_at = _utcnow_naive()
            runtime_state.auth_lock_ttl_seconds = utcms_config.RPA_LOCK_TTL_SECONDS
            await session.commit()

            # C3: keep this lock alive for the whole bot window via the
            # lease-renewal thread.
            if lock_holder is not None:
                lock_holder.register(auth_lock_key)

            driver_lock_key = rpa_runtime.submit_lock_key(job.client_id, driver.id)
            driver_lock_acquired = await rpa_runtime.acquire_lock(driver_lock_key, utcms_config.RPA_LOCK_TTL_SECONDS)
            if not driver_lock_acquired:
                # Release auth lock since submit lock failed
                await rpa_runtime.release_lock(auth_lock_key)
                auth_lock_acquired = False
                runtime_state.auth_lock_owner = None
                runtime_state.auth_lock_acquired_at = None
                runtime_state.auth_lock_ttl_seconds = None
                await session.commit()

                retry_at = _utcnow_naive() + timedelta(seconds=utcms_config.DRIVER_RETRY_DELAY_SECONDS)
                JobStateMachine.transition(
                    session,
                    job,
                    TaskStatus.WAITING_RETRY.value,
                    celery_task_id=None,
                    retryable=True,
                    next_retry_at=retry_at,
                    submit_after=retry_at,
                    last_error="Another waybill submission is already running for this driver",
                    error_category="driver_submission_in_progress",
                    updated_at=_utcnow_naive(),
                )
                await session.commit()
                return {"status": TaskStatus.WAITING_RETRY.value, "next_retry_at": retry_at.isoformat()}

            # C3: submit lock acquired — register it for periodic TTL renewal.
            if lock_holder is not None:
                lock_holder.register(driver_lock_key)

            if isinstance(job.payload_json, dict):
                payload = job.payload_json
            elif isinstance(job.payload_json, str):
                payload = json.loads(job.payload_json)
            else:
                payload = {}

            # Hard Idempotency Guard: Never resubmit if tracking_code already confirmed!
            if isinstance(job.result_json, dict) and job.result_json.get("tracking_code"):
                logger.info("job_already_confirmed_skipping_submit", extra={"extra_fields": {"job_id": job_id}})
                await rpa_runtime.release_lock(auth_lock_key)
                await rpa_runtime.release_lock(driver_lock_key)
                return {"status": TaskStatus.SUCCESS.value, "result": job.result_json, "reused": True}

            # Persist durable mutation intent & digest before submit
            import hashlib

            request_digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            job.request_digest = request_digest
            job.mutation_status = "intent_persisted"
            job.mutation_at = _utcnow_naive()
            await session.commit()

            from app.services.session_vault import session_vault

            auth_state_path = session_vault.auth_state_path_for_account(
                username=username,
                national_code=driver.driver_national_code,
                fallback=username,
                scope=f"client-{job.client_id}-driver-{driver.id}",
            )

            # Check session version mismatch (Session Versioning logic)
            try:
                expected_version = runtime_state.session_version
                stored_version = await session_vault.async_get_session_version(auth_state_path)
                if stored_version is not None and stored_version < expected_version:
                    logger.warning(
                        f"Session version mismatch for driver {driver.id}: stored={stored_version}, expected={expected_version}"
                    )
                    await rpa_runtime.release_lock(auth_lock_key)
                    await rpa_runtime.release_lock(driver_lock_key)
                    runtime_state.auth_lock_owner = None
                    runtime_state.auth_lock_acquired_at = None
                    runtime_state.auth_lock_ttl_seconds = None
                    await session.commit()

                    retry_at = _utcnow_naive() + timedelta(seconds=utcms_config.DRIVER_RETRY_DELAY_SECONDS)
                    JobStateMachine.transition(
                        session,
                        job,
                        TaskStatus.WAITING_RETRY.value,
                        celery_task_id=None,
                        retryable=True,
                        next_retry_at=retry_at,
                        submit_after=retry_at,
                        last_error=f"Session version mismatch (stored version {stored_version} is less than DB version {expected_version})",
                        error_category="session_version_mismatch",
                        updated_at=_utcnow_naive(),
                    )
                    await session.commit()
                    return {"status": TaskStatus.WAITING_RETRY.value, "error_category": "session_version_mismatch"}
            except Exception as e:
                logger.error(f"Fail-closed session vault check failed: {e}", exc_info=True)
                await rpa_runtime.release_lock(auth_lock_key)
                await rpa_runtime.release_lock(driver_lock_key)
                runtime_state.auth_lock_owner = None
                runtime_state.auth_lock_acquired_at = None
                runtime_state.auth_lock_ttl_seconds = None
                await session.commit()

                retry_at = _utcnow_naive() + timedelta(seconds=utcms_config.DRIVER_RETRY_DELAY_SECONDS)
                JobStateMachine.transition(
                    session,
                    job,
                    TaskStatus.WAITING_RETRY.value,
                    celery_task_id=None,
                    retryable=True,
                    next_retry_at=retry_at,
                    submit_after=retry_at,
                    last_error=f"Redis session vault check failed: {e}",
                    error_category="session_vault_error",
                    updated_at=_utcnow_naive(),
                )
                await session.commit()
                return {"status": TaskStatus.WAITING_RETRY.value, "error_category": "session_vault_error"}

            if stop_event and stop_event.is_set():
                raise StateTransitionError(f"Execution {execution_id} was cancelled/invalidated during execution")
            if execution_id and fencing_token is not None:
                await _assert_still_valid(execution_id, fencing_token)

            # Submission Gate Check: only an explicit live OTP_FREE observation
            # permits mutation. Clock predictions must not turn an unknown
            # state into a fixed overnight wait.
            gate_state = await utcms_submission_gate.get_state()
            if gate_state.value != "otp_free":
                logger.info(
                    "gate_closed_pre_execution_transition",
                    extra={"extra_fields": {"job_id": job_id, "driver_id": driver.id}},
                )
                await rpa_runtime.release_lock(auth_lock_key)
                await rpa_runtime.release_lock(driver_lock_key)
                runtime_state.auth_lock_owner = None
                runtime_state.auth_lock_acquired_at = None
                runtime_state.auth_lock_ttl_seconds = None
                runtime_state.state = DriverRuntimeStateValue.WAITING_SUBMISSION_WINDOW.value
                retry_at = _utcnow_naive() + timedelta(seconds=utcms_config.GATE_PROBE_INTERVAL_SECONDS)
                gate_err_msg = (
                    "UTCMS به‌صورت زنده OTP را لازم اعلام کرده است؛ پس از پروب بعدی دوباره بررسی می‌شود"
                    if gate_state.value == "otp_required"
                    else "وضعیت OTP سامانه هنوز به‌صورت زنده مشخص نشده است؛ پس از پروب بعدی دوباره بررسی می‌شود"
                )
                JobStateMachine.transition(
                    session,
                    job,
                    TaskStatus.WAITING_SUBMISSION_WINDOW.value,
                    celery_task_id=None,
                    retryable=True,
                    next_retry_at=retry_at,
                    submit_after=retry_at,
                    last_error=gate_err_msg,
                    error_category="otp_required" if gate_state.value == "otp_required" else "gate_unknown",
                    updated_at=_utcnow_naive(),
                )
                await session.commit()
                return {
                    "status": TaskStatus.WAITING_SUBMISSION_WINDOW.value,
                    "error_category": "otp_required" if gate_state.value == "otp_required" else "gate_unknown",
                }

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
                    job_timeout = getattr(utcms_config, "JOB_TIMEOUT_SECONDS", 330)
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
                            "status": "unknown",
                            "error": f"Execution timed out after {job_timeout}s",
                            "error_category": ErrorCategory.SUBMISSION_UNCONFIRMED.value,
                            "mutation_status": "ambiguous",
                            "needs_reconciliation": True,
                        }

                    result_status = str(result.get("status", "")).strip().lower()
                    now = _utcnow_naive()

                    if result_status == "otp_backoff":
                        await utcms_submission_gate.record_otp_detected(worker_id=worker_id, evidence=result)
                        night_decision = register_safe_night_failure(job)
                        if night_decision.standby:
                            retry_at = night_decision.retry_at
                            error_category = "night_submission_attempts_exhausted"
                            message = "سه تلاش امن شبانه ناموفق بود؛ ثبت تا ساعت ۰۸:۰۰ تهران در آماده‌باش است"
                        else:
                            retry_minutes = int(result.get("next_retry_at_minutes_add", 60))
                            retry_at = now + timedelta(minutes=retry_minutes)
                            error_category = "otp_required"
                            message = result.get("message", "OTP challenge detected")
                        JobStateMachine.transition(
                            session,
                            job,
                            TaskStatus.WAITING_SUBMISSION_WINDOW.value,
                            celery_task_id=None,
                            next_retry_at=retry_at,
                            submit_after=retry_at,
                            last_error=message,
                            error_category=error_category,
                            finished_at=None,
                        )
                        runtime_state.state = DriverRuntimeStateValue.WAITING_SUBMISSION_WINDOW.value
                        runtime_state.next_retry_at = retry_at
                        runtime_state.updated_at = datetime.now(UTC).replace(tzinfo=None)
                        await session.commit()

                        await _add_job_log(
                            session=session,
                            job_id=job_id,
                            client_id=job.client_id,
                            step="otp_backoff",
                            status="waiting_submission_window",
                            message=message,
                            details_json=result,
                        )
                        await _record_event(
                            session=session,
                            client_id=job.client_id,
                            driver_id=job.driver_id,
                            job_id=job.job_id,
                            event_type=OTP_DETECTED,
                            payload={
                                "retry_at": retry_at.isoformat(),
                                "message": job.last_error,
                                "night_attempt_count": night_decision.attempt_count,
                                "standby": night_decision.standby,
                            },
                        )

                        logger.info(f"Job {job_id} entered WAITING_SUBMISSION_WINDOW, retry at {job.next_retry_at}")
                        return result

                    if result_status == "validated":
                        validation_payload = result.get("result") if isinstance(result.get("result"), dict) else {}
                        JobStateMachine.transition(
                            session,
                            job,
                            TaskStatus.NEEDS_REVIEW.value,
                            result_json=validation_payload,
                            celery_task_id=None,
                            last_error="Waybill form validated; live submit is disabled",
                            error_category="live_submit_disabled",
                            retryable=False,
                            next_retry_at=None,
                            finished_at=now,
                        )
                        runtime_state.state = DriverRuntimeStateValue.READY.value
                        runtime_state.next_retry_at = None
                        runtime_state.updated_at = now
                        await session.commit()
                        logger.info("Job %s passed safe pre-submit validation", job_id)
                        return result

                    if result_status == TaskStatus.SUCCESS.value:
                        result_payload = result.get("result")
                        tracking_code = (
                            result_payload.get("tracking_code") if isinstance(result_payload, dict) else None
                        )
                        if not tracking_code:
                            # CRITICAL REDLINE: SUCCESS without tracking code is forbidden -> downgrade to UNKNOWN
                            result_status = TaskStatus.UNKNOWN.value
                            result["status"] = TaskStatus.UNKNOWN.value
                            result["error"] = (
                                "Portal success response did not include a tracking code; reconciliation required"
                            )
                            result["error_category"] = ErrorCategory.SUBMISSION_UNCONFIRMED.value
                            job.mutation_status = "ambiguous"
                            JobStateMachine.transition(
                                session,
                                job,
                                TaskStatus.UNKNOWN.value,
                                celery_task_id=None,
                                retryable=False,
                                last_error=result["error"],
                                error_category=ErrorCategory.SUBMISSION_UNCONFIRMED.value,
                                finished_at=now,
                            )
                            runtime_state.state = DriverRuntimeStateValue.READY.value
                            runtime_state.next_retry_at = None
                            runtime_state.updated_at = datetime.now(UTC).replace(tzinfo=None)
                            await session.commit()
                            return result
                        else:
                            job.mutation_status = "dispatched"
                            if (
                                isinstance(result_payload, dict)
                                and "document_id" in result_payload
                                and result_payload["document_id"]
                            ):
                                job.document_id = str(result_payload["document_id"])

                            provisional_result = dict(result_payload)
                            provisional_result["confirmation_status"] = "pending_history_reconciliation"
                            reconciliation_at = now + timedelta(seconds=15)
                            JobStateMachine.transition(
                                session,
                                job,
                                TaskStatus.UNKNOWN.value,
                                result_json=provisional_result,
                                finished_at=now,
                                last_error="Tracking code received; UTCMS History reconciliation is pending",
                                error_category=ErrorCategory.SUBMISSION_UNCONFIRMED.value,
                                retryable=False,
                                next_retry_at=reconciliation_at,
                            )
                            runtime_state.state = DriverRuntimeStateValue.READY.value
                            runtime_state.next_retry_at = None
                            runtime_state.updated_at = datetime.now(UTC).replace(tzinfo=None)
                            await session.commit()

                            await _add_job_log(
                                session=session,
                                job_id=job_id,
                                client_id=job.client_id,
                                step="reconciliation_pending",
                                status="unknown",
                                message="Tracking code received; waiting for UTCMS History confirmation",
                                details_json=provisional_result,
                            )
                            logger.info("Job %s submitted and queued for mandatory reconciliation", job_id)
                            await browser_manager.record_success_for_recycle()
                            result["status"] = TaskStatus.UNKNOWN.value
                            result["mutation_status"] = "dispatched"
                            result["needs_reconciliation"] = True
                            return result

                    if (
                        result_status == "unknown"
                        or result_status == TaskStatus.UNKNOWN.value
                        or result.get("mutation_status") == "ambiguous"
                        or result.get("error_category") == ErrorCategory.SUBMISSION_UNCONFIRMED.value
                    ):
                        job.mutation_status = "ambiguous"
                        error_msg = result.get(
                            "error",
                            "Waybill submission status ambiguous; reconciliation required",
                        )
                        JobStateMachine.transition(
                            session,
                            job,
                            TaskStatus.UNKNOWN.value,
                            celery_task_id=None,
                            retryable=False,
                            last_error=error_msg,
                            error_category=ErrorCategory.SUBMISSION_UNCONFIRMED.value,
                            finished_at=now,
                        )
                        runtime_state.state = DriverRuntimeStateValue.READY.value
                        runtime_state.next_retry_at = None
                        runtime_state.updated_at = datetime.now(UTC).replace(tzinfo=None)
                        await session.commit()

                        await _add_job_log(
                            session=session,
                            job_id=job_id,
                            client_id=job.client_id,
                            step="mutation_ambiguous",
                            status="unknown",
                            message=error_msg,
                            details_json=result,
                        )
                        await _record_event(
                            session=session,
                            client_id=job.client_id,
                            driver_id=job.driver_id,
                            job_id=job.job_id,
                            event_type=JOB_EXECUTION_FAILED,
                            payload={
                                "status": "unknown",
                                "error": error_msg,
                                "error_category": ErrorCategory.SUBMISSION_UNCONFIRMED.value,
                            },
                        )
                        logger.warning(
                            "job_entered_unknown_for_mandatory_reconciliation",
                            extra={"extra_fields": {"job_id": job_id, "error": error_msg}},
                        )
                        return result

                    job.last_error = result.get("error", "Unknown error")
                    job.error_category = classify_error_string(
                        error_msg=job.last_error,
                        error_category_hint=result.get("error_category"),
                        status_hint=result.get("status"),
                    ).value

                    night_decision = register_safe_night_failure(job)
                    if night_decision.standby:
                        retry_at = night_decision.retry_at
                        JobStateMachine.transition(
                            session,
                            job,
                            TaskStatus.WAITING_SUBMISSION_WINDOW.value,
                            celery_task_id=None,
                            retryable=True,
                            next_retry_at=retry_at,
                            submit_after=retry_at,
                            finished_at=None,
                            last_error="سه تلاش امن شبانه ناموفق بود؛ ثبت تا ساعت ۰۸:۰۰ تهران در آماده‌باش است",
                            error_category="night_submission_attempts_exhausted",
                        )
                        runtime_state.state = DriverRuntimeStateValue.WAITING_SUBMISSION_WINDOW.value
                        runtime_state.next_retry_at = retry_at
                        runtime_state.updated_at = now
                        await session.commit()
                        return {
                            **result,
                            "status": TaskStatus.WAITING_SUBMISSION_WINDOW.value,
                            "next_retry_at": retry_at.isoformat(),
                            "night_attempt_count": night_decision.attempt_count,
                        }

                    if job.attempt_count < job.max_retries and _is_retryable(result):
                        retry_delay = get_retry_delay(result, job.attempt_count)
                        retry_at = now + timedelta(seconds=retry_delay)
                        JobStateMachine.transition(
                            session,
                            job,
                            TaskStatus.WAITING_RETRY.value,
                            celery_task_id=None,
                            retryable=True,
                            next_retry_at=retry_at,
                            submit_after=retry_at,
                            finished_at=None,
                        )
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
                            details_json=result,
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

                    target_status = (
                        TaskStatus.NEEDS_REVIEW.value
                        if job.error_category
                        in {
                            ErrorCategory.AUTH_FAILURE.value,
                            ErrorCategory.USER_DATA_ERROR.value,
                            ErrorCategory.SELECTOR_CHANGED.value,
                            ErrorCategory.BOT_DETECTED.value,
                        }
                        else TaskStatus.FAILED.value
                    )
                    JobStateMachine.transition(
                        session, job, target_status, retryable=False, finished_at=now, next_retry_at=None
                    )
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
                        details_json=result.get("steps", []),
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

            # Once a durable mutation intent exists, a timeout/crash may have
            # happened after the portal accepted the POST. Never let Celery's
            # retry policy submit the same waybill again; reconcile instead.
            if job is not None and job.mutation_status in {
                "intent_persisted",
                "dispatching",
                "dispatched",
                "ambiguous",
            }:
                try:
                    await session.rollback()
                    JobStateMachine.transition(
                        session,
                        job,
                        TaskStatus.UNKNOWN.value,
                        celery_task_id=None,
                        retryable=False,
                        last_error=f"Mutation outcome ambiguous after worker exception: {e}",
                        error_category=ErrorCategory.SUBMISSION_UNCONFIRMED.value,
                        finished_at=_utcnow_naive(),
                        next_retry_at=_utcnow_naive() + timedelta(seconds=15),
                    )
                    job.mutation_status = "ambiguous"
                    await session.commit()
                    return {
                        "status": TaskStatus.UNKNOWN.value,
                        "mutation_status": "ambiguous",
                        "needs_reconciliation": True,
                        "error_category": ErrorCategory.SUBMISSION_UNCONFIRMED.value,
                    }
                except Exception:
                    logger.warning("ambiguous_mutation_persist_failed", exc_info=True)

            # Check if browser crash occurred and recycle browser
            err_msg = str(e).lower()
            if any(msg in err_msg for msg in ("target closed", "browser closed", "context closed", "page closed")):
                logger.warning("Browser crash detected. Triggering browser recycle.")
                try:
                    await browser_manager.recycle_browser()
                except Exception as recycle_err:
                    logger.error(f"Failed to recycle browser after crash: {recycle_err}")

            from app.core.circuit_breaker import check_and_report_failure

            await check_and_report_failure(str(e))

            try:
                if job is not None:
                    await session.rollback()
                    runtime_state = await _get_or_create_runtime_state(session, cached_client_id, cached_driver_id)
                    JobStateMachine.transition(
                        session,
                        job,
                        TaskStatus.NEEDS_REVIEW.value,
                        last_error=str(e),
                        error_category=classify_exception(e)[0].value,
                        finished_at=_utcnow_naive(),
                    )
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
            if job is not None and cached_client_id is not None and cached_driver_id is not None:
                if lock_holder is not None:
                    lock_holder.clear()
                if auth_lock_acquired:
                    try:
                        statement = select(DriverRuntimeState).where(DriverRuntimeState.driver_id == cached_driver_id)
                        res = await session.exec(statement)
                        state = res.first()
                        if state is not None:
                            state.auth_lock_owner = None
                            state.auth_lock_acquired_at = None
                            state.auth_lock_ttl_seconds = None
                            await session.commit()
                    except Exception:
                        logger.warning("failed_to_clear_auth_lock_columns_db", exc_info=True)

                if cached_client_id and cached_driver_id:
                    try:
                        await rpa_runtime.release_lock(rpa_runtime.submit_lock_key(cached_client_id, cached_driver_id))
                    except Exception:
                        pass
                    try:
                        await rpa_runtime.release_lock(rpa_runtime.auth_lock_key(cached_client_id, cached_driver_id))
                    except Exception:
                        pass
            await session.close()


def _is_retryable(result: dict[str, Any]) -> bool:
    """Determine if a failed job should be retried."""
    if result.get("mutation_status") == "ambiguous" or result.get("mutation_attempted") is True:
        return False
    error_category = str(result.get("error_category", "")).strip().lower()
    if error_category in (
        "submission_unconfirmed",
        "ambiguous_mutation",
        "duplicate_submission",
        "payload_validation_failed",
        "user_data_error",
    ):
        return False
    status_hint = str(result.get("status", "")).strip().lower().replace("_", "").replace("-", "")
    if status_hint in ("unknown", "reconciling"):
        return False
    if status_hint == "captchafailed":
        return True

    from app.core.error_taxonomy import classify_error_string, is_retryable_terminal_category

    cat = classify_error_string(
        error_msg=str(result.get("error", "")),
        error_category_hint=result.get("error_category"),
        status_hint=result.get("status"),
    )
    return is_retryable_terminal_category(cat)


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
        try:
            async with session.begin_nested():
                state = DriverRuntimeState(client_id=client_id, driver_id=driver_id)
                session.add(state)
                await session.flush()
        except IntegrityError:
            result = await session.exec(statement)
            state = result.first()
            if state is None:
                raise
    return state


async def _update_job_status(
    job_id: str,
    status: str,
    error: str | None = None,
    error_category: str | None = None,
):
    """Update job status in database."""
    async with async_session_factory() as session:
        statement = select(WaybillJob).where(WaybillJob.job_id == job_id)
        result = await session.exec(statement)
        job = result.first()

        if job:
            extra_fields = {}
            if error:
                extra_fields["last_error"] = error
            if error_category:
                extra_fields["error_category"] = error_category
            if status in [TaskStatus.SUCCESS.value, TaskStatus.FAILED.value, TaskStatus.DEAD_LETTER.value]:
                extra_fields["finished_at"] = _utcnow_naive()
            JobStateMachine.transition(session, job, status, **extra_fields)
            await session.commit()


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


def get_retry_delay(result: dict[str, Any], attempt_count: int) -> int:
    """Calculate exponential backoff delay based on error category and attempt count."""
    error_category = str(result.get("error_category", "")).strip().lower()
    if error_category in {
        "captcha_failed",
        "network_error",
        "login_failed",
        "system_error",
        "transient_infra_error",
        "target_site_timeout",
        "auth_failure",
        "worker_resource_error",
    }:
        base = 60
        return min(base * (2 ** max(0, attempt_count - 1)), 1800)
    return utcms_config.DRIVER_RETRY_DELAY_SECONDS
