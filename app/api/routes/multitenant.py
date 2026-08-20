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
import os
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth_multitenant import get_current_admin, get_current_client, get_current_user_or_admin
from app.automation.fuel_scraper import FUEL_SCREENSHOTS_DIR
from app.core.config import utcms_config
from app.core.database import get_session
from app.models_multitenant import Client, TaskSource
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
from app.services.client_service import ClientService
from app.services.driver_schedule_service import DriverScheduleService
from app.services.driver_service import DriverService
from app.services.excel_upload_service import ExcelUploadService
from app.services.fuel_inquiry_service import fuel_inquiry_service
from app.services.plate_service import PlateService
from app.services.user_reporting_service import user_reporting_service
from app.services.waybill_job_service import WaybillJobService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["multi-tenant"])
alias_router = APIRouter(tags=["multi-tenant-compat"])
security = HTTPBearer()
AUTH_COOKIE_NAME = "utcms_auth_token"

WAYBILL_SCREENSHOTS_DIR = Path(os.getenv("WAYBILL_SCREENSHOTS_DIR", "runtime/screenshots/waybill"))
_SAFE_JOB_ID = re.compile(r"^[A-Za-z0-9_-]+$")


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
    jwt_ttl_seconds = utcms_config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=result.access_token,
        httponly=True,
        max_age=jwt_ttl_seconds,
        expires=jwt_ttl_seconds,
        samesite="lax",
        secure=_auth_cookie_secure(),
        path="/",
    )
    return result.public_response


@router.post("/admin/login")
async def login_master_admin(
    request: AdminLoginRequest,
    response: Response,
):
    """Authenticate the singleton master admin account."""
    result = await ClientService.login_master_admin(request)
    jwt_ttl_seconds = utcms_config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=result.access_token,
        httponly=True,
        max_age=jwt_ttl_seconds,
        expires=jwt_ttl_seconds,
        samesite="lax",
        secure=_auth_cookie_secure(),
        path="/",
    )
    return result.public_response


@router.post("/auth/logout")
async def logout_client(request: Request, response: Response):
    """Log out the current user/admin and blacklist the JWT token server-side."""
    # Extract token from Authorization header or cookie for blacklisting
    from jwt.exceptions import PyJWTError as JWTError

    from app.auth_multitenant import _decode_jwt
    from app.core.token_blacklist import blacklist_token

    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    if not token:
        token = request.cookies.get(AUTH_COOKIE_NAME)

    if token:
        try:
            payload = _decode_jwt(token)
            jti = payload.get("jti")
            exp = payload.get("exp")
            if jti and exp:
                # PyJWT returns exp as a Unix timestamp (int)
                from datetime import UTC, datetime

                expires_at = datetime.fromtimestamp(int(exp), tz=UTC)
                await blacklist_token(jti, expires_at)
        except (JWTError, Exception):
            # If decoding fails, the token is already invalid — nothing to blacklist
            logger.debug("logout_token_blacklist_skipped", exc_info=True)

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
    user_context: dict = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Create a new driver for the client.

    Each driver has unique UTCMS credentials for waybill registration.
    """
    return await DriverService.create_driver(user_context, request, session)


@router.get("/drivers", response_model=list[DriverResponse])
async def list_drivers(
    status_filter: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    user_context: dict = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    List all drivers for the client or all for admin.

    Supports filtering by status and pagination.
    """
    return await DriverService.list_drivers(
        user_context,
        session,
        status_filter=status_filter,
        page=page,
        page_size=page_size,
    )


