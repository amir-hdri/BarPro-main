from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models_multitenant import Client, Driver
from app.schemas.multitenant import FuelInquiryCreateRequest
from app.services.fuel_inquiry_service import fuel_inquiry_service


@pytest.mark.asyncio
async def test_fuel_inquiry_service_lifecycle():
    # Setup async SQLite in-memory engine
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Create all tables (includes FuelInquiry since it registers on SQLModel.metadata)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session() as session:
        # 1. Create client and driver
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

        # Create an active plate for the driver (required by create_inquiry)
        from app.models_multitenant import DriverPlate

        plate = DriverPlate(
            client_id=client.id,
            driver_id=driver.id,
            plate_number="12الف345",
            status="active",
        )
        session.add(plate)
        await session.commit()

        # 2. Test create_inquiry
        # Mock dispatch_fuel_inquiry_task to prevent celery dependency call in unit test
        with patch("app.workers.tasks.dispatch_fuel_inquiry_task") as mock_dispatch:
            req = FuelInquiryCreateRequest(driver_id=driver.id)
            response = await fuel_inquiry_service.create_inquiry(client, req, session)

            # Assertions
            assert response.client_id == client.id
            assert response.driver_id == driver.id
            assert response.status == "pending"
            assert response.driver_name == "John Doe"
            mock_dispatch.assert_called_once_with(response.id)

        # 3. Test list_inquiries
        history = await fuel_inquiry_service.list_inquiries(client, page=1, page_size=10, session=session)
        assert history.total == 1
        assert len(history.items) == 1
        assert history.items[0].driver_name == "John Doe"

        # 4. Test get_inquiry
        inquiry_details = await fuel_inquiry_service.get_inquiry(client, history.items[0].id, session)
        assert inquiry_details.id == history.items[0].id
        assert inquiry_details.status == "pending"

    await engine.dispose()
