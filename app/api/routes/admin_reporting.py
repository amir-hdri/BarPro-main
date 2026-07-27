"""
Admin reporting API routes.

Provides endpoints for the master admin to:
- View per-client summary (drivers, plates, jobs, success/failure)
- View detailed driver reports with filters
- View failure analysis across all tenants
"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth_multitenant import get_current_admin
from app.core.database import get_session
from app.schemas.admin import DriverReportFilter
from app.services.admin_reporting_service import admin_reporting_service

router = APIRouter(prefix="/api/v1/admin/reports", tags=["admin-reports"])


@router.get(
    "/clients/summary",
    summary="خلاصه آمار تمام مشتریان",
    dependencies=[Depends(get_current_admin)],
)
async def get_clients_summary(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
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
    "/audit-logs",
    summary="لاگ فعالیت‌های سیستم",
    dependencies=[Depends(get_current_admin)],
)
async def get_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get recent waybill job activity as audit log entries."""
    return await admin_reporting_service.audit_logs(
        client_id=None,
        page=page,
        page_size=page_size,
        session=session,
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
    return await admin_reporting_service.client_detail(
        client_id=client_id,
        session=session,
        date_from=date_from,
        date_to=date_to,
    )
