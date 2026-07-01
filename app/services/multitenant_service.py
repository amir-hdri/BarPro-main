"""
Multi-tenant services for managing clients, drivers, and waybill jobs.

All services enforce tenant isolation - clients can only access their own data.
"""

import asyncio
import json
import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth_multitenant import (
    create_access_token,
    decrypt_driver_password,
    encrypt_driver_password,
    hash_password,
    is_master_admin,
    verify_password,
    verify_tenant_ownership,
)
from app.core.network import is_retryable_network_error
from app.models_multitenant import (
    Client,
    ClientStatus,
    Driver,
    DriverPlate,
    DriverSchedule,
    DriverStatus,
    ScheduleFrequency,
    TaskSource,
    TaskStatus,
    WaybillJob,
    WaybillTaskLog,
)
from app.models_rpa import DomainEvent, DriverRuntimeState, DriverRuntimeStateValue
from app.rpa.event_taxonomy import (
    JOB_RETRY_REQUESTED,
    timeline_phase_for,
    timeline_title_for,
)
from app.schemas.multitenant import (
    AdminClientUpdateRequest,
    AdminLoginRequest,
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
    PlateCreateRequest,
    PlateResponse,
    PlateUpdateRequest,
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
from app.services.rpa_dispatch_service import rpa_dispatch_service
from app.services.rpa_runtime_service import rpa_runtime
from app.services.rpa_scheduler_service import rpa_scheduler_service

logger = logging.getLogger(__name__)


def _safe_json_payload(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {"value": payload}
    except Exception:
        return {"raw": raw}


def _deep_merge_dict(base: dict, updates: dict) -> dict:
    """Recursively merge dictionaries while letting override values win."""
    merged = dict(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _timeline_matches_query(entry: TaskTimelineEntry, query: TaskTimelineQuery) -> bool:
    if query.phase and (entry.phase or "").lower() != query.phase.lower():
        return False
    if query.event_type and entry.event_type != query.event_type:
        return False
    if query.source and entry.source != query.source:
        return False
    if query.q:
        needle = query.q.lower()
        haystack = " ".join(
            [
                entry.title,
                entry.event_type,
                entry.message or "",
                entry.status or "",
                entry.source,
                json.dumps(entry.payload or {}, ensure_ascii=False),
            ]
        ).lower()
        if needle not in haystack:
            return False
    return True


def _parse_weekdays_csv(raw: str | None) -> list[int]:
    if not raw:
        return []
    output: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if token.isdigit():
            value = int(token)
            if 0 <= value <= 6:
                output.append(value)
    return sorted(set(output))


def _build_weekdays_csv(values: list[int] | None) -> str | None:
    if not values:
        return None
    normalized = sorted({int(item) for item in values if 0 <= int(item) <= 6})
    return ",".join(str(item) for item in normalized) if normalized else None


def _parse_csv_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _build_csv_list(values: list[str] | None) -> str | None:
    if not values:
        return None
    normalized = [item.strip() for item in values if item and item.strip()]
    return ",".join(sorted(set(normalized))) if normalized else None


def _resolve_run_times(item: DriverSchedule) -> list[str]:
    run_times = _parse_csv_list(item.run_times_csv)
    if run_times:
        return run_times
    return [item.run_time]


# ==================== CLIENT SERVICE ====================


class ClientService:
    """Service for managing clients (tenants)."""

    @staticmethod
    async def register_client(
        request: ClientRegisterRequest,
        session: AsyncSession,
    ) -> ClientResponse:
        """Register a new client."""
        status_value = (request.status or ClientStatus.ACTIVE.value).strip().lower()
        access_level_value = (request.access_level or "standard").strip().lower()

        # Validate status if provided
        if status_value not in [value.value for value in ClientStatus]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status. Valid statuses are: {[value.value for value in ClientStatus]}",
            )

        # Check if email or client_code already exists
        existing = await session.exec(
            select(Client).where((Client.email == request.email) | (Client.client_code == request.client_code))
        )
        if existing.first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Client with this email or code already exists",
            )

        # Create new client (with required NOT NULL fields username and full_name)
        client = Client(
            client_code=request.client_code,
            name=request.name,
            email=request.email,
            phone=request.phone,
            username=request.client_code,  # fill the mandatory column
            full_name=request.name,  # fill the mandatory column
            hashed_password=hash_password(request.password),
            status=status_value,
            access_level=access_level_value,
            max_drivers=request.max_drivers or 10,
            max_plates=request.max_plates or 20,
        )

        # Add retry logic for database operations to handle network errors
        max_retries = 3
        for attempt in range(max_retries):
            try:
                session.add(client)
                await session.commit()
                await session.refresh(client)
                break  # Exit loop if successful
            except Exception as e:
                await session.rollback()  # Rollback on error
                # If it's the last attempt, raise the appropriate error
                if attempt == max_retries - 1:  # Last attempt
                    # If it's a network error, return appropriate status
                    if is_retryable_network_error(e):
                        logger.error(
                            f"Failed to register client due to network error after {max_retries} attempts: {str(e)}"
                        )
                        raise HTTPException(
                            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Service temporarily unavailable due to network issues. Please try again later.",
                        ) from e
                    else:
                        logger.error(f"Failed to register client: {str(e)}")
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to register client: {str(e)}"
                        ) from e
                # Only continue retrying if it's a network-related error
                if not is_retryable_network_error(e):
                    logger.error(f"Non-network error during client registration: {str(e)}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to register client: {str(e)}"
                    ) from e
                # Wait before retry with exponential backoff
                logger.warning(f"Retrying client registration after network error (attempt {attempt + 1}): {str(e)}")
                await asyncio.sleep(2**attempt)  # 1s, 2s, 4s backoff

        logger.info(
            "audit_client_registered",
            extra={"extra_fields": {"client_id": client.id, "client_code": client.client_code, "email": client.email}},
        )

        return ClientResponse.model_validate(client)

    @staticmethod
    async def login_client(
        request: ClientLoginRequest,
        session: AsyncSession,
    ) -> dict:
        """Authenticate a client and return JWT token."""
        # Find client by email
        statement = select(Client).where(Client.email == request.email)
        result = await session.exec(statement)
        client = result.first()

        if not client or not verify_password(request.password, client.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        if client.status != ClientStatus.ACTIVE.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Client account is not active",
            )

        # Update last login time
        client.last_login_at = datetime.now(UTC).replace(tzinfo=None)
        await session.commit()

        # Create JWT token
        token = create_access_token(
            client_id=client.id,
            client_code=client.client_code,
            email=client.email,
        )

        logger.info(
            "audit_client_login",
            extra={"extra_fields": {"client_id": client.id, "client_code": client.client_code, "email": client.email}},
        )

        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": 86400,  # 24 hours
            "client": ClientResponse.model_validate(client),
        }

    @staticmethod
    async def login_master_admin(request: AdminLoginRequest) -> dict:
        """Authenticate the singleton master admin user."""
        if not is_master_admin(request.username, request.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid admin username or password",
            )

        token = create_access_token(
            client_id=0,
            client_code=request.username,
            email=f"{request.username}@local.admin",
            role="master_admin",
        )
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": 86400,
            "admin": {
                "username": request.username,
                "role": "master_admin",
            },
        }

    @staticmethod
    async def get_client_profile(
        client: Client,
        session: AsyncSession,
    ) -> ClientResponse:
        """Get client profile."""
        await session.refresh(client)
        return ClientResponse.model_validate(client)

    @staticmethod
    async def get_client_stats(
        client: Client,
        session: AsyncSession,
    ) -> ClientStatsResponse:
        """Get client dashboard statistics."""
        today = datetime.now(UTC).replace(tzinfo=None).date()
        today_start = datetime.combine(today, datetime.min.time())

        # Count drivers using db aggregate
        from sqlmodel import func
        total_drivers = (await session.exec(select(func.count(Driver.id)).where(Driver.client_id == client.id))).one()
        active_drivers = (await session.exec(select(func.count(Driver.id)).where(Driver.client_id == client.id, Driver.status == DriverStatus.ACTIVE.value))).one()

        # Group jobs by status to get counts in one database trip
        jobs_stmt = select(WaybillJob.status, func.count(WaybillJob.id)).where(WaybillJob.client_id == client.id).group_by(WaybillJob.status)
        jobs_result = await session.exec(jobs_stmt)
        status_counts = dict(jobs_result.all())

        total_jobs = sum(status_counts.values())
        pending_jobs = status_counts.get(TaskStatus.PENDING.value, 0)
        in_progress_jobs = status_counts.get(TaskStatus.IN_PROGRESS.value, 0)
        success_jobs = status_counts.get(TaskStatus.SUCCESS.value, 0)
        failed_jobs = sum(status_counts.get(s, 0) for s in [TaskStatus.FAILED.value, TaskStatus.DEAD_LETTER.value, TaskStatus.NEEDS_REVIEW.value])

        # Today's stats
        today_stmt = select(WaybillJob.status, func.count(WaybillJob.id)).where(WaybillJob.client_id == client.id, WaybillJob.created_at >= today_start).group_by(WaybillJob.status)
        today_result = await session.exec(today_stmt)
        today_counts = dict(today_result.all())

        today_jobs_count = sum(today_counts.values())
        today_success = today_counts.get(TaskStatus.SUCCESS.value, 0)
        today_failed = sum(today_counts.get(s, 0) for s in [TaskStatus.FAILED.value, TaskStatus.DEAD_LETTER.value, TaskStatus.NEEDS_REVIEW.value])

        # Success rate
        success_rate = (success_jobs / total_jobs * 100) if total_jobs > 0 else 0.0

        return ClientStatsResponse(
            client_id=client.id,
            total_drivers=total_drivers,
            active_drivers=active_drivers,
            total_jobs=total_jobs,
            pending_jobs=pending_jobs,
            in_progress_jobs=in_progress_jobs,
            success_jobs=success_jobs,
            failed_jobs=failed_jobs,
            today_jobs=today_jobs_count,
            today_success=today_success,
            today_failed=today_failed,
            success_rate=round(success_rate, 2),
            created_at=client.created_at,
        )

    @staticmethod
    async def list_clients(
        session: AsyncSession,
        *,
        q: str | None = None,
        status_filter: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[ClientResponse]:
        """List tenant accounts for master admin operations with search and pagination."""
        statement = select(Client)
        if status_filter:
            statement = statement.where(Client.status == status_filter)
        if q:
            needle = f"%{q.strip()}%"
            statement = statement.where(
                (col(Client.name).ilike(needle))
                | (col(Client.email).ilike(needle))
                | (col(Client.client_code).ilike(needle))
            )

        statement = statement.order_by(col(Client.created_at).desc())
        statement = statement.offset(max(0, page - 1) * max(1, page_size)).limit(max(1, page_size))
        result = await session.exec(statement)
        return [ClientResponse.model_validate(item) for item in result.all()]

    @staticmethod
    async def update_client_by_admin(
        client_id: int,
        request: AdminClientUpdateRequest,
        session: AsyncSession,
    ) -> ClientResponse:
        """Allow master admin to update tenant account fields."""
        client = await session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

        if request.client_code and request.client_code != client.client_code:
            existing_code = await session.exec(select(Client).where(Client.client_code == request.client_code))
            if existing_code.first():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Client code already exists")
            client.client_code = request.client_code

        if request.email and request.email != client.email:
            existing_email = await session.exec(select(Client).where(Client.email == request.email))
            if existing_email.first():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Client email already exists")
            client.email = request.email

        for field in (
            "name",
            "phone",
            "status",
            "access_level",
            "max_drivers",
            "max_plates",
            "max_concurrent_tasks",
            "max_daily_tasks",
        ):
            value = getattr(request, field)
            if value is not None:
                setattr(client, field, value)

        if request.password:
            client.hashed_password = hash_password(request.password)

        client.updated_at = datetime.now(UTC).replace(tzinfo=None)

        # Add retry logic for database operations to handle network errors
        max_retries = 3
        for attempt in range(max_retries):
            try:
                session.add(client)
                await session.commit()
                await session.refresh(client)
                break  # Exit loop if successful
            except Exception as e:
                await session.rollback()  # Rollback on error
                # If it's the last attempt, raise the appropriate error
                if attempt == max_retries - 1:  # Last attempt
                    # If it's a network error, return appropriate status
                    if is_retryable_network_error(e):
                        logger.error(
                            f"Failed to update client due to network error after {max_retries} attempts: {str(e)}"
                        )
                        raise HTTPException(
                            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Service temporarily unavailable due to network issues. Please try again later.",
                        ) from e
                    else:
                        logger.error(f"Failed to update client: {str(e)}")
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to update client: {str(e)}"
                        ) from e
                # Only continue retrying if it's a network-related error
                if not is_retryable_network_error(e):
                    logger.error(f"Non-network error during client update: {str(e)}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to update client: {str(e)}"
                    ) from e
                # Wait before retry with exponential backoff
                logger.warning(f"Retrying client update after network error (attempt {attempt + 1}): {str(e)}")
                await asyncio.sleep(2**attempt)  # 1s, 2s, 4s backoff

        logger.info(
            "audit_client_updated", extra={"extra_fields": {"client_id": client.id, "client_code": client.client_code}}
        )
        return ClientResponse.model_validate(client)

    @staticmethod
    async def delete_client_by_admin(client_id: int, session: AsyncSession) -> None:
        """Delete a tenant account."""
        client = await session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

        logger.info(
            "audit_client_deleted", extra={"extra_fields": {"client_id": client.id, "client_code": client.client_code}}
        )

        # Add retry logic for database operations to handle network errors
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await session.delete(client)
                await session.commit()
                break  # Exit loop if successful
            except Exception as e:
                await session.rollback()  # Rollback on error
                # If it's the last attempt, raise the appropriate error
                if attempt == max_retries - 1:  # Last attempt
                    # If it's a network error, return appropriate status
                    if is_retryable_network_error(e):
                        logger.error(
                            f"Failed to delete client due to network error after {max_retries} attempts: {str(e)}"
                        )
                        raise HTTPException(
                            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Service temporarily unavailable due to network issues. Please try again later.",
                        ) from e
                    else:
                        logger.error(f"Failed to delete client: {str(e)}")
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to delete client: {str(e)}"
                        ) from e
                # Only continue retrying if it's a network-related error
                if not is_retryable_network_error(e):
                    logger.error(f"Non-network error during client deletion: {str(e)}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to delete client: {str(e)}"
                    ) from e
                # Wait before retry with exponential backoff
                logger.warning(f"Retrying client deletion after network error (attempt {attempt + 1}): {str(e)}")
                await asyncio.sleep(2**attempt)  # 1s, 2s, 4s backoff


