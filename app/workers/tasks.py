import logging
import time
from typing import Any

from fastapi import HTTPException

from app.core.config import utcms_config
from app.core.error_taxonomy import classify_exception
from app.core.execution_context import bind_execution_context, reset_execution_context
from app.core.network import is_retryable_network_error
from app.core.utils import run_async as _run_async
from app.monitoring.metrics import track_task_latency
from app.schemas.waybill import WaybillMapRequest
from app.services.task_service import task_service
from app.services.waybill_service import waybill_service
from app.workers.celery_app import celery_app


def _retry_delay_seconds(attempt_number: int) -> float:
    base = max(0.1, utcms_config.CELERY_RETRY_BASE_SECONDS)
    jitter = max(0.0, utcms_config.CELERY_RETRY_JITTER_SECONDS)
    return (base * (2 ** max(0, attempt_number - 1))) + min(jitter, 10.0)


def _is_retryable_exception(exc: Exception) -> bool:
    if isinstance(exc, HTTPException):
        if exc.status_code in (429, 503):
            return True
        if exc.status_code >= 500:
            return True
        return False
    return is_retryable_network_error(exc)


def _error_category(exc: Exception) -> str:
    return classify_exception(exc)[0].value


logger = logging.getLogger(__name__)

if celery_app is not None:

    @celery_app.task(bind=True, name="app.workers.tasks.process_waybill_task")
    def process_waybill_task(self, task_id: str) -> Any:
        if utcms_config.DEPRECATE_OLD_EXECUTION_PATH:
            logger.warning(
                f"Deprecation Warning: app.workers.tasks.process_waybill_task called for {task_id}. "
                "Redirecting execution to waybill.process_job."
            )
            from app.workers.waybill_worker import process_waybill_job
            return process_waybill_job.apply_async(
                args=[task_id],
                queue="waybill_tasks",
                priority=self.request.priority or 5,
            )
        else:
            max_retries = max(0, utcms_config.CELERY_MAX_RETRIES)
            attempt = int(self.request.retries) + 1
            worker_id = self.request.hostname or "celery-worker"
            started_at = time.perf_counter()

            _run_async(task_service.mark_processing(task_id, worker_id=worker_id, attempt_count=attempt))
            payload = _run_async(task_service.get_payload(task_id))
            if payload is None:
                _run_async(
                    task_service.mark_failure(
                        task_id=task_id,
                        error_text="payload_not_found",
                        category="unknown",
                        attempt_count=attempt,
                        retryable=False,
                    )
                )
                raise RuntimeError("Task payload not found")

            request = WaybillMapRequest.model_validate(payload)
            execution_tokens = bind_execution_context(
                correlation_id=payload.get("correlation_id"),
                task_id=task_id,
                batch_id=payload.get("batch_id"),
                worker_id=worker_id,
            )

            try:
                try:
                    result = _run_async(waybill_service.create_waybill_with_map(request))
                except Exception as exc:
                    retryable = _is_retryable_exception(exc)
                    category = _error_category(exc)

                    if retryable and self.request.retries < max_retries:
                        _run_async(
                            task_service.mark_retrying(
                                task_id=task_id,
                                error_text=str(exc),
                                category=category,
                                attempt_count=attempt,
                            )
                        )
                        raise self.retry(exc=exc, countdown=_retry_delay_seconds(attempt)) from exc

                    _run_async(
                        task_service.mark_failure(
                            task_id=task_id,
                            error_text=str(exc),
                            category=category,
                            attempt_count=attempt,
                            retryable=retryable,
                            dead_letter=retryable and self.request.retries >= max_retries,
                        )
                    )
                    raise

                _run_async(task_service.mark_success(task_id=task_id, result=result, attempt_count=attempt))
                track_task_latency(time.perf_counter() - started_at)
                return result
            finally:
                reset_execution_context(execution_tokens)

    @celery_app.task(bind=True, name="app.workers.tasks.process_fuel_inquiry_task")
    def process_fuel_inquiry_task(self, inquiry_id: int) -> Any:
        from app.core.database import async_session_factory
        from app.services.fuel_inquiry_service import fuel_inquiry_service

        async def _run():
            import socket
            import os
            w_id = os.environ.get("WORKER_ID", socket.gethostname())
            from app.automation.worker_proxy import is_worker_draining, drain_worker_consumers, increment_worker_failures, transition_worker_to_draining
            
            # Check if draining before execution
            if await is_worker_draining(w_id):
                logger.warning(f"Worker {w_id} is draining, refusing fuel inquiry {inquiry_id}")
                drain_worker_consumers(self)
                from app.models_multitenant import FuelInquiry
                from app.core.error_taxonomy import ErrorCategory
                from app.orchestrator.state_machine import set_fuel_inquiry_status
                from datetime import UTC, datetime
                async with async_session_factory() as session:
                    inquiry = await session.get(FuelInquiry, inquiry_id)
                    if inquiry:
                        set_fuel_inquiry_status(inquiry, "failed")
                        inquiry.error_message = "سرور در حال خارج شدن از سرویس (draining) می‌باشد"
                        inquiry.error_category = ErrorCategory.TRANSIENT_INFRA_ERROR.value
                        inquiry.updated_at = datetime.now(UTC).replace(tzinfo=None)
                        session.add(inquiry)
                        await session.commit()
                raise ConnectionError(f"Worker {w_id} is currently draining")

            # Circuit-breaker guard (X6 + NEW-7): fuel inquiries share one queue,
            # so a worker whose egress IP was just blocked by UTCMS would otherwise
            # greedily claim them (fast failure = faster re-claim = anti-affinity).
            # When this worker's index is blocked AND another healthy index exists,
            # requeue (bounded, max 3 times) so a healthy worker handles it.
            idx = os.environ.get("WORKER_IP_INDEX", "").strip()
            if idx.isdigit():
                from app.core.redis import redis_manager
                r = await redis_manager.get()
                if r is not None:
                    block_key = f"utcms:circuit_breaker:blocked:{idx}"
                    if await r.exists(block_key):
                        from app.core.circuit_breaker import (
                            get_available_ip_indices,
                            _get_known_ip_indices,
                            _get_unavailable_ip_indices,
                        )
                        available = get_available_ip_indices()
                        unavailable = await _get_unavailable_ip_indices()
                        known = await _get_known_ip_indices()
                        healthy = [
                            i for i in available
                            if i != int(idx)
                            and i not in unavailable
                            and (not known or i in known)
                        ]
                        if healthy:
                            req_key = f"utcms:circuit_breaker:fuel_requeue:{inquiry_id}:{idx}"
                            attempts = await r.incr(req_key)
                            await r.expire(req_key, 600)
                            if attempts <= 3:
                                logger.warning(
                                    f"Worker IP index {idx} is blocked by the UTCMS circuit "
                                    f"breaker; requeueing fuel inquiry {inquiry_id} "
                                    f"(attempt {attempts}) so another healthy IP handles it"
                                )
                                process_fuel_inquiry_task.apply_async(
                                    args=[inquiry_id],
                                    queue=utcms_config.CELERY_FUEL_INQUIRY_QUEUE,
                                    countdown=15,
                                )
                                return
                            await r.delete(req_key)

            async with async_session_factory() as session:
                try:
                    await fuel_inquiry_service.run_automation(inquiry_id, session)
                    await session.commit()
                except Exception as e:
                    await session.rollback()
                    logger.error(f"Failed in process_fuel_inquiry_task: {e}")
                    
                    # Track failures for auto-heal draining on infrastructure errors
                    err_msg = str(e).lower()
                    if "proxy" in err_msg or "network" in err_msg or "timeout" in err_msg or any(msg in err_msg for msg in ("target closed", "browser closed", "context closed", "page closed")):
                        failures = await increment_worker_failures(w_id)
                        if failures > 3:
                            await transition_worker_to_draining(w_id)
                            drain_worker_consumers(self)
                    raise

        return _run_async(_run())

