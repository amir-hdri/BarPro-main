"""
User-facing reporting service for the multi-tenant panel.

Provides:
- Driver and plate lists with status
- Waybill history (success/failure)
- Error details and causes
- Auto-execution timestamps and schedule status
- Per-driver performance summaries
"""

import logging
from collections import defaultdict
from datetime import UTC, datetime, time, timedelta
from typing import Any

from sqlalchemy import case, func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.jalali import tehran_day_end_utc, tehran_day_start_utc
from app.models_multitenant import (
    Client,
    Driver,
    DriverPlate,
    DriverSchedule,
    TaskStatus,
    WaybillJob,
    WaybillTaskLog,
)
from app.models_rpa import DriverRuntimeState

logger = logging.getLogger(__name__)


class UserReportingService:
    """Reports accessible to a single client about their own data."""

    async def driver_list_with_status(
        self,
        client: Client,
        session: AsyncSession,
        page: int = 1,
        page_size: int = 20,
    ) -> list[dict[str, Any]]:
        # client is a DB-loaded row: the PK is always populated at runtime.
        assert client.id is not None, "client must be a persisted row"
        stmt = select(Driver).where(Driver.client_id == client.id).order_by(col(Driver.created_at).desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await session.exec(stmt)
        drivers = result.all()

        if not drivers:
            return []

        driver_ids = [d.id for d in drivers]

        # Fetch all related WaybillJobs (aggregated). The six-column select
        # does not fit sqlmodel's typed select() overloads, so it is split
        # into two narrower queries with identical semantics; merged below.
        failed_statuses = [TaskStatus.FAILED.value, TaskStatus.DEAD_LETTER.value, TaskStatus.NEEDS_REVIEW.value]
        pending_statuses = [TaskStatus.PENDING.value, TaskStatus.QUEUED.value, TaskStatus.IN_PROGRESS.value]

        counts_stmt = (
            select(
                col(WaybillJob.driver_id),
                func.count(col(WaybillJob.id)).label("total_jobs"),
                func.sum(case((col(WaybillJob.status) == TaskStatus.SUCCESS.value, 1), else_=0)).label("success_jobs"),
                func.sum(case((col(WaybillJob.status).in_(failed_statuses), 1), else_=0)).label("failed_jobs"),
            )
            .where(col(WaybillJob.client_id) == client.id, col(WaybillJob.driver_id).in_(driver_ids))
            .group_by(col(WaybillJob.driver_id))
        )
        counts_by_driver: dict[Any, dict[str, Any]] = {}
        for driver_id_val, total_v, success_v, failed_v in (await session.exec(counts_stmt)).all():
            counts_by_driver[driver_id_val] = {
                "total_jobs": total_v,
                "success_jobs": success_v,
                "failed_jobs": failed_v,
            }

        pending_stmt = (
            select(
                col(WaybillJob.driver_id),
                func.sum(case((col(WaybillJob.status).in_(pending_statuses), 1), else_=0)).label("pending_jobs"),
                func.max(col(WaybillJob.created_at)).label("last_job_at"),
            )
            .where(col(WaybillJob.client_id) == client.id, col(WaybillJob.driver_id).in_(driver_ids))
            .group_by(col(WaybillJob.driver_id))
        )
        pending_by_driver: dict[Any, dict[str, Any]] = {}
        for driver_id_val, pending_v, last_job_v in (await session.exec(pending_stmt)).all():
            pending_by_driver[driver_id_val] = {
                "pending_jobs": pending_v,
                "last_job_at": last_job_v,
            }

        # Fetch all DriverRuntimeStates
        runtime_stmt = select(DriverRuntimeState).where(col(DriverRuntimeState.driver_id).in_(driver_ids))
        runtime_result = await session.exec(runtime_stmt)
        runtime_by_driver: dict[int | None, DriverRuntimeState] = {r.driver_id: r for r in runtime_result.all()}

        # Fetch all DriverSchedules
        schedules_stmt = select(DriverSchedule).where(
            DriverSchedule.client_id == client.id,
            col(DriverSchedule.driver_id).in_(driver_ids),
        )
        schedules_result = await session.exec(schedules_stmt)
        schedules_by_driver: defaultdict[int | None, list[DriverSchedule]] = defaultdict(list)
        for schedule in schedules_result.all():
            schedules_by_driver[schedule.driver_id].append(schedule)

        # Fetch all DriverPlates
        plates_stmt = select(DriverPlate).where(
            DriverPlate.client_id == client.id,
            col(DriverPlate.driver_id).in_(driver_ids),
        )
        plates_result = await session.exec(plates_stmt)
        plates_by_driver: defaultdict[int | None, list[DriverPlate]] = defaultdict(list)
        for plate in plates_result.all():
            plates_by_driver[plate.driver_id].append(plate)

        output = []
        for driver in drivers:
            stats = counts_by_driver.get(driver.id)
            pstats = pending_by_driver.get(driver.id)

            total = int(stats["total_jobs"]) if stats and stats["total_jobs"] else 0
            success = int(stats["success_jobs"]) if stats and stats["success_jobs"] else 0
            failed = int(stats["failed_jobs"]) if stats and stats["failed_jobs"] else 0
            pending = int(pstats["pending_jobs"]) if pstats and pstats["pending_jobs"] else 0
            last_job_at = pstats["last_job_at"].isoformat() if pstats and pstats["last_job_at"] else None

            schedules = schedules_by_driver.get(driver.id, [])
            plates = plates_by_driver.get(driver.id, [])

            # Using bulk-fetched runtime state if available, falling back to driver's cached state
            runtime_state = runtime_by_driver.get(driver.id)
            runtime_status = runtime_state.state if runtime_state else driver.runtime_status

            output.append(
                {
                    "driver_id": driver.id,
                    "driver_name": driver.full_name,
                    "national_code": driver.driver_national_code,
                    "phone": driver.phone,
                    "status": driver.status,
                    "runtime_status": runtime_status,
                    "last_auth_at": driver.last_auth_at.isoformat() if driver.last_auth_at else None,
                    "last_session_expires_at": (
                        driver.last_session_expires_at.isoformat() if driver.last_session_expires_at else None
                    ),
                    "last_error_code": driver.last_error_code,
                    "total_jobs": total,
                    "success_jobs": success,
                    "failed_jobs": failed,
                    "pending_jobs": pending,
                    "last_job_at": last_job_at,
                    "success_rate": round(success / max(1, total) * 100, 2),
                    "schedules": [
                        {
                            "id": s.id,
                            "title": s.title,
                            "is_active": s.is_active,
                            "frequency": s.frequency,
                            "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None,
                            "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
                        }
                        for s in schedules
                    ],
                    "plates": [
                        {
                            "id": p.id,
                            "plate_number": p.plate_number,
                            "vehicle_type": p.vehicle_type,
                            "status": p.status,
                        }
                        for p in plates
                    ],
                }
            )
        return output

    async def get_filter_options(
        self,
        client: Client,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """Get distinct driver and plate filter options for the client."""
        drivers_res = await session.exec(select(Driver).where(Driver.client_id == client.id).order_by(Driver.full_name))
        drivers = drivers_res.all()

        plates_res = await session.exec(
            select(DriverPlate).where(DriverPlate.client_id == client.id).order_by(DriverPlate.plate_number)
        )
        plates = plates_res.all()

        return {
            "drivers": [
                {
                    "id": d.id,
                    "full_name": d.full_name,
                    "driver_national_code": d.driver_national_code,
                }
                for d in drivers
            ],
            "plates": [
                {
                    "id": p.id,
                    "plate_number": p.plate_number,
                    "driver_id": p.driver_id,
                }
                for p in plates
            ],
        }

    async def waybill_history(
        self,
        client: Client,
        session: AsyncSession,
        driver_id: int | None = None,
        driver_name: str | None = None,
        plate_number: str | None = None,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        from sqlalchemy import or_

        # client is a DB-loaded row: the PK is always populated at runtime.
        assert client.id is not None, "client must be a persisted row"

        driver_subquery = None
        if driver_name:
            d_stmt = select(col(Driver.id)).where(
                Driver.client_id == client.id,
                col(Driver.full_name).contains(driver_name.strip()),
            )
            driver_subquery = d_stmt

        plate_subquery = None
        if plate_number:
            p_stmt = select(col(DriverPlate.driver_id)).where(
                DriverPlate.client_id == client.id,
                col(DriverPlate.plate_number).contains(plate_number.strip()),
            )
            plate_subquery = p_stmt

        def apply_filters(query):
            query = query.where(col(WaybillJob.client_id) == client.id)
            if driver_id:
                query = query.where(col(WaybillJob.driver_id) == driver_id)
            if driver_subquery is not None or driver_name:
                d_conds = []
                if driver_subquery is not None:
                    d_conds.append(col(WaybillJob.driver_id).in_(driver_subquery))
                if driver_name:
                    dn = driver_name.strip()
                    d_conds.append(col(WaybillJob.payload_json)["driver_name"].as_string().contains(dn))
                query = query.where(or_(*d_conds))

            if plate_subquery is not None or plate_number:
                p_conds = []
                if plate_subquery is not None:
                    p_conds.append(col(WaybillJob.driver_id).in_(plate_subquery))
                if plate_number:
                    pn = plate_number.strip()
                    p_conds.append(col(WaybillJob.payload_json)["plate_number"].as_string().contains(pn))
                    p_conds.append(col(WaybillJob.payload_json)["vehicle_plate"].as_string().contains(pn))
                query = query.where(or_(*p_conds))

            if status:
                query = query.where(col(WaybillJob.status) == status.strip().lower())
            if date_from:
                dt = tehran_day_start_utc(date_from)
                query = query.where(col(WaybillJob.created_at) >= dt)
            if date_to:
                dt = tehran_day_end_utc(date_to)
                query = query.where(col(WaybillJob.created_at) < dt)
            return query

        stmt = apply_filters(select(WaybillJob)).order_by(col(WaybillJob.created_at).desc())
        count_stmt = apply_filters(select(func.count(col(WaybillJob.id))))

        count_result = await session.exec(count_stmt)
        total = count_result.one()

        start = (page - 1) * page_size
        stmt = stmt.offset(start).limit(page_size)
        result = await session.exec(stmt)
        jobs = result.all()

        # Bulk fetch drivers and plates for display
        driver_ids = {j.driver_id for j in jobs if j.driver_id}
        drivers_map = {}
        plates_map = {}
        if driver_ids:
            drivers_stmt = select(Driver).where(col(Driver.id).in_(list(driver_ids)))
            drivers_result = await session.exec(drivers_stmt)
            drivers_map = {d.id: d for d in drivers_result.all()}

            plates_stmt = select(DriverPlate).where(col(DriverPlate.driver_id).in_(list(driver_ids)))
            plates_result = await session.exec(plates_stmt)
            for p in plates_result.all():
                plates_map[p.driver_id] = p.plate_number

        rows = []
        for job in jobs:
            driver = drivers_map.get(job.driver_id)
            plate_no = (
                plates_map.get(job.driver_id)
                or (job.payload_json or {}).get("plate_number")
                or (job.payload_json or {}).get("vehicle_plate")
                or None
            )
            rows.append(
                {
                    "job_id": job.job_id,
                    "driver_id": job.driver_id,
                    "driver_name": driver.full_name if driver else (job.payload_json or {}).get("driver_name"),
                    "driver_national_code": driver.driver_national_code if driver else None,
                    "plate_number": plate_no,
                    "status": job.status,
                    "source": job.source,
                    "business_date": job.business_date,
                    "last_error": job.last_error,
                    "error_category": job.error_category,
                    "attempt_count": job.attempt_count,
                    "created_at": job.created_at.isoformat(),
                    "started_at": job.started_at.isoformat() if job.started_at else None,
                    "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                    "is_scheduled": job.schedule_id is not None,
                    "schedule_id": job.schedule_id,
                }
            )

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if page_size else 1,
            "jobs": rows,
        }

    async def error_details(
        self,
        client: Client,
        session: AsyncSession,
        driver_id: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        # client is a DB-loaded row: the PK is always populated at runtime.
        assert client.id is not None, "client must be a persisted row"
        stmt = select(WaybillJob).where(
            WaybillJob.client_id == client.id,
            col(WaybillJob.status).in_(
                [
                    TaskStatus.FAILED.value,
                    TaskStatus.DEAD_LETTER.value,
                    TaskStatus.NEEDS_REVIEW.value,
                ]
            ),
        )
        if driver_id:
            stmt = stmt.where(WaybillJob.driver_id == driver_id)
        if date_from:
            dt = tehran_day_start_utc(date_from)
            stmt = stmt.where(WaybillJob.created_at >= dt)
        if date_to:
            dt = tehran_day_end_utc(date_to)
            stmt = stmt.where(WaybillJob.created_at < dt)
        stmt = stmt.order_by(col(WaybillJob.created_at).desc()).limit(limit)

        result = await session.exec(stmt)
        failed_jobs = result.all()

        if not failed_jobs:
            return []

        # Optimization: Bulk fetch drivers and logs
        driver_ids = {j.driver_id for j in failed_jobs if j.driver_id}
        drivers_map = {}
        if driver_ids:
            drivers_stmt = select(Driver).where(col(Driver.id).in_(list(driver_ids)))
            drivers_result = await session.exec(drivers_stmt)
            drivers_map = {d.id: d for d in drivers_result.all()}

        job_ids = [j.job_id for j in failed_jobs]
        logs_map: defaultdict[str, list[WaybillTaskLog]] = defaultdict(list)
        if job_ids:
            logs_stmt = (
                select(WaybillTaskLog)
                .where(
                    WaybillTaskLog.client_id == client.id,
                    col(WaybillTaskLog.job_id).in_(job_ids),
                )
                .order_by(col(WaybillTaskLog.job_id), col(WaybillTaskLog.created_at).desc())
            )

            logs_result = await session.exec(logs_stmt)
            for log in logs_result.all():
                if len(logs_map[log.job_id]) < 10:
                    logs_map[log.job_id].append(log)

        output = []
        for job in failed_jobs:
            driver = drivers_map.get(job.driver_id)
            logs = logs_map[job.job_id]

            output.append(
                {
                    "job_id": job.job_id,
                    "driver_id": job.driver_id,
                    "driver_name": driver.full_name if driver else None,
                    "status": job.status,
                    "error_category": job.error_category,
                    "last_error": job.last_error,
                    "attempt_count": job.attempt_count,
                    "created_at": job.created_at.isoformat(),
                    "steps": [
                        {
                            "step": log.step,
                            "status": log.status,
                            "message": log.message,
                            "created_at": log.created_at.isoformat(),
                        }
                        for log in logs
                    ],
                }
            )
        return output

    async def scheduled_execution_history(
        self,
        client: Client,
        session: AsyncSession,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        # client is a DB-loaded row: the PK is always populated at runtime.
        assert client.id is not None, "client must be a persisted row"
        schedules_stmt = (
            select(DriverSchedule)
            .where(
                DriverSchedule.client_id == client.id,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await session.exec(schedules_stmt)
        schedules = result.all()

        if not schedules:
            return {"schedules": [], "total_schedules": 0}

        # Optimization: Bulk fetch drivers and jobs
        driver_ids = {s.driver_id for s in schedules if s.driver_id}
        drivers_map = {}
        if driver_ids:
            drivers_stmt = select(Driver).where(col(Driver.id).in_(list(driver_ids)))
            drivers_result = await session.exec(drivers_stmt)
            drivers_map = {d.id: d for d in drivers_result.all()}

        schedule_ids = [s.id for s in schedules]

        # Optimization: Fetch aggregates and top 5 recent jobs using Window functions
        failed_statuses = [TaskStatus.FAILED.value, TaskStatus.DEAD_LETTER.value, TaskStatus.NEEDS_REVIEW.value]

        recent_jobs_by_schedule: defaultdict[int | None, list[WaybillJob]] = defaultdict(list)

        if schedule_ids:
            # 1. Fetch aggregates grouped by schedule_id
            agg_stmt = (
                select(
                    col(WaybillJob.schedule_id),
                    func.count(col(WaybillJob.id)).label("total_jobs"),
                    func.sum(case((col(WaybillJob.status) == TaskStatus.SUCCESS.value, 1), else_=0)).label(
                        "success_jobs"
                    ),
                    func.sum(case((col(WaybillJob.status).in_(failed_statuses), 1), else_=0)).label("failed_jobs"),
                )
                .where(col(WaybillJob.client_id) == client.id, col(WaybillJob.schedule_id).in_(schedule_ids))
                .group_by(col(WaybillJob.schedule_id))
            )
            stats_by_schedule: dict[Any, dict[str, Any]] = {}
            for sched_id_val, total_v, success_v, failed_v in (await session.exec(agg_stmt)).all():
                stats_by_schedule[sched_id_val] = {
                    "total_jobs": total_v,
                    "success_jobs": success_v,
                    "failed_jobs": failed_v,
                }

            # 2. Fetch top 5 recent jobs per schedule using a window function efficiently
            row_num = (
                func.row_number()
                .over(partition_by=col(WaybillJob.schedule_id), order_by=col(WaybillJob.created_at).desc())
                .label("rn")
            )

            subq = (
                select(WaybillJob, row_num)
                .where(col(WaybillJob.client_id) == client.id, col(WaybillJob.schedule_id).in_(schedule_ids))
                .subquery()
            )

            recent_jobs_stmt = (
                select(WaybillJob)
                .join(subq, col(WaybillJob.job_id) == subq.c.job_id)
                .where(subq.c.rn <= 5)
                .order_by(col(WaybillJob.schedule_id), col(WaybillJob.created_at).desc())
            )
            recent_jobs_res = await session.exec(recent_jobs_stmt)
            for j in recent_jobs_res.all():
                recent_jobs_by_schedule[j.schedule_id].append(j)

        rows = []
        for schedule in schedules:
            driver = drivers_map.get(schedule.driver_id)
            stats = stats_by_schedule.get(schedule.id)
            recent_jobs = recent_jobs_by_schedule.get(schedule.id, [])

            total_jobs = int(stats["total_jobs"]) if stats and stats["total_jobs"] else 0
            success_jobs = int(stats["success_jobs"]) if stats and stats["success_jobs"] else 0
            failed_jobs = int(stats["failed_jobs"]) if stats and stats["failed_jobs"] else 0

            rows.append(
                {
                    "schedule_id": schedule.id,
                    "title": schedule.title,
                    "driver_id": schedule.driver_id,
                    "driver_name": driver.full_name if driver else None,
                    "frequency": schedule.frequency,
                    "is_active": schedule.is_active,
                    "last_run_at": schedule.last_run_at.isoformat() if schedule.last_run_at else None,
                    "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
                    "total_jobs_created": total_jobs,
                    "success_jobs": success_jobs,
                    "failed_jobs": failed_jobs,
                    "recent_jobs": [
                        {
                            "job_id": j.job_id,
                            "status": j.status,
                            "created_at": j.created_at.isoformat(),
                            "error": j.last_error,
                        }
                        for j in recent_jobs
                    ],
                }
            )

        return {
            "schedules": rows,
            "total_schedules": len(rows),
        }

    async def driver_performance(
        self,
        client: Client,
        session: AsyncSession,
        page: int = 1,
        page_size: int = 20,
    ) -> list[dict[str, Any]]:
        # client is a DB-loaded row: the PK is always populated at runtime.
        assert client.id is not None, "client must be a persisted row"
        drivers_stmt = (
            select(Driver).where(Driver.client_id == client.id).offset((page - 1) * page_size).limit(page_size)
        )
        drivers_result = await session.exec(drivers_stmt)
        drivers = drivers_result.all()

        if not drivers:
            return []

        # Use DB aggregation to prevent memory issues with thousands of jobs.
        # The five-column select does not fit sqlmodel's typed select()
        # overloads, so it is split into two narrower queries with identical
        # semantics; merged below.
        failed_statuses = [TaskStatus.FAILED.value, TaskStatus.DEAD_LETTER.value, TaskStatus.NEEDS_REVIEW.value]

        counts_stmt = (
            select(
                col(WaybillJob.driver_id),
                func.count(col(WaybillJob.id)).label("total_jobs"),
                func.sum(case((col(WaybillJob.status) == TaskStatus.SUCCESS.value, 1), else_=0)).label("success_jobs"),
                func.sum(case((col(WaybillJob.status).in_(failed_statuses), 1), else_=0)).label("failed_jobs"),
            )
            .where(col(WaybillJob.client_id) == client.id)
            .group_by(col(WaybillJob.driver_id))
        )
        counts_by_driver: dict[Any, dict[str, Any]] = {}
        for driver_id_val, total_v, success_v, failed_v in (await session.exec(counts_stmt)).all():
            counts_by_driver[driver_id_val] = {
                "total_jobs": total_v,
                "success_jobs": success_v,
                "failed_jobs": failed_v,
            }

        last_stmt = (
            select(
                col(WaybillJob.driver_id),
                func.max(col(WaybillJob.created_at)).label("last_job_at"),
            )
            .where(col(WaybillJob.client_id) == client.id)
            .group_by(col(WaybillJob.driver_id))
        )
        last_by_driver: dict[Any, dict[str, Any]] = {}
        for driver_id_val, last_job_v in (await session.exec(last_stmt)).all():
            last_by_driver[driver_id_val] = {"last_job_at": last_job_v}

        output = []
        for driver in drivers:
            stats = counts_by_driver.get(driver.id)
            lstats = last_by_driver.get(driver.id)
            total = int(stats["total_jobs"]) if stats and stats["total_jobs"] else 0
            success = int(stats["success_jobs"]) if stats and stats["success_jobs"] else 0
            failed = int(stats["failed_jobs"]) if stats and stats["failed_jobs"] else 0
            last_job_at = lstats["last_job_at"].isoformat() if lstats and lstats["last_job_at"] else None

            rate = round(success / max(1, total) * 100, 2)

            output.append(
                {
                    "driver_id": driver.id,
                    "driver_name": driver.full_name,
                    "national_code": driver.driver_national_code,
                    "status": driver.status,
                    "total_jobs": total,
                    "success_jobs": success,
                    "failed_jobs": failed,
                    "success_rate": rate,
                    "last_job_at": last_job_at,
                }
            )
        return output

    async def daily_summary(
        self,
        client_id: int,
        days: int,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """Return per-day job statistics for the given client, backfilled over *days* days."""
        days = max(1, min(days, 90))
        today = datetime.now(UTC).replace(tzinfo=None).date()
        start_date = today - timedelta(days=days - 1)

        stmt = (
            select(
                func.date(col(WaybillJob.created_at)).label("report_date"),
                col(WaybillJob.status),
                func.count(col(WaybillJob.id)).label("job_count"),
            )
            .where(
                (col(WaybillJob.client_id) == client_id)
                & (col(WaybillJob.created_at) >= datetime.combine(start_date, time.min))
                & (col(WaybillJob.created_at) <= datetime.combine(today, time.max))
            )
            .group_by(func.date(col(WaybillJob.created_at)), col(WaybillJob.status))
            .order_by(func.date(col(WaybillJob.created_at)).desc())
        )

        result = await session.exec(stmt)
        rows = result.all()

        per_day: dict[str, dict[str, int]] = {}
        for report_date, status_value, job_count in rows:
            day_key = report_date.isoformat() if hasattr(report_date, "isoformat") else str(report_date)
            stats = per_day.setdefault(day_key, {"total": 0, "success": 0, "failed": 0, "pending": 0})
            count_int = int(job_count or 0)
            stats["total"] += count_int

            if status_value == TaskStatus.SUCCESS.value:
                stats["success"] += count_int
            elif status_value in {TaskStatus.FAILED.value, TaskStatus.DEAD_LETTER.value, TaskStatus.NEEDS_REVIEW.value}:
                stats["failed"] += count_int
            else:
                stats["pending"] += count_int

        summary = []
        for i in range(days):
            date_value = today - timedelta(days=i)
            date_key = date_value.isoformat()
            day_stats = per_day.get(date_key, {})
            summary.append(
                {
                    "date": date_key,
                    "total": day_stats.get("total", 0),
                    "success": day_stats.get("success", 0),
                    "failed": day_stats.get("failed", 0),
                    "pending": day_stats.get("pending", 0),
                }
            )

        return {"client_id": client_id, "summary": summary}

    async def dashboard_stats(
        self,
        client: Client,
        session: AsyncSession,
    ) -> dict[str, Any]:
        # client is a DB-loaded row: the PK is always populated at runtime.
        assert client.id is not None, "client must be a persisted row"
        drivers_stmt = select(Driver).where(Driver.client_id == client.id)
        drivers_result = await session.exec(drivers_stmt)
        drivers = drivers_result.all()
        total_drivers = len(drivers)
        active_drivers = sum(1 for d in drivers if d.status == "active")

        plates_stmt = select(DriverPlate).where(DriverPlate.client_id == client.id)
        plates_result = await session.exec(plates_stmt)
        plates = plates_result.all()
        total_plates = len(plates)

        # Use DB aggregation to prevent memory issues with thousands of jobs
        failed_statuses = [TaskStatus.FAILED.value, TaskStatus.DEAD_LETTER.value, TaskStatus.NEEDS_REVIEW.value]
        pending_statuses = [TaskStatus.PENDING.value, TaskStatus.QUEUED.value, TaskStatus.IN_PROGRESS.value]
        today = datetime.now(UTC).replace(tzinfo=None).date()
        today_start = datetime.combine(today, datetime.min.time())

        # The seven-column select does not fit sqlmodel's typed select()
        # overloads, so it is split into two narrower queries with identical
        # semantics; merged below.
        totals_stmt = select(
            func.count(col(WaybillJob.id)).label("total_jobs"),
            func.sum(case((col(WaybillJob.status) == TaskStatus.SUCCESS.value, 1), else_=0)).label("success_jobs"),
            func.sum(case((col(WaybillJob.status).in_(failed_statuses), 1), else_=0)).label("failed_jobs"),
            func.sum(case((col(WaybillJob.status).in_(pending_statuses), 1), else_=0)).label("pending_jobs"),
        ).where(col(WaybillJob.client_id) == client.id)
        totals_row = (await session.exec(totals_stmt)).first()
        if totals_row is not None:
            total_v, success_v, failed_v, pending_v = totals_row
        else:
            total_v = success_v = failed_v = pending_v = 0

        today_stmt = select(
            func.sum(case((col(WaybillJob.created_at) >= today_start, 1), else_=0)).label("today_jobs"),
            func.sum(
                case(
                    (
                        (col(WaybillJob.created_at) >= today_start)
                        & (col(WaybillJob.status) == TaskStatus.SUCCESS.value),
                        1,
                    ),
                    else_=0,
                )
            ).label("today_success"),
            func.sum(
                case(
                    (
                        (col(WaybillJob.created_at) >= today_start) & (col(WaybillJob.status).in_(failed_statuses)),
                        1,
                    ),
                    else_=0,
                )
            ).label("today_failed"),
        ).where(col(WaybillJob.client_id) == client.id)
        today_row = (await session.exec(today_stmt)).first()
        if today_row is not None:
            today_v, today_success_v, today_failed_v = today_row
        else:
            today_v = today_success_v = today_failed_v = 0

        total_jobs = int(total_v) if total_v else 0
        success_jobs = int(success_v) if success_v else 0
        failed_jobs = int(failed_v) if failed_v else 0
        pending_jobs = int(pending_v) if pending_v else 0

        today_jobs_count = int(today_v) if today_v else 0
        today_success = int(today_success_v) if today_success_v else 0
        today_failed = int(today_failed_v) if today_failed_v else 0

        return {
            "client_id": client.id,
            "total_drivers": total_drivers,
            "active_drivers": active_drivers,
            "total_plates": total_plates,
            "total_jobs": total_jobs,
            "success_jobs": success_jobs,
            "failed_jobs": failed_jobs,
            "pending_jobs": pending_jobs,
            "today_jobs": today_jobs_count,
            "today_success": today_success,
            "today_failed": today_failed,
            "success_rate": round(success_jobs / max(1, total_jobs) * 100, 2),
        }


user_reporting_service = UserReportingService()