# ==================== DRIVER SERVICE ====================


class DriverService:
    """Service for managing drivers with tenant isolation."""

    @staticmethod
    async def create_driver(
        client: Client,
        request: DriverCreateRequest,
        session: AsyncSession,
    ) -> DriverResponse:
        """Create a new driver for the client."""
        # Check driver limit
        from sqlmodel import func
        driver_count = (await session.exec(select(func.count(Driver.id)).where(Driver.client_id == client.id))).one()
        if driver_count >= client.max_drivers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Driver limit reached. Maximum allowed: {client.max_drivers}",
            )

        # Check if national code already exists for this client
        existing = await session.exec(
            select(Driver).where(
                (Driver.client_id == client.id) & (Driver.driver_national_code == request.driver_national_code)
            )
        )
        if existing.first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Driver with this national code already exists",
            )

        # Create driver
        driver = Driver(
            client_id=client.id,
            driver_national_code=request.driver_national_code,
            full_name=request.full_name,
            phone=request.phone,
            license_number=request.license_number,
            utcms_username=request.utcms_username,
            utcms_password_encrypted=encrypt_driver_password(request.utcms_password),
            status=DriverStatus.ACTIVE.value,
        )

        # Add retry logic for database operations to handle network errors
        max_retries = 3
        for attempt in range(max_retries):
            try:
                session.add(driver)
                await session.commit()
                await session.refresh(driver)
                break  # Exit loop if successful
            except Exception as e:
                await session.rollback()  # Rollback on error
                # If it's the last attempt, raise the appropriate error
                if attempt == max_retries - 1:  # Last attempt
                    # If it's a network error, return appropriate status
                    if is_retryable_network_error(e):
                        logger.error(
                            f"Failed to create driver due to network error after {max_retries} attempts: {str(e)}"
                        )
                        raise HTTPException(
                            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Service temporarily unavailable due to network issues. Please try again later.",
                        ) from e
                    else:
                        logger.error(f"Failed to create driver: {str(e)}")
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to create driver: {str(e)}"
                        ) from e
                # Only continue retrying if it's a network-related error
                if not is_retryable_network_error(e):
                    logger.error(f"Non-network error during driver creation: {str(e)}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to create driver: {str(e)}"
                    ) from e
                # Wait before retry with exponential backoff
                logger.warning(f"Retrying driver creation after network error (attempt {attempt + 1}): {str(e)}")
                await asyncio.sleep(2**attempt)  # 1s, 2s, 4s backoff

        return DriverResponse(
            id=driver.id,
            client_id=driver.client_id,
            driver_national_code=driver.driver_national_code,
            full_name=driver.full_name,
            phone=driver.phone,
            license_number=driver.license_number,
            utcms_username=driver.utcms_username,
            status=driver.status,
            created_at=driver.created_at,
            updated_at=driver.updated_at,
        )

    @staticmethod
    async def list_drivers(
        client: Client,
        session: AsyncSession,
        status_filter: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[DriverResponse]:
        """List all drivers for the client."""
        statement = select(Driver).where(Driver.client_id == client.id)
        if status_filter:
            statement = statement.where(Driver.status == status_filter)
        statement = statement.offset((page - 1) * page_size).limit(page_size)

        result = await session.exec(statement)
        drivers = result.all()

        return [
            DriverResponse(
                id=d.id,
                client_id=d.client_id,
                driver_national_code=d.driver_national_code,
                full_name=d.full_name,
                phone=d.phone,
                license_number=d.license_number,
                utcms_username=d.utcms_username,
                status=d.status,
                created_at=d.created_at,
                updated_at=d.updated_at,
            )
            for d in drivers
        ]

    @staticmethod
    async def get_driver(
        client: Client,
        driver_id: int,
        session: AsyncSession,
    ) -> DriverResponse:
        """Get a specific driver."""
        driver = await session.get(Driver, driver_id)
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver not found",
            )

        # Verify tenant ownership
        verify_tenant_ownership(client, driver, Driver)

        return DriverResponse(
            id=driver.id,
            client_id=driver.client_id,
            driver_national_code=driver.driver_national_code,
            full_name=driver.full_name,
            phone=driver.phone,
            license_number=driver.license_number,
            utcms_username=driver.utcms_username,
            status=driver.status,
            created_at=driver.created_at,
            updated_at=driver.updated_at,
        )

    @staticmethod
    async def update_driver(
        client: Client,
        driver_id: int,
        request: DriverUpdateRequest,
        session: AsyncSession,
    ) -> DriverResponse:
        """Update driver information."""
        driver = await session.get(Driver, driver_id)
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver not found",
            )

        # Verify tenant ownership
        verify_tenant_ownership(client, driver, Driver)

        # Update fields
        update_data = request.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if field == "utcms_password" and value:
                driver.utcms_password_encrypted = encrypt_driver_password(value)
            elif field != "utcms_password":
                setattr(driver, field, value)

        driver.updated_at = datetime.now(UTC).replace(tzinfo=None)

        # Add retry logic for database operations to handle network errors
        max_retries = 3
        for attempt in range(max_retries):
            try:
                session.add(driver)
                await session.commit()
                await session.refresh(driver)
                break  # Exit loop if successful
            except Exception as e:
                await session.rollback()  # Rollback on error
                # If it's the last attempt, raise the appropriate error
                if attempt == max_retries - 1:  # Last attempt
                    # If it's a network error, return appropriate status
                    if is_retryable_network_error(e):
                        logger.error(
                            f"Failed to update driver due to network error after {max_retries} attempts: {str(e)}"
                        )
                        raise HTTPException(
                            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Service temporarily unavailable due to network issues. Please try again later.",
                        ) from e
                    else:
                        logger.error(f"Failed to update driver: {str(e)}")
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to update driver: {str(e)}"
                        ) from e
                # Only continue retrying if it's a network-related error
                if not is_retryable_network_error(e):
                    logger.error(f"Non-network error during driver update: {str(e)}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to update driver: {str(e)}"
                    ) from e
                # Wait before retry with exponential backoff
                logger.warning(f"Retrying driver update after network error (attempt {attempt + 1}): {str(e)}")
                await asyncio.sleep(2**attempt)  # 1s, 2s, 4s backoff

        return DriverResponse(
            id=driver.id,
            client_id=driver.client_id,
            driver_national_code=driver.driver_national_code,
            full_name=driver.full_name,
            phone=driver.phone,
            license_number=driver.license_number,
            utcms_username=driver.utcms_username,
            status=driver.status,
            created_at=driver.created_at,
            updated_at=driver.updated_at,
        )

    @staticmethod
    async def delete_driver(
        client: Client,
        driver_id: int,
        session: AsyncSession,
    ) -> bool:
        """Delete a driver."""
        driver = await session.get(Driver, driver_id)
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver not found",
            )

        # Verify tenant ownership
        verify_tenant_ownership(client, driver, Driver)

        # Add retry logic for database operations to handle network errors
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await session.delete(driver)
                await session.commit()
                return True  # Exit loop if successful
            except Exception as e:
                await session.rollback()  # Rollback on error
                # If it's the last attempt, raise the appropriate error
                if attempt == max_retries - 1:  # Last attempt
                    # If it's a network error, return appropriate status
                    if is_retryable_network_error(e):
                        logger.error(
                            f"Failed to delete driver due to network error after {max_retries} attempts: {str(e)}"
                        )
                        raise HTTPException(
                            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Service temporarily unavailable due to network issues. Please try again later.",
                        ) from e
                    else:
                        logger.error(f"Failed to delete driver: {str(e)}")
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to delete driver: {str(e)}"
                        ) from e
                # Only continue retrying if it's a network-related error
                if not is_retryable_network_error(e):
                    logger.error(f"Non-network error during driver deletion: {str(e)}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to delete driver: {str(e)}"
                    ) from e
                # Wait before retry with exponential backoff
                logger.warning(f"Retrying driver deletion after network error (attempt {attempt + 1}): {str(e)}")
                await asyncio.sleep(2**attempt)  # 1s, 2s, 4s backoff

        return False

    @staticmethod
    async def get_driver_credentials(
        client: Client,
        driver_id: int,
        session: AsyncSession,
    ) -> tuple[str, str]:
        """Get driver's UTCMS credentials (decrypted) for RPA bot."""
        driver = await session.get(Driver, driver_id)
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver not found",
            )

        # Verify tenant ownership
        verify_tenant_ownership(client, driver, Driver)

        username = driver.utcms_username
        password = decrypt_driver_password(driver.utcms_password_encrypted)

        return username, password


