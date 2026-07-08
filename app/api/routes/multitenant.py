"""
Multi-tenant API routes for the UTCMS Automation SaaS.

Provides endpoints for:
- Client authentication (login/register)
- Driver management (CRUD)
- Waybill job management (create, list, status)
- Excel bulk upload
- Real-time reporting and analytics

All endpoints enforce tenant isolation - clients can only access their own data.
"""

import logging
from datetime import UTC, datetime, time, timedelta

from fastapi import APIRouter, Body, Depends, Query, UploadFile, status
from fastapi.responses import Response
from fastapi.security import HTTPBearer
from sqlmodel import case, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth_multitenant import get_current_admin, get_current_client
from app.core.config import utcms_config
from app.core.database import get_session
from app.models_multitenant import Client, Driver, TaskSource, TaskStatus, WaybillJob
from app.schemas.multitenant import (
    AdminClientUpdateRequest,
    AdminLoginRequest,
    BatchStatusResponse,
    BulkUploadResponse,
    ClientLoginRequest,
    ClientRegisterRequest,
    ClientResponse,
    ClientStatsResponse,
    DriverCreateRequest,
    DriverResponse,
    DriverScheduleCreateRequest,
    DriverScheduleResponse,
    DriverScheduleUpdateRequest,
    DriverUpdateRequest,
    FuelInquiryCreateRequest,
    FuelInquiryListResponse,
    FuelInquiryResponse,
    PlateCreateRequest,
    PlateResponse,
    PlateUpdateRequest,
    TaskFilterRequest,
    TaskListResponse,
    TaskLogsResponse,
    TaskTimelineQuery,
    TaskTimelineResponse,
    WaybillJobCreateRequest,
    WaybillJobResponse,
    WaybillJobUpdateRequest,
    WaybillRetryRequest,
)
from app.services.excel_upload_service import ExcelUploadService
from app.services.fuel_inquiry_service import fuel_inquiry_service
from app.services.multitenant_service import (
    ClientService,
    DriverScheduleService,
    DriverService,
    PlateService,
    WaybillJobService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["multi-tenant"])
alias_router = APIRouter(tags=["multi-tenant-compat"])
security = HTTPBearer()
AUTH_COOKIE_NAME = "utcms_auth_token"


def _auth_cookie_secure() -> bool:
    """Keep HTTP deployments working while allowing HTTPS hardening via env."""
    return utcms_config.AUTH_COOKIE_SECURE


# ==================== AUTH ENDPOINTS ====================


