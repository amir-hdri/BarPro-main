"""Vehicle plate management service with tenant isolation."""

import logging
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth_multitenant import verify_tenant_ownership
from app.models_multitenant import Client, Driver, DriverPlate
from app.schemas.multitenant import (
    PlateCreateRequest,
    PlateResponse,
    PlateUpdateRequest,
)

logger = logging.getLogger(__name__)


class PlateService:
    """Manage vehicle plates with tenant isolation."""

    @staticmethod
    async def create_plate(user_context: dict | Client, request: PlateCreateRequest, session: AsyncSession) -> PlateResponse:
        driver = await session.get(Driver, request.driver_id)
        if not driver:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Driver not found")

        if isinstance(user_context, Client):
            client = user_context
        elif isinstance(user_context, dict) and user_context.get("role") == "master_admin":
            client = await session.get(Client, driver.client_id)
            if not client:
                client = (await session.exec(select(Client))).first()
        else:
            client = user_context.get("user") if isinstance(user_context, dict) else user_context
            verify_tenant_ownership(client, driver, Driver)

        if client:
            plate_count = (
                await session.exec(select(func.count(DriverPlate.id)).where(DriverPlate.client_id == client.id))
            ).one()
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

        client_id = client.id if client else driver.client_id

        plate = DriverPlate(
            client_id=client_id,
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
        user_context: dict, session: AsyncSession, driver_id: int | None = None, page: int = 1, page_size: int = 20
    ) -> list[PlateResponse]:
        if isinstance(user_context, Client):
            user_context = {"role": "client", "user": user_context}
        role = user_context.get("role")
        if role == "master_admin":
            statement = select(DriverPlate)
        else:
            client = user_context["user"]
            statement = select(DriverPlate).where(DriverPlate.client_id == client.id)

        if driver_id:
            statement = statement.where(DriverPlate.driver_id == driver_id)
        statement = statement.order_by(col(DriverPlate.created_at).desc())
        statement = statement.offset((page - 1) * page_size).limit(page_size)
        rows = (await session.exec(statement)).all()
        return [PlateResponse.model_validate(item) for item in rows]

    @staticmethod
    async def update_plate(
        user_context: dict | Client, plate_id: int, request: PlateUpdateRequest, session: AsyncSession
    ) -> PlateResponse:
        plate = await session.get(DriverPlate, plate_id)
        if not plate:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plate not found")

        if not (isinstance(user_context, dict) and user_context.get("role") == "master_admin"):
            client = user_context.get("user") if isinstance(user_context, dict) else user_context
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
    async def delete_plate(user_context: dict | Client, plate_id: int, session: AsyncSession) -> None:
        plate = await session.get(DriverPlate, plate_id)
        if not plate:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plate not found")

        if not (isinstance(user_context, dict) and user_context.get("role") == "master_admin"):
            client = user_context.get("user") if isinstance(user_context, dict) else user_context
            verify_tenant_ownership(client, plate, DriverPlate)

        await session.delete(plate)
        await session.commit()

