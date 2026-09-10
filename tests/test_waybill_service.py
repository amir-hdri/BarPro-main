from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.core.exceptions import WaybillError
from app.schemas.multitenant import WaybillJobResponse
from app.schemas.task import TaskStatus, WaybillTaskStatusResponse
from app.schemas.waybill import (
    CargoModel,
    FinancialModel,
    GeoCoordinateModel,
    LocationModel,
    OperationMode,
    ReceiverModel,
    SenderModel,
    UTCMSLoginModel,
    VehicleModel,
    WaybillMapRequest,
)
from app.services.waybill_job_service import WaybillJobService
from app.services.waybill_service import WaybillService


def create_request(operation_mode: OperationMode = OperationMode.SAFE) -> WaybillMapRequest:
    return WaybillMapRequest(
        session_id="svc-test",
        operation_mode=operation_mode,
        sender=SenderModel(
            name="علی رضایی", phone="09121111111", address="تهران خیابان کارگر", national_code="0084575948"
        ),
        receiver=ReceiverModel(name="حسن محمدی", phone="09122222222", address="کرج میدان شهدا"),
        origin=LocationModel(
            province="تهران",
            city="تهران",
            address="خیابان کارگر شمالی پلاک ۱",
            coordinates=GeoCoordinateModel(lat=1.0, lng=1.0),
        ),
        destination=LocationModel(
            province="البرز", city="کرج", address="میدان شهدا پلاک ۱۰", coordinates=GeoCoordinateModel(lat=2.0, lng=2.0)
        ),
        cargo=CargoModel(type="آهن آلات", packaging="فله", weight=1000, count=1, value=1000000, description="test"),
        vehicle=VehicleModel(
            driver_national_code="0084575948", driver_phone="09120000000", plate="12ب345ایران11", type="کامیون"
        ),
        financial=FinancialModel(cost=1000, payment_method="Cash"),
        utcms_auth=UTCMSLoginModel(username="test-user", password="test-password"),
    )


@pytest.mark.asyncio
async def test_service_returns_safe_mode_response():
    service = WaybillService()
    request = create_request(OperationMode.SAFE)

    with (
        patch("app.automation.browser.browser_manager.initialize", AsyncMock()),
        patch("app.automation.browser.browser_manager.create_context", AsyncMock(return_value=("sid", AsyncMock()))),
        patch("app.automation.browser.browser_manager.new_page", AsyncMock(return_value=AsyncMock())),
        patch("app.automation.browser.browser_manager.close_context", AsyncMock()),
        patch("app.automation.auth.UTCMSAuthenticator") as auth_cls,
        patch("app.automation.waybill_enhanced.EnhancedWaybillManager") as manager_cls,
        patch("app.automation.reporting.report_service.record_request", AsyncMock()),
        patch("app.automation.reporting.report_service.record_success", AsyncMock()),
        patch("app.automation.reporting.report_service.record_map_usage", AsyncMock()),
    ):
        auth_instance = auth_cls.return_value
        auth_instance._is_logged_in = AsyncMock(return_value=True)

        manager_instance = manager_cls.return_value
        manager_instance.create_waybill_with_map = AsyncMock(
            return_value={"success": True, "status": "validated", "validation_summary": {"ready_for_submit": True}}
        )
        manager_instance.close = AsyncMock()

        response = await service.create_waybill_with_map(request)

    assert response["mode"] == "safe"
    assert response["status"] == "validated"
    assert "request_id" in response
    assert response["validation_summary"]["has_driver_data"] is True
    manager_instance.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_service_rejects_incomplete_safe_payload_before_browser():
    service = WaybillService()
    request = create_request(OperationMode.SAFE)
    request.origin.address = ""
    initialize = AsyncMock()

    with patch("app.services.waybill_service.browser_manager.initialize", initialize):
        with pytest.raises(HTTPException) as exc:
            await service.create_waybill_with_map(request)

    assert exc.value.status_code == 422
    assert exc.value.detail["error"] == "WAYBILL_PAYLOAD_INCOMPLETE"
    assert "آدرس مبدا" in exc.value.detail["errors"]
    assert exc.value.detail["mutation_dispatched"] is False
    assert exc.value.detail["browser_started"] is False
    initialize.assert_not_awaited()


