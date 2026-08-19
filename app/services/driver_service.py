"""Driver management service with tenant isolation."""

import asyncio
import logging
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import delete, text
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth_multitenant import (
    decrypt_driver_password,
    encrypt_driver_password,
    verify_tenant_ownership,
)
from app.core.network import is_retryable_network_error
from app.models_multitenant import (
    Client,
    Driver,
    DriverPlate,
    DriverSchedule,
    DriverStatus,
    FuelInquiry,
    TaskStatus,
    WaybillJob,
)

from app.models.admin import AdminDriverSchedule
from app.models_rpa import (
    DriverDailyCounter,
    DriverRuntimeState,
    DriverSessionMetadata,
    DomainEvent,
    WaybillAttempt,
)


from app.schemas.multitenant import (
    DriverCreateRequest,
    DriverResponse,
    DriverUpdateRequest,
    _normalize_plate,
)

logger = logging.getLogger(__name__)


def _normalize_digits_str(val: str | None) -> str | None:
    if not val:
        return val
    table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    return val.translate(table).strip()


class DriverService:
    """Service for managing drivers with tenant isolation."""

    @staticmethod
    async def create_driver(
        user_context: dict | Client,
        request: DriverCreateRequest,
        session: AsyncSession,
    ) -> DriverResponse:
        """Create a new driver for the client."""
        if isinstance(user_context, Client):
            client = user_context
        elif isinstance(user_context, dict) and user_context.get("role") == "master_admin":
            # For master admin, associate with the first active client or find one
            client = (await session.exec(select(Client).where(Client.status == "active"))).first()
            if not client:
                client = (await session.exec(select(Client))).first()
            if not client:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No client account found to associate driver with.",
                )
        else:
            client = user_context.get("user") if isinstance(user_context, dict) else user_context

        driver_count = (await session.exec(select(func.count(Driver.id)).where(Driver.client_id == client.id))).one()
        if driver_count >= client.max_drivers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Driver limit reached. Maximum allowed: {client.max_drivers}",
            )

        clean_nat_code = _normalize_digits_str(request.driver_national_code) or ""
        clean_phone = _normalize_digits_str(request.phone)

        # Check if national code already exists for this client
        existing = await session.exec(
            select(Driver).where(
                (Driver.client_id == client.id) & (Driver.driver_national_code == clean_nat_code)
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
            driver_national_code=clean_nat_code,
            full_name=request.full_name.strip(),
            phone=clean_phone,
            license_number=request.license_number.strip() if request.license_number else None,
            utcms_username=request.utcms_username.strip(),
            utcms_password_encrypted=encrypt_driver_password(request.utcms_password.strip()),
            status=DriverStatus.ACTIVE.value,
        )

        session.add(driver)
        await session.commit()
        await session.refresh(driver)

        raw_plate = (request.plate_number or "").strip()
        if not raw_plate:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="ثبت پلاک خودرو برای هر راننده الزامی است.",
            )

        clean_plate = _normalize_plate(raw_plate)
        existing_plate = (
            await session.exec(
                select(DriverPlate).where(
                    (DriverPlate.client_id == client.id)
                    & (DriverPlate.driver_id == driver.id)
                    & (DriverPlate.plate_number == clean_plate)
                )
            )
        ).first()
        if not existing_plate:
            new_plate = DriverPlate(
                client_id=client.id,
                driver_id=driver.id,
                plate_number=clean_plate,
                vehicle_type=request.vehicle_type or "کامیون",
                status="active",
            )
            session.add(new_plate)
            await session.commit()
        elif existing_plate.status != "active":
            existing_plate.status = "active"
            session.add(existing_plate)
            await session.commit()

        resp = DriverResponse.model_validate(driver)
        resp.active_plate = clean_plate
        return resp

    @staticmethod
    async def list_drivers(
        user_context: dict | Client,
        session: AsyncSession,
        status_filter: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[DriverResponse]:
        """List all drivers for the client or all for admin."""
        if isinstance(user_context, Client):
            user_context = {"role": "client", "user": user_context}
        role = user_context.get("role")
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

        d_ids = [d.id for d in drivers if getattr(d, "id", None)]
        active_plates: dict[int, str] = {}
        if d_ids:
            try:
                plate_stmt = select(DriverPlate).where(
                    col(DriverPlate.driver_id).in_(d_ids),
                    DriverPlate.status == "active",
                )
                plate_res = await session.exec(plate_stmt)
                plate_rows = plate_res.all() if hasattr(plate_res, "all") else []
                for p in plate_rows:
                    p_did = getattr(p, "driver_id", None)
                    p_pnum = getattr(p, "plate_number", None)
                    if p_did is not None and p_pnum and p_did not in active_plates:
                        active_plates[p_did] = str(p_pnum)
            except Exception as e:
                logger.debug(f"Could not fetch driver active plates: {e}")

        responses = []
        for d in drivers:
            r = DriverResponse.model_validate(d)
            r.active_plate = active_plates.get(getattr(d, "id", None))
            responses.append(r)
        return responses

    @staticmethod
    async def get_driver(
        user_context: dict | Client,
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

        # Verify tenant ownership unless master admin
        if not (isinstance(user_context, dict) and user_context.get("role") == "master_admin"):
            client = user_context.get("user") if isinstance(user_context, dict) else user_context
            verify_tenant_ownership(client, driver, Driver)

        active_plate_str = None
        try:
            plate_stmt = select(DriverPlate).where(
                (DriverPlate.driver_id == driver.id) & (DriverPlate.status == "active")
            )
            plate_res = await session.exec(plate_stmt)
            active_plate_row = plate_res.first() if hasattr(plate_res, "first") else None
            if active_plate_row and hasattr(active_plate_row, "plate_number"):
                active_plate_str = str(active_plate_row.plate_number)
        except Exception:
            pass

        resp = DriverResponse.model_validate(driver)
        resp.active_plate = active_plate_str
        return resp

    @staticmethod
    async def update_driver(
        user_context: dict | Client,
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

        # Verify tenant ownership unless master admin
        if not (isinstance(user_context, dict) and user_context.get("role") == "master_admin"):
            client = user_context.get("user") if isinstance(user_context, dict) else user_context
            verify_tenant_ownership(client, driver, Driver)

        update_data = request.model_dump(exclude_unset=True)

        # If driver_national_code is being updated, check uniqueness for client
        if "driver_national_code" in update_data and update_data["driver_national_code"]:
            clean_nat = _normalize_digits_str(update_data["driver_national_code"])
            if clean_nat and clean_nat != driver.driver_national_code:
                existing = await session.exec(
                    select(Driver).where(
                        (Driver.client_id == driver.client_id)
                        & (Driver.driver_national_code == clean_nat)
                        & (Driver.id != driver.id)
                    )
                )
                if existing.first():
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Driver with this national code already exists",
                    )
                driver.driver_national_code = clean_nat

        if "phone" in update_data:
            driver.phone = _normalize_digits_str(update_data["phone"]) if update_data["phone"] else None

        active_plate_str = None
        for field, value in update_data.items():
            if field in ("driver_national_code", "phone", "plate_number", "vehicle_type"):
                continue
            elif field == "utcms_password":
                if value is not None and str(value).strip():
                    driver.utcms_password_encrypted = encrypt_driver_password(str(value).strip())
            else:
                setattr(driver, field, value)

        driver.updated_at = datetime.now(UTC).replace(tzinfo=None)

        session.add(driver)
        await session.commit()
        await session.refresh(driver)

        if "plate_number" in update_data and update_data["plate_number"] is not None:
            raw_plate = str(update_data["plate_number"]).strip()
            if raw_plate:
                try:
                    clean_plate = _normalize_plate(raw_plate)
                    existing_plate = (
                        await session.exec(
                            select(DriverPlate).where(
                                (DriverPlate.client_id == driver.client_id)
                                & (DriverPlate.driver_id == driver.id)
                            )
                        )
                    ).first()
                    if existing_plate:
                        existing_plate.plate_number = clean_plate
                        existing_plate.status = "active"
                        if "vehicle_type" in update_data and update_data["vehicle_type"]:
                            existing_plate.vehicle_type = str(update_data["vehicle_type"]).strip()
                        session.add(existing_plate)
                    else:
                        new_plate = DriverPlate(
                            client_id=driver.client_id,
                            driver_id=driver.id,
                            plate_number=clean_plate,
                            vehicle_type=str(update_data.get("vehicle_type") or "کامیون").strip(),
                            status="active",
                        )
                        session.add(new_plate)
                    await session.commit()
                    active_plate_str = clean_plate
                except Exception as e:
                    logger.warning(f"Failed to update plate for driver {driver.id}: {e}")
            else:
                active_plate_str = None
        else:
            try:
                plate_stmt = select(DriverPlate).where(
                    (DriverPlate.driver_id == driver.id) & (DriverPlate.status == "active")
                )
                plate_res = await session.exec(plate_stmt)
                active_plate_row = plate_res.first() if hasattr(plate_res, "first") else None
                if active_plate_row and hasattr(active_plate_row, "plate_number"):
                    active_plate_str = str(active_plate_row.plate_number)
            except Exception:
                pass

        resp = DriverResponse.model_validate(driver)
        resp.active_plate = active_plate_str
        return resp

    @staticmethod
    async def delete_driver(
        user_context: dict | Client,
        driver_id: int,
        session: AsyncSession,
    ) -> bool:
        """Delete a driver safely with complete cascade cleanup."""
        driver = await session.get(Driver, driver_id)
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver not found",
            )

        # Verify tenant ownership unless master admin
        if not (isinstance(user_context, dict) and user_context.get("role") == "master_admin"):
            client = user_context.get("user") if isinstance(user_context, dict) else user_context
            verify_tenant_ownership(client, driver, Driver)

        try:
            # 1. Clean up driver runtime states
            await session.exec(delete(DriverRuntimeState).where(DriverRuntimeState.driver_id == driver.id))
            # 2. Clean up driver plates
            await session.exec(delete(DriverPlate).where(DriverPlate.driver_id == driver.id))
            # 3. Clean up driver schedules
            await session.exec(delete(DriverSchedule).where(DriverSchedule.driver_id == driver.id))
            # 4. Clean up legacy admin driver schedules
            await session.exec(delete(AdminDriverSchedule).where(AdminDriverSchedule.driver_id == driver.id))
            # 5. Clean up driver daily counters
            await session.exec(delete(DriverDailyCounter).where(DriverDailyCounter.driver_id == driver.id))
            # 6. Clean up driver session metadata
            await session.exec(delete(DriverSessionMetadata).where(DriverSessionMetadata.driver_id == driver.id))
            # 7. Clean up fuel inquiries
            await session.exec(delete(FuelInquiry).where(FuelInquiry.driver_id == driver.id))
            # 8. Clean up waybill attempts belonging to this driver
            await session.exec(delete(WaybillAttempt).where(WaybillAttempt.driver_id == driver.id))
            # 9. Clean up domain events referencing this driver
            await session.exec(delete(DomainEvent).where(DomainEvent.driver_id == driver.id))

            # 10. Nullify driver_id in historical waybill jobs (preserving audit trail)
            jobs = (await session.exec(select(WaybillJob).where(WaybillJob.driver_id == driver.id))).all()
            for j in jobs:
                j.driver_id = None
                session.add(j)

            # 11. Delete the driver record
            await session.delete(driver)
            await session.commit()
            return True

        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to delete driver {driver_id}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to delete driver: {str(e)}"
            ) from e


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
