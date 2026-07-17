from unittest.mock import patch
import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from fastapi import HTTPException

from app.models_multitenant import Client, Driver, DriverPlate
from app.schemas.multitenant import FuelInquiryCreateRequest
from app.services.fuel_inquiry_service import fuel_inquiry_service


@pytest.mark.asyncio
async def test_fuel_inquiry_duplicate_prevention():
    # Setup async SQLite in-memory engine
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session() as session:
        # 1. Setup data
        client = Client(
            client_code="tenant-test",
            name="Test Tenant",
            email="test@example.com",
            hashed_password="hashed_pwd",
            username="test_user",
            full_name="Test User",
        )
        session.add(client)
        await session.commit()
        await session.refresh(client)

        driver = Driver(
            client_id=client.id,
            driver_national_code="1234567890",
            full_name="John Doe",
            utcms_username="john_doe",
            utcms_password_encrypted="encrypted_pwd",
        )
        session.add(driver)
        await session.commit()
        await session.refresh(driver)

        plate = DriverPlate(
            client_id=client.id,
            driver_id=driver.id,
            plate_number="12الف345",
            status="active",
        )
        session.add(plate)
        await session.commit()

        # 2. Create first inquiry
        with patch("app.workers.tasks.dispatch_fuel_inquiry_task"):
            req = FuelInquiryCreateRequest(driver_id=driver.id, year=1403, month=4)
            await fuel_inquiry_service.create_inquiry(client, req, session)

        # 3. Try to create duplicate inquiry (same driver, year, month)
        with patch("app.workers.tasks.dispatch_fuel_inquiry_task"):
            with pytest.raises(HTTPException) as excinfo:
                await fuel_inquiry_service.create_inquiry(client, req, session)
            assert excinfo.value.status_code == 409
            assert "یک استعلام فعال" in excinfo.value.detail

        # 4. Try to create inquiry for different period (should succeed)
        with patch("app.workers.tasks.dispatch_fuel_inquiry_task"):
            req2 = FuelInquiryCreateRequest(driver_id=driver.id, year=1403, month=5)
            response2 = await fuel_inquiry_service.create_inquiry(client, req2, session)
            assert response2.status == "pending"

    await engine.dispose()
