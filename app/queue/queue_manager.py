from typing import Any

from fastapi import HTTPException

from app.core.config import utcms_config
from app.core.error_taxonomy import classify_exception
from app.core.exceptions import WaybillError
from app.core.execution_context import generate_correlation_id
from app.core.network import is_retryable_network_error
from app.schemas.task import EnqueueWaybillResponse, TaskStatus
from app.schemas.waybill import WaybillMapRequest
from app.services.task_service import task_service
from app.services.waybill_service import waybill_service
from app.workers.tasks import dispatch_waybill_task


class WaybillQueueManager:
    async def enqueue_waybill(
        self,
        request: WaybillMapRequest,
        idempotency_key: str | None = None,
    ) -> EnqueueWaybillResponse:
        payload = request.model_dump()
        payload["correlation_id"] = (payload.get("correlation_id") or generate_correlation_id()).strip()
        payload["batch_id"] = (payload.get("batch_id") or payload.get("session_id") or payload["correlation_id"]).strip()
        normalized_key = task_service.build_idempotency_key(payload, idempotency_key)
        task, reused = await task_service.create_or_get_task(
            payload=payload,
            idempotency_key=normalized_key,
            max_retries=utcms_config.CELERY_MAX_RETRIES,
        )

        if reused:
            return EnqueueWaybillResponse(
                task_id=task.task_id,
                idempotency_key=task.idempotency_key,
                correlation_id=payload["correlation_id"],
                priority=int(payload.get("priority", utcms_config.CELERY_DEFAULT_PRIORITY)),
                status=TaskStatus(task.status),
                queued=task.status in {TaskStatus.QUEUED.value, TaskStatus.RETRYING.value, TaskStatus.PROCESSING.value},
                reused=True,
                celery_task_id=task.celery_task_id,
            )

        if utcms_config.QUEUE_ENABLED:
            try:
                async_result = dispatch_waybill_task(
                    task.task_id,
                    priority=int(payload.get("priority", utcms_config.CELERY_DEFAULT_PRIORITY)),
                )
                await task_service.set_celery_task_id(task.task_id, async_result.id)
                return EnqueueWaybillResponse(
                    task_id=task.task_id,
                    idempotency_key=task.idempotency_key,
                    correlation_id=payload["correlation_id"],
                    priority=int(payload.get("priority", utcms_config.CELERY_DEFAULT_PRIORITY)),
                    status=TaskStatus.QUEUED,
                    queued=True,
                    reused=False,
                    celery_task_id=async_result.id,
                )
            except Exception as exc:
                if not utcms_config.QUEUE_INLINE_FALLBACK:
                    await task_service.mark_failure(
                        task_id=task.task_id,
                        error_text=f"queue_dispatch_failed: {exc}",
                        category="queue",
                        attempt_count=1,
                        retryable=True,
                    )
                    raise HTTPException(
                        status_code=503,
                        detail="صف Celery در دسترس نیست و fallback غیرفعال است",
                    )

        return await self._execute_inline(task.task_id, task.idempotency_key)

    async def _execute_inline(self, task_id: str, idempotency_key: str) -> EnqueueWaybillResponse:
        payload = await task_service.get_payload(task_id)
        if payload is None:
            raise HTTPException(status_code=500, detail="payload تسک یافت نشد")

        await task_service.mark_processing(task_id, worker_id="inline-api", attempt_count=1)
        try:
            result = await waybill_service.create_waybill_with_map(WaybillMapRequest.model_validate(payload))
            await task_service.mark_success(task_id, result=result, attempt_count=1)
        except Exception as exc:
            category, retryable = self._classify_inline_error(exc)
            await task_service.mark_failure(
                task_id=task_id,
                error_text=str(exc),
                category=category,
                attempt_count=1,
                retryable=retryable,
            )
            raise

        return EnqueueWaybillResponse(
            task_id=task_id,
            idempotency_key=idempotency_key,
            correlation_id=payload.get("correlation_id", task_id),
            priority=int(payload.get("priority", utcms_config.CELERY_DEFAULT_PRIORITY)),
            status=TaskStatus.SUCCEEDED,
            queued=False,
            reused=False,
            celery_task_id=None,
        )

    @staticmethod
    def _classify_inline_error(error: Exception) -> tuple[str, bool]:
        category, retryable = classify_exception(error)
        if category.value:
            return category.value, retryable
        if isinstance(error, HTTPException):
            if error.status_code in {401, 403}:
                return "auth", False
            if error.status_code == 429:
                return "network", True
            if error.status_code >= 500:
                return "network", True
            return "form", False

        if isinstance(error, WaybillError):
            retryable = is_retryable_network_error(error)
            return ("network" if retryable else "form"), retryable

        retryable = is_retryable_network_error(error)
        if retryable:
            return "network", True

        text = str(error).lower()
        if "captcha" in text:
            return "captcha", False
        if "login" in text or "auth" in text or "credential" in text:
            return "auth", False
        if "map" in text or "location" in text:
            return "map", False
        if "validation" in text or "field" in text or "form" in text:
            return "form", False
        return "unknown", False

    async def get_task_status(self, task_id: str) -> dict[str, Any] | None:
        return await task_service.get_task_status(task_id)

    async def snapshot(self) -> dict[str, int]:
        return await task_service.queue_snapshot()


queue_manager = WaybillQueueManager()
