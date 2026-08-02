"""Waybill job management service with tenant isolation."""

import json
import logging
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models_multitenant import (
    Client,
    Driver,
    DriverStatus,
    TaskSource,
    TaskStatus,
    WaybillJob,
    WaybillTaskLog,
)
from app.models_rpa import DomainEvent, DriverRuntimeState, DriverRuntimeStateValue
from app.orchestrator.state_machine import JobStateMachine
from app.rpa.event_taxonomy import (
    JOB_RETRY_REQUESTED,
    timeline_phase_for,
    timeline_title_for,
)
from app.schemas.multitenant import (
    TaskFilterRequest,
    TaskListResponse,
    TaskLogEntry,
    TaskLogsResponse,
    TaskTimelineEntry,
    TaskTimelineQuery,
    TaskTimelineResponse,
    WaybillJobCreateRequest,
    WaybillJobResponse,
    WaybillJobUpdateRequest,
    WaybillRetryRequest,
)
from app.services._helpers import (
    _deep_merge_dict,
    _safe_json_payload,
    _timeline_matches_query,
)
from app.services.rpa_dispatch_service import rpa_dispatch_service
from app.services.rpa_runtime_service import rpa_runtime
from app.services.rpa_scheduler_service import rpa_scheduler_service

logger = logging.getLogger(__name__)


