"""Live-submit guard tests for the multitenant waybill bot."""

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


def _bot_with_logged_in_session(manager_result):
    page = MagicMock()
    page.url = "about:blank"
    context = MagicMock()
    bot = WaybillAutomationBot(page, context)
    bot.authenticator._is_logged_in = AsyncMock(return_value=True)
    bot.manager.create_waybill_with_map = AsyncMock(return_value=manager_result)
    return bot


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
async def test_worker_bot_acknowledges_tracking_code_immediately() -> None:
    """A non-empty tracking code is an immediate operator acknowledgement.

    The bot must return ``status='success'`` with the acknowledgement contract
    (confirmation_status='tracking_received', operator_acknowledged=True) and
    must NOT mark the job as needing reconciliation — the code is not on the
    critical path anymore, and resubmission is never implied.
    """
    bot = _bot_with_logged_in_session({"success": True, "tracking_code": "123456"})

    with patch("app.automation.waybill_bot_multitenant.utcms_config.ALLOW_LIVE_SUBMIT", True):
        result = await bot.execute_waybill_job(
            username="user",
            password="password",
            payload=COMPLETE_PAYLOAD,
            job_id="job-test",
            client_id=1,
        )

    assert result["status"] == "success"
    assert result["result"]["tracking_code"] == "123456"
    assert result["result"]["confirmation_status"] == "tracking_received"
    assert result["result"]["operator_acknowledged"] is True
    assert result["result"]["requires_reconciliation"] is False
    assert result["result"]["requires_resubmission"] is False
    assert result["mutation_status"] == "dispatched"
    assert result.get("needs_reconciliation") is not True
    assert bot.manager.create_waybill_with_map.await_args.kwargs["dry_run"] is False


@pytest.mark.asyncio
async def test_worker_bot_acknowledges_real_manager_submitted_result() -> None:
    """Parity for the real manager shape: status='submitted' + tracking code.

    The mutation-boundary check must NOT treat a successful result carrying a
    tracking code as 'mutation may have been dispatched' (the historical bug:
    this shape fell into the ambiguous path and the acknowledgement never
    happened). It is an acknowledged success, not an ambiguity.
    """
    bot = _bot_with_logged_in_session(
        {
            "success": True,
            "status": "submitted",
            "confirmation_status": "pending_history_reconciliation",
            "tracking_code": "123456",
            "document_id": "214",
        }
    )

    with patch("app.automation.waybill_bot_multitenant.utcms_config.ALLOW_LIVE_SUBMIT", True):
        result = await bot.execute_waybill_job(
            username="user",
            password="password",
            payload=COMPLETE_PAYLOAD,
            job_id="job-test",
            client_id=1,
        )

    assert result["status"] == "success"
    assert result["result"]["tracking_code"] == "123456"
    assert result["result"]["confirmation_status"] == "tracking_received"
    assert result["result"]["operator_acknowledged"] is True
    assert result["result"]["requires_reconciliation"] is False
    assert result["result"]["requires_resubmission"] is False
    assert result["mutation_status"] == "dispatched"
    assert result.get("needs_reconciliation") is not True


@pytest.mark.asyncio
async def test_worker_bot_success_without_tracking_code_requires_history_only() -> None:
    """Success-shaped response without a code crosses the mutation boundary.

    The result must carry the missing-code contract: history_only
    reconciliation, never a resubmission.
    """
    bot = _bot_with_logged_in_session({"success": True, "status": "submitted", "document_id": "214000001"})

    with patch("app.automation.waybill_bot_multitenant.utcms_config.ALLOW_LIVE_SUBMIT", True):
        result = await bot.execute_waybill_job(
            username="user",
            password="password",
            payload=COMPLETE_PAYLOAD,
            job_id="job-test",
            client_id=1,
        )

    assert result["status"] == "unknown"
    assert result["error_category"] == "submission_unconfirmed"
    assert result["result"]["confirmation_status"] == "tracking_missing_history_required"
    assert result["result"]["operator_acknowledged"] is False
    assert result["result"]["reconciliation_mode"] == "history_only"
    assert result["result"]["requires_reconciliation"] is True
    assert result["result"]["requires_resubmission"] is False
    assert result["result"]["document_id"] == "214000001"


@pytest.mark.asyncio
async def test_worker_bot_does_not_resubmit_when_first_result_already_has_tracking_code() -> None:
    """Session-expired retry must not re-submit when a code was already obtained.

    The fresh-login retry loop (session expired → login → create_waybill again)
    must short-circuit when the first manager result already carries a
    tracking code: the mutation happened, a second submit could duplicate the
    waybill.
    """
    page = MagicMock()
    page.url = "about:blank"
    context = MagicMock()
    bot = WaybillAutomationBot(page, context)
    bot.authenticator._is_logged_in = AsyncMock(return_value=True)
    bot.authenticator.login = AsyncMock(return_value=False)
    bot.manager.create_waybill_with_map = AsyncMock(
        return_value={
            "success": False,
            "status": "failed",
            "tracking_code": "123456",
            "error": "فرم بارنامه پس از بازیابی در دسترس نیست",
        }
    )

    with patch("app.automation.waybill_bot_multitenant.utcms_config.ALLOW_LIVE_SUBMIT", True):
        result = await bot.execute_waybill_job(
            username="user",
            password="password",
            payload=COMPLETE_PAYLOAD,
            job_id="job-test",
            client_id=1,
        )

    bot.manager.create_waybill_with_map.assert_awaited_once()
    bot.authenticator.login.assert_not_awaited()
    # A code obtained before the failure is still an acknowledgement, never a resubmit.
    assert result["result"]["tracking_code"] == "123456"
    assert result["result"]["confirmation_status"] == "tracking_received"
    assert result["result"]["operator_acknowledged"] is True
