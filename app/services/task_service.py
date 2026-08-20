import asyncio
import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.alerts import alert_manager
from app.core.config import utcms_config
from app.core.database import async_session_factory
from app.core.execution_context import generate_correlation_id
from app.core.redis_client import redis_manager
from app.models_legacy import WaybillTask
from app.models_multitenant import WaybillJob
from app.monitoring.metrics import set_queue_depth, summarize_queue_depth, track_task_status
from app.realtime.events import event_hub
from app.schemas.task import TaskStatus

logger = logging.getLogger(__name__)

# Maximum length for idempotency keys before SHA-256 hashing
# Configurable via IDEMPOTENCY_KEY_MAX_LENGTH environment variable (default: 200)
IDEMPOTENCY_KEY_MAX_LENGTH = utcms_config.IDEMPOTENCY_KEY_MAX_LENGTH


class WaybillTaskService:
    QUEUE_DEPTH_KEY = "waybill:queue_depth"
    QUEUE_DEPTH_SEEDED = "waybill:queue_depth:seeded"

    @staticmethod
    def build_idempotency_key(payload: dict[str, Any], provided: str | None = None) -> str:
        candidate = str(provided).strip() if provided is not None else None
        if candidate:
            if len(candidate) > IDEMPOTENCY_KEY_MAX_LENGTH:
                digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
                return f"user-{digest}"
            return candidate

        from app.core.submission_identity import compute_canonical_payload_digest

        digest = compute_canonical_payload_digest(payload)
        return f"auto-{digest}"

    async def create_or_get_task(
        self,
        payload: dict[str, Any],
        idempotency_key: str,
        client_id: int,
        driver_id: int | None = None,
        max_retries: int | None = None,
    ) -> tuple[dict[str, Any], bool]:
        retries = utcms_config.CELERY_MAX_RETRIES if max_retries is None else max_retries
        payload.setdefault("correlation_id", generate_correlation_id())
        payload.setdefault("batch_id", payload.get("session_id") or payload["correlation_id"])
        task_payload = json.dumps(payload, ensure_ascii=False)

        async with async_session_factory() as session:
            existing = await self._find_by_idempotency_key(session, idempotency_key)
            if existing:
                await self._sync_queue_depth()
                return self._to_public_dict(existing), True

            task = WaybillJob(
                job_id=f"job_{uuid.uuid4().hex[:16]}",
                idempotency_key=idempotency_key,
                status=TaskStatus.PENDING.value,
                payload_json=task_payload,
                max_retries=max(0, int(retries)),
                retryable=False,
                client_id=client_id,
                driver_id=driver_id,
                source="legacy",
                correlation_id=payload.get("correlation_id", generate_correlation_id()),
                business_date=datetime.now(UTC).strftime("%Y-%m-%d"),
                priority=payload.get("priority", utcms_config.CELERY_DEFAULT_PRIORITY),
                submit_after=datetime.now(UTC).replace(tzinfo=None),
            )
            session.add(task)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                for attempt in range(5):
                    await asyncio.sleep(0.05 * (attempt + 1))
                    async with async_session_factory() as read_session:
                        existing = await self._find_by_idempotency_key(read_session, idempotency_key)
                        if existing:
                            await self._sync_queue_depth()
                            return self._to_public_dict(existing), True
                raise
            await session.refresh(task)
            track_task_status(TaskStatus.PENDING.value)
            await self._sync_queue_depth()
            await self._emit_task_event(task.job_id, TaskStatus.PENDING.value)
            return self._to_public_dict(task), False

    async def set_celery_task_id(self, task_id: str, celery_task_id: str) -> None:
        await self._update_task(
            task_id,
            lambda task: self._apply_updates(
                task,
                {
                    "celery_task_id": celery_task_id,
                    "updated_at": datetime.now(UTC).replace(tzinfo=None),
                },
            ),
        )
        # For WaybillJob, task_id is job_id
        await self._emit_task_event(task_id, "dispatched")

    async def mark_processing(self, task_id: str, worker_id: str | None, attempt_count: int) -> None:
        await self._update_task(
            task_id,
            lambda task: self._apply_updates(
                task,
                {
                    "status": TaskStatus.PROCESSING.value,
                    "worker_id": worker_id,
                    "attempt_count": max(1, attempt_count),
                    "started_at": task.started_at or datetime.now(UTC).replace(tzinfo=None),
                    "updated_at": datetime.now(UTC).replace(tzinfo=None),
                },
            ),
            metric_status=TaskStatus.PROCESSING.value,
        )
        await self._emit_task_event(task_id, TaskStatus.PROCESSING.value)

    async def mark_retrying(
        self,
        task_id: str,
        error_text: str,
        category: str,
        attempt_count: int,
    ) -> None:
        await self._update_task(
            task_id,
            lambda task: self._apply_updates(
                task,
                {
                    "status": TaskStatus.RETRYING.value,
                    "last_error": error_text[:3000],
                    "error_category": category,
                    "retryable": True,
                    "attempt_count": max(1, attempt_count),
                    "updated_at": datetime.now(UTC).replace(tzinfo=None),
                },
            ),
            metric_status=TaskStatus.RETRYING.value,
        )
        await self._emit_task_event(task_id, TaskStatus.RETRYING.value)

    async def mark_success(self, task_id: str, result: dict[str, Any], attempt_count: int) -> None:
        await self._update_task(
            task_id,
            lambda task: self._apply_updates(
                task,
                {
                    "status": TaskStatus.SUCCEEDED.value,
                    "result_json": json.dumps(result, ensure_ascii=False),
                    "last_error": None,
                    "retryable": False,
                    "attempt_count": max(1, attempt_count),
                    "finished_at": datetime.now(UTC).replace(tzinfo=None),
                    "updated_at": datetime.now(UTC).replace(tzinfo=None),
                },
            ),
            metric_status=TaskStatus.SUCCEEDED.value,
        )
        await self._emit_task_event(task_id, TaskStatus.SUCCEEDED.value)

    async def mark_failure(
        self,
        task_id: str,
        error_text: str,
        category: str,
        attempt_count: int,
        retryable: bool,
        dead_letter: bool = False,
    ) -> None:
        next_status = TaskStatus.DEAD_LETTER.value if dead_letter else TaskStatus.FAILED.value
        await self._update_task(
            task_id,
            lambda task: self._apply_updates(
                task,
                {
                    "status": next_status,
                    "last_error": error_text[:3000],
                    "error_category": category,
                    "retryable": bool(retryable),
                    "attempt_count": max(1, attempt_count),
                    "finished_at": datetime.now(UTC).replace(tzinfo=None),
                    "updated_at": datetime.now(UTC).replace(tzinfo=None),
                },
            ),
            metric_status=next_status,
        )
        await self._emit_task_event(task_id, next_status)
        if dead_letter or not retryable:
            status = await self.get_task_status(task_id)
            alert_manager.emit(
                "warning" if retryable else "error",
                "waybill_task_failure",
                {
                    "task_id": task_id,
                    "status": next_status,
                    "category": category,
                    "attempt_count": attempt_count,
                    "retryable": retryable,
                    "correlation_id": (status or {}).get("correlation_id", task_id),
                },
            )

    async def get_task_status(self, task_id: str) -> dict[str, Any] | None:
        async with async_session_factory() as session:
            if task_id.startswith("job_"):
                statement = select(WaybillJob).where(WaybillJob.job_id == task_id)
                result = await session.exec(statement)
                job = result.first()
                if not job:
                    return None
                return self._to_public_dict(job)

            statement = select(WaybillTask).where(WaybillTask.task_id == task_id)
            result = await session.exec(statement)
            task = result.first()
            if not task:
                return None
            return self._to_public_dict(task)

    async def get_payload(self, task_id: str) -> dict[str, Any] | None:
        async with async_session_factory() as session:
            if task_id.startswith("job_"):
                statement = select(WaybillJob).where(WaybillJob.job_id == task_id)
                result = await session.exec(statement)
                job = result.first()
                if not job:
                    return None
                return self._safe_json_load(job.payload_json)

            statement = select(WaybillTask).where(WaybillTask.task_id == task_id)
            result = await session.exec(statement)
            task = result.first()
            if not task:
                return None
            return self._safe_json_load(task.payload_json)

    async def queue_snapshot(self) -> dict[str, int]:
        async with async_session_factory() as session:
            task_statuses = (await session.exec(select(WaybillJob.status))).all()
            counters = {
                TaskStatus.QUEUED.value: 0,
                TaskStatus.PROCESSING.value: 0,
                TaskStatus.RETRYING.value: 0,
                TaskStatus.OTP_BACKOFF.value: 0,
                TaskStatus.SUCCEEDED.value: 0,
                TaskStatus.FAILED.value: 0,
                TaskStatus.DEAD_LETTER.value: 0,
            }
            for status in task_statuses:
                if status in counters:
                    counters[status] += 1
            return {
                "queued": counters[TaskStatus.QUEUED.value],
                "processing": counters[TaskStatus.PROCESSING.value],
                "retrying": counters[TaskStatus.RETRYING.value],
                "otp_backoff": counters[TaskStatus.OTP_BACKOFF.value],
                "succeeded": counters[TaskStatus.SUCCEEDED.value],
                "failed": counters[TaskStatus.FAILED.value],
                "dead_letter": counters[TaskStatus.DEAD_LETTER.value],
            }

    async def list_tasks(self, limit: int = 50) -> list[dict[str, Any]]:
        async with async_session_factory() as session:
            statement = select(WaybillJob).order_by(WaybillJob.updated_at.desc()).limit(max(1, min(500, int(limit))))
            result = await session.exec(statement)
            tasks = result.all()
            return [self._to_public_dict(task) for task in tasks]

    async def _find_by_idempotency_key(self, session: AsyncSession, key: str) -> WaybillJob | None:
        statement = select(WaybillJob).where(WaybillJob.idempotency_key == key)
        result = await session.exec(statement)
        return result.first()

    async def _update_task(self, task_id: str, updater, metric_status: str | None = None) -> None:
        if task_id.startswith("job_"):
            await self._ensure_queue_depth_seeded()
        async with async_session_factory() as session:
            if task_id.startswith("job_"):
                statement = select(WaybillJob).where(WaybillJob.job_id == task_id)
                result = await session.exec(statement)
                job = result.first()
                if not job:
                    return
                old_status = job.status
                updater(job)
                new_status = job.status
                session.add(job)
                await session.commit()
                await self._adjust_queue_depth(old_status, new_status)
            else:
                statement = select(WaybillTask).where(WaybillTask.task_id == task_id)
                result = await session.exec(statement)
                task = result.first()
                if not task:
                    return
                updater(task)
                session.add(task)
                await session.commit()

        if metric_status:
            track_task_status(metric_status)
        await self._sync_queue_depth()

    async def _sync_queue_depth(self) -> None:
        snapshot = await self._queue_depth_snapshot()
        set_queue_depth(summarize_queue_depth(snapshot))

    @staticmethod
    def _queue_depth_status_values() -> tuple[str, ...]:
        return (
            TaskStatus.QUEUED.value,
            TaskStatus.PROCESSING.value,
            TaskStatus.RETRYING.value,
            TaskStatus.OTP_BACKOFF.value,
            TaskStatus.SUCCEEDED.value,
            TaskStatus.FAILED.value,
            TaskStatus.DEAD_LETTER.value,
        )

    async def _ensure_queue_depth_seeded(self) -> dict[str, int]:
        try:
            redis = await redis_manager.get()
            if redis is not None and await redis.get(self.QUEUE_DEPTH_SEEDED):
                return await self._queue_depth_snapshot()
        except Exception:
            logger.warning("queue_depth_redis_unavailable", exc_info=True)
            return await self.queue_snapshot()
        return await self.reconcile_queue_depth()

    async def _queue_depth_snapshot(self) -> dict[str, int]:
        try:
            redis = await redis_manager.get()
        except Exception:
            logger.warning("queue_depth_redis_snapshot_unavailable", exc_info=True)
            return await self.queue_snapshot()
        if redis is None:
            return await self.queue_snapshot()
        try:
            values = await redis.hgetall(self.QUEUE_DEPTH_KEY)
        except Exception:
            logger.warning("queue_depth_redis_snapshot_command_failed", exc_info=True)
            return await self.queue_snapshot()
        return {status: int(values.get(status, 0)) for status in self._queue_depth_status_values()}

    async def _adjust_queue_depth(self, old_status: str | None, new_status: str | None) -> None:
        if old_status == new_status:
            return
        try:
            redis = await redis_manager.get()
        except Exception:
            logger.warning("queue_depth_redis_adjust_unavailable", exc_info=True)
            return
        if redis is None:
            return
        try:
            await self._ensure_queue_depth_seeded()
            if old_status in self._queue_depth_status_values():
                await redis.hincrby(self.QUEUE_DEPTH_KEY, old_status, -1)
            if new_status in self._queue_depth_status_values():
                await redis.hincrby(self.QUEUE_DEPTH_KEY, new_status, 1)
        except Exception:
            logger.warning("queue_depth_redis_adjust_command_failed", exc_info=True)

    async def reconcile_queue_depth(self) -> dict[str, int]:
        snapshot = await self.queue_snapshot()
        try:
            redis = await redis_manager.get()
        except Exception:
            logger.warning("queue_depth_redis_reconcile_unavailable", exc_info=True)
            return snapshot
        if redis is not None:
            try:
                await redis.hset(self.QUEUE_DEPTH_KEY, mapping=snapshot)
                await redis.set(self.QUEUE_DEPTH_SEEDED, "1")
            except Exception:
                logger.warning("queue_depth_redis_reconcile_command_failed", exc_info=True)
        return snapshot

    @staticmethod
    def _safe_json_load(raw: str | None) -> dict[str, Any] | None:
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _apply_updates(task: Any, updates: dict[str, Any]) -> None:
        for key, value in updates.items():
            setattr(task, key, value)

    def _to_public_dict(self, task) -> dict[str, Any]:
        is_job = hasattr(task, "job_id")
        return {
            "task_id": task.job_id if is_job else task.task_id,
            "client_id": task.client_id if is_job else None,
            "idempotency_key": task.idempotency_key,
            "status": task.status,
            "correlation_id": self._extract_correlation_id(task),
            "priority": self._extract_priority(task),
            "attempt_count": task.attempt_count,
            "max_retries": task.max_retries,
            "retryable": task.retryable,
            "celery_task_id": task.celery_task_id,
            "worker_id": task.worker_id,
            "error_category": task.error_category,
            "last_error": task.last_error,
            "result": self._safe_json_load(task.result_json),
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "started_at": task.started_at,
            "finished_at": task.finished_at,
        }

    def _extract_correlation_id(self, task: WaybillTask) -> str:
        payload = self._safe_json_load(task.payload_json) or {}
        correlation_id = payload.get("correlation_id")
        if isinstance(correlation_id, str) and correlation_id.strip():
            return correlation_id.strip()
        return task.task_id

    def _extract_priority(self, task: WaybillTask) -> int:
        payload = self._safe_json_load(task.payload_json) or {}
        try:
            priority = int(payload.get("priority", utcms_config.CELERY_DEFAULT_PRIORITY))
        except Exception:
            priority = utcms_config.CELERY_DEFAULT_PRIORITY
        return max(utcms_config.CELERY_MIN_PRIORITY, min(utcms_config.CELERY_MAX_PRIORITY, priority))

    async def _get_task_status_and_payload(self, task_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        async with async_session_factory() as session:
            if task_id.startswith("job_"):
                statement = select(WaybillJob).where(WaybillJob.job_id == task_id)
                result = await session.exec(statement)
                row = result.first()
                if not row:
                    return None, None
                return self._to_public_dict(row), self._safe_json_load(row.payload_json)

            statement = select(WaybillTask).where(WaybillTask.task_id == task_id)
            result = await session.exec(statement)
            row = result.first()
            if not row:
                return None, None
            return self._to_public_dict(row), self._safe_json_load(row.payload_json)

    async def _emit_task_event(self, task_id: str, event_type: str) -> None:
        status, payload = await self._get_task_status_and_payload(task_id)
        if not status:
            return
        payload = payload or {}
        await event_hub.publish(
            {
                "type": event_type,
                "task_id": status["task_id"],
                "tenant_id": status.get("client_id"),
                "correlation_id": status["correlation_id"],
                "batch_id": payload.get("batch_id"),
                "priority": status["priority"],
                "status": status["status"],
                "attempt_count": status["attempt_count"],
                "worker_id": status.get("worker_id"),
                "updated_at": status["updated_at"].isoformat() if status.get("updated_at") else None,
            }
        )


task_service = WaybillTaskService()