@router.post("/auth/register", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def register_client(
    request: ClientRegisterRequest,
    admin=Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Register a new client (tenant).

    This creates a new isolated account with its own drivers and jobs.
    """
    del admin
    return await ClientService.register_client(request, session)


@router.post("/auth/login")
async def login_client(
    request: ClientLoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    """
    Authenticate client and return JWT token.

    The token is used for all subsequent API calls to enforce tenant isolation.
    """
    result = await ClientService.login_client(request, session)
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=result["access_token"],
        httponly=True,
        max_age=86400,
        expires=86400,
        samesite="lax",
        secure=_auth_cookie_secure(),
        path="/",
    )
    return result


@router.post("/admin/login")
async def login_master_admin(
    request: AdminLoginRequest,
    response: Response,
):
    """Authenticate the singleton master admin account."""
    result = await ClientService.login_master_admin(request)
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=result["access_token"],
        httponly=True,
        max_age=86400,
        expires=86400,
        samesite="lax",
        secure=_auth_cookie_secure(),
        path="/",
    )
    return result


@router.post("/auth/logout")
async def logout_client(response: Response):
    """Log out the current user/admin and clear the authentication cookie."""
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        samesite="lax",
        secure=_auth_cookie_secure(),
        path="/",
    )
    return {"success": True, "detail": "Logged out successfully"}


@router.get("/admin/clients", response_model=list[ClientResponse])
async def list_clients_for_admin(
    q: str | None = None,
    status_filter: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin=Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    """List all tenant accounts for master admin."""
    del admin
    return await ClientService.list_clients(
        session,
        q=q,
        status_filter=status_filter,
        page=page,
        page_size=page_size,
    )


@router.post("/admin/clients", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client_for_admin(
    request: ClientRegisterRequest,
    admin=Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    """Create a tenant account via master admin."""
    del admin
    return await ClientService.register_client(request, session)


@router.put("/admin/clients/{client_id}", response_model=ClientResponse)
async def update_client_for_admin(
    client_id: int,
    request: AdminClientUpdateRequest,
    admin=Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    """Update a tenant account via master admin."""
    del admin
    return await ClientService.update_client_by_admin(client_id, request, session)


@router.delete("/admin/clients/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client_for_admin(
    client_id: int,
    admin=Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    """Delete a tenant account via master admin."""
    del admin
    await ClientService.delete_client_by_admin(client_id, session)
    return None


@alias_router.get("/admin/clients", response_model=list[ClientResponse])
async def list_clients_for_admin_alias(
    q: str | None = None,
    status_filter: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin=Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    """Compatibility alias for root /admin/clients access."""
    del admin
    return await ClientService.list_clients(
        session,
        q=q,
        status_filter=status_filter,
        page=page,
        page_size=page_size,
    )


@alias_router.post("/admin/clients", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client_for_admin_alias(
    request: ClientRegisterRequest,
    admin=Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    """Compatibility alias for root /admin/clients access."""
    del admin
    return await ClientService.register_client(request, session)


@alias_router.put("/admin/clients/{client_id}", response_model=ClientResponse)
async def update_client_for_admin_alias(
    client_id: int,
    request: AdminClientUpdateRequest,
    admin=Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    """Compatibility alias for root /admin/clients access."""
    del admin
    return await ClientService.update_client_by_admin(client_id, request, session)


@alias_router.delete("/admin/clients/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client_for_admin_alias(
    client_id: int,
    admin=Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    """Compatibility alias for root /admin/clients access."""
    del admin
    await ClientService.delete_client_by_admin(client_id, session)
    return None


@router.get("/auth/me", response_model=ClientResponse)
async def get_client_profile(
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    """Get current client profile."""
    return await ClientService.get_client_profile(client, session)


@router.get("/auth/stats", response_model=ClientStatsResponse)
async def get_client_stats(
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    """
    Get client dashboard statistics.

    Returns real-time metrics for the client's account including:
    - Total/active drivers
    - Job counts by status
    - Today's performance
    - Success rate
    """
    return await ClientService.get_client_stats(client, session)


# ==================== DRIVER ENDPOINTS ====================


@router.post("/drivers", response_model=DriverResponse, status_code=status.HTTP_201_CREATED)
async def create_driver(
    request: DriverCreateRequest,
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    """
    Create a new driver for the client.

    Each driver has unique UTCMS credentials for waybill registration.
    """
    return await DriverService.create_driver(client, request, session)


@router.get("/drivers", response_model=list[DriverResponse])
async def list_drivers(
    status_filter: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    """
    List all drivers for the client.

    Supports filtering by status and pagination.
    """
    return await DriverService.list_drivers(
        client,
        session,
        status_filter=status_filter,
        page=page,
        page_size=page_size,
    )


@router.get("/drivers/{driver_id}", response_model=DriverResponse)
async def get_driver(
    driver_id: int,
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    """Get a specific driver's information."""
    return await DriverService.get_driver(client, driver_id, session)


@router.put("/drivers/{driver_id}", response_model=DriverResponse)
async def update_driver(
    driver_id: int,
    request: DriverUpdateRequest,
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    """Update driver information."""
    return await DriverService.update_driver(client, driver_id, request, session)


@router.delete("/drivers/{driver_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_driver(
    driver_id: int,
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    """Delete a driver."""
    await DriverService.delete_driver(client, driver_id, session)
    return None


@router.post("/plates", response_model=PlateResponse, status_code=status.HTTP_201_CREATED)
async def create_plate(
    request: PlateCreateRequest,
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    return await PlateService.create_plate(client, request, session)


@router.get("/plates", response_model=list[PlateResponse])
async def list_plates(
    driver_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    return await PlateService.list_plates(client, session, driver_id=driver_id, page=page, page_size=page_size)


@router.put("/plates/{plate_id}", response_model=PlateResponse)
async def update_plate(
    plate_id: int,
    request: PlateUpdateRequest,
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    return await PlateService.update_plate(client, plate_id, request, session)


@router.delete("/plates/{plate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plate(
    plate_id: int,
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    await PlateService.delete_plate(client, plate_id, session)
    return None


@router.post("/driver-schedules", response_model=DriverScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_driver_schedule(
    request: DriverScheduleCreateRequest,
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    return await DriverScheduleService.create_schedule(client, request, session)


@router.get("/driver-schedules", response_model=list[DriverScheduleResponse])
async def list_driver_schedules(
    driver_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    return await DriverScheduleService.list_schedules(
        client, session, driver_id=driver_id, page=page, page_size=page_size
    )


@router.put("/driver-schedules/{schedule_id}", response_model=DriverScheduleResponse)
async def update_driver_schedule(
    schedule_id: int,
    request: DriverScheduleUpdateRequest,
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    return await DriverScheduleService.update_schedule(client, schedule_id, request, session)


@router.delete("/driver-schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_driver_schedule(
    schedule_id: int,
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    await DriverScheduleService.delete_schedule(client, schedule_id, session)
    return None


@router.post("/driver-schedules/run-due")
async def run_due_driver_schedules(
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    """Trigger due schedules for current tenant (can be called by external cron)."""
    return await DriverScheduleService.run_due_schedules(client, session)


# ==================== WAYBILL JOB ENDPOINTS ====================


@router.post("/waybill-jobs", response_model=WaybillJobResponse, status_code=status.HTTP_201_CREATED)
async def create_waybill_job(
    request: WaybillJobCreateRequest,
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    """
    Create a new waybill job (manual form entry).

    The job is queued for RPA processing and will be executed by a background worker.
    """
    return await WaybillJobService.create_job(client, request, session, source=TaskSource.MANUAL)


@router.get("/waybill-jobs", response_model=TaskListResponse)
async def list_waybill_jobs(
    status: str | None = None,
    driver_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    """
    List waybill jobs for the client.

    Supports filtering by status, driver, and date range.
    """
    filters = TaskFilterRequest(
        status=status,
        driver_id=driver_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return await WaybillJobService.list_jobs(client, session, filters)


@router.post("/waybill-jobs/{job_id}/retry", response_model=WaybillJobResponse)
async def retry_waybill_job(
    job_id: str,
    request: WaybillRetryRequest = Body(default=WaybillRetryRequest()),
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    """Retry a waybill job with optional auth refresh and payload overrides."""
    return await WaybillJobService.retry_job(client, job_id, session, request)


@router.post("/waybill-jobs/{job_id}/requeue", response_model=WaybillJobResponse)
async def requeue_waybill_job(
    job_id: str,
    request: WaybillRetryRequest = Body(default=WaybillRetryRequest()),
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    """Alias endpoint for manual requeue so operations can distinguish it from automatic retries."""
    return await WaybillJobService.retry_job(client, job_id, session, request)


@router.get("/waybill-jobs/{job_id}", response_model=WaybillJobResponse)
async def get_waybill_job(
    job_id: str,
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    """Get a specific waybill job's status."""
    return await WaybillJobService.get_job(client, job_id, session)


@router.get("/waybill-jobs/{job_id}/timeline", response_model=TaskTimelineResponse)
async def get_waybill_job_timeline(
    job_id: str,
    phase: str | None = None,
    event_type: str | None = None,
    source: str | None = None,
    q: str | None = None,
    include_payload: bool = True,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    """Get a unified timeline for a waybill job."""
    filters = TaskTimelineQuery(
        phase=phase,
        event_type=event_type,
        source=source,
        q=q,
        include_payload=include_payload,
        page=page,
        page_size=page_size,
    )
    return await WaybillJobService.get_job_timeline(client, job_id, session, filters)


@router.get("/waybill-jobs/{job_id}/logs", response_model=TaskLogsResponse)
async def get_waybill_job_logs(
    job_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    """
    Get execution logs for a waybill job.

    Provides detailed step-by-step execution history for audit purposes.
    """
    return await WaybillJobService.get_job_logs(client, job_id, session, page=page, page_size=page_size)


@router.patch("/waybill-jobs/{job_id}", response_model=WaybillJobResponse)
async def update_waybill_job(
    job_id: str,
    request: WaybillJobUpdateRequest,
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    """
    Update an existing waybill job.

    Allows modification of job properties such as priority, max_retries, status, etc.
    Only accessible to the job owner (client) or master admin.
    """
    return await WaybillJobService.update_job(client, job_id, session, request)


@router.delete("/waybill-jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_waybill_job(
    job_id: str,
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    """
    Delete a waybill job permanently.

    Removes the job from the system. This action cannot be undone.
    Only accessible to the job owner (client) or master admin.
    """
    await WaybillJobService.delete_job(client, job_id, session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==================== EXCEL UPLOAD ENDPOINTS ====================


@router.post("/upload/excel", response_model=BulkUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_excel_file(
    file: UploadFile,
    max_retries: int = 3,
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    """
    Upload Excel file for bulk waybill creation.

    The Excel file should contain columns for:
    - driver_national_code (required)
    - origin (required) - TEXT ONLY, no map
    - destination (required) - TEXT ONLY, no map
    - waybill_number (optional)
    - cargo_type (optional)
    - cargo_weight (optional)
    - vehicle_type (optional)
    - plate_number (optional)
    - notes (optional)

    All rows are validated before job creation.
    Invalid rows are reported in the response.
    """
    return await ExcelUploadService.process_upload(
        client,
        file,
        session,
        max_retries=max_retries,
    )


@router.get("/upload/batches/{batch_id}", response_model=BatchStatusResponse)
async def get_batch_status(
    batch_id: str,
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    """Get the processing status of an uploaded batch."""
    return await ExcelUploadService.get_batch_status(client, batch_id, session)


# ==================== REPORTING ENDPOINTS ====================


@router.get("/reports/daily-summary")
async def get_daily_summary(
    days: int = 7,
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    """
    Get daily summary report for the client.

    Returns aggregated statistics for the specified number of days.
    Uses func.date(created_at) for SQLite/PostgreSQL compatibility.
    """
    days = max(1, min(days, 90))
    today = datetime.now(UTC).replace(tzinfo=None).date()
    start_date = today - timedelta(days=days - 1)

    stmt = (
        select(
            func.date(WaybillJob.created_at).label("report_date"),
            WaybillJob.status,
            func.count(WaybillJob.id).label("job_count"),
        )
        .where(
            (WaybillJob.client_id == client.id)
            & (WaybillJob.created_at >= datetime.combine(start_date, time.min))
            & (WaybillJob.created_at <= datetime.combine(today, time.max))
        )
        .group_by(func.date(WaybillJob.created_at), WaybillJob.status)
        .order_by(func.date(WaybillJob.created_at).desc())
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

    return {"client_id": client.id, "summary": summary}


@router.get("/reports/driver-performance")
async def get_driver_performance(
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    """
    Get driver performance report.

    Shows success rate and job counts for each driver.
    Uses aggregate query to avoid N+1 problem.
    """
    # Fetch all drivers for this client
    drivers_stmt = select(Driver).where(Driver.client_id == client.id)
    drivers_result = await session.exec(drivers_stmt)
    drivers = drivers_result.all()

    if not drivers:
        return {"client_id": client.id, "drivers": []}

    driver_ids = [d.id for d in drivers]

    # Single aggregate query for all driver job statistics
    success_statuses = [TaskStatus.SUCCESS.value]
    failed_statuses = [
        TaskStatus.FAILED.value,
        TaskStatus.DEAD_LETTER.value,
        TaskStatus.NEEDS_REVIEW.value,
    ]

    jobs_agg_stmt = (
        select(
            WaybillJob.driver_id,
            func.count(WaybillJob.id).label("total"),
            func.count(
                case(
                    (WaybillJob.status.in_(success_statuses), WaybillJob.id),
                    else_=None,
                )
            ).label("success"),
            func.count(
                case(
                    (WaybillJob.status.in_(failed_statuses), WaybillJob.id),
                    else_=None,
                )
            ).label("failed"),
        )
        .where((WaybillJob.client_id == client.id) & (WaybillJob.driver_id.in_(driver_ids)))
        .group_by(WaybillJob.driver_id)
    )

    agg_result = await session.exec(jobs_agg_stmt)
    stats_by_driver: dict[int, dict] = {
        row.driver_id: {
            "total": int(row.total or 0),
            "success": int(row.success or 0),
            "failed": int(row.failed or 0),
        }
        for row in agg_result.all()
    }

    performance = []
    for driver in drivers:
        stats = stats_by_driver.get(driver.id, {"total": 0, "success": 0, "failed": 0})
        total = stats["total"]
        success = stats["success"]
        failed = stats["failed"]
        success_rate = (success / total * 100) if total > 0 else 0.0

        performance.append(
            {
                "driver_id": driver.id,
                "driver_name": driver.full_name,
                "national_code": driver.driver_national_code,
                "total_jobs": total,
                "success": success,
                "failed": failed,
                "success_rate": round(success_rate, 2),
            }
        )

    return {"client_id": client.id, "drivers": performance}


# ==================== FUEL INQUIRY ENDPOINTS ====================


@router.post("/fuel-inquiries", response_model=FuelInquiryResponse, status_code=status.HTTP_201_CREATED)
async def create_fuel_inquiry(
    request: FuelInquiryCreateRequest,
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    """
    سفارش استعلام سهمیه سوخت جدید برای یک راننده.
    این کار در پس‌زمینه اجرا می‌شود و وضعیت آن در ابتدا pending خواهد بود.
    """
    return await fuel_inquiry_service.create_inquiry(client, request, session)


@router.get("/fuel-inquiries", response_model=FuelInquiryListResponse)
async def list_fuel_inquiries(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    """
    دریافت لیست تاریخچه استعلام‌های سوخت مربوط به این مشتری (مستاجر).
    """
    return await fuel_inquiry_service.list_inquiries(client, page, page_size, session)


@router.get("/fuel-inquiries/{inquiry_id}", response_model=FuelInquiryResponse)
async def get_fuel_inquiry(
    inquiry_id: int,
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    """
    دریافت وضعیت و اطلاعات استخراج‌شده یک استعلام سوخت خاص.
    """
    return await fuel_inquiry_service.get_inquiry(client, inquiry_id, session)
