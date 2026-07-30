"""Driver management service with tenant isolation."""

import asyncio
import logging
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth_multitenant import (
    decrypt_driver_password,
    encrypt_driver_password,
    verify_tenant_ownership,
)
from app.core.network import is_retryable_network_error
from app.models_multitenant import Client, Driver, DriverStatus
from app.schemas.multitenant import (
    DriverCreateRequest,
    DriverResponse,
    DriverUpdateRequest,
)

logger = logging.getLogger(__name__)


class DriverService:
    """Service for managing drivers with tenant isolation."""

    @staticmethod
    async def create_driver(
        client: Client,
        request: DriverCreateRequest,
        session: AsyncSession,
    ) -> DriverResponse:
        """Create a new driver for the client."""
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
        user_context: dict,
        session: AsyncSession,
        status_filter: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[DriverResponse]:
        """List all drivers for the client."""
        if isinstance(user_context, Client):
            user_context = {"role": "client", "user": user_context}
        role = user_context["role"]
        if role == "master_admin":
            statement = select(Driver)
        else:
            client = user_context["user"]
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

    @staticmethod
    async def reencrypt_driver_password(
        driver_id: int,
        new_plain_password: str,
        session: AsyncSession,
        client_id: int | None = None,
    ) -> Driver:
        """Re-encrypt a driver's UTCMS password with the current DRIVER_ENCRYPTION_KEY.

        This is the recovery path when a driver's stored ciphertext was encrypted with
        a different (old) key and decryption fails with ``InvalidToken``.

        Args:
            driver_id:         Primary key of the driver to update.
            new_plain_password: The plaintext UTCMS password to encrypt and store.
            session:           Active async database session.
            client_id:         When provided, enforces that the driver belongs to this
                               tenant (admin callers may pass ``None`` to skip the check).

        Returns:
            The updated ``Driver`` ORM object.

        Raises:
            HTTPException 404: Driver not found.
            HTTPException 400: Encryption failed (propagated from Fernet).
        """
        driver = await session.get(Driver, driver_id)
        if not driver:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Driver not found")

        if client_id is not None and driver.client_id != client_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Driver not found")

        try:
            driver.utcms_password_encrypted = encrypt_driver_password(new_plain_password)
        except Exception as exc:
            logger.error(
                "driver_reencrypt_failed",
                extra={"extra_fields": {"driver_id": driver_id, "error": str(exc)}},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to encrypt driver password. Check DRIVER_ENCRYPTION_KEY configuration.",
            ) from exc

        driver.updated_at = datetime.now(UTC).replace(tzinfo=None)
        session.add(driver)
        await session.commit()
        await session.refresh(driver)
        logger.info("driver_password_reencrypted", extra={"extra_fields": {"driver_id": driver_id}})
        return driver

    @staticmethod
    async def check_all_drivers_encryption_health(
        session: AsyncSession,
        client_id: int | None = None,
    ) -> dict:
        """Check which drivers cannot be decrypted with the current DRIVER_ENCRYPTION_KEY.

        Iterates all drivers (optionally filtered by tenant) and attempts decryption.
        Returns a summary with counts and a list of problematic driver IDs.

        This is a *read-only* operation — no passwords are modified.
        """
        from sqlmodel import select as _select

        from app.auth_multitenant import DriverPasswordDecryptError

        stmt = _select(Driver)
        if client_id is not None:
            stmt = stmt.where(Driver.client_id == client_id)
        drivers = (await session.exec(stmt)).all()

        ok_count = 0
        failed: list[dict] = []

        for driver in drivers:
            try:
                decrypt_driver_password(driver.utcms_password_encrypted)
                ok_count += 1
            except (DriverPasswordDecryptError, Exception):
                failed.append(
                    {
                        "driver_id": driver.id,
                        "client_id": driver.client_id,
                        "utcms_username": driver.utcms_username,
                    }
                )

        return {
            "total": len(drivers),
            "ok": ok_count,
            "failed_count": len(failed),
            "failed_drivers": failed,
        }
