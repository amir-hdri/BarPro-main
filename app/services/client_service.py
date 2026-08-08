"""Client (tenant) management service."""

import asyncio
import logging
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth_multitenant import (
    create_access_token,
    hash_password,
    is_master_admin,
    verify_password,
)
from app.core.network import is_retryable_network_error
from app.models_multitenant import (
    Client,
    ClientStatus,
    Driver,
    DriverStatus,
    TaskStatus,
    WaybillJob,
)
from app.schemas.multitenant import (
    AdminClientUpdateRequest,
    AdminLoginRequest,
    ClientLoginRequest,
    ClientRegisterRequest,
    ClientResponse,
    ClientStatsResponse,
)

logger = logging.getLogger(__name__)


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
            hashed_password=await hash_password(request.password),
            status=status_value,
            access_level=access_level_value,
            max_drivers=request.max_drivers or 10,
            max_plates=request.max_plates or 20,
            subscription_start_date=request.subscription_start_date,
            subscription_end_date=request.subscription_end_date,
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

        if not client or not await verify_password(request.password, client.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        if client.status != ClientStatus.ACTIVE.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Client account is not active",
            )

        # Check subscription dates
        now = datetime.now(UTC).replace(tzinfo=None)
        if client.subscription_start_date and client.subscription_start_date > now:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="اشتراک شما هنوز شروع نشده است.",
            )
        if client.subscription_end_date and client.subscription_end_date < now:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="اشتراک شما به پایان رسیده است.",
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
            "token_type": "bearer",
            "expires_in": 86400,  # 24 hours
            "client": ClientResponse.model_validate(client),
        }

    @staticmethod
    async def login_master_admin(request: AdminLoginRequest) -> dict:
        """Authenticate the singleton master admin user."""
        if not await is_master_admin(request.username, request.password):
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
        total_drivers = (await session.exec(select(func.count(Driver.id)).where(Driver.client_id == client.id))).one()
        active_drivers = (
            await session.exec(
                select(func.count(Driver.id)).where(
                    Driver.client_id == client.id, Driver.status == DriverStatus.ACTIVE.value
                )
            )
        ).one()

        # Group jobs by status to get counts in one database trip
        jobs_stmt = (
            select(WaybillJob.status, func.count(WaybillJob.id))
            .where(WaybillJob.client_id == client.id)
            .group_by(WaybillJob.status)
        )
        jobs_result = await session.exec(jobs_stmt)
        status_counts = dict(jobs_result.all())

        total_jobs = sum(status_counts.values())
        pending_jobs = status_counts.get(TaskStatus.PENDING.value, 0)
        in_progress_jobs = status_counts.get(TaskStatus.IN_PROGRESS.value, 0)
        success_jobs = status_counts.get(TaskStatus.SUCCESS.value, 0)
        failed_jobs = sum(
            status_counts.get(s, 0)
            for s in [TaskStatus.FAILED.value, TaskStatus.DEAD_LETTER.value, TaskStatus.NEEDS_REVIEW.value]
        )

        # Today's stats
        today_stmt = (
            select(WaybillJob.status, func.count(WaybillJob.id))
            .where(WaybillJob.client_id == client.id, WaybillJob.created_at >= today_start)
            .group_by(WaybillJob.status)
        )
        today_result = await session.exec(today_stmt)
        today_counts = dict(today_result.all())

        today_jobs_count = sum(today_counts.values())
        today_success = today_counts.get(TaskStatus.SUCCESS.value, 0)
        today_failed = sum(
            today_counts.get(s, 0)
            for s in [TaskStatus.FAILED.value, TaskStatus.DEAD_LETTER.value, TaskStatus.NEEDS_REVIEW.value]
        )

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

        if "subscription_start_date" in request.model_fields_set:
            client.subscription_start_date = request.subscription_start_date
        if "subscription_end_date" in request.model_fields_set:
            client.subscription_end_date = request.subscription_end_date

        if request.password:
            client.hashed_password = await hash_password(request.password)

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
