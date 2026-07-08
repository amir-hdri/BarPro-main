import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

from app.schemas.management import (
    ManagedAccountUpsertRequest,
    ManagedQueueCreateRequest,
    ManagedQueueDispatchRequest,
    ManagementBootstrapRequest,
    ManagementExcelImportOptions,
)
from app.schemas.waybill import (
    CargoModel,
    FinancialModel,
    GeoCoordinateModel,
    LocationModel,
    ReceiverModel,
    SenderModel,
    UTCMSLoginModel,
    VehicleModel,
    WaybillMapRequest,
)
from app.services.management_service import management_service
from scripts.generate_waybill_excel_template import generate_template


class TestManagementService(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "management_test.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False, future=True)
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

        self.patches = [
            patch("app.services.management_service.engine", self.engine),
        ]
        for active_patch in self.patches:
            active_patch.start()

    async def asyncTearDown(self):
        for active_patch in reversed(self.patches):
            active_patch.stop()
        await self.engine.dispose()
        self.tmpdir.cleanup()

    async def test_create_and_dispatch_local_queue_item(self):
        waybill_payload = WaybillMapRequest(
            session_id="s1",
            sender=SenderModel(name="Sender", phone="09121234567", address="Addr", national_code="1234567890"),
            receiver=ReceiverModel(name="Receiver", phone="09121234567", address="Addr"),
            origin=LocationModel(
                province="Tehran", city="Tehran", address="Origin", coordinates=GeoCoordinateModel(lat=35.7, lng=51.4)
            ),
            destination=LocationModel(
                province="Alborz", city="Karaj", address="Dest", coordinates=GeoCoordinateModel(lat=35.8, lng=50.9)
            ),
            cargo=CargoModel(type="General", weight=1000, count=1, description="Desc"),
            vehicle=VehicleModel(
                driver_national_code="1234567890", driver_phone="09121234567", plate="12A34567", type="Truck"
            ),
            financial=FinancialModel(cost=1000, payment_method="Cash"),
        )
        created = await management_service.create_queue_item(
            ManagedQueueCreateRequest(
                account_external_name="DRV1",
                route_key="route-1",
                bot_owner="demo_user",
                waybill_payload=waybill_payload,
            )
        )
        self.assertEqual(created["status"], "queued")

        fake_enqueue = AsyncMock(
            return_value=type("Resp", (), {"model_dump": lambda self: {"task_id": "t1", "status": "queued"}})()
        )
        with patch("app.services.management_service.queue_manager.enqueue_waybill", new=fake_enqueue):
            dispatched = await management_service.dispatch_queue_item(
                created["queue_item_id"],
                ManagedQueueDispatchRequest(idempotency_key="idem-1"),
            )

        self.assertEqual(dispatched["status"], "dispatched")
        fake_enqueue.assert_awaited()

    async def test_diagnostics_reports_gaps(self):
        diagnostics = await management_service.diagnostics()
        self.assertIn("summary", diagnostics)
        self.assertIn("issues", diagnostics)
        self.assertIn("accounts_missing_route", diagnostics["issues"])

    async def test_bootstrap_local_scenario_creates_customer_route_account_and_queue(self):
        waybill_payload = WaybillMapRequest(
            session_id="s-bootstrap",
            sender=SenderModel(name="Sender", phone="09121234567", address="Origin Addr", national_code="1234567890"),
            receiver=ReceiverModel(name="Receiver", phone="09129876543", address="Dest Addr"),
            origin=LocationModel(
                province="Tehran", city="Tehran", address="Origin", coordinates=GeoCoordinateModel(lat=35.7, lng=51.4)
            ),
            destination=LocationModel(
                province="Isfahan",
                city="Isfahan",
                address="Destination",
                coordinates=GeoCoordinateModel(lat=32.65, lng=51.68),
            ),
            cargo=CargoModel(type="General", weight=1000, count=1, description="Desc"),
            vehicle=VehicleModel(
                driver_national_code="1234567890", driver_phone="09123334444", plate="12A34567", type="Truck"
            ),
            financial=FinancialModel(cost=1000, payment_method="Cash"),
        )
        result = await management_service.bootstrap_local_scenario(
            ManagementBootstrapRequest(
                customer_external_key="cust-bootstrap",
                customer_name="Bootstrap Customer",
                bot_owner="operator-bootstrap",
                account_external_name="DRV-BOOTSTRAP",
                waybill_payload=waybill_payload,
            )
        )

        self.assertEqual(result["customer"]["external_key"], "cust-bootstrap")
        self.assertEqual(result["account"]["external_name"], "DRV-BOOTSTRAP")
        self.assertTrue(result["queue_item"]["queue_item_id"])

        summary = await management_service.summary()
        self.assertEqual(summary["customers_count"], 1)
        self.assertEqual(summary["routes_count"], 1)
        self.assertEqual(summary["accounts_count"], 1)
        self.assertEqual(summary["queue_count"], 1)

    async def test_import_excel_workbook_creates_management_entities(self):
        workbook_path = Path(self.tmpdir.name) / "import.xlsx"
        generate_template(workbook_path)
        content = workbook_path.read_bytes()

        result = await management_service.import_excel_workbook(
            content,
            "import.xlsx",
            ManagementExcelImportOptions(
                customer_external_key="excel-customer",
                customer_name="Excel Customer",
                bot_owner="excel-operator",
                include_auth=True,
                create_queue=True,
                default_province="اصفهان",
                default_city="اصفهان",
            ),
        )

        self.assertEqual(result["summary"]["rows_failed"], 0)
        self.assertGreaterEqual(result["summary"]["rows_imported"], 1)

        summary = await management_service.summary()
        self.assertGreaterEqual(summary["customers_count"], 1)
        self.assertGreaterEqual(summary["accounts_count"], 1)
        self.assertGreaterEqual(summary["queue_count"], 1)

    async def test_warm_account_session_uses_account_specific_auth_state(self):
        waybill_payload = WaybillMapRequest(
            session_id="s-session",
            utcms_auth=UTCMSLoginModel(username="DRV-SESSION", password="secret-pass"),
            sender=SenderModel(name="Sender", phone="09121234567", address="Origin Addr", national_code="1234567890"),
            receiver=ReceiverModel(name="Receiver", phone="09129876543", address="Dest Addr"),
            origin=LocationModel(
                province="Tehran", city="Tehran", address="Origin", coordinates=GeoCoordinateModel(lat=35.7, lng=51.4)
            ),
            destination=LocationModel(
                province="Isfahan",
                city="Isfahan",
                address="Destination",
                coordinates=GeoCoordinateModel(lat=32.65, lng=51.68),
            ),
            cargo=CargoModel(type="General", weight=1000, count=1, description="Desc"),
            vehicle=VehicleModel(
                driver_national_code="1234567890", driver_phone="09123334444", plate="12A34567", type="Truck"
            ),
            financial=FinancialModel(cost=1000, payment_method="Cash"),
        )
        await management_service.bootstrap_local_scenario(
            ManagementBootstrapRequest(
                customer_external_key="cust-bootstrap",
                customer_name="Bootstrap Customer",
                bot_owner="operator-bootstrap",
                account_external_name="DRV-SESSION",
                waybill_payload=waybill_payload,
            )
        )

        mock_context = AsyncMock()
        mock_page = AsyncMock()
        with (
            patch("app.services.management_service.browser_manager.initialize", new=AsyncMock()),
            patch(
                "app.services.management_service.browser_manager.create_context",
                new=AsyncMock(return_value=("sid-1", mock_context)),
            ) as mock_create_context,
            patch("app.services.management_service.browser_manager.new_page", new=AsyncMock(return_value=mock_page)),
            patch(
                "app.services.management_service.browser_manager.save_auth_state", new=AsyncMock()
            ) as mock_save_auth_state,
            patch(
                "app.services.management_service.browser_manager.close_context", new=AsyncMock()
            ) as mock_close_context,
            patch("app.services.management_service.UTCMSAuthenticator") as mock_auth_cls,
        ):
            auth_instance = mock_auth_cls.return_value
            auth_instance._is_logged_in = AsyncMock(return_value=False)
            auth_instance.login = AsyncMock(return_value=True)

            result = await management_service.warm_account_session("DRV-SESSION")

        self.assertTrue(result["session_ready"])
        self.assertFalse(result["session_reused"])
        self.assertIn("DRV-SESSION", result["auth_state_path"])
        self.assertEqual(mock_create_context.await_args.kwargs["auth_state_path"], result["auth_state_path"])
        mock_save_auth_state.assert_awaited_once()
        mock_close_context.assert_awaited_once_with("sid-1")

    async def test_dispatch_queue_item_warms_session_before_enqueue(self):
        waybill_payload = WaybillMapRequest(
            session_id="s-dispatch",
            utcms_auth=UTCMSLoginModel(username="LOGIN-USER", password="secret-pass"),
            sender=SenderModel(name="Sender", phone="09121234567", address="Origin Addr", national_code="1234567890"),
            receiver=ReceiverModel(name="Receiver", phone="09129876543", address="Dest Addr"),
            origin=LocationModel(
                province="Tehran", city="Tehran", address="Origin", coordinates=GeoCoordinateModel(lat=35.7, lng=51.4)
            ),
            destination=LocationModel(
                province="Isfahan",
                city="Isfahan",
                address="Destination",
                coordinates=GeoCoordinateModel(lat=32.65, lng=51.68),
            ),
            cargo=CargoModel(type="General", weight=1000, count=1, description="Desc"),
            vehicle=VehicleModel(
                driver_national_code="1234567890", driver_phone="09123334444", plate="12A34567", type="Truck"
            ),
            financial=FinancialModel(cost=1000, payment_method="Cash"),
        )
        bootstrap = await management_service.bootstrap_local_scenario(
            ManagementBootstrapRequest(
                customer_external_key="cust-dispatch",
                customer_name="Dispatch Customer",
                bot_owner="operator-dispatch",
                account_external_name="DISPLAY-NAME",
                waybill_payload=waybill_payload,
            )
        )

        queue_item_id = bootstrap["queue_item"]["queue_item_id"]
        fake_warm = AsyncMock(return_value={"session_ready": True, "auth_state_path": "/tmp/auth_LOGIN-USER.json"})

        async def fake_enqueue_side_effect(*args, **kwargs):
            self.assertEqual(fake_warm.await_count, 1)
            return type(
                "Resp", (), {"model_dump": lambda self: {"task_id": "t-smart", "status": "queued"}, "queued": True}
            )()

        fake_enqueue = AsyncMock(side_effect=fake_enqueue_side_effect)
        with (
            patch.object(management_service, "warm_account_session", new=fake_warm),
            patch("app.services.management_service.queue_manager.enqueue_waybill", new=fake_enqueue),
        ):
            dispatched = await management_service.dispatch_queue_item(
                queue_item_id,
                ManagedQueueDispatchRequest(idempotency_key="idem-smart", warm_session_first=True),
            )

        self.assertEqual(dispatched["status"], "dispatched")
        self.assertEqual(dispatched["result"]["warm_session"]["session_ready"], True)
        fake_warm.assert_awaited_once_with("DISPLAY-NAME")
        fake_enqueue.assert_awaited()

    async def test_dispatch_queue_item_blocks_when_otp_is_pending(self):
        waybill_payload = WaybillMapRequest(
            session_id="s-otp",
            sender=SenderModel(name="Sender", phone="09121234567", address="Origin Addr", national_code="1234567890"),
            receiver=ReceiverModel(name="Receiver", phone="09129876543", address="Dest Addr"),
            origin=LocationModel(
                province="Tehran", city="Tehran", address="Origin", coordinates=GeoCoordinateModel(lat=35.7, lng=51.4)
            ),
            destination=LocationModel(
                province="Isfahan",
                city="Isfahan",
                address="Destination",
                coordinates=GeoCoordinateModel(lat=32.65, lng=51.68),
            ),
            cargo=CargoModel(type="General", weight=1000, count=1, description="Desc"),
            vehicle=VehicleModel(
                driver_national_code="1234567890", driver_phone="09123334444", plate="12A34567", type="Truck"
            ),
            financial=FinancialModel(cost=1000, payment_method="Cash"),
        )
        await management_service.upsert_account(
            ManagedAccountUpsertRequest(
                external_name="OTP-ACCOUNT",
                bot_owner="operator-otp",
                otp_needed=True,
                start_shipping=True,
                route_key="route-otp",
            )
        )
        created = await management_service.create_queue_item(
            ManagedQueueCreateRequest(
                account_external_name="OTP-ACCOUNT",
                route_key="route-otp",
                bot_owner="operator-otp",
                waybill_payload=waybill_payload,
            )
        )

        fake_enqueue = AsyncMock()
        with patch("app.services.management_service.queue_manager.enqueue_waybill", new=fake_enqueue):
            blocked = await management_service.dispatch_queue_item(
                created["queue_item_id"],
                ManagedQueueDispatchRequest(),
            )

        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["last_error"], "otp_required")
        self.assertTrue(blocked["result"]["dispatch_blocked"])
        fake_enqueue.assert_not_awaited()

    async def test_account_session_ready_uses_utcms_username_identity(self):
        await management_service.upsert_account(
            ManagedAccountUpsertRequest(
                external_name="DISPLAY-ACCOUNT",
                national_code="1234567890",
                phone_number="09120000000",
                raw={
                    "utcms_auth": {
                        "username": "LOGIN-IDENTITY",
                        "password": "secret-pass",
                    }
                },
            )
        )

        with patch(
            "app.services.management_service.session_vault.auth_state_exists",
            side_effect=lambda path: "LOGIN-IDENTITY" in path,
        ):
            accounts = await management_service.list_accounts()

        self.assertEqual(len(accounts), 1)
        self.assertIn("LOGIN-IDENTITY", accounts[0]["session_state_path"])
        self.assertTrue(accounts[0]["session_ready"])

    async def test_operator_tasks_enriches_tasks_with_artifact_count(self):
        fake_tasks = [
            {"task_id": "t-1", "status": "succeeded"},
            {"task_id": "t-2", "status": "failed"},
        ]

        async def mock_list_tasks(limit=50):
            return fake_tasks

        def mock_list_artifacts_for_task(task_id):
            if task_id == "t-1":
                return [{"path": "file1.png"}, {"path": "file2.txt"}]
            return []

        with (
            patch("app.services.management_service.task_service.list_tasks", side_effect=mock_list_tasks),
            patch.object(management_service, "_list_artifacts_for_task", side_effect=mock_list_artifacts_for_task),
        ):
            result = await management_service.operator_tasks(limit=10)

        self.assertEqual(result["count"], 2)
        tasks = result["tasks"]

        task1 = next(t for t in tasks if t["task_id"] == "t-1")
        self.assertEqual(task1["artifact_count"], 2)

        task2 = next(t for t in tasks if t["task_id"] == "t-2")
        self.assertEqual(task2["artifact_count"], 0)

    async def test_operator_artifacts_returns_task_artifacts_and_history(self):
        fake_task = {"task_id": "t-3", "status": "queued"}

        async def mock_get_task_status(task_id):
            return fake_task

        def mock_list_artifacts_for_task(task_id):
            return [{"path": "file_task.png"}]

        def mock_event_history(task_id=None):
            return [{"event": "created", "task_id": "t-3"}]

        with (
            patch("app.services.management_service.task_service.get_task_status", side_effect=mock_get_task_status),
            patch.object(management_service, "_list_artifacts_for_task", side_effect=mock_list_artifacts_for_task),
            patch("app.services.management_service.event_hub.history", side_effect=mock_event_history),
        ):
            result = await management_service.operator_artifacts("t-3")

        self.assertEqual(result["task"], fake_task)
        self.assertEqual(len(result["artifacts"]), 1)
        self.assertEqual(result["artifacts"][0]["path"], "file_task.png")
        self.assertEqual(len(result["event_history"]), 1)
        self.assertEqual(result["event_history"][0]["event"], "created")

    async def test_upsert_customer_creates_new_record(self):
        from sqlalchemy.ext.asyncio import AsyncSession
        from sqlmodel import select

        from app.models_management import ManagedCustomer
        from app.schemas.management import ManagedCustomerUpsertRequest

        request = ManagedCustomerUpsertRequest(
            source_system="test_system",
            external_key="cust-123",
            full_name="John Doe",
            wallet="1000",
            driver_limit=5,
            bot_running=True,
            raw={"foo": "bar"},
        )

        result = await management_service.upsert_customer(request)

        self.assertEqual(result["source_system"], "test_system")
        self.assertEqual(result["external_key"], "cust-123")
        self.assertEqual(result["full_name"], "John Doe")
        self.assertEqual(result["wallet"], "1000")
        self.assertEqual(result["driver_limit"], 5)
        self.assertEqual(result["bot_running"], True)

        async with AsyncSession(self.engine) as session:
            statement = select(ManagedCustomer).where(
                ManagedCustomer.source_system == "test_system", ManagedCustomer.external_key == "cust-123"
            )
            record = (await session.execute(statement)).scalars().first()
            self.assertIsNotNone(record)
            self.assertEqual(record.full_name, "John Doe")
            self.assertEqual(record.wallet, "1000")
            self.assertEqual(record.driver_limit, 5)
            self.assertEqual(record.bot_running, True)

    async def test_upsert_customer_updates_existing_record(self):
        from sqlalchemy.ext.asyncio import AsyncSession
        from sqlmodel import select

        from app.models_management import ManagedCustomer
        from app.schemas.management import ManagedCustomerUpsertRequest

        # Create initial record
        async with AsyncSession(self.engine) as session:
            record = ManagedCustomer(
                source_system="test_system_2",
                external_key="cust-456",
                full_name="Jane Doe",
                wallet="500",
                driver_limit=2,
            )
            session.add(record)
            await session.commit()

        request = ManagedCustomerUpsertRequest(
            source_system="test_system_2",
            external_key="cust-456",
            full_name="Jane Smith",
            wallet="2000",
            driver_limit=10,
            bot_running=False,
            two_way=True,
            raw={"updated": True},
        )

        result = await management_service.upsert_customer(request)

        self.assertEqual(result["full_name"], "Jane Smith")
        self.assertEqual(result["wallet"], "2000")
        self.assertEqual(result["driver_limit"], 10)
        self.assertEqual(result["bot_running"], False)
        self.assertEqual(result["two_way"], True)

        async with AsyncSession(self.engine) as session:
            statement = select(ManagedCustomer).where(
                ManagedCustomer.source_system == "test_system_2", ManagedCustomer.external_key == "cust-456"
            )
            updated_record = (await session.execute(statement)).scalars().first()
            self.assertIsNotNone(updated_record)
            self.assertEqual(updated_record.full_name, "Jane Smith")
            self.assertEqual(updated_record.wallet, "2000")
            self.assertEqual(updated_record.driver_limit, 10)
            self.assertEqual(updated_record.bot_running, False)
            self.assertEqual(updated_record.two_way, True)

    async def test_upsert_customer_returns_dict(self):
        from app.schemas.management import ManagedCustomerUpsertRequest

        request = ManagedCustomerUpsertRequest(
            source_system="test_system_3", external_key="cust-789", full_name="Bob Builder"
        )

        result = await management_service.upsert_customer(request)

        self.assertIsInstance(result, dict)
        self.assertIn("source_system", result)
        self.assertIn("external_key", result)
        self.assertIn("full_name", result)
        self.assertIn("synced_at", result)
