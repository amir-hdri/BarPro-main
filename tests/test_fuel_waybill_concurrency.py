from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models_multitenant import Client, Driver, DriverPlate, FuelInquiry
from app.models_rpa import DriverRuntimeState
from app.schemas.multitenant import FuelInquiryCreateRequest
from app.services.fuel_inquiry_service import fuel_inquiry_service


@pytest.mark.asyncio
async def test_fuel_and_waybill_concurrent_execution_for_same_driver():
    """Verify that a driver can have a running waybill pipeline while simultaneously

    executing a fuel quota inquiry without any lock contention, slot interference,
    or session corruption.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session() as session:
        # 1. Setup Client, Driver, and Active Plate
        client = Client(
            client_code="tenant-conc",
            name="Concurrent Tenant",
            email="conc@example.com",
            hashed_password="hashed_pwd",
            username="conc_user",
            full_name="Conc User",
        )
        session.add(client)
        await session.commit()
        await session.refresh(client)

        driver = Driver(
            client_id=client.id,
            driver_national_code="1810364371",
            full_name="Behrouz Baghlani",
            utcms_username="behrouz_b",
            utcms_password_encrypted="encrypted_pwd",
        )
        session.add(driver)
        await session.commit()
        await session.refresh(driver)

        plate = DriverPlate(
            client_id=client.id,
            driver_id=driver.id,
            plate_number="12ب345ایران67",
            status="active",
        )
        session.add(plate)

        # 2. Simulate an active Waybill pipeline holding the driver execution slot
        active_intent = "intent-waybill-running-999"
        runtime_state = DriverRuntimeState(
            client_id=client.id,
            driver_id=driver.id,
            active_execution_id=active_intent,
            state="running",
        )
        session.add(runtime_state)
        await session.commit()

        # 3. Create a fuel inquiry concurrently for this exact same driver
        with patch("app.workers.tasks.dispatch_fuel_inquiry_task") as mock_dispatch:
            req = FuelInquiryCreateRequest(driver_id=driver.id, year=1405, month=3)
            fuel_resp = await fuel_inquiry_service.create_inquiry(client, req, session)

            assert fuel_resp.driver_id == driver.id
            assert fuel_resp.status == "pending"
            mock_dispatch.assert_called_once_with(fuel_resp.id)

        # 4. Verify that the Waybill's driver slot was NOT touched or cleared
        check_state = (await session.exec(select(DriverRuntimeState).where(DriverRuntimeState.driver_id == driver.id))).first()
        assert check_state is not None
        assert check_state.active_execution_id == active_intent
        assert check_state.state == "running"

        # 5. Simulate fuel scraper execution in isolated browser context (auth_state_path=None)
        mock_scraper_result = {
            "success": True,
            "quota_data": {
                "tables": [
                    {
                        "title": "سهمیه عملکردی",
                        "rows": [{"period": "1405/03", "quota": "1200"}],
                    }
                ]
            },
            "screenshot_url": None,
        }

        mock_context = MagicMock()
        mock_page = MagicMock()

        with patch("app.automation.browser.browser_manager.initialize", new_callable=AsyncMock), \
             patch("app.automation.browser.browser_manager.new_page", new_callable=AsyncMock, return_value=mock_page), \
             patch("app.services.fuel_inquiry_service.managed_browser_session") as mock_managed_session, \
             patch("app.automation.fuel_scraper.FuelScraper.scrape_fuel_quota", new_callable=AsyncMock) as mock_scrape, \
             patch("app.automation.worker_proxy.get_playwright_proxy", return_value=None):

            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def _mock_cm(*args, **kwargs):
                yield ("sess-1", mock_context)

            mock_managed_session.side_effect = _mock_cm
            mock_scrape.return_value = mock_scraper_result

            # Run fuel inquiry automation
            await fuel_inquiry_service.run_automation(fuel_resp.id, session)

            # Ensure managed_browser_session was called with auth_state_path=None (Zero session collision!)
            mock_managed_session.assert_called_once_with(
                auth_state_path=None,
                proxy_dict=None,
            )

        # 6. Verify fuel inquiry reached success in DB
        completed_inquiry = await session.get(FuelInquiry, fuel_resp.id)
        assert completed_inquiry.status == "success"
        assert completed_inquiry.quota_data_json["tables"][0]["rows"][0]["quota"] == "1200"

        # 7. Re-verify that the active Waybill execution slot is STILL intact and running
        final_state = (await session.exec(select(DriverRuntimeState).where(DriverRuntimeState.driver_id == driver.id))).first()
        assert final_state.active_execution_id == active_intent

    await engine.dispose()
