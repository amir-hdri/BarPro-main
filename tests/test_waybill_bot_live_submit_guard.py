from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.automation.waybill_bot_multitenant import WaybillAutomationBot

COMPLETE_PAYLOAD = {
    "sender": {"name": "علی فلاح", "phone": "09121234567"},
    "receiver": {"name": "احمد مومنی", "phone": "09129876543"},
    "origin": {"province": "هرمزگان", "city": "میناب", "address": "بلوار خلیج فارس"},
    "destination": {"province": "هرمزگان", "city": "میناب", "address": "طالوار"},
    "cargo": {"type": "مصالح", "packaging": "فله", "weight": "15", "value": "35000000"},
    "vehicle": {"driver_national_code": "3390745335", "plate": "79ع989ایران84"},
}


@pytest.mark.asyncio
async def test_worker_bot_uses_dry_run_when_live_submit_is_disabled() -> None:
    page = MagicMock()
    page.url = "about:blank"
    context = MagicMock()
    bot = WaybillAutomationBot(page, context)
    bot.authenticator._is_logged_in = AsyncMock(return_value=True)
    bot.manager.create_waybill_with_map = AsyncMock(
        return_value={"success": True, "status": "validated", "validation_summary": {"ready_for_submit": True}}
    )

    with patch("app.automation.waybill_bot_multitenant.utcms_config.ALLOW_LIVE_SUBMIT", False):
        result = await bot.execute_waybill_job(
            username="user",
            password="password",
            payload=COMPLETE_PAYLOAD,
            job_id="job-test",
            client_id=1,
        )

    assert result["status"] == "validated"
    assert result["result"] == {"ready_for_submit": True}
    bot.manager.create_waybill_with_map.assert_awaited_once()
    assert bot.manager.create_waybill_with_map.await_args.kwargs["dry_run"] is True


@pytest.mark.asyncio
async def test_worker_bot_keeps_tracking_code_pending_history_reconciliation() -> None:
    page = MagicMock()
    page.url = "about:blank"
    context = MagicMock()
    bot = WaybillAutomationBot(page, context)
    bot.authenticator._is_logged_in = AsyncMock(return_value=True)
    bot.manager.create_waybill_with_map = AsyncMock(return_value={"success": True, "tracking_code": "123456"})

    with patch("app.automation.waybill_bot_multitenant.utcms_config.ALLOW_LIVE_SUBMIT", True):
        result = await bot.execute_waybill_job(
            username="user",
            password="password",
            payload=COMPLETE_PAYLOAD,
            job_id="job-test",
            client_id=1,
        )

    # A browser tracking code is witness 1/3 only.  The worker must keep the
    # job UNKNOWN until the DB and UTCMS History/Search witnesses reconcile it.
    assert result["status"] == "unknown"
    assert result["result"]["tracking_code"] == "123456"
    assert result["result"]["confirmation_status"] == "pending_history_reconciliation"
    assert result["error_category"] == "submission_unconfirmed"
    assert result["mutation_status"] == "dispatched"
    assert result["needs_reconciliation"] is True
    assert bot.manager.create_waybill_with_map.await_args.kwargs["dry_run"] is False
