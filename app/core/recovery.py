import asyncio
import logging

from app.core.alerts import alert_manager
from app.core.config import utcms_config
from app.core.worker_heartbeat import worker_heartbeat_registry
from app.services.task_service import task_service
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


class RecoveryManager:
    async def recover_stalled_tasks(self) -> dict[str, dict[str, float | str]]:
        stalled = worker_heartbeat_registry.detect_stalled(utcms_config.WORKER_STALL_TIMEOUT_SECONDS)
        for task_id, payload in stalled.items():
            task_status = await task_service.get_task_status(task_id)
            if not task_status:
                continue

            celery_task_id = task_status.get("celery_task_id")
            if celery_app is not None and celery_task_id:
                try:
                    celery_app.control.revoke(celery_task_id, terminate=True)
                except Exception as exc:
                    logger.warning(
                        "stalled_task_revoke_failed",
                        extra={"extra_fields": {"task_id": task_id, "error": str(exc)}},
                    )

            retryable = task_status.get("attempt_count", 0) < task_status.get("max_retries", 0)
            if retryable:
                await task_service.mark_retrying(
                    task_id=task_id,
                    error_text="worker_stalled_recovered",
                    category="WORKER_RESOURCE_ERROR",
                    attempt_count=task_status.get("attempt_count", 0) + 1,
                )
            else:
                await task_service.mark_failure(
                    task_id=task_id,
                    error_text="worker_stalled_dead_letter",
                    category="WORKER_RESOURCE_ERROR",
                    attempt_count=task_status.get("attempt_count", 0),
                    retryable=False,
                    dead_letter=True,
                )
            alert_manager.emit(
                "error",
                "worker_stalled_recovery",
                {"task_id": task_id, "correlation_id": task_status.get("correlation_id"), "payload": payload},
            )
        return stalled

    async def watchdog_loop(self) -> None:
        while True:
            try:
                await self.recover_stalled_tasks()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("recovery_watchdog_failed", extra={"extra_fields": {"error": str(exc)}})
            await asyncio.sleep(max(5.0, utcms_config.WORKER_HEARTBEAT_INTERVAL_SECONDS))


recovery_manager = RecoveryManager()
