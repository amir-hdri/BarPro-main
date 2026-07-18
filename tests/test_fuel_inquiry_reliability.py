from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models_multitenant import Client, Driver, DriverPlate, FuelInquiry
from app.services.fuel_inquiry_service import fuel_inquiry_service


@pytest.mark.asyncio
async def test_fuel_worker_claims_once_and_submits_driver_national_code():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)

    async with async_session() as session:
        client = Client(
            client_code="fuel-claim",
            name="Fuel Claim",
            email="fuel-claim@example.com",
            hashed_password="hash",
            username="fuel_claim",
            full_name="Fuel Claim",
        )
        session.add(client)
        await session.commit()
        await session.refresh(client)

        driver = Driver(
            client_id=client.id,
            driver_national_code="1234567890",
            full_name="Fuel Driver",
            utcms_username="different_portal_username",
            utcms_password_encrypted="encrypted",
        )
        session.add(driver)
        await session.commit()
        await session.refresh(driver)
        expected_national_code = driver.driver_national_code

        session.add(
            DriverPlate(
                client_id=client.id,
                driver_id=driver.id,
                plate_number="12ب34567",
                status="active",
            )
        )
        inquiry = FuelInquiry(client_id=client.id, driver_id=driver.id, year=1405, month=4)
        session.add(inquiry)
        await session.commit()
        await session.refresh(inquiry)

        context = AsyncMock()
        page = AsyncMock()

        @asynccontextmanager
        async def fake_browser_session(**_kwargs):
            yield "session-id", context

        scrape = AsyncMock(
            return_value={
                "success": True,
                "quota_data": {
                    "tables": [{"headers": ["quota"], "rows": [["100"]]}],
                    "key_values": {},
                    "summary": {},
                },
                "screenshot_url": f"/api/v1/fuel-inquiries/{inquiry.id}/screenshot",
            }
        )

        with (
            patch("app.services.fuel_inquiry_service.managed_browser_session", new=fake_browser_session),
            patch("app.services.fuel_inquiry_service.browser_manager.initialize", new=AsyncMock()),
            patch("app.services.fuel_inquiry_service.browser_manager.new_page", new=AsyncMock(return_value=page)),
            patch("app.services.fuel_inquiry_service.browser_manager.save_auth_state", new=AsyncMock()),
            patch("app.automation.worker_proxy.get_playwright_proxy", return_value=None),
            patch("app.services.fuel_inquiry_service.FuelScraper.scrape_fuel_quota", new=scrape),
        ):
            await fuel_inquiry_service.run_automation(inquiry.id, session)
            await fuel_inquiry_service.run_automation(inquiry.id, session)

        await session.refresh(inquiry)
        assert inquiry.status == "success"
        assert scrape.await_count == 1
        assert scrape.await_args.kwargs["national_code"] == expected_national_code
        assert "username" not in scrape.await_args.kwargs

    await engine.dispose()


@pytest.mark.asyncio
async def test_fuel_setup_failure_does_not_leave_processing_status():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)

    async with async_session() as session:
        inquiry = FuelInquiry(client_id=999, driver_id=999, year=1405, month=4)
        session.add(inquiry)
        await session.commit()
        await session.refresh(inquiry)

        await fuel_inquiry_service.run_automation(inquiry.id, session)

        await session.refresh(inquiry)
        assert inquiry.status == "failed"
        assert inquiry.error_message == "104"

    await engine.dispose()


def test_waybill_submit_parsers_require_explicit_success():
    from app.automation.waybill_enhanced import EnhancedWaybillManager

    string_false = EnhancedWaybillManager._parse_register_submit_payload(
        {"success": "false", "data": {"resultCode": 200, "obj": {"id": 1}}}
    )
    missing_result_code = EnhancedWaybillManager._parse_register_submit_payload(
        {"success": True, "data": {"obj": {"id": 1}}}
    )
    missing_otp_result_code = EnhancedWaybillManager._parse_otp_submit_payload({"obj": 1})

    assert string_false["success"] is False
    assert missing_result_code["success"] is False
    assert missing_otp_result_code["success"] is False
