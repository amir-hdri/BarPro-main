"""
User-facing reporting API routes for the multi-tenant panel.

Provides endpoints for each client to view:
- Driver list with status and performance
- Waybill history with filters
- Error details with execution steps
- Scheduled execution history
- Driver performance summaries
- Dashboard statistics
"""
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth_multitenant import get_current_client
from app.core.database import get_session
from app.models_multitenant import Client
from app.services.user_reporting_service import user_reporting_service

router = APIRouter(prefix="/user/reports", tags=["user-reports"])


@router.get(
    "/drivers",
    summary="لیست رانندگان با وضعیت",
)
async def get_driver_list_with_status(
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Get all drivers with their status, jobs, schedules, and plates."""
    return await user_reporting_service.driver_list_with_status(client, session)


@router.get(
    "/waybills",
    summary="تاریخچه بارنامه‌ها",
)
async def get_waybill_history(
    driver_id: int | None = Query(None, description="Filter by driver"),
    status: str | None = Query(None, description="Filter by status"),
    date_from: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get waybill history with filtering and pagination."""
    return await user_reporting_service.waybill_history(
        client=client,
        session=session,
        driver_id=driver_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/errors",
    summary="جزئیات خطاها",
)
async def get_error_details(
    driver_id: int | None = Query(None, description="Filter by driver"),
    date_from: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(100, ge=1, le=500),
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Get error details with execution steps for failed jobs."""
    return await user_reporting_service.error_details(
        client=client,
        session=session,
        driver_id=driver_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )


@router.get(
    "/scheduled-history",
    summary="تاریخچه اجراهای خودکار",
)
async def get_scheduled_execution_history(
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get scheduled execution history and status."""
    return await user_reporting_service.scheduled_execution_history(client, session)


@router.get(
    "/driver-performance",
    summary="عملکرد رانندگان",
)
async def get_driver_performance(
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Get per-driver performance summary."""
    return await user_reporting_service.driver_performance(client, session)


@router.get(
    "/dashboard",
    summary="داشبورد اصلی",
)
async def get_dashboard_stats(
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get dashboard statistics summary."""
    return await user_reporting_service.dashboard_stats(client, session)