class PlateService:
    """Manage vehicle plates with tenant isolation."""

    @staticmethod
    async def create_plate(client: Client, request: PlateCreateRequest, session: AsyncSession) -> PlateResponse:
        driver = await session.get(Driver, request.driver_id)
        if not driver:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Driver not found")
        verify_tenant_ownership(client, driver, Driver)

        from sqlmodel import func
        plate_count = (await session.exec(select(func.count(DriverPlate.id)).where(DriverPlate.client_id == client.id))).one()
        if plate_count >= client.max_plates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Plate limit reached. Maximum allowed: {client.max_plates}",
            )

        existing = await session.exec(
            select(DriverPlate).where(
                (DriverPlate.client_id == client.id) & (DriverPlate.plate_number == request.plate_number)
            )
        )
        if existing.first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Plate already exists")

        plate = DriverPlate(
            client_id=client.id,
            driver_id=request.driver_id,
            plate_number=request.plate_number,
            vehicle_type=request.vehicle_type,
            status=request.status,
            notes=request.notes,
        )
        session.add(plate)
        await session.commit()
        await session.refresh(plate)
        return PlateResponse.model_validate(plate)

    @staticmethod
    async def list_plates(
        client: Client, session: AsyncSession, driver_id: int | None = None, page: int = 1, page_size: int = 20
    ) -> list[PlateResponse]:
        statement = select(DriverPlate).where(DriverPlate.client_id == client.id)
        if driver_id:
            statement = statement.where(DriverPlate.driver_id == driver_id)
        statement = statement.order_by(col(DriverPlate.created_at).desc())
        statement = statement.offset((page - 1) * page_size).limit(page_size)
        rows = (await session.exec(statement)).all()
        return [PlateResponse.model_validate(item) for item in rows]

    @staticmethod
    async def update_plate(
        client: Client, plate_id: int, request: PlateUpdateRequest, session: AsyncSession
    ) -> PlateResponse:
        plate = await session.get(DriverPlate, plate_id)
        if not plate:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plate not found")
        verify_tenant_ownership(client, plate, DriverPlate)

        update_data = request.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(plate, field, value)
        plate.updated_at = datetime.now(UTC).replace(tzinfo=None)
        session.add(plate)
        await session.commit()
        await session.refresh(plate)
        return PlateResponse.model_validate(plate)

    @staticmethod
    async def delete_plate(client: Client, plate_id: int, session: AsyncSession) -> None:
        plate = await session.get(DriverPlate, plate_id)
        if not plate:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plate not found")
        verify_tenant_ownership(client, plate, DriverPlate)
        await session.delete(plate)
        await session.commit()


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
            payload_template_json=json.dumps(request.payload_template, ensure_ascii=False),
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
            item.payload_template_json = json.dumps(payload.pop("payload_template") or {}, ensure_ascii=False)
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
            schedule.next_run_at = now + timedelta(days=1 if schedule.frequency == ScheduleFrequency.DAILY.value else 7)
            schedule.updated_at = now
            session.add(schedule)
        await session.commit()
        return {"created_jobs": created_jobs, "created_count": len(created_jobs), "skipped": skipped}