@pytest.mark.asyncio
async def test_service_blocks_full_mode_without_env_flag():
    service = WaybillService()
    request = create_request(OperationMode.FULL)

    with patch("app.core.config.utcms_config.ALLOW_LIVE_SUBMIT", False):
        with pytest.raises(HTTPException) as exc:
            await service.create_waybill_with_map(request)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_service_rejects_full_mode_when_preflight_requirements_missing():
    service = WaybillService()
    request = create_request(OperationMode.FULL)
    request.vehicle.driver_national_code = None
    request.vehicle.plate = None

    with patch("app.core.config.utcms_config.ALLOW_LIVE_SUBMIT", True):
        with pytest.raises(HTTPException) as exc:
            await service.create_waybill_with_map(request)

    assert exc.value.status_code == 422
    assert "missing_requirements" in exc.value.detail


@pytest.mark.asyncio
async def test_service_returns_503_when_login_fails_due_to_network():
    service = WaybillService()
    request = create_request(OperationMode.FULL)
    request.utcms_auth = UTCMSLoginModel(
        username="user",
        password="pass",
        login_url="https://barname.utcms.ir/Barname/Account/Login",
    )

    with (
        patch("app.core.config.utcms_config.ALLOW_LIVE_SUBMIT", True),
        patch("app.automation.browser.browser_manager.initialize", AsyncMock()),
        patch("app.automation.browser.browser_manager.create_context", AsyncMock(return_value=("sid", AsyncMock()))),
        patch("app.automation.browser.browser_manager.new_page", AsyncMock(return_value=AsyncMock())),
        patch("app.automation.browser.browser_manager.close_context", AsyncMock()),
        patch("app.automation.auth.UTCMSAuthenticator") as auth_cls,
        patch("app.automation.reporting.report_service.record_request", AsyncMock()),
        patch("app.automation.reporting.report_service.record_failure", AsyncMock()),
    ):
        auth_instance = auth_cls.return_value
        auth_instance._is_logged_in = AsyncMock(return_value=False)
        auth_instance.login = AsyncMock(return_value=False)
        auth_instance.last_error = "دسترسی به صفحه ورود UTCMS ممکن نشد (ERR_NAME_NOT_RESOLVED)."

        with pytest.raises(HTTPException) as exc:
            await service.create_waybill_with_map(request)

    assert exc.value.status_code == 503
    assert "اتصال" in exc.value.detail


@pytest.mark.asyncio
async def test_solve_waybill_captcha_closes_manager_when_execution_raises():
    service = WaybillService()

    with patch("app.automation.waybill_enhanced.EnhancedWaybillManager") as manager_cls:
        manager_instance = manager_cls.return_value
        manager_instance.create_waybill_with_map = AsyncMock(side_effect=RuntimeError("form execution failed"))
        manager_instance.close = AsyncMock()

        with pytest.raises(RuntimeError, match="form execution failed"):
            await service._solve_waybill_captcha(AsyncMock(), AsyncMock(), {}, dry_run=True)

    manager_instance.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_detect_map_closes_manager_before_early_return():
    service = WaybillService()
    page = AsyncMock()
    page.url = "https://barname.utcms.ir/barname/DocumentList/Index"
    context = AsyncMock()
    proxy_rotator = AsyncMock()
    proxy_rotator.get_next.return_value = None

    with (
        patch("app.services.waybill_service.browser_manager.initialize", AsyncMock()),
        patch(
            "app.services.waybill_service.browser_manager.create_context",
            AsyncMock(return_value=("detect-map-session", context)),
        ),
        patch("app.services.waybill_service.browser_manager.new_page", AsyncMock(return_value=page)),
        patch("app.services.waybill_service.browser_manager.close_context", AsyncMock()) as close_context,
        patch("app.services.waybill_service.get_proxy_rotator", return_value=proxy_rotator),
        patch("app.automation.auth.UTCMSAuthenticator") as auth_cls,
        patch("app.automation.waybill_enhanced.EnhancedWaybillManager") as manager_cls,
        patch("app.services.waybill_service.report_service.record_map_usage", AsyncMock()),
    ):
        auth_instance = auth_cls.return_value
        auth_instance._is_logged_in = AsyncMock(return_value=True)
        auth_instance.last_error = None

        manager_instance = manager_cls.return_value
        manager_instance._ensure_waybill_form_page = AsyncMock(side_effect=WaybillError("waybill form unavailable"))
        manager_instance.close = AsyncMock()

        result = await service.detect_map(session_id="public-session")

    assert result["has_map"] is False
    assert result["authenticated"] is True
    manager_instance.close.assert_awaited_once()
    page.close.assert_awaited_once()
    close_context.assert_awaited_once_with("detect-map-session")


