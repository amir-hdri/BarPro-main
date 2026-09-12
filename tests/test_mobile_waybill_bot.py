"""Mobile transport integration tests at the bot and scheduler boundaries."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.automation.utcms_mobile_client import UtcmsMobileClient
from app.automation.waybill_bot_multitenant import WaybillAutomationBot
from app.models_multitenant import Client, Driver, TaskStatus, WaybillJob
from app.orchestrator.reconciliation_service import _is_operator_otp_pending
from app.services.scheduled_waybill_executor import _execute_single_job


@pytest.fixture
async def async_db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    session = AsyncSession(engine, expire_on_commit=False)
    client = Client(
        id=1,
        client_code="mobile-test",
        name="Mobile Test",
        username="mobile-test",
        full_name="Mobile Test",
        email="mobile@test.invalid",
        hashed_password="hash",
        status="active",
    )
    driver = Driver(
        id=1,
        client_id=1,
        driver_national_code="0084575948",
        full_name="Test Driver",
        utcms_username="user",
        utcms_password_encrypted="enc",
        status="active",
    )
    job = WaybillJob(
        id=1,
        job_id="job-mobile-scheduled",
        idempotency_key="idem-mobile-scheduled",
        client_id=1,
        driver_id=1,
        status=TaskStatus.PENDING.value,
        source="api",
        payload_json={"driver_national_code": "0084575948"},
        max_retries=3,
    )
    session.add(client)
    session.add(driver)
    session.add(job)
    await session.commit()
    yield session, job, client, driver
    await session.close()
    await engine.dispose()


def _mobile_payload() -> dict:
    return {
        "sender": {
            "is_company": False,
            "first_name": "علی",
            "last_name": "رضایی",
            "phone": "09121234567",
            "national_code": "0084575948",
            "postal_code": "1111111111",
        },
        "receiver": {
            "is_company": False,
            "first_name": "حسن",
            "last_name": "محمدی",
            "phone": "09129876543",
            "national_code": "0012345679",
            "postal_code": "2222222222",
        },
        "origin": {
            "province": "تهران",
            "city": "تهران",
            "address": "خیابان آزادی",
            "postal_code": "1111111111",
            "lat": 35.7,
            "lon": 51.4,
        },
        "destination": {
            "province": "البرز",
            "city": "کرج",
            "address": "بلوار جمهوری",
            "postal_code": "2222222222",
            "lat": 35.84,
            "lon": 50.94,
        },
        "cargo": {
            "items": [
                {"product_id": 17, "pack_type_id": 3, "weight": 100, "count": 2, "description": "آهن"},
                {"product_id": 18, "pack_type_id": 4, "weight": 50, "count": 1, "description": "میلگرد"},
            ],
            "value": 2500000,
        },
        "vehicle": {
            "driver_national_code": "0084575948",
            "driver_phone": "09121234567",
            "tag_type": 1,
            "t1": "11",
            "t2": "345",
            "t3": "ب",
            "t4": "12",
            "capacity": 10,
            "type": "کامیون",
        },
        "insurance": {"have_insurance": True, "cover": 1000000},
        "financial": {"cost": 5000000, "bearing_cost": 100000, "pre_rent": 1000000, "post_rent": 4000000},
    }


class _FakeMobileClient:
    extract_document_id = staticmethod(UtcmsMobileClient.extract_document_id)
    extract_tracking_code = staticmethod(UtcmsMobileClient.extract_tracking_code)
    extract_otp_required = staticmethod(UtcmsMobileClient.extract_otp_required)

    def __init__(self, *args, **kwargs):
        self.insert_calls = 0

    async def login(self, username: str, password: str, cap_token: str):
        assert (username, password, cap_token) == ("user", "password", "login-cap")
        return SimpleNamespace(token="token-1", expires_at="2026-09-11T10:00:00")

    async def insert_document(self, payload, *, allow_live_submit: bool, cap_token: str | None = None):
        self.insert_calls += 1
        assert allow_live_submit is True
        assert cap_token == "issue-cap"
        return {"resultCode": 200, "obj": {"id": "doc-1", "isOtpNeeded": True}}


@pytest.mark.asyncio
async def test_mobile_bot_preserves_server_otp_signal_without_resubmitting():
    page = MagicMock()
    context = MagicMock()
    bot = WaybillAutomationBot(page, context)
    payload = _mobile_payload()

    with (
        patch("app.automation.waybill_bot_multitenant.utcms_config.UTCMS_TRANSPORT", "mobile"),
        patch("app.automation.waybill_bot_multitenant.utcms_config.ALLOW_LIVE_SUBMIT", True),
        patch("app.automation.waybill_bot_multitenant.utcms_config.UTCMS_CAPTCHA_VALUE", "login-cap"),
        patch("app.automation.waybill_bot_multitenant.build_enhanced_waybill_payload", return_value=payload),
        patch("app.automation.waybill_bot_multitenant.validate_live_waybill_payload", return_value=[]),
        patch("app.automation.utcms_mobile_client.UtcmsMobileClient", _FakeMobileClient),
    ):
        result = await bot.execute_waybill_job(
            username="user",
            password="password",
            payload={**payload, "mobile_issue_cap_token": "issue-cap"},
            job_id="job-mobile-otp",
            client_id=1,
        )

    assert result["status"] == "unknown"
    assert result["error_category"] == "otp_required"
    assert result["requires_operator_otp"] is True
    assert result["mutation_status"] == "dispatched"
    assert result["document_id"] == "doc-1"
    assert result["result"]["otp_required"] is True
    assert result["result"]["document_id"] == "doc-1"


@pytest.mark.asyncio
async def test_scheduled_mobile_transport_does_not_create_browser_page(async_db):
    session, job, client, driver = async_db
    job.status = "in_progress"
    session.add(job)
    await session.commit()

    browser_session = MagicMock()
    browser_session.__aenter__ = AsyncMock(return_value=(None, None))
    browser_session.__aexit__ = AsyncMock(return_value=False)
    bot_instance = MagicMock()
    bot_instance.execute_waybill_job = AsyncMock(return_value={"status": "validated", "result": {"mode": "dry_run"}})

    with (
        patch("app.services.scheduled_waybill_executor.utcms_config.UTCMS_TRANSPORT", "mobile"),
        patch("app.services.scheduled_waybill_executor.utcms_submission_gate.is_submission_allowed", new_callable=AsyncMock, return_value=True),
        patch("app.services.scheduled_waybill_executor.managed_browser_session", return_value=browser_session) as session_factory,
        patch("app.services.scheduled_waybill_executor.browser_manager.new_page", new_callable=AsyncMock) as new_page,
        patch("app.services.scheduled_waybill_executor.decrypt_driver_password", return_value="pw"),
        patch("app.services.scheduled_waybill_executor.WaybillAutomationBot", return_value=bot_instance),
    ):
        result = await _execute_single_job(client, driver, job, session, attempt=1, driver_password="pw")

    assert result["status"] == "validated"
    session_factory.assert_called_once()
    assert session_factory.call_args.kwargs["skip_browser"] is True
    new_page.assert_not_awaited()
    bot_instance.execute_waybill_job.assert_awaited_once()
    assert bot_instance.execute_waybill_job.await_args.kwargs["auth_state_path"]


@pytest.mark.asyncio
async def test_scheduled_mobile_otp_closes_gate_and_skips_reconciliation(async_db):
    session, job, client, driver = async_db
    job.status = "in_progress"
    session.add(job)
    await session.commit()

    browser_session = MagicMock()
    browser_session.__aenter__ = AsyncMock(return_value=(None, None))
    browser_session.__aexit__ = AsyncMock(return_value=False)
    bot_instance = MagicMock()
    bot_instance.execute_waybill_job = AsyncMock(
        return_value={
            "status": "unknown",
            "transport": "mobile",
            "error": "UTCMS برای صدور نهایی OTP خواسته است",
            "error_category": "otp_required",
            "mutation_status": "dispatched",
            "requires_operator_otp": True,
            "result": {"document_id": "doc-otp", "otp_required": True},
        }
    )

    with (
        patch("app.services.scheduled_waybill_executor.utcms_config.UTCMS_TRANSPORT", "mobile"),
        patch("app.services.scheduled_waybill_executor.utcms_submission_gate.is_submission_allowed", new_callable=AsyncMock, return_value=True),
        patch("app.services.scheduled_waybill_executor.utcms_submission_gate.record_otp_detected", new_callable=AsyncMock) as record_otp,
        patch("app.services.scheduled_waybill_executor.managed_browser_session", return_value=browser_session),
        patch("app.services.scheduled_waybill_executor.browser_manager.new_page", new_callable=AsyncMock) as new_page,
        patch("app.services.scheduled_waybill_executor.decrypt_driver_password", return_value="pw"),
        patch("app.services.scheduled_waybill_executor.WaybillAutomationBot", return_value=bot_instance),
    ):
        result = await _execute_single_job(client, driver, job, session, attempt=1, driver_password="pw")

    assert result["status"] == TaskStatus.UNKNOWN.value
    assert result["error_category"] == "otp_required"
    assert job.error_category == "otp_required"
    assert job.document_id == "doc-otp"
    assert job.next_retry_at is None
    assert _is_operator_otp_pending(job) is True
    record_otp.assert_awaited_once()
    new_page.assert_not_awaited()


@pytest.mark.asyncio
async def test_mobile_bot_auto_solves_login_captcha():
    """Verify that if cap_token is missing, client.auto_solve_captcha(form_id='login') is called."""
    payload = _mobile_payload()
    payload.pop("mobile_cap_token", None)
    payload.pop("cap_token", None)

    login_calls = []
    auto_solve_calls = []

    class _AutoSolveMockClient:
        extract_document_id = staticmethod(UtcmsMobileClient.extract_document_id)
        extract_tracking_code = staticmethod(UtcmsMobileClient.extract_tracking_code)
        extract_otp_required = staticmethod(UtcmsMobileClient.extract_otp_required)

        def __init__(self, *args, **kwargs):
            pass

        async def auto_solve_captcha(self, form_id: str = "login"):
            auto_solve_calls.append(form_id)
            return ("solved-cap-text", "cap-token-123")

        async def login(self, username: str, password: str, cap_token: str):
            login_calls.append((username, password, cap_token))
            return SimpleNamespace(token="token-auto", expires_at="2026-09-11T12:00:00")

        async def get_user_fleet_list(self):
            return {"resultCode": 200, "obj": []}

    bot = WaybillAutomationBot()  # Standalone headless: no page, no context

    with (
        patch("app.automation.waybill_bot_multitenant.utcms_config.UTCMS_TRANSPORT", "mobile"),
        patch("app.automation.waybill_bot_multitenant.utcms_config.ALLOW_LIVE_SUBMIT", False),
        patch("app.automation.waybill_bot_multitenant.utcms_config.UTCMS_CAPTCHA_VALUE", ""),
        patch("app.automation.waybill_bot_multitenant.build_enhanced_waybill_payload", return_value=payload),
        patch("app.automation.waybill_bot_multitenant.validate_live_waybill_payload", return_value=[]),
        patch("app.automation.utcms_mobile_client.UtcmsMobileClient", _AutoSolveMockClient),
    ):
        result = await bot.execute_waybill_job(
            username="user",
            password="password",
            payload={**payload, "mobile_issue_cap_token": "issue-cap"},
            job_id="job-auto-cap",
            client_id=1,
        )

    assert auto_solve_calls == ["login"]
    assert len(login_calls) == 1
    # ``auto_solve_captcha`` returns (display answer, server proof token);
    # login must send the proof token accepted by the mobile API.
    assert login_calls[0][2] == "cap-token-123"
    assert result["status"] == "validated"


@pytest.mark.asyncio
async def test_mobile_bot_matches_driver_fleet():
    """Verify fleet matching from /Truck/GetUserFleetList enriches vehicle payload."""
    payload = _mobile_payload()
    # Initial vehicle has capacity 10
    assert payload["vehicle"]["capacity"] == 10

    class _FleetMockClient:
        extract_document_id = staticmethod(UtcmsMobileClient.extract_document_id)
        extract_tracking_code = staticmethod(UtcmsMobileClient.extract_tracking_code)
        extract_otp_required = staticmethod(UtcmsMobileClient.extract_otp_required)

        def __init__(self, *args, **kwargs):
            pass

        async def login(self, username: str, password: str, cap_token: str):
            return SimpleNamespace(token="token-fleet", expires_at="2026-09-11T12:00:00")

        async def get_user_fleet_list(self):
            return {
                "resultCode": 200,
                "obj": [
                    {
                        "carTag": "11ب345ایران12",
                        "tagType": 2,
                        "capacity": 25000,
                        "type": "تریلی چادری",
                        "haveCertificate": True,
                        "have3rdInsurance": True,
                        "freighterId": 777,
                        "id": 9999,
                    }
                ],
            }

    bot = WaybillAutomationBot()

    with (
        patch("app.automation.waybill_bot_multitenant.utcms_config.UTCMS_TRANSPORT", "mobile"),
        patch("app.automation.waybill_bot_multitenant.utcms_config.ALLOW_LIVE_SUBMIT", False),
        patch("app.automation.waybill_bot_multitenant.utcms_config.UTCMS_CAPTCHA_VALUE", "cap-1"),
        patch("app.automation.waybill_bot_multitenant.build_enhanced_waybill_payload", return_value=payload),
        patch("app.automation.waybill_bot_multitenant.validate_live_waybill_payload", return_value=[]),
        patch("app.automation.utcms_mobile_client.UtcmsMobileClient", _FleetMockClient),
    ):
        result = await bot.execute_waybill_job(
            username="user",
            password="password",
            payload={**payload, "mobile_issue_cap_token": "issue-cap"},
            job_id="job-fleet",
            client_id=1,
        )

    assert result["status"] == "validated"
    step_names = [s["step"] for s in result["steps"]]
    assert "mobile_fleet_match" in step_names
    # Verify vehicle was enriched
    assert payload["vehicle"]["freighter_id"] == 777
    assert payload["vehicle"]["server_truck_id"] == 9999


@pytest.mark.asyncio
async def test_mobile_bot_live_submit_success():
    """Verify live submit executes insert_document and records document_id and tracking_code."""
    payload = _mobile_payload()

    class _LiveSubmitMockClient:
        extract_document_id = staticmethod(UtcmsMobileClient.extract_document_id)
        extract_tracking_code = staticmethod(UtcmsMobileClient.extract_tracking_code)
        extract_otp_required = staticmethod(UtcmsMobileClient.extract_otp_required)

        def __init__(self, *args, **kwargs):
            pass

        async def login(self, username: str, password: str, cap_token: str):
            return SimpleNamespace(token="token-live", expires_at="2026-09-11T12:00:00")

        async def get_user_fleet_list(self):
            return {"resultCode": 200, "obj": []}

        async def insert_document(self, payload, *, allow_live_submit: bool, cap_token: str | None = None):
            assert allow_live_submit is True
            return {
                "resultCode": 200,
                "obj": {
                    "docId": "doc-live-123",
                    "trackingCode": "TRK-9999-LIVE",
                    "isOtpNeeded": False,
                },
            }

    bot = WaybillAutomationBot()

    with (
        patch("app.automation.waybill_bot_multitenant.utcms_config.UTCMS_TRANSPORT", "mobile"),
        patch("app.automation.waybill_bot_multitenant.utcms_config.UTCMS_CAPTCHA_VALUE", "cap-1"),
        patch("app.automation.waybill_bot_multitenant.build_enhanced_waybill_payload", return_value=payload),
        patch("app.automation.waybill_bot_multitenant.validate_live_waybill_payload", return_value=[]),
        patch("app.automation.utcms_mobile_client.UtcmsMobileClient", _LiveSubmitMockClient),
    ):
        result = await bot.execute_waybill_job(
            username="user",
            password="password",
            payload={**payload, "mobile_issue_cap_token": "issue-cap"},
            job_id="job-live-submit",
            client_id=1,
            allow_live_submit=True,
        )

    assert result["status"] == TaskStatus.SUCCESS.value
    assert result["document_id"] == "doc-live-123"
    assert result["tracking_code"] == "TRK-9999-LIVE"
    assert result["result"]["document_id"] == "doc-live-123"
    assert result["result"]["tracking_code"] == "TRK-9999-LIVE"
    step_names = [s["step"] for s in result["steps"]]
    assert "mobile_insert" in step_names


@pytest.mark.asyncio
async def test_waybill_worker_executes_mobile_without_browser(async_db):
    """Verify worker execution in mobile transport does NOT call browser_manager."""
    session, job, client, driver = async_db
    job.status = TaskStatus.QUEUED.value
    session.add(job)
    await session.commit()

    from app.workers.waybill_worker import _execute_job

    mock_task = MagicMock()
    mock_task.request.hostname = "worker-mobile-test"
    mock_task.request.id = "task-mobile-test-123"

    bot_mock = MagicMock()
    bot_mock.execute_waybill_job = AsyncMock(
        return_value={
            "status": TaskStatus.SUCCESS.value,
            "document_id": "doc-worker-1",
            "tracking_code": "TRK-WORKER-777",
            "result": {
                "document_id": "doc-worker-1",
                "tracking_code": "TRK-WORKER-777",
            },
        }
    )

    def session_factory():
        return AsyncSession(session.bind, expire_on_commit=False)

    with (
        patch("app.workers.waybill_worker.utcms_config.UTCMS_TRANSPORT", "mobile"),
        patch("app.workers.waybill_worker.utcms_config.ALLOW_LIVE_SUBMIT", True),
        patch("app.workers.waybill_worker.get_worker_proxy_url", return_value="http://squid1:3128"),
        patch("app.workers.waybill_worker.browser_manager.create_context", new_callable=AsyncMock) as create_context,
        patch("app.workers.waybill_worker.browser_manager.new_page", new_callable=AsyncMock) as new_page,
        patch("app.workers.waybill_worker.managed_browser_session") as browser_session,
        patch("app.workers.waybill_worker.decrypt_driver_password", return_value="secret"),
        patch("app.workers.waybill_worker.utcms_submission_gate.get_state", new_callable=AsyncMock, return_value=MagicMock(value="otp_free")),
        patch("app.workers.waybill_worker.rpa_runtime.acquire_lock", new_callable=AsyncMock, return_value=True),
        patch("app.workers.waybill_worker.rpa_runtime.release_lock", new_callable=AsyncMock, return_value=True),
        patch("app.services.session_vault.session_vault.async_get_session_version", new_callable=AsyncMock, return_value=None),
        patch("app.workers.waybill_worker.WaybillAutomationBot", return_value=bot_mock) as bot_cls,
        patch("app.workers.waybill_worker.async_session_factory", session_factory),
    ):
        result = await _execute_job(mock_task, job.job_id)

    assert result["status"] == TaskStatus.SUCCESS.value

    # Assert browser was never touched
    create_context.assert_not_awaited()
    new_page.assert_not_awaited()
    browser_session.assert_not_called()

    # Assert bot was instantiated headless with worker proxy
    bot_cls.assert_called_once_with(page=None, context=None, proxy_url="http://squid1:3128")
    bot_mock.execute_waybill_job.assert_awaited_once()

    # Assert job is recorded with document_id and tracking_code in DB
    async with AsyncSession(session.bind) as check_session:
        updated_job = (await check_session.exec(select(WaybillJob).where(WaybillJob.job_id == job.job_id))).first()
        assert updated_job is not None
        assert updated_job.document_id == "doc-worker-1"
        assert updated_job.result_json["tracking_code"] == "TRK-WORKER-777"
        assert updated_job.result_json["document_id"] == "doc-worker-1"