# ==================== WAYBILL JOB SERVICE ====================


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
        client: Client,
        session: AsyncSession,
        filters: TaskFilterRequest,
    ) -> TaskListResponse:
        """List jobs for the client with filtering."""
        statement = select(WaybillJob).where(WaybillJob.client_id == client.id)

        if filters.status:
            statement = statement.where(WaybillJob.status == filters.status)
        if filters.driver_id:
            statement = statement.where(WaybillJob.driver_id == filters.driver_id)
        if filters.date_from:
            statement = statement.where(WaybillJob.created_at >= filters.date_from)
        if filters.date_to:
            statement = statement.where(WaybillJob.created_at <= filters.date_to)

        # Get total count
        from sqlmodel import func
        count_stmt = select(func.count(WaybillJob.id)).where(WaybillJob.client_id == client.id)
        if filters.status:
            count_stmt = count_stmt.where(WaybillJob.status == filters.status)
        if filters.driver_id:
            count_stmt = count_stmt.where(WaybillJob.driver_id == filters.driver_id)
        if filters.date_from:
            count_stmt = count_stmt.where(WaybillJob.created_at >= filters.date_from)
        if filters.date_to:
            count_stmt = count_stmt.where(WaybillJob.created_at <= filters.date_to)
        count_result = await session.exec(count_stmt)
        total = count_result.one()

        # Get paginated results
        statement = statement.order_by(col(WaybillJob.created_at).desc())
        statement = statement.offset((filters.page - 1) * filters.page_size).limit(filters.page_size)

        result = await session.exec(statement)
        jobs = result.all()

        total_pages = (total + filters.page_size - 1) // filters.page_size

        return TaskListResponse(
            tasks=[WaybillJobResponse.model_validate(j) for j in jobs],
            total=total,
            page=filters.page,
            page_size=filters.page_size,
            total_pages=total_pages,
        )

    @staticmethod
    async def get_job(
        client: Client,
        job_id: str,
        session: AsyncSession,
    ) -> WaybillJobResponse:
        """Get a specific job."""
        statement = select(WaybillJob).where((WaybillJob.client_id == client.id) & (WaybillJob.job_id == job_id))
        result = await session.exec(statement)
        job = result.first()

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found",
            )

        return WaybillJobResponse.model_validate(job)

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
            job.payload_json = json.dumps(payload, ensure_ascii=False)
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

        job.status = TaskStatus.PENDING.value
        job.submit_after = now
        job.next_retry_at = None
        job.finished_at = None
        job.started_at = None
        job.retryable = True
        job.updated_at = now
        job.last_error = None
        job.error_category = None
        job.terminal_reason = None
        job.worker_id = None
        job.celery_task_id = None

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
                details_json=json.dumps(event_payload, ensure_ascii=False),
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
        client: Client,
        job_id: str,
        session: AsyncSession,
        filters: TaskTimelineQuery | None = None,
    ) -> TaskTimelineResponse:
        """Get a merged timeline of domain events and task logs for a job."""
        query = filters or TaskTimelineQuery()
        job_stmt = select(WaybillJob).where((WaybillJob.client_id == client.id) & (WaybillJob.job_id == job_id))
        job_result = await session.exec(job_stmt)
        job = job_result.first()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found",
            )

        logs_stmt = select(WaybillTaskLog).where(
            (WaybillTaskLog.client_id == client.id) & (WaybillTaskLog.job_id == job_id)
        )
        events_stmt = select(DomainEvent).where((DomainEvent.client_id == client.id) & (DomainEvent.job_id == job_id))

        logs = (await session.exec(logs_stmt)).all()
        events = (await session.exec(events_stmt)).all()

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
        if request.business_date is not None:
            update_data["business_date"] = request.business_date
        if request.correlation_id is not None:
            update_data["correlation_id"] = request.correlation_id

        for key, value in update_data.items():
            setattr(job, key, value)

        session.add(job)
        await session.commit()
        await session.refresh(job)

        session.add(
            WaybillTaskLog(
                job_id=job.job_id,
                client_id=client.id,
                step="manual_update",
                status="success",
                message=f"Job updated: {list(update_data.keys())}",
                details_json=json.dumps({"updated_fields": list(update_data.keys())}, ensure_ascii=False),
            )
        )
        await session.commit()

        return WaybillJobResponse.model_validate(job)

    @staticmethod
    async def delete_job(
        client: Client,
        job_id: str,
        session: AsyncSession,
    ) -> dict[str, object]:
        """Delete a waybill job permanently."""
        statement = select(WaybillJob).where((WaybillJob.client_id == client.id) & (WaybillJob.job_id == job_id))
        result = await session.exec(statement)
        job = result.first()

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found",
            )

        job_id_to_delete = job.job_id
        client_id = job.client_id

        await session.delete(job)
        await session.commit()

        session.add(
            WaybillTaskLog(
                job_id=job_id_to_delete,
                client_id=client_id,
                step="manual_delete",
                status="success",
                message="Job deleted by user",
                details_json=json.dumps({"deleted": True, "job_id": job_id_to_delete}, ensure_ascii=False),
            )
        )
        await session.commit()

        return {
            "success": True,
            "message": "Job deleted successfully",
            "job_id": job_id_to_delete,
        }
