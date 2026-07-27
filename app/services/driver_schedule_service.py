"""Per-driver automatic waybill schedule management service."""

import logging
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth_multitenant import verify_tenant_ownership
from app.models_multitenant import (
    Client,
    Driver,
    DriverSchedule,
    ScheduleFrequency,
    TaskSource,
)
from app.schemas.multitenant import (
    DriverScheduleCreateRequest,
    DriverScheduleResponse,
    DriverScheduleUpdateRequest,
    WaybillJobCreateRequest,
)
from app.services._helpers import (
    _build_csv_list,
    _build_weekdays_csv,
    _parse_csv_list,
    _parse_weekdays_csv,
    _resolve_run_times,
    _safe_json_payload,
)

logger = logging.getLogger(__name__)


class DriverScheduleService:
    """Manage per-driver automatic waybill schedules."""

    @staticmethod
    def _schedule_response(item: DriverSchedule) -> DriverScheduleResponse:
        return DriverScheduleResponse(
            id=item.id,
            client_id=item.client_id,
            driver_id=item.driver_id,
            title=item.title,
            frequency=item.frequency,
            run_time=item.run_time,
            run_times=_resolve_run_times(item),
            weekdays=_parse_weekdays_csv(item.weekdays_csv),
            specific_dates=_parse_csv_list(item.specific_dates_csv),
            start_date=item.start_date,
            end_date=item.end_date,
            timezone=item.timezone,
            payload_template=_safe_json_payload(item.payload_template_json) or {},
            is_active=item.is_active,
            last_run_at=item.last_run_at,
            next_run_at=item.next_run_at,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    @staticmethod
    async def create_schedule(
        client: Client, request: DriverScheduleCreateRequest, session: AsyncSession
    ) -> DriverScheduleResponse:
        driver = await session.get(Driver, request.driver_id)
        if not driver:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Driver not found")
        verify_tenant_ownership(client, driver, Driver)
        schedule = DriverSchedule(
            client_id=client.id,
            driver_id=request.driver_id,
            title=request.title,
            frequency=request.frequency,
            run_time=request.run_time,
            run_times_csv=_build_csv_list(request.run_times),
            weekdays_csv=_build_weekdays_csv(request.weekdays),
            specific_dates_csv=_build_csv_list(request.specific_dates),
            start_date=request.start_date,
            end_date=request.end_date,
            timezone=request.timezone,
            payload_template_json=request.payload_template or {},
            is_active=request.is_active,
        )
        session.add(schedule)
        await session.commit()
        await session.refresh(schedule)
        return DriverScheduleService._schedule_response(schedule)

    @staticmethod
    async def list_schedules(
        client: Client, session: AsyncSession, driver_id: int | None = None, page: int = 1, page_size: int = 20
    ) -> list[DriverScheduleResponse]:
        statement = select(DriverSchedule).where(DriverSchedule.client_id == client.id)
        if driver_id:
            statement = statement.where(DriverSchedule.driver_id == driver_id)
        statement = statement.order_by(col(DriverSchedule.created_at).desc())
        statement = statement.offset((page - 1) * page_size).limit(page_size)
        rows = (await session.exec(statement)).all()
        return [DriverScheduleService._schedule_response(item) for item in rows]

    @staticmethod
    async def update_schedule(
        client: Client,
        schedule_id: int,
        request: DriverScheduleUpdateRequest,
        session: AsyncSession,
    ) -> DriverScheduleResponse:
        item = await session.get(DriverSchedule, schedule_id)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
        verify_tenant_ownership(client, item, DriverSchedule)

        payload = request.model_dump(exclude_unset=True)
        if "weekdays" in payload:
            item.weekdays_csv = _build_weekdays_csv(payload.pop("weekdays"))
        if "run_times" in payload:
            item.run_times_csv = _build_csv_list(payload.pop("run_times"))
        if "specific_dates" in payload:
            item.specific_dates_csv = _build_csv_list(payload.pop("specific_dates"))
        if "payload_template" in payload:
            item.payload_template_json = payload.pop("payload_template") or {}
        for field, value in payload.items():
            setattr(item, field, value)
        item.updated_at = datetime.now(UTC).replace(tzinfo=None)
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return DriverScheduleService._schedule_response(item)

    @staticmethod
    async def delete_schedule(client: Client, schedule_id: int, session: AsyncSession) -> None:
        item = await session.get(DriverSchedule, schedule_id)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
        verify_tenant_ownership(client, item, DriverSchedule)
        await session.delete(item)
        await session.commit()

    @staticmethod
    async def run_due_schedules(client: Client, session: AsyncSession) -> dict:
        # Import here to avoid circular dependency at module level
        from app.services.waybill_job_service import WaybillJobService

        now = datetime.now(UTC).replace(tzinfo=None)
        today = now.date()
        current_hhmm = now.strftime("%H:%M")
        schedules = (
            await session.exec(
                select(DriverSchedule).where(
                    (DriverSchedule.client_id == client.id) & (col(DriverSchedule.is_active).is_(True))
                )
            )
        ).all()
        created_jobs: list[str] = []
        skipped = 0
        # Pre-fetch drivers to avoid N+1 queries
        driver_ids = {s.driver_id for s in schedules}
        drivers_map = {}
        if driver_ids:
            drivers_result = await session.exec(
                select(Driver).where((col(Driver.id).in_(driver_ids)) & (Driver.client_id == client.id))
            )
            drivers_map = {d.id: d for d in drivers_result.all()}

        for schedule in schedules:
            if schedule.next_run_at and schedule.next_run_at > now:
                skipped += 1
                continue
            if schedule.start_date and today < date.fromisoformat(schedule.start_date):
                skipped += 1
                continue
            if schedule.end_date and today > date.fromisoformat(schedule.end_date):
                skipped += 1
                continue
            specific_dates = _parse_csv_list(schedule.specific_dates_csv)
            if specific_dates and today.isoformat() not in specific_dates:
                skipped += 1
                continue
            if schedule.frequency == ScheduleFrequency.WEEKLY.value:
                allowed = _parse_weekdays_csv(schedule.weekdays_csv)
                if allowed and now.weekday() not in allowed:
                    skipped += 1
                    continue
            due_times = [value for value in _resolve_run_times(schedule) if value <= current_hhmm]
            if not due_times:
                skipped += 1
                continue
            target_slot = due_times[-1]
            slot_signature = f"{today.isoformat()}@{target_slot}"
            if schedule.last_run_signature == slot_signature:
                skipped += 1
                continue

            driver = drivers_map.get(schedule.driver_id)
            if not driver:
                skipped += 1
                continue

            payload = _safe_json_payload(schedule.payload_template_json) or {}
            if "driver_national_code" not in payload:
                payload["driver_national_code"] = driver.driver_national_code
            request = WaybillJobCreateRequest(
                driver_national_code=driver.driver_national_code,
                payload=payload,  # type: ignore[arg-type]
                priority=5,
                max_retries=3,
                idempotency_key=f"schedule:{schedule.id}:{slot_signature}",
            )
            job = await WaybillJobService.create_job(client, request, session, source=TaskSource.API)
            created_jobs.append(job.job_id)
            schedule.last_run_at = now
            schedule.last_run_signature = slot_signature
            if schedule.frequency == ScheduleFrequency.ONCE.value:
                schedule.is_active = False
                schedule.next_run_at = None
            else:
                schedule.next_run_at = now + timedelta(
                    days=1 if schedule.frequency == ScheduleFrequency.DAILY.value else 7
                )
            schedule.updated_at = now
            session.add(schedule)
        await session.commit()
        return {"created_jobs": created_jobs, "created_count": len(created_jobs), "skipped": skipped}