@router.get("/drivers/{driver_id}", response_model=DriverResponse)
async def get_driver(
    driver_id: int,
    user_context: dict = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    """Get a specific driver's information."""
    return await DriverService.get_driver(user_context, driver_id, session)


@router.put("/drivers/{driver_id}", response_model=DriverResponse)
async def update_driver(
    driver_id: int,
    request: DriverUpdateRequest,
    user_context: dict = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    """Update driver information."""
    return await DriverService.update_driver(user_context, driver_id, request, session)


@router.delete("/drivers/{driver_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_driver(
    driver_id: int,
    user_context: dict = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    """Delete a driver."""
    await DriverService.delete_driver(user_context, driver_id, session)
    return None


@router.post("/plates", response_model=PlateResponse, status_code=status.HTTP_201_CREATED)
async def create_plate(
    request: PlateCreateRequest,
    user_context: dict = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    return await PlateService.create_plate(user_context, request, session)


@router.get("/plates", response_model=list[PlateResponse])
async def list_plates(
    driver_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    user_context: dict = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    return await PlateService.list_plates(user_context, session, driver_id=driver_id, page=page, page_size=page_size)


@router.put("/plates/{plate_id}", response_model=PlateResponse)
async def update_plate(
    plate_id: int,
    request: PlateUpdateRequest,
    user_context: dict = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    return await PlateService.update_plate(user_context, plate_id, request, session)


@router.delete("/plates/{plate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plate(
    plate_id: int,
    user_context: dict = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    await PlateService.delete_plate(user_context, plate_id, session)
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
    page_size: int = Query(20, ge=1, le=1000),
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
    driver_name: str | None = None,
    plate_number: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    user_context: dict = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    List waybill jobs for the client or admin.

    Supports filtering by status, driver, plate number, and date range.
    """
    dt_from = datetime.fromisoformat(date_from) if date_from else None
    dt_to = datetime.fromisoformat(date_to) if date_to else None
    filters = TaskFilterRequest(
        status=status,
        driver_id=driver_id,
        driver_name=driver_name,
        plate_number=plate_number,
        date_from=dt_from,
        date_to=dt_to,
        page=page,
        page_size=page_size,
    )
    return await WaybillJobService.list_jobs(user_context, session, filters)


@router.post("/waybill-jobs/{job_id}/retry", response_model=WaybillJobResponse)
async def retry_waybill_job(
    job_id: str,
    request: WaybillRetryRequest = Body(default=WaybillRetryRequest()),
    user_context: dict = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    """Retry a waybill job with optional auth refresh and payload overrides."""
    return await WaybillJobService.retry_job(user_context, job_id, session, request)


@router.post("/waybill-jobs/{job_id}/requeue", response_model=WaybillJobResponse)
async def requeue_waybill_job(
    job_id: str,
    request: WaybillRetryRequest = Body(default=WaybillRetryRequest()),
    user_context: dict = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    """Alias endpoint for manual requeue so operations can distinguish it from automatic retries."""
    return await WaybillJobService.retry_job(user_context, job_id, session, request)


@router.get("/waybill-jobs/{job_id}", response_model=WaybillJobResponse)
async def get_waybill_job(
    job_id: str,
    user_context: dict = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    """Get a specific waybill job's status."""
    return await WaybillJobService.get_job(user_context, job_id, session)


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
    user_context: dict = Depends(get_current_user_or_admin),
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
    return await WaybillJobService.get_job_timeline(user_context, job_id, session, filters)


@router.get("/waybill-jobs/{job_id}/logs", response_model=TaskLogsResponse)
async def get_waybill_job_logs(
    job_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_context: dict = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Get execution logs for a waybill job.

    Provides detailed step-by-step execution history for audit purposes.
    """
    return await WaybillJobService.get_job_logs(user_context, job_id, session, page=page, page_size=page_size)


@router.get("/waybill-jobs/{job_id}/screenshot", response_class=FileResponse)
async def get_waybill_job_screenshot(
    job_id: str,
    user_context: dict = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Return the waybill submission screenshot.

    Tenant-scoped: clients may only fetch screenshots of their own jobs;
    the master admin may fetch any. The old public mount
    (``/assets/screenshots/waybill/*``) was removed for security reasons and
    is replaced by this authenticated endpoint.
    """
    await WaybillJobService.get_job(user_context, job_id, session)

    if not _SAFE_JOB_ID.match(job_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid job id")

    screenshot_path = WAYBILL_SCREENSHOTS_DIR / f"{job_id}.png"
    if not screenshot_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenshot not found")

    logger.info(
        "waybill_screenshot_served",
        extra={"extra_fields": {"job_id": job_id, "role": user_context.get("role", "client")}},
    )
    return FileResponse(str(screenshot_path), media_type="image/png")


@router.patch("/waybill-jobs/{job_id}", response_model=WaybillJobResponse)
async def update_waybill_job(
    job_id: str,
    request: WaybillJobUpdateRequest,
    user_context: dict = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Update an existing waybill job.

    Allows modification of job properties such as priority, max_retries, status, etc.
    Only accessible to the job owner (client) or master admin.
    """
    return await WaybillJobService.update_job(user_context, job_id, session, request)


@router.delete("/waybill-jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_waybill_job(
    job_id: str,
    user_context: dict = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Delete a waybill job permanently.

    Removes the job from the system. This action cannot be undone.
    Only accessible to the job owner (client) or master admin.
    """
    await WaybillJobService.delete_job(user_context, job_id, session)
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
    return await user_reporting_service.daily_summary(client.id, days, session)


@router.get("/reports/driver-performance")
async def get_driver_performance(
    client: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_session),
):
    """
    Get driver performance report.

    Shows success rate and job counts for each driver.
    Delegates to UserReportingService.driver_performance().
    """
    drivers_data = await user_reporting_service.driver_performance(client, session, page=1, page_size=1000)
    performance = []
    for d in drivers_data:
        performance.append(
            {
                "driver_id": d["driver_id"],
                "driver_name": d["driver_name"],
                "national_code": d["national_code"],
                "total_jobs": d["total_jobs"],
                "success": d["success_jobs"],
                "failed": d["failed_jobs"],
                "success_rate": d["success_rate"],
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
    page_size: int = Query(20, ge=1, le=1000),
    driver_id: int | None = Query(None),
    status: str | None = Query(None),
    driver_name: str | None = Query(None),
    plate_number: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    user_context: dict = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    دریافت لیست تاریخچه استعلام‌های سوخت مربوط به مشتری یا تمام استعلام‌ها برای ادمین همراه با فیلترهای پیشرفته.
    """
    dt_from = datetime.fromisoformat(date_from) if date_from else None
    dt_to = datetime.fromisoformat(date_to) if date_to else None
    return await fuel_inquiry_service.list_inquiries(
        user_context,
        page,
        page_size,
        session,
        driver_id=driver_id,
        status=status,
        driver_name=driver_name,
        plate_number=plate_number,
        date_from=dt_from,
        date_to=dt_to,
    )


@router.get("/fuel-inquiries/options")
async def get_fuel_inquiry_options():
    """
    دریافت گزینه‌های معتبر سال و ماه برای فرم استعلام سوخت بر اساس تاریخ جاری.
    """
    from app.automation.fuel_scraper import get_current_jalali

    current_year, current_month = get_current_jalali()
    years = [current_year - i for i in range(10)]
    months = [
        {"value": 1, "name": "فروردین"},
        {"value": 2, "name": "اردیبهشت"},
        {"value": 3, "name": "خرداد"},
        {"value": 4, "name": "تیر"},
        {"value": 5, "name": "مرداد"},
        {"value": 6, "name": "شهریور"},
        {"value": 7, "name": "مهر"},
        {"value": 8, "name": "آبان"},
        {"value": 9, "name": "آذر"},
        {"value": 10, "name": "دی"},
        {"value": 11, "name": "بهمن"},
        {"value": 12, "name": "اسفند"},
    ]
    return {
        "success": True,
        "current_year": current_year,
        "current_month": current_month,
        "years": years,
        "months": months,
    }


@router.get("/fuel-inquiries/{inquiry_id}", response_model=FuelInquiryResponse)
async def get_fuel_inquiry(
    inquiry_id: int,
    user_context: dict = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    دریافت وضعیت و اطلاعات استخراج‌شده یک استعلام سوخت خاص.
    """
    return await fuel_inquiry_service.get_inquiry(user_context, inquiry_id, session)


@router.get("/fuel-inquiries/{inquiry_id}/screenshot")
async def get_fuel_inquiry_screenshot(
    inquiry_id: int,
    user_context: dict = Depends(get_current_user_or_admin),
    session: AsyncSession = Depends(get_session),
):
    """Return a fuel screenshot only after tenant/admin ownership validation."""
    import base64

    from fastapi import Response

    inquiry = await fuel_inquiry_service.get_inquiry(user_context, inquiry_id, session)
    screenshot_path = FUEL_SCREENSHOTS_DIR / f"fuel_inquiry_{inquiry.id}.png"
    if screenshot_path.is_file():
        return FileResponse(
            screenshot_path,
            media_type="image/png",
            filename=f"fuel-inquiry-{inquiry.id}.png",
        )

    # Fallback to Base64 Data URI stored in database (e.g. from remote worker nodes)
    raw_url = inquiry.screenshot_url or ""
    if raw_url.startswith("data:image/"):
        try:
            b64_data = raw_url.split(",", 1)[1]
            img_bytes = base64.b64decode(b64_data)
            return Response(content=img_bytes, media_type="image/png")
        except Exception:
            pass

    from fastapi import HTTPException

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="تصویر استعلام یافت نشد")


# ==================== ADMIN DRIVER ENCRYPTION RECOVERY ====================


class DriverReencryptRequest(BaseModel):
    """Request body for re-encrypting a driver's UTCMS password."""

    plain_password: str = Field(
        ...,
        min_length=1,
        description=(
            "Plaintext UTCMS password for this driver. "
            "It will be encrypted with the current DRIVER_ENCRYPTION_KEY before storage."
        ),
    )


@router.post(
    "/admin/drivers/{driver_id}/reencrypt-password",
    summary="Re-encrypt driver password with current key",
    description=(
        "Sets and re-encrypts a driver's UTCMS password using the currently active "
        "``DRIVER_ENCRYPTION_KEY``. Use this to recover from an "
        "``InvalidToken`` / ``driver_key_mismatch`` error caused by a key rotation "
        "or environment mismatch. The plaintext password is **never logged**."
    ),
)
async def admin_reencrypt_driver_password(
    driver_id: int,
    body: DriverReencryptRequest,
    _: dict = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    """Re-encrypt a driver's UTCMS password with the current DRIVER_ENCRYPTION_KEY (admin-only)."""
    await DriverService.reencrypt_driver_password(
        driver_id=driver_id,
        new_plain_password=body.plain_password,
        session=session,
        client_id=None,  # Admin may update any tenant's driver
    )
    return {
        "success": True,
        "driver_id": driver_id,
        "message": "Driver password re-encrypted with current DRIVER_ENCRYPTION_KEY.",
    }


@router.get(
    "/admin/drivers/encryption-health",
    summary="Check encryption health for all drivers",
    description=(
        "Attempts to decrypt every driver's stored UTCMS password with the current "
        "``DRIVER_ENCRYPTION_KEY`` and reports which drivers fail (key mismatch). "
        "Use this after a key rotation to quickly identify which drivers need their "
        "password re-saved via ``/admin/drivers/{id}/reencrypt-password``."
    ),
)
async def admin_check_driver_encryption_health(
    client_id: int | None = Query(default=None, description="Filter by client tenant ID (omit for all tenants)"),
    _: dict = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    """Check which drivers cannot be decrypted with the current DRIVER_ENCRYPTION_KEY (admin-only)."""
    return await DriverService.check_all_drivers_encryption_health(session=session, client_id=client_id)
