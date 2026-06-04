import asyncio
import time
from typing import Any

from fastapi import HTTPException

from app.core.config import utcms_config
from app.core.error_taxonomy import classify_exception
from app.core.execution_context import bind_execution_context, reset_execution_context
from app.core.network import is_retryable_network_error
from app.core.worker_heartbeat import heartbeat_lease, worker_heartbeat_registry
from app.monitoring.metrics import track_task_latency
from app.schemas.waybill import WaybillMapRequest
from app.services.task_service import task_service
from app.services.waybill_service import waybill_service
from app.workers.celery_app import celery_app


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("Cannot run task coroutine inside an active event loop")


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


if celery_app is not None:
    @celery_app.task(bind=True, name="app.workers.tasks.process_waybill_task")
    def process_waybill_task(self, task_id: str) -> Any:
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
            with heartbeat_lease(
                task_id,
                worker_id=worker_id,
                correlation_id=str(payload.get("correlation_id") or task_id),
                batch_id=str(payload.get("batch_id") or task_id),
                interval_seconds=utcms_config.WORKER_HEARTBEAT_INTERVAL_SECONDS,
            ):
                worker_heartbeat_registry.beat(task_id, current_step="execute_waybill")
                try:
                    result = _run_async(waybill_service.create_waybill_with_map(request))
                except Exception as exc:
                    retryable = _is_retryable_exception(exc)
                    category = _error_category(exc)
                    worker_heartbeat_registry.beat(task_id, status="failing", current_step=category)

                    if retryable and self.request.retries < max_retries:
                        _run_async(
                            task_service.mark_retrying(
                                task_id=task_id,
                                error_text=str(exc),
                                category=category,
                                attempt_count=attempt,
                            )
                        )
                        raise self.retry(exc=exc, countdown=_retry_delay_seconds(attempt))

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

                worker_heartbeat_registry.finish(task_id, "succeeded")
                _run_async(task_service.mark_success(task_id=task_id, result=result, attempt_count=attempt))
                track_task_latency(time.perf_counter() - started_at)
                return result
        finally:
            reset_execution_context(execution_tokens)
else:
    def process_waybill_task(*_args, **_kwargs):
        raise RuntimeError("Celery is not installed")


def dispatch_waybill_task(task_id: str, priority: int | None = None):
    if celery_app is None:
        raise RuntimeError("Celery is not available in current environment")
    normalized_priority = utcms_config.CELERY_DEFAULT_PRIORITY if priority is None else int(priority)
    normalized_priority = max(utcms_config.CELERY_MIN_PRIORITY, min(utcms_config.CELERY_MAX_PRIORITY, normalized_priority))
    
    import random
    jitter_countdown = random.randint(3, 10)

    return process_waybill_task.apply_async(
        args=[task_id],
        queue=utcms_config.CELERY_TASK_QUEUE,
        priority=normalized_priority,
        countdown=jitter_countdown,
    )