# ── Tracking-first acknowledgement exposure tests (plan Task 5) ──────────────


class _JobLike:
    """Minimal attributes WaybillJobResponse needs for model_validate."""

    def __init__(self, **kwargs):
        base = {
            "id": 1,
            "job_id": "job-ack-1",
            "client_id": 1,
            "driver_id": 1,
            "status": "unknown",
            "source": "api",
            "correlation_id": None,
            "business_date": None,
            "priority": 5,
            "last_error": None,
            "error_category": None,
            "next_retry_at": None,
            "submit_after": None,
            "terminal_reason": None,
            "attempt_count": 1,
            "max_retries": 3,
            "created_at": datetime(2026, 9, 9, 12, 0, 0),
            "updated_at": datetime(2026, 9, 9, 12, 0, 0),
        }
        base.update(kwargs)
        for key, value in base.items():
            setattr(self, key, value)


def test_job_response_acknowledges_tracking_received():
    resp = WaybillJobResponse.model_validate(
        _JobLike(
            result_json={
                "tracking_code": "UTC-123",
                "confirmation_status": "tracking_received",
                "operator_acknowledged": True,
            }
        )
    )
    assert resp.operator_acknowledged is True
    assert isinstance(resp.result_json, dict) and resp.result_json["tracking_code"] == "UTC-123"


def test_job_response_not_acknowledged_for_missing_code():
    resp = WaybillJobResponse.model_validate(
        _JobLike(
            result_json={
                "confirmation_status": "tracking_missing_history_required",
                "requires_reconciliation": True,
            }
        )
    )
    assert resp.operator_acknowledged is False


def test_job_response_acknowledged_with_json_string_result():
    resp = WaybillJobResponse.model_validate(
        _JobLike(
            result_json='{"tracking_code": "UTC-123", "confirmation_status": "tracking_received"}'
        )
    )
    assert resp.operator_acknowledged is True


def test_task_status_response_mirrors_ack_fields():
    resp = WaybillTaskStatusResponse(
        task_id="t1",
        idempotency_key="k1",
        status=TaskStatus.UNKNOWN,
        created_at=datetime(2026, 9, 9, 12, 0, 0),
        updated_at=datetime(2026, 9, 9, 12, 0, 0),
        result={
            "tracking_code": "UTC-123",
            "confirmation_status": "tracking_received",
            "operator_acknowledged": True,
            "requires_resubmission": False,
        },
    )
    assert resp.operator_acknowledged is True
    assert resp.requires_resubmission is False


def test_task_status_response_defaults_false_without_result():
    resp = WaybillTaskStatusResponse(
        task_id="t2",
        idempotency_key="k2",
        status=TaskStatus.PENDING,
        created_at=datetime(2026, 9, 9, 12, 0, 0),
        updated_at=datetime(2026, 9, 9, 12, 0, 0),
    )
    assert resp.operator_acknowledged is False
    assert resp.requires_resubmission is False


async def test_retry_rejects_job_with_persisted_tracking_code():
    """409 before any state change — a code-bearing job is never retried."""
    service = WaybillJobService()
    job = _JobLike(
        status="failed",
        error_category="network_error",
        result_json={"tracking_code": "UTC-409", "confirmation_status": "tracking_received"},
    )

    session = MagicMock()
    exec_result = MagicMock()
    exec_result.first = MagicMock(return_value=job)
    session.exec = AsyncMock(return_value=exec_result)

    client_obj = _JobLike(id=1, client_id=1)
    user_context = {"role": "client", "user": client_obj}

    with pytest.raises(HTTPException) as exc_info:
        await service.retry_job(user_context, "job-ack-1", session)
    assert exc_info.value.status_code == 409
    assert "کد رهگیری" in exc_info.value.detail