class WaybillJobService:
    """Service for managing waybill jobs with tenant isolation."""

    @staticmethod
    async def create_job(
        client: Client,
        request: WaybillJobCreateRequest,
        session: AsyncSession,
        source: TaskSource = TaskSource.MANUAL,
    ) -> WaybillJobResponse:
        """Create a new waybill job."""
        # Find driver
        driver_stmt = select(Driver).where(
            (Driver.client_id == client.id) & (Driver.driver_national_code == request.driver_national_code)
        )
        driver_result = await session.exec(driver_stmt)
        driver = driver_result.first()

        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver not found",
            )

        job = await rpa_scheduler_service.create_job(
            client_id=client.id or 0,
            driver=driver,
            payload=request.payload.model_dump(),
            source=source,
            max_retries=request.max_retries,
            priority=request.priority,
            correlation_id=request.correlation_id,
            idempotency_key=request.idempotency_key,
        )
        return WaybillJobResponse.model_validate(job)

    @staticmethod
    async def list_jobs(
        user_context: dict,
        session: AsyncSession,
        filters: TaskFilterRequest,
    ) -> TaskListResponse:
        """List jobs for the client with filtering, or all for master admin."""
        if isinstance(user_context, Client):
            user_context = {"role": "client", "user": user_context}
        role = user_context["role"]
        if role == "master_admin":
            statement = select(WaybillJob)
            count_stmt = select(func.count(WaybillJob.id))
        else:
            client = user_context["user"]
            statement = select(WaybillJob).where(WaybillJob.client_id == client.id)
            count_stmt = select(func.count(WaybillJob.id)).where(WaybillJob.client_id == client.id)

        if filters.status:
            statement = statement.where(WaybillJob.status == filters.status)
            count_stmt = count_stmt.where(WaybillJob.status == filters.status)
        if filters.driver_id:
            statement = statement.where(WaybillJob.driver_id == filters.driver_id)
            count_stmt = count_stmt.where(WaybillJob.driver_id == filters.driver_id)
        if filters.driver_name:
            driver_stmt = select(Driver.id).where(Driver.full_name.ilike(f"%{filters.driver_name.strip()}%"))
            driver_ids = (await session.exec(driver_stmt)).all()
            if driver_ids:
                statement = statement.where(col(WaybillJob.driver_id).in_(driver_ids))
                count_stmt = count_stmt.where(col(WaybillJob.driver_id).in_(driver_ids))
            else:
                statement = statement.where(col(WaybillJob.driver_id) == -1)
                count_stmt = count_stmt.where(col(WaybillJob.driver_id) == -1)
        if filters.plate_number:
            plate_kw = filters.plate_number.strip()
            statement = statement.where(col(WaybillJob.payload_json).cast(String).ilike(f"%{plate_kw}%"))
            count_stmt = count_stmt.where(col(WaybillJob.payload_json).cast(String).ilike(f"%{plate_kw}%"))
        if filters.date_from:
            statement = statement.where(WaybillJob.created_at >= filters.date_from)
            count_stmt = count_stmt.where(WaybillJob.created_at >= filters.date_from)
        if filters.date_to:
            statement = statement.where(WaybillJob.created_at <= filters.date_to)
            count_stmt = count_stmt.where(WaybillJob.created_at <= filters.date_to)

        # Get total count
        count_result = await session.exec(count_stmt)
        total = count_result.one()

        # Get paginated results
        statement = statement.order_by(col(WaybillJob.created_at).desc())
        statement = statement.offset((filters.page - 1) * filters.page_size).limit(filters.page_size)

        result = await session.exec(statement)
        jobs = result.all()

        tasks = []
        client_map: dict[int, Client] = {}
        if role != "client" and jobs:
            client_ids = {j.client_id for j in jobs if j.client_id is not None}
            if client_ids:
                client_stmt = select(Client).where(Client.id.in_(client_ids))
                clients = (await session.exec(client_stmt)).all()
                client_map = {c.id: c for c in clients}

        for j in jobs:
            resp = WaybillJobResponse.model_validate(j)
            if role == "client":
                resp.last_error = None
                resp.terminal_reason = None
            else:
                cl = client_map.get(j.client_id)
                if cl:
                    resp.client_name = cl.name
                    resp.client_code = cl.client_code
            tasks.append(resp)

        total_pages = (total + filters.page_size - 1) // filters.page_size

        return TaskListResponse(
            tasks=tasks,
            total=total,
            page=filters.page,
            page_size=filters.page_size,
            total_pages=total_pages,
        )

    @staticmethod
    async def get_job(
        user_context: dict,
        job_id: str,
        session: AsyncSession,
    ) -> WaybillJobResponse:
        """Get a specific job status and details."""
        if isinstance(user_context, Client):
            user_context = {"role": "client", "user": user_context}
        role = user_context["role"]
        if role == "master_admin":
            statement = select(WaybillJob).where(WaybillJob.job_id == job_id)
        else:
            client = user_context["user"]
            statement = select(WaybillJob).where((WaybillJob.client_id == client.id) & (WaybillJob.job_id == job_id))

        result = await session.exec(statement)
        job = result.first()

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found",
            )

        resp = WaybillJobResponse.model_validate(job)
        if role == "client":
            resp.last_error = None
            resp.terminal_reason = None
        else:
            cl = await session.get(Client, job.client_id)
            if cl:
                resp.client_name = cl.name
                resp.client_code = cl.client_code
        return resp

    @staticmethod
    async def retry_job(
        client: Client,
        job_id: str,
        session: AsyncSession,
        request: WaybillRetryRequest | None = None,
    ) -> WaybillJobResponse:
        """Manually retry or requeue a job with optional payload overrides."""
        statement = select(WaybillJob).where((WaybillJob.client_id == client.id) & (WaybillJob.job_id == job_id))
        result = await session.exec(statement)
        job = result.first()

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found",
            )

        if job.status in {TaskStatus.IN_PROGRESS.value, TaskStatus.QUEUED.value}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Job is already being processed",
            )

        retry_request = request or WaybillRetryRequest()
        now = datetime.now(UTC).replace(tzinfo=None)
        event_payload: dict[str, object] = {
            "requested_at": now.isoformat(),
            "dispatch_now": retry_request.dispatch_now,
        }

        payload = _safe_json_payload(job.payload_json) or {}
        if retry_request.retry_with_overrides:
            payload = _deep_merge_dict(payload, retry_request.retry_with_overrides)
            job.payload_json = payload
            event_payload["retry_with_overrides"] = retry_request.retry_with_overrides

        if retry_request.force_auth_refresh and job.driver_id:
            await rpa_runtime.delete_session(client.id or 0, job.driver_id)

            runtime_state = (
                await session.exec(
                    select(DriverRuntimeState).where(
                        DriverRuntimeState.client_id == client.id,
                        DriverRuntimeState.driver_id == job.driver_id,
                    )
                )
            ).first()
            if runtime_state is not None:
                runtime_state.state = DriverRuntimeStateValue.AUTH_REQUIRED.value
                runtime_state.next_retry_at = None
                runtime_state.session_expires_at = None
                runtime_state.last_error_code = None
                runtime_state.updated_at = now
                session.add(runtime_state)

            driver = await session.get(Driver, job.driver_id)
            if driver is not None:
                driver.runtime_status = DriverStatus.AUTH_REQUIRED.value
                driver.last_session_expires_at = None
                driver.last_error_code = None
                driver.updated_at = now
                session.add(driver)

            event_payload["force_auth_refresh"] = True

        JobStateMachine.transition(
            session,
            job,
            TaskStatus.PENDING.value,
            attempt_count=0,
            submit_after=now,
            next_retry_at=None,
            finished_at=None,
            started_at=None,
            retryable=True,
            updated_at=now,
            last_error=None,
            error_category=None,
            terminal_reason=None,
            worker_id=None,
            celery_task_id=None,
        )
        job.retryable = True  # ensure mutable flag is set even when previous status blocked keyword-only fields

        session.add(job)
        session.add(
            DomainEvent(
                event_id=f"evt_retry_{uuid.uuid4().hex[:24]}",
                event_type=JOB_RETRY_REQUESTED,
                client_id=client.id,
                driver_id=job.driver_id,
                job_id=job.job_id,
                payload_json=json.dumps(event_payload, ensure_ascii=False),
            )
        )
        session.add(
            WaybillTaskLog(
                job_id=job.job_id,
                client_id=client.id,
                step="manual_requeue",
                status="pending",
                message="Job manually requeued for immediate retry",
                details_json=event_payload,
            )
        )
        await session.commit()

        if retry_request.dispatch_now:
            dispatch_message = await rpa_dispatch_service.dispatch_waybill_job_now(session, job, now)
            if dispatch_message:
                logger.info(
                    "manual_retry_dispatch", extra={"extra_fields": {"job_id": job.job_id, "message": dispatch_message}}
                )

        await session.refresh(job)
        return WaybillJobResponse.model_validate(job)

    @staticmethod
    async def get_job_timeline(
        user_context: dict,
        job_id: str,
        session: AsyncSession,
        filters: TaskTimelineQuery | None = None,
    ) -> TaskTimelineResponse:
        """Get a merged timeline of domain events and task logs for a job."""
        if isinstance(user_context, Client):
            user_context = {"role": "client", "user": user_context}
        role = user_context["role"]
        query = filters or TaskTimelineQuery()

        if role == "master_admin":
            job_stmt = select(WaybillJob).where(WaybillJob.job_id == job_id)
        else:
            client = user_context["user"]
            job_stmt = select(WaybillJob).where((WaybillJob.client_id == client.id) & (WaybillJob.job_id == job_id))

        job_result = await session.exec(job_stmt)
        job = job_result.first()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found",
            )

        if role == "master_admin":
            logs_stmt = select(WaybillTaskLog).where(WaybillTaskLog.job_id == job_id)
            events_stmt = select(DomainEvent).where(DomainEvent.job_id == job_id)
        else:
            client = user_context["user"]
            logs_stmt = select(WaybillTaskLog).where(
                (WaybillTaskLog.client_id == client.id) & (WaybillTaskLog.job_id == job_id)
            )
            events_stmt = select(DomainEvent).where(
                (DomainEvent.client_id == client.id) & (DomainEvent.job_id == job_id)
            )

        logs = (await session.exec(logs_stmt)).all()
        events = (await session.exec(events_stmt)).all()

        # Calculate progress percent
        progress_percent = 10
        if job.status == "success":
            progress_percent = 100
        elif job.status in ("failed", "dead_letter", "needs_review"):
            progress_percent = 100
        elif job.status == "processing":
            progress_percent = min(15 + len(events) * 15 + len(logs) * 10, 95)

        if role == "client":
            # For client, do not send timeline entries at all
            return TaskTimelineResponse(
                job_id=job.job_id,
                total=0,
                page=query.page,
                page_size=query.page_size,
                entries=[],
                progress_percent=progress_percent,
            )

        # Build detailed timeline entries for admin
        entries: list[TaskTimelineEntry] = []

        for event in events:
            payload = _safe_json_payload(event.payload_json)
            entries.append(
                TaskTimelineEntry(
                    entry_id=event.event_id,
                    job_id=job_id,
                    source="domain_event",
                    event_type=event.event_type,
                    phase=timeline_phase_for(event.event_type, "domain_event"),
                    title=timeline_title_for(event.event_type, "domain_event", payload),
                    status=(payload or {}).get("status") if isinstance(payload, dict) else None,
                    message=(payload or {}).get("message") if isinstance(payload, dict) else None,
                    payload=payload if query.include_payload else None,
                    created_at=event.created_at,
                )
            )

        for log in logs:
            entries.append(
                TaskTimelineEntry(
                    entry_id=f"log_{log.id}",
                    job_id=job_id,
                    source="task_log",
                    event_type=log.step,
                    phase=timeline_phase_for(log.step, "task_log"),
                    title=timeline_title_for(log.step, "task_log"),
                    status=log.status,
                    message=log.message,
                    payload=_safe_json_payload(log.details_json) if query.include_payload else None,
                    created_at=log.created_at,
                )
            )

        entries.sort(key=lambda item: item.created_at)
        filtered_entries = [entry for entry in entries if _timeline_matches_query(entry, query)]
        total = len(filtered_entries)
        start = (query.page - 1) * query.page_size
        end = start + query.page_size
        return TaskTimelineResponse(
            job_id=job.job_id,
            total=total,
            page=query.page,
            page_size=query.page_size,
            entries=filtered_entries[start:end],
            progress_percent=progress_percent,
        )

    @staticmethod
    async def get_job_logs(
        client: Client,
        job_id: str,
        session: AsyncSession,
        page: int = 1,
        page_size: int = 20,
    ) -> TaskLogsResponse:
        """Get execution logs for a job."""
        # Verify job belongs to client
        job_stmt = select(WaybillJob).where((WaybillJob.client_id == client.id) & (WaybillJob.job_id == job_id))
        job_result = await session.exec(job_stmt)
        if not job_result.first():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found",
            )

        # Get paginated logs
        logs_stmt = (
            select(WaybillTaskLog)
            .where((WaybillTaskLog.client_id == client.id) & (WaybillTaskLog.job_id == job_id))
            .order_by(col(WaybillTaskLog.created_at).asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        logs_result = await session.exec(logs_stmt)
        logs = logs_result.all()

        return TaskLogsResponse(
            job_id=job_id,
            logs=[
                TaskLogEntry(
                    id=log.id,
                    job_id=log.job_id,
                    step=log.step,
                    status=log.status,
                    message=log.message,
                    details_json=_safe_json_payload(log.details_json),
                    created_at=log.created_at,
                )
                for log in logs
            ],
        )

    @staticmethod
    async def add_job_log(
        session: AsyncSession,
        job_id: str,
        client_id: int,
        step: str,
        status: str,
        message: str | None = None,
        details_json: str | None = None,
    ) -> None:
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

    @staticmethod
    async def update_job(
        client: Client,
        job_id: str,
        session: AsyncSession,
        request: WaybillJobUpdateRequest,
    ) -> WaybillJobResponse:
        """Update an existing waybill job."""

        statement = select(WaybillJob).where((WaybillJob.client_id == client.id) & (WaybillJob.job_id == job_id))
        result = await session.exec(statement)
        job = result.first()

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found",
            )

        now = datetime.now(UTC).replace(tzinfo=None)
        update_data: dict[str, object] = {"updated_at": now}

        if request.priority is not None:
            update_data["priority"] = request.priority
        if request.max_retries is not None:
            update_data["max_retries"] = request.max_retries
        if request.status is not None:
            update_data["status"] = request.status
        if request.terminal_reason is not None:
            update_data["terminal_reason"] = request.terminal_reason

        for key, value in update_data.items():
            setattr(job, key, value)

        session.add(job)
        await session.commit()
        await session.refresh(job)
        return WaybillJobResponse.model_validate(job)

    @staticmethod
    async def delete_job(client: Client, job_id: str, session: AsyncSession) -> None:
        """Delete a waybill job."""
        statement = select(WaybillJob).where((WaybillJob.client_id == client.id) & (WaybillJob.job_id == job_id))
        result = await session.exec(statement)
        job = result.first()

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found",
            )

        await session.delete(job)
        await session.commit()
