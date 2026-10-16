import json
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import utcms_config
from app.core.error_taxonomy import ErrorCategory, classify_error_string
from app.models_multitenant import TaskStatus
from app.orchestrator.utcms_reconciliation_scraper import (
    ScraperOutcome,
    UTCMSReconciliationScraper,
)
from app.workers.waybill_worker import _is_retryable


def test_classify_error_string_suspension_code_3000():
    """Verify that UTCMS 3000 suspension error is classified as AUTH_FAILURE, not TARGET_SITE_TIMEOUT."""
    raw_error = (
        "عدم رعایت ضوابط سامانه به طور موقت مسدود می باشد. علت مسدودی : عدم ورود کد دو عاملی. "
        "تاریخ خروج از لیست مسدودی : 1405/07/25 زمان خروج از لیست مسدودی : 09:57:05 (code: 3000)"
    )
    # Test with and without category hint
    cat = classify_error_string(raw_error, error_category_hint="mobile_api_error")
    assert cat == ErrorCategory.AUTH_FAILURE

    cat_no_hint = classify_error_string(raw_error)
    assert cat_no_hint == ErrorCategory.AUTH_FAILURE


def test_classify_error_string_api_hint_does_not_mask_errors():
    """Verify that general 'api' in category hint does not force TARGET_SITE_TIMEOUT unless unreachable/timeout."""
    cat = classify_error_string("Generic client rejection", error_category_hint="mobile_api_error")
    assert cat != ErrorCategory.TARGET_SITE_TIMEOUT

    cat_timeout = classify_error_string("Connection timed out", error_category_hint="api_timeout")
    assert cat_timeout == ErrorCategory.TARGET_SITE_TIMEOUT


def test_is_retryable_rejects_driver_suspension():
    """Verify that _is_retryable rejects code 3000 and suspension strings immediately."""
    result_suspension = {
        "status": TaskStatus.FAILED.value,
        "error": "عدم رعایت ضوابط سامانه به طور موقت مسدود می باشد. علت مسدودی : عدم ورود کد دو عاملی. (code: 3000)",
        "error_category": ErrorCategory.AUTH_FAILURE.value,
    }
    assert _is_retryable(result_suspension) is False

    result_code_only = {
        "status": TaskStatus.FAILED.value,
        "error": "portal rejected with code 3000",
        "error_category": "auth_failure",
    }
    assert _is_retryable(result_code_only) is False

    result_blocked_phrase = {
        "status": TaskStatus.FAILED.value,
        "error": "حساب کاربری شما مسدود می باشد لطفا با پشتیبانی تماس بگیرید",
        "error_category": "auth_failure",
    }
    assert _is_retryable(result_blocked_phrase) is False


@pytest.mark.asyncio
async def test_utcms_reconciliation_scraper_rejects_cancelled_and_draft_statuses():
    """Verify that reconciliation scraper rejects rows with draft, cancelled, or pending statuses."""
    scraper = UTCMSReconciliationScraper()

    # Case 1: Status is 'ابطال شده'
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.url = scraper.HISTORY_URL
    mock_page.evaluate = AsyncMock(
        return_value={
            "status": 200,
            "json": {
                "data": [
                    {
                        "docNo": "1362896488",
                        "statusName": "ابطال شده",
                        "dateFarsi": "1405/07/24",
                        "Id": "238997938",
                    }
                ]
            },
        }
    )

    res = await scraper.query_waybill_status(mock_page, tracking_code="1362896488")
    assert res.outcome == ScraperOutcome.NOT_FOUND
    assert res.details.get("reason") == "status_unconfirmed"
    assert "ابطال" in res.status_text

    # Case 2: Status is 'پیش‌نویس'
    mock_page.evaluate = AsyncMock(
        return_value={
            "status": 200,
            "json": {
                "data": [
                    {
                        "docNo": "1362896488",
                        "statusName": "پیش‌نویس",
                        "dateFarsi": "1405/07/24",
                        "Id": "238997938",
                    }
                ]
            },
        }
    )
    res_draft = await scraper.query_waybill_status(mock_page, tracking_code="1362896488")
    assert res_draft.outcome == ScraperOutcome.NOT_FOUND
    assert res_draft.details.get("reason") == "status_unconfirmed"

    # Case 3: Confirmed status 'ثبت شده'
    mock_page.evaluate = AsyncMock(
        return_value={
            "status": 200,
            "json": {
                "data": [
                    {
                        "docNo": "1362896488",
                        "statusName": "ثبت شده",
                        "dateFarsi": "1405/07/24",
                        "Id": "238997938",
                    }
                ]
            },
        }
    )
    res_confirmed = await scraper.query_waybill_status(mock_page, tracking_code="1362896488")
    assert res_confirmed.outcome == ScraperOutcome.REGISTERED
    assert res_confirmed.tracking_code == "1362896488"


def test_sweep_otp_stream_task_ignores_result():
    """Verify that sweep_otp_stream Celery task is configured with ignore_result=True."""
    from app.workers.tasks import sweep_otp_stream

    assert getattr(sweep_otp_stream, "ignore_result", False) is True


@pytest.mark.asyncio
async def test_hub_state_cannot_be_claimed_by_non_hub_number(monkeypatch):
    """When HUB_NUMBERS is configured, a forwarder with a different phone cannot claim HUB state."""
    from fastapi import Request

    from app.api.routes import otp_forwarder

    monkeypatch.setattr(utcms_config, "OTP_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setattr(utcms_config, "HUB_NUMBERS", ["09121111111"])

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.set = AsyncMock(return_value=True)

    # 1. Non-hub phone tries to send HEALTH_CHECK with app_role=HUB
    body_non_hub = json.dumps(
        {
            "event": "HEALTH_CHECK",
            "driver_phone": "09382173202",  # Non-hub phone
            "app_role": "HUB",
            "device_id": "phone-1",
        }
    ).encode()

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/otp/sms-forwarder",
        "headers": [
            (b"x-otp-webhook-token", b"test-secret"),
            (b"content-type", b"application/json"),
            (b"x-app-role", b"HUB"),
        ],
    }

    async def receive_non_hub():
        return {"type": "http.request", "body": body_non_hub, "more_body": False}

    request_non_hub = Request(scope, receive_non_hub)

    with patch("app.core.redis_client.redis_manager.get", new_callable=AsyncMock, return_value=mock_redis):
        res = await otp_forwarder.receive_sms_forwarder_webhook(request_non_hub)

    assert res["success"] is True
    # Ensure set(HUB_STATE_KEY, ...) was NEVER called for non-hub phone
    for call in mock_redis.set.call_args_list:
        assert "rpa:forwarder:hub:connected" not in call[0]

    # 2. Configured hub phone sends HEALTH_CHECK
    body_hub = json.dumps(
        {
            "event": "HEALTH_CHECK",
            "driver_phone": "09121111111",  # Configured hub phone
            "app_role": "HUB",
            "device_id": "phone-hub",
        }
    ).encode()

    async def receive_hub():
        return {"type": "http.request", "body": body_hub, "more_body": False}

    request_hub = Request(scope, receive_hub)
    with patch("app.core.redis_client.redis_manager.get", new_callable=AsyncMock, return_value=mock_redis):
        res_hub = await otp_forwarder.receive_sms_forwarder_webhook(request_hub)

    assert res_hub["success"] is True
    hub_set_calls = [call for call in mock_redis.set.call_args_list if "rpa:forwarder:hub:connected" in call[0]]
    assert len(hub_set_calls) > 0