else:

    def process_waybill_task(*_args, **_kwargs):
        raise RuntimeError("Celery is not installed")

    def process_fuel_inquiry_task(*_args, **_kwargs):
        raise RuntimeError("Celery is not installed")


def dispatch_waybill_task(task_id: str, priority: int | None = None):
    if celery_app is None:
        raise RuntimeError("Celery is not available in current environment")
    normalized_priority = utcms_config.CELERY_DEFAULT_PRIORITY if priority is None else int(priority)
    normalized_priority = max(
        utcms_config.CELERY_MIN_PRIORITY, min(utcms_config.CELERY_MAX_PRIORITY, normalized_priority)
    )

    import random

    from app.core.circuit_breaker import get_routed_queue

    jitter_countdown = random.randint(5, 25)
    routed_queue = get_routed_queue(utcms_config.CELERY_TASK_QUEUE)

    return process_waybill_task.apply_async(
        args=[task_id],
        queue=routed_queue,
        priority=normalized_priority,
        countdown=jitter_countdown,
    )


def dispatch_fuel_inquiry_task(inquiry_id: int):
    if celery_app is None:
        import threading

        from app.core.database import async_session_factory
        from app.services.fuel_inquiry_service import fuel_inquiry_service

        def run_in_thread():
            async def _run():
                async with async_session_factory() as session:
                    try:
                        await fuel_inquiry_service.run_automation(inquiry_id, session)
                        await session.commit()
                    except Exception as e:
                        await session.rollback()
                        logger.error(f"Thread fuel inquiry failed: {e}")

            _run_async(_run())

        threading.Thread(target=run_in_thread, daemon=True).start()
        return None

    import random

    jitter_countdown = random.randint(1, 3)

    return process_fuel_inquiry_task.apply_async(
        args=[inquiry_id],
        queue=utcms_config.CELERY_FUEL_INQUIRY_QUEUE,
        countdown=jitter_countdown,
    )


if celery_app is not None:
    @celery_app.task(name="orchestrator.scheduler.run")
    def run_scheduler():
        from app.orchestrator.scheduler_service import scheduler_service
        return _run_async(scheduler_service.run())

    @celery_app.task(name="orchestrator.dispatcher.run")
    def run_dispatcher():
        from app.orchestrator.dispatcher_service import dispatcher_service
        return _run_async(dispatcher_service.run())

    @celery_app.task(name="orchestrator.orphan_detector.run")
    def run_orphan_detector():
        from app.orchestrator.orphan_detector import orphan_detector
        return _run_async(orphan_detector.run())

    @celery_app.task(name="orchestrator.claim_reaper.run")
    def run_claim_reaper():
        from app.orchestrator.claim_reaper import claim_reaper
        return _run_async(claim_reaper.run())

    @celery_app.task(name="orchestrator.reconciliation.run")
    def run_reconciliation():
        from app.core.database import async_session_factory
        from app.orchestrator.reconciliation_service import reconciliation_service

        async def _run():
            async with async_session_factory() as session:
                return await reconciliation_service.reconcile_orphaned_jobs(session)

        return _run_async(_run())

    @celery_app.task(name="fuel.cleanup_stale_inquiries")
    def cleanup_stale_fuel_inquiries():
        """Mark abandoned fuel inquiries as stale (every 10 min via beat)."""
        from app.services.fuel_inquiry_service import fuel_inquiry_service
        return _run_async(fuel_inquiry_service.cleanup_stale_inquiries())

