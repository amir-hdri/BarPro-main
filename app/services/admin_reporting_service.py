"""
Comprehensive reporting service for admin and user-level analytics.

Admin reports:
- Per-client driver/plate counts
- Per-driver waybill counts (total/success/failed)
- Failure reasons and categories
- Activity time ranges
- Filtering by date, client, driver, plate, status, operation type

User reports:
- Driver/plate list with status
- Waybill history (success/failure)
- Error details
- Auto-execution timestamps
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import case, func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import async_session_factory
from app.models_multitenant import (
    Client,
    Driver,
    DriverPlate,
    TaskStatus,
    WaybillJob,
)
from app.schemas.admin import DriverReportFilter

logger = logging.getLogger(__name__)


def _safe_json(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


class AdminReportingService:
    """Reports accessible by the master admin across all tenants."""

    async def client_summary(
        self,
        page: int = 1,
        page_size: int = 50,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict[str, Any]:
        session = async_session_factory()
        try:
            from sqlalchemy import func

            total_clients = (await session.exec(select(func.count(Client.id)))).one()
            active_clients = (await session.exec(select(func.count(Client.id)).where(Client.status == "active"))).one()

            # Paginate clients at database level
            stmt = (
                select(Client).order_by(col(Client.created_at).desc()).offset((page - 1) * page_size).limit(page_size)
            )
            result = await session.exec(stmt)
            clients = result.all()

            # Extract paginated client IDs to fetch related data in bulk (avoid N+1)
            client_ids = [c.id for c in clients]

            # Fetch all drivers for these clients
            drivers_by_client = defaultdict(list)
            if client_ids:
                driver_stmt = select(Driver).where(col(Driver.client_id).in_(client_ids))
                driver_result = await session.exec(driver_stmt)
                for d in driver_result.all():
                    drivers_by_client[d.client_id].append(d)

            # Fetch all plates for these clients
            plates_by_client = defaultdict(list)
            if client_ids:
                plate_stmt = select(DriverPlate).where(col(DriverPlate.client_id).in_(client_ids))
                plate_result = await session.exec(plate_stmt)
                for p in plate_result.all():
                    plates_by_client[p.client_id].append(p)

            # Fetch aggregated jobs for these clients
            failed_statuses = [
                TaskStatus.FAILED.value,
                TaskStatus.DEAD_LETTER.value,
                TaskStatus.NEEDS_REVIEW.value,
            ]

            stats_by_client = {}
            if client_ids:
                from sqlalchemy import case, func

                agg_stmt = (
                    select(
                        WaybillJob.client_id,
                        func.count(WaybillJob.id).label("total_jobs"),
                        func.sum(case((WaybillJob.status == TaskStatus.SUCCESS.value, 1), else_=0)).label(
                            "success_jobs"
                        ),
                        func.sum(case((col(WaybillJob.status).in_(failed_statuses), 1), else_=0)).label("failed_jobs"),
                        func.min(WaybillJob.created_at).label("first_job_at"),
                        func.max(WaybillJob.created_at).label("last_job_at"),
                    )
                    .where(col(WaybillJob.client_id).in_(client_ids))
                    .group_by(WaybillJob.client_id)
                )

                if date_from:
                    dt = datetime.fromisoformat(date_from)
                    agg_stmt = agg_stmt.where(WaybillJob.created_at >= dt)
                if date_to:
                    dt = datetime.fromisoformat(date_to) + timedelta(days=1)
                    agg_stmt = agg_stmt.where(WaybillJob.created_at < dt)

                agg_result = await session.exec(agg_stmt)
                stats_by_client = {row.client_id: row for row in agg_result.all()}

            rows = []
            for client in clients:
                drivers = drivers_by_client.get(client.id, [])
                total_drivers = len(drivers)
                active_drivers = sum(1 for d in drivers if d.status == "active")

                plates = plates_by_client.get(client.id, [])
                total_plates = len(plates)
                active_plates = sum(1 for p in plates if p.status == "active")

                stats = stats_by_client.get(client.id)
                total_jobs = int(stats.total_jobs) if stats and stats.total_jobs else 0
                success_jobs = int(stats.success_jobs) if stats and stats.success_jobs else 0
                failed_jobs = int(stats.failed_jobs) if stats and stats.failed_jobs else 0

                first_job = stats.first_job_at if stats and stats.first_job_at else None
                last_job = stats.last_job_at if stats and stats.last_job_at else None

                failure_reasons: dict[str, int] = defaultdict(int)
                # Failure reasons aggregation moved to specific reports or omitted in summary to avoid massive fetch

                rows.append(
                    {
                        "client_id": client.id,
                        "client_code": client.client_code,
                        "name": client.name,
                        "email": client.email,
                        "status": client.status,
                        "total_drivers": total_drivers,
                        "active_drivers": active_drivers,
                        "total_plates": total_plates,
                        "active_plates": active_plates,
                        "total_jobs": total_jobs,
                        "success_jobs": success_jobs,
                        "failed_jobs": failed_jobs,
                        "success_rate": round(success_jobs / max(1, total_jobs) * 100, 2),
                        "failure_reasons": dict(failure_reasons),
                        "first_activity": first_job.isoformat() if first_job else None,
                        "last_activity": last_job.isoformat() if last_job else None,
                        "created_at": client.created_at.isoformat(),
                    }
                )

            return {
                "total_clients": total_clients,
                "active_clients": active_clients,
                "page": page,
                "page_size": page_size,
                "total_rows": total_clients,
                "rows": rows,
            }
        finally:
            await session.close()

    async def driver_report(
        self,
        filters: DriverReportFilter,
    ) -> dict[str, Any]:
        session = async_session_factory()
        try:
            stmt = select(WaybillJob)
            if filters.client_id:
                stmt = stmt.where(WaybillJob.client_id == filters.client_id)
            if filters.driver_id:
                stmt = stmt.where(WaybillJob.driver_id == filters.driver_id)
            if filters.plate_id:
                from app.models_multitenant import DriverPlate

                plate_driver_subquery = select(DriverPlate.driver_id).where(DriverPlate.id == filters.plate_id)
                stmt = stmt.where(WaybillJob.driver_id.in_(plate_driver_subquery))
            if filters.status:
                stmt = stmt.where(WaybillJob.status == filters.status)
            if filters.date_from:
                dt = datetime.fromisoformat(filters.date_from)
                stmt = stmt.where(WaybillJob.created_at >= dt)
            if filters.date_to:
                dt = datetime.fromisoformat(filters.date_to) + timedelta(days=1)
                stmt = stmt.where(WaybillJob.created_at < dt)
            if filters.operation_type:
                stmt = stmt.where(WaybillJob.source == filters.operation_type)
            stmt = stmt.order_by(col(WaybillJob.created_at).desc())

            # Get total count using a light aggregate query
            from sqlalchemy import func

            count_stmt = select(func.count(WaybillJob.id))
            if filters.client_id:
                count_stmt = count_stmt.where(WaybillJob.client_id == filters.client_id)
            if filters.driver_id:
                count_stmt = count_stmt.where(WaybillJob.driver_id == filters.driver_id)
            if filters.plate_id:
                from app.models_multitenant import DriverPlate

                plate_driver_subquery = select(DriverPlate.driver_id).where(DriverPlate.id == filters.plate_id)
                count_stmt = count_stmt.where(WaybillJob.driver_id.in_(plate_driver_subquery))
            if filters.status:
                count_stmt = count_stmt.where(WaybillJob.status == filters.status)
            if filters.date_from:
                dt = datetime.fromisoformat(filters.date_from)
                count_stmt = count_stmt.where(WaybillJob.created_at >= dt)
            if filters.date_to:
                dt = datetime.fromisoformat(filters.date_to) + timedelta(days=1)
                count_stmt = count_stmt.where(WaybillJob.created_at < dt)
            if filters.operation_type:
                count_stmt = count_stmt.where(WaybillJob.source == filters.operation_type)

            count_result = await session.exec(count_stmt)
            total = count_result.one()

            # Paginate jobs at database level
            start = (filters.page - 1) * filters.page_size
            stmt = stmt.offset(start).limit(filters.page_size)
            result = await session.exec(stmt)
            paginated = result.all()

            # Bulk fetch clients and drivers to prevent N+1 queries
            client_ids = list({job.client_id for job in paginated if job.client_id})
            driver_ids = list({job.driver_id for job in paginated if job.driver_id})

            clients_dict = {}
            if client_ids:
                clients_res = await session.exec(select(Client).where(col(Client.id).in_(client_ids)))
                clients_dict = {c.id: c for c in clients_res.all()}

            drivers_dict = {}
            if driver_ids:
                drivers_res = await session.exec(select(Driver).where(col(Driver.id).in_(driver_ids)))
                drivers_dict = {d.id: d for d in drivers_res.all()}

            rows = []
            for job in paginated:
                driver = drivers_dict.get(job.driver_id) if job.driver_id else None
                client = clients_dict.get(job.client_id)

                rows.append(
                    {
                        "job_id": job.job_id,
                        "client_id": job.client_id,
                        "client_name": client.name if client else None,
                        "driver_id": job.driver_id,
                        "driver_name": driver.full_name if driver else None,
                        "driver_national_code": driver.driver_national_code if driver else None,
                        "status": job.status,
                        "source": job.source,
                        "business_date": job.business_date,
                        "priority": job.priority,
                        "last_error": job.last_error,
                        "error_category": job.error_category,
                        "attempt_count": job.attempt_count,
                        "created_at": job.created_at.isoformat(),
                        "started_at": job.started_at.isoformat() if job.started_at else None,
                        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                    }
                )

            return {
                "total": total,
                "page": filters.page,
                "page_size": filters.page_size,
                "total_pages": (total + filters.page_size - 1) // filters.page_size if filters.page_size else 1,
                "jobs": rows,
            }
        finally:
            await session.close()

    async def failure_analysis(
        self,
        client_id: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict[str, Any]:
        session = async_session_factory()
        try:
            stmt = select(WaybillJob).where(
                col(WaybillJob.status).in_(
                    [
                        TaskStatus.FAILED.value,
                        TaskStatus.DEAD_LETTER.value,
                        TaskStatus.NEEDS_REVIEW.value,
                    ]
                )
            )
            if client_id:
                stmt = stmt.where(WaybillJob.client_id == client_id)
            if date_from:
                dt = datetime.fromisoformat(date_from)
                stmt = stmt.where(WaybillJob.created_at >= dt)
            if date_to:
                dt = datetime.fromisoformat(date_to) + timedelta(days=1)
                stmt = stmt.where(WaybillJob.created_at < dt)

            result = await session.exec(stmt)
            failed_jobs = result.all()

            by_category: dict[str, int] = defaultdict(int)
            by_client: dict[str, int] = defaultdict(int)
            by_driver: dict[str, int] = defaultdict(int)
            examples: dict[str, list[dict]] = defaultdict(list)

            # Bulk fetch clients and drivers to prevent N+1 queries
            client_ids = list({job.client_id for job in failed_jobs if job.client_id})
            driver_ids = list({job.driver_id for job in failed_jobs if job.driver_id})

            clients_dict = {}
            if client_ids:
                clients_res = await session.exec(select(Client).where(col(Client.id).in_(client_ids)))
                clients_dict = {c.id: c for c in clients_res.all()}

            drivers_dict = {}
            if driver_ids:
                drivers_res = await session.exec(select(Driver).where(col(Driver.id).in_(driver_ids)))
                drivers_dict = {d.id: d for d in drivers_res.all()}
                client_stmt = select(Client).where(col(Client.id).in_(client_ids))
                client_result = await session.exec(client_stmt)
                for c in client_result.all():
                    clients_dict[c.id] = c

            drivers_dict = {}
            if driver_ids:
                driver_stmt = select(Driver).where(col(Driver.id).in_(driver_ids))
                driver_result = await session.exec(driver_stmt)
                for d in driver_result.all():
                    drivers_dict[d.id] = d

            for job in failed_jobs:
                cat = job.error_category or "unknown"
                by_category[cat] += 1

                client = clients_dict.get(job.client_id)
                client_name = client.name if client else f"client_{job.client_id}"
                by_client[client_name] += 1

                if job.driver_id:
                    driver = drivers_dict.get(job.driver_id)
                    driver_name = driver.full_name if driver else f"driver_{job.driver_id}"
                else:
                    driver_name = "unknown"
                by_driver[driver_name] += 1

                if len(examples[cat]) < 3:
                    examples[cat].append(
                        {
                            "job_id": job.job_id,
                            "client": client_name,
                            "driver": driver_name,
                            "error": job.last_error,
                            "created_at": job.created_at.isoformat(),
                        }
                    )

            return {
                "total_failed": len(failed_jobs),
                "by_category": dict(by_category),
                "by_client": dict(by_client),
                "by_driver": dict(by_driver),
                "examples": dict(examples),
            }
        finally:
            await session.close()

    async def audit_logs(
        self,
        client_id: int | None,
        page: int,
        page_size: int,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """Return recent waybill job activity as audit log entries."""
        offset = (page - 1) * page_size
        stmt = select(WaybillJob).order_by(WaybillJob.updated_at.desc()).offset(offset).limit(page_size)

        if client_id is not None:
            stmt = stmt.where(WaybillJob.client_id == client_id)

        result = await session.exec(stmt)
        jobs = result.all()

        # Bulk fetch drivers to prevent N+1 queries
        driver_ids = list({j.driver_id for j in jobs if j.driver_id})
        drivers_dict = {}
        if driver_ids:
            drivers_res = await session.exec(select(Driver).where(Driver.id.in_(driver_ids)))
            drivers_dict = {d.id: d for d in drivers_res.all()}

        entries = []
        for j in jobs:
            driver = drivers_dict.get(j.driver_id) if j.driver_id else None
            driver_code = driver.driver_national_code if driver else "—"
            driver_name = driver.full_name if driver else "—"

            desc_parts = [f"بارنامه #{j.id}"]
            if driver_name != "—":
                desc_parts.append(f"راننده: {driver_name} ({driver_code})")
            if j.worker_id:
                desc_parts.append(f"ورکر: {j.worker_id}")
            if j.last_error:
                desc_parts.append(f"خطا: {j.last_error[:60]}")
            else:
                desc_parts.append(f"وضعیت: {j.status}")

            entries.append(
                {
                    "id": j.id,
                    "user_type": "client",
                    "user_id": j.client_id,
                    "action": j.status.upper() if j.status else "UNKNOWN",
                    "entity_type": "waybill_job",
                    "entity_id": j.id,
                    "description": " — ".join(desc_parts),
                    "ip_address": j.worker_id or "system",
                    "created_at": (j.updated_at or j.created_at).isoformat()
                    if (j.updated_at or j.created_at)
                    else None,
                }
            )

        return {"items": entries, "page": page, "page_size": page_size}

    async def client_detail(
        self,
        client_id: int,
        session: AsyncSession,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict[str, Any]:
        """Return detailed report for a specific client using SQL aggregation."""
        client = await session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")

        # --- Driver counts via SQL aggregation ---
        drivers_stmt = select(Driver).where(Driver.client_id == client_id)
        drivers_result = await session.exec(drivers_stmt)
        drivers = drivers_result.all()

        total_drivers = len(drivers)
        active_drivers = sum(1 for d in drivers if d.status == "active")

        # --- Plate count via SQL count ---
        plates_count_stmt = select(func.count(DriverPlate.id)).where(DriverPlate.client_id == client_id)
        plates_result = await session.exec(plates_count_stmt)
        total_plates = plates_result.one()

        # --- Job aggregation (overall) ---
        failed_statuses = [
            TaskStatus.FAILED.value,
            TaskStatus.DEAD_LETTER.value,
            TaskStatus.NEEDS_REVIEW.value,
        ]

        jobs_agg_stmt = select(
            func.count(WaybillJob.id).label("total_jobs"),
            func.sum(case((WaybillJob.status == TaskStatus.SUCCESS.value, 1), else_=0)).label("success_jobs"),
            func.sum(case((col(WaybillJob.status).in_(failed_statuses), 1), else_=0)).label("failed_jobs"),
        ).where(WaybillJob.client_id == client_id)

        if date_from:
            try:
                dt = datetime.fromisoformat(date_from)
                jobs_agg_stmt = jobs_agg_stmt.where(WaybillJob.created_at >= dt)
            except ValueError:
                raise HTTPException(
                    status_code=422, detail=f"Invalid date_from format: '{date_from}'. Use YYYY-MM-DD."
                ) from None
        if date_to:
            try:
                dt = datetime.fromisoformat(date_to) + timedelta(days=1)
                jobs_agg_stmt = jobs_agg_stmt.where(WaybillJob.created_at < dt)
            except ValueError:
                raise HTTPException(
                    status_code=422, detail=f"Invalid date_to format: '{date_to}'. Use YYYY-MM-DD."
                ) from None

        agg_result = await session.exec(jobs_agg_stmt)
        agg_row = agg_result.one()

        total_jobs = int(agg_row.total_jobs) if agg_row.total_jobs else 0
        success_jobs = int(agg_row.success_jobs) if agg_row.success_jobs else 0
        failed_jobs = int(agg_row.failed_jobs) if agg_row.failed_jobs else 0

        # --- Per-driver breakdown via SQL aggregation ---
        driver_ids = [d.id for d in drivers]
        driver_breakdown = []
        if driver_ids:
            driver_agg_stmt = (
                select(
                    WaybillJob.driver_id,
                    func.count(WaybillJob.id).label("total_jobs"),
                    func.sum(case((WaybillJob.status == TaskStatus.SUCCESS.value, 1), else_=0)).label("success_jobs"),
                    func.sum(case((col(WaybillJob.status).in_(failed_statuses), 1), else_=0)).label("failed_jobs"),
                )
                .where(WaybillJob.client_id == client_id, col(WaybillJob.driver_id).in_(driver_ids))
                .group_by(WaybillJob.driver_id)
            )

            if date_from:
                dt = datetime.fromisoformat(date_from)
                driver_agg_stmt = driver_agg_stmt.where(WaybillJob.created_at >= dt)
            if date_to:
                dt = datetime.fromisoformat(date_to) + timedelta(days=1)
                driver_agg_stmt = driver_agg_stmt.where(WaybillJob.created_at < dt)

            driver_agg_result = await session.exec(driver_agg_stmt)
            stats_by_driver = {row.driver_id: row for row in driver_agg_result.all()}

            for driver in drivers:
                stats = stats_by_driver.get(driver.id)
                d_total = int(stats.total_jobs) if stats and stats.total_jobs else 0
                d_success = int(stats.success_jobs) if stats and stats.success_jobs else 0
                d_failed = int(stats.failed_jobs) if stats and stats.failed_jobs else 0

                driver_breakdown.append(
                    {
                        "driver_id": driver.id,
                        "driver_name": driver.full_name,
                        "national_code": driver.driver_national_code,
                        "total_jobs": d_total,
                        "success": d_success,
                        "failed": d_failed,
                        "success_rate": round(d_success / max(1, d_total) * 100, 2),
                    }
                )

        # --- Failure reasons via SQL aggregation ---
        failure_stmt = (
            select(
                WaybillJob.error_category,
                func.count(WaybillJob.id).label("count"),
            )
            .where(
                WaybillJob.client_id == client_id,
                WaybillJob.error_category.isnot(None),
                col(WaybillJob.status).in_(failed_statuses),
            )
            .group_by(WaybillJob.error_category)
        )

        if date_from:
            dt = datetime.fromisoformat(date_from)
            failure_stmt = failure_stmt.where(WaybillJob.created_at >= dt)
        if date_to:
            dt = datetime.fromisoformat(date_to) + timedelta(days=1)
            failure_stmt = failure_stmt.where(WaybillJob.created_at < dt)

        failure_result = await session.exec(failure_stmt)
        failure_reasons = {row.error_category: int(row.count) for row in failure_result.all()}

        return {
            "client_id": client.id,
            "client_code": client.client_code,
            "name": client.name,
            "email": client.email,
            "status": client.status,
            "total_drivers": total_drivers,
            "active_drivers": active_drivers,
            "total_plates": total_plates,
            "total_jobs": total_jobs,
            "success_jobs": success_jobs,
            "failed_jobs": failed_jobs,
            "success_rate": round(success_jobs / max(1, total_jobs) * 100, 2),
            "failure_reasons": failure_reasons,
            "driver_breakdown": driver_breakdown,
            "created_at": client.created_at.isoformat(),
        }


admin_reporting_service = AdminReportingService()
