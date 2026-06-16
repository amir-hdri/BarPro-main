"""
Admin reporting API routes.

Provides endpoints for the master admin to:
- View per-client summary (drivers, plates, jobs, success/failure)
- View detailed driver reports with filters
- View failure analysis across all tenants
"""

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth_multitenant import get_current_admin
from app.core.database import get_session
from app.models_multitenant import Client, Driver, DriverPlate, WaybillJob
from app.schemas.admin import DriverReportFilter
from app.services.admin_reporting_service import admin_reporting_service

router = APIRouter(prefix="/admin/reports", tags=["admin-reports"])


@router.get(
    "/clients/summary",
    summary="خلاصه آمار تمام مشتریان",
    dependencies=[Depends(get_current_admin)],
)
async def get_clients_summary(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    date_from: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get summary statistics for all clients."""
    return await admin_reporting_service.client_summary(
        page=page,
        page_size=page_size,
        date_from=date_from,
        date_to=date_to,
    )


@router.get(
    "/drivers/report",
    summary="گزارش تفصیلی رانندگان",
    dependencies=[Depends(get_current_admin)],
)
async def get_driver_report(
    filters: DriverReportFilter = Depends(),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get detailed driver/waybill report with filters."""
    return await admin_reporting_service.driver_report(filters=filters)


@router.get(
    "/failure-analysis",
    summary="تحلیل شکست‌ها",
    dependencies=[Depends(get_current_admin)],
)
async def get_failure_analysis(
    client_id: int | None = Query(None, description="Filter by client"),
    date_from: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Analyze failures across all tenants or a specific client."""
    return await admin_reporting_service.failure_analysis(
        client_id=client_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get(
    "/clients/{client_id}/detail",
    summary="جزئیات کامل یک مشتری",
    dependencies=[Depends(get_current_admin)],
)
async def get_client_detail(
    client_id: int,
    date_from: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get detailed report for a specific client."""
    client = await session.get(Client, client_id)
    if not client:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Client not found")

    drivers_stmt = select(Driver).where(Driver.client_id == client_id)
    drivers_result = await session.exec(drivers_stmt)
    drivers = drivers_result.all()

    total_drivers = len(drivers)
    active_drivers = sum(1 for d in drivers if d.status == "active")

    plates_stmt = select(DriverPlate).where(DriverPlate.client_id == client_id)
    plates_result = await session.exec(plates_stmt)
    plates = plates_result.all()
    total_plates = len(plates)

    jobs_stmt = select(WaybillJob).where(WaybillJob.client_id == client_id)
    if date_from:
        dt = datetime.fromisoformat(date_from)
        jobs_stmt = jobs_stmt.where(WaybillJob.created_at >= dt)
    if date_to:
        dt = datetime.fromisoformat(date_to) + timedelta(days=1)
        jobs_stmt = jobs_stmt.where(WaybillJob.created_at < dt)
    jobs_result = await session.exec(jobs_stmt)
    jobs = jobs_result.all()

    total_jobs = len(jobs)
    success_jobs = sum(1 for j in jobs if j.status == "success")
    failed_jobs = sum(1 for j in jobs if j.status in ("failed", "dead_letter", "needs_review"))

    # Per-driver breakdown
    driver_breakdown = []
    for driver in drivers:
        driver_jobs = [j for j in jobs if j.driver_id == driver.id]
        driver_success = sum(1 for j in driver_jobs if j.status == "success")
        driver_failed = sum(1 for j in driver_jobs if j.status in ("failed", "dead_letter", "needs_review"))

        driver_breakdown.append(
            {
                "driver_id": driver.id,
                "driver_name": driver.full_name,
                "national_code": driver.driver_national_code,
                "total_jobs": len(driver_jobs),
                "success": driver_success,
                "failed": driver_failed,
                "success_rate": round(driver_success / max(1, len(driver_jobs)) * 100, 2),
            }
        )

    # Top failure reasons
    failure_reasons = {}
    for j in jobs:
        if j.error_category:
            failure_reasons[j.error_category] = failure_reasons.get(j.error_category, 0) + 1

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
