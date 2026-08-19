import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from fastapi.testclient import TestClient

from app.main import app
from app.models_multitenant import Client, Driver, DriverPlate, FuelInquiry, WaybillJob
from app.models_rpa import DriverRuntimeState
from app.schemas.multitenant import DriverCreateRequest, FuelInquiryCreateRequest
from app.services.driver_service import DriverService
from app.services.fuel_inquiry_service import fuel_inquiry_service
from app.services.waybill_job_service import WaybillJobService
from app.auth_multitenant import get_current_client, get_current_user_or_admin
from app.core.database import get_session


@pytest.mark.asyncio
async def test_fullstack_e2e_driver_waybill_fuel_lifecycle():
    """Comprehensive E2E test verifying:

    1. Driver registration with unique vehicle plate auto-binding
    2. Driver listing with active_plate attached
    3. Waybill job creation with automatic plate inheritance
    4. Fuel inquiry creation with plate auto-resolution
    5. Parallel execution of Waybill + Fuel inquiry for the same driver without collision
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session() as session:
        # Step 0: Provision Client
        client = Client(
            client_code="tenant-e2e",
            name="E2E Transport Co",
            email="e2e@example.com",
            hashed_password="hashed_password",
            username="e2e_admin",
            full_name="E2E Admin",
        )
        session.add(client)
        await session.commit()
        await session.refresh(client)

        # ---------------------------------------------------------
        # Step 1: Register Driver with Vehicle Plate (/drivers)
        # ---------------------------------------------------------
        driver_payload = DriverCreateRequest(
            driver_national_code="1810364371",
            full_name="بهروز بغلانی",
            phone="09123456789",
            license_number="987654",
            utcms_username="behrouz_utcms",
            utcms_password="secure_password_123",
            plate_number="12الف345ایران67",
            vehicle_type="کامیون کشنده",
        )

        user_context = {"role": "client", "user": client}
        created_driver = await DriverService.create_driver(
            user_context=user_context,
            request=driver_payload,
            session=session,
        )

        assert created_driver.id is not None
        assert created_driver.driver_national_code == "1810364371"
        assert created_driver.full_name == "بهروز بغلانی"

        # Verify DriverPlate was automatically created and active
        plate_stmt = select(DriverPlate).where(
            (DriverPlate.driver_id == created_driver.id) & (DriverPlate.status == "active")
        )
        plate_row = (await session.exec(plate_stmt)).first()
        assert plate_row is not None
        assert plate_row.plate_number == "12الف345ایران67"
        assert plate_row.vehicle_type == "کامیون کشنده"

        # ---------------------------------------------------------
        # Step 2: List Drivers (/drivers) - Verify active_plate attached
        # ---------------------------------------------------------
        drivers_list = await DriverService.list_drivers(user_context=user_context, session=session)
        assert len(drivers_list) == 1
        assert drivers_list[0].id == created_driver.id
        assert drivers_list[0].active_plate == "12الف345ایران67"

        # ---------------------------------------------------------
        # Step 3: Create Waybill Job (/new) - Plate Auto-Inheritance
        # ---------------------------------------------------------
        from app.schemas.multitenant import WaybillJobCreateRequest, WaybillPayload

        waybill_payload = WaybillPayload(
            driver_national_code="1810364371",
            origin="تهران",
            destination="مشهد",
            cargo_type="آهن آلات",
            cargo_weight=15000.0,
            vehicle_type="کامیون کشنده",
            plate_number="12الف345ایران67",
            driver_phone="09123456789",
        )
        waybill_req = WaybillJobCreateRequest(
            driver_national_code="1810364371",
            payload=waybill_payload,
        )

        mock_job = WaybillJob(
            id=123,
            job_id="job-e2e-12345",
            client_id=client.id,
            driver_id=created_driver.id,
            status="pending",
            priority=5,
            payload_json=waybill_payload.model_dump(),
        )

        with patch("app.services.waybill_job_service.rpa_scheduler_service.create_job", new_callable=AsyncMock, return_value=mock_job):
            job_resp = await WaybillJobService.create_job(
                client=client,
                request=waybill_req,
                session=session,
            )
            assert job_resp.job_id == "job-e2e-12345"
            assert job_resp.driver_id == created_driver.id
            assert job_resp.status == "pending"

        # ---------------------------------------------------------
        # Step 4: Create Fuel Inquiry (/fuel) - Plate Auto-Resolution
        # ---------------------------------------------------------
        with patch("app.workers.tasks.dispatch_fuel_inquiry_task") as mock_fuel_dispatch:
            fuel_req = FuelInquiryCreateRequest(
                driver_id=created_driver.id,
                year=1405,
                month=5,
            )
            fuel_inquiry_resp = await fuel_inquiry_service.create_inquiry(
                client=client,
                request=fuel_req,
                session=session,
            )
            assert fuel_inquiry_resp.id is not None
            assert fuel_inquiry_resp.driver_id == created_driver.id
            assert fuel_inquiry_resp.status == "pending"
            assert fuel_inquiry_resp.plate_number == "12الف345ایران67"
            mock_fuel_dispatch.assert_called_once_with(fuel_inquiry_resp.id)

        # ---------------------------------------------------------
        # Step 5: Concurrent Execution - Waybill & Fuel Inquiry
        # ---------------------------------------------------------
        # Simulate Waybill pipeline actively running for the driver
        runtime_state = DriverRuntimeState(
            client_id=client.id,
            driver_id=created_driver.id,
            active_execution_id="intent-concurrent-e2e",
            state="running",
        )
        session.add(runtime_state)
        await session.commit()

        # Run fuel inquiry automation in isolated browser session
        mock_scraper_result = {
            "success": True,
            "quota_data": {
                "tables": [
                    {
                        "title": "سهمیه پایه و عملکردی",
                        "rows": [
                            {"period": "1405/05", "base": "500", "performance": "1500", "total": "2000"}
                        ],
                    }
                ]
            },
            "screenshot_url": None,
        }

        mock_context = MagicMock()
        mock_page = MagicMock()

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _mock_cm(*args, **kwargs):
            yield ("sess-e2e", mock_context)

        with patch("app.automation.browser.browser_manager.initialize", new_callable=AsyncMock), \
             patch("app.automation.browser.browser_manager.new_page", new_callable=AsyncMock, return_value=mock_page), \
             patch("app.services.fuel_inquiry_service.managed_browser_session", side_effect=_mock_cm) as mock_managed_session, \
             patch("app.automation.fuel_scraper.FuelScraper.scrape_fuel_quota", new_callable=AsyncMock, return_value=mock_scraper_result), \
             patch("app.automation.worker_proxy.get_playwright_proxy", return_value=None):

            await fuel_inquiry_service.run_automation(fuel_inquiry_resp.id, session)

            # Ensure isolated session was used (auth_state_path=None)
            mock_managed_session.assert_called_once_with(
                auth_state_path=None,
                proxy_dict=None,
            )

        # ---------------------------------------------------------
        # Step 6: Verify Final Invariants
        # ---------------------------------------------------------
        # 1. Fuel inquiry is marked as success with complete quota data
        finished_inquiry = await session.get(FuelInquiry, fuel_inquiry_resp.id)
        assert finished_inquiry.status == "success"
        assert finished_inquiry.quota_data_json["tables"][0]["rows"][0]["total"] == "2000"

        # 2. Driver runtime state for Waybill was NOT altered or corrupted
        persisted_runtime = (await session.exec(select(DriverRuntimeState).where(DriverRuntimeState.driver_id == created_driver.id))).first()
        assert persisted_runtime.active_execution_id == "intent-concurrent-e2e"
        assert persisted_runtime.state == "running"

        # 3. Fuel inquiry details endpoint returns formatted driver & plate info
        fuel_details = await fuel_inquiry_service.get_inquiry(
            user_context=user_context,
            inquiry_id=fuel_inquiry_resp.id,
            session=session,
        )
        assert fuel_details.driver_name == "بهروز بغلانی"
        assert fuel_details.plate_number == "12الف345ایران67"
        assert fuel_details.status == "success"

    await engine.dispose()


@pytest.mark.asyncio
async def test_waybill_payload_flexibility_and_vehicle_type_auto_sync():
    """Verify that waybill job creation accepts flat, nested, and hybrid payloads,

    safely handles vehicle_type, driver_phone, and updates DriverPlate.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session() as session:
        client = Client(
            client_code="tenant-test-payload",
            name="Test Payload Tenant",
            email="payload@example.com",
            hashed_password="hashed_password",
            username="payload_admin",
            full_name="Payload Admin",
        )
        session.add(client)
        await session.commit()
        await session.refresh(client)

        driver = Driver(
            client_id=client.id,
            driver_national_code="1810364371",
            full_name="جواد سمیرات",
            phone="09161112233",
            utcms_username="javad_utcms",
            utcms_password_encrypted="encrypted_pwd",
        )
        session.add(driver)
        await session.commit()
        await session.refresh(driver)

        # 1. Test frontend-like hybrid payload (with vehicle_type, cargo_packaging, metadata_json)
        from app.schemas.multitenant import WaybillJobCreateRequest

        frontend_payload_dict = {
            "driver_national_code": "1810364371",
            "origin": "اهواز",
            "destination": "خرمشهر",
            "cargo_type": "مطالح",
            "cargo_packaging": "فله",
            "cargo_weight": "15",
            "cargo_value": "100000000",
            "vehicle_type": "جفت (۱۵ تن)",
            "plate_number": "12ب345ایران67",
            "metadata_json": {
                "origin_province": "خوزستان",
                "origin_address": "اهواز، جاده ساحلی",
                "destination_province": "خوزستان",
                "destination_address": "خرمشهر، بندر",
                "cargo_packaging": "فله",
                "cargo_value": "100000000",
                "vehicle_type": "جفت (۱۵ تن)",
                "sender_name": "جواد سمیرات",
                "receiver_name": "علی معماری",
                "sender": {"name": "جواد سمیرات"},
                "receiver": {"name": "علی معماری"},
                "origin": {"province": "خوزستان", "city": "اهواز", "address": "اهواز، جاده ساحلی"},
                "destination": {"province": "خوزستان", "city": "خرمشهر", "address": "خرمشهر، بندر"},
                "cargo": {"type": "مطالح", "packaging": "فله", "weight": "15", "value": "100000000"},
                "vehicle": {"driver_national_code": "1810364371", "plate": "12ب345ایران67", "type": "جفت (۱۵ تن)"},
            },
        }

        req = WaybillJobCreateRequest(
            driver_national_code="1810364371",
            payload=frontend_payload_dict,
        )

        mock_job = WaybillJob(
            id=101,
            job_id="job-payload-test-1",
            client_id=client.id,
            driver_id=driver.id,
            status="pending",
            priority=5,
            payload_json=frontend_payload_dict,
        )

        with patch("app.services.waybill_job_service.rpa_scheduler_service.create_job", new_callable=AsyncMock, return_value=mock_job):
            resp = await WaybillJobService.create_job(
                client=client,
                request=req,
                session=session,
            )
            assert resp.job_id == "job-payload-test-1"

        # Verify DriverPlate was registered with vehicle_type="جفت (۱۵ تن)"
        plate_stmt = select(DriverPlate).where(
            (DriverPlate.driver_id == driver.id) & (DriverPlate.plate_number == "12ب345ایران67")
        )
        plate_row = (await session.exec(plate_stmt)).first()
        assert plate_row is not None
        assert plate_row.vehicle_type == "جفت (۱۵ تن)"
        assert plate_row.status == "active"

        # 2. Test adapter normalisation on this payload
        from app.automation.multitenant_payload_adapter import build_enhanced_waybill_payload, validate_enhanced_waybill_payload

        enhanced = build_enhanced_waybill_payload(frontend_payload_dict)
        assert enhanced["vehicle"]["type"] == "جفت (۱۵ تن)"
        assert enhanced["vehicle"]["plate"] == "12ب345ایران67"
        assert enhanced["cargo"]["packaging"] == "فله"
        assert enhanced["origin"]["city"] == "اهواز"
        assert enhanced["destination"]["city"] == "خرمشهر"
        assert enhanced["sender"]["name"] == "جواد سمیرات"
        assert enhanced["receiver"]["name"] == "علی معماری"

        validation_errors = validate_enhanced_waybill_payload(enhanced)
        assert validation_errors == []

    await engine.dispose()

