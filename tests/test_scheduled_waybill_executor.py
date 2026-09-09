"""Tracking-first parity tests for the scheduled waybill executor (plan Task 3).

The scheduled executor and the normal worker must expose IDENTICAL
tracking-first semantics:
- code-present  → UNKNOWN + tracking_received ack, no reconciliation schedule
- code-missing  → UNKNOWN + tracking_missing_history_required, history-only
                  reconciliation at +15s, never a resubmission
- unknown result → persisted unknown WITHOUT any recursive retry
"""

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

from app.models_multitenant import Client, Driver, TaskStatus, WaybillJob
from app.schemas.task import build_tracking_received_result
from app.services.scheduled_waybill_executor import _execute_single_job


@pytest.fixture(autouse=True)
def dev_env():
    with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
        yield


@pytest.fixture
async def async_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async_session = AsyncSession(engine, expire_on_commit=False)

    client = Client(
        id=1,
        client_code="sched-parity",
        name="Sched Parity",
        username="schedparity",
        full_name="Sched Parity",
        email="sched@parity.com",
        hashed_password="hash",
        status="active",
    )
    driver = Driver(
        id=1,
        client_id=1,
        driver_national_code="1234567890",
        full_name="Sched Driver",
        utcms_username="sched_driver",
        utcms_password_encrypted="enc",
        status="active",
    )
    async_session.add(client)
    async_session.add(driver)

    job = WaybillJob(
        id=1,
        job_id="job-sched-parity",
        idempotency_key="idem-sched-parity",
        client_id=1,
        driver_id=1,
        status=TaskStatus.PENDING.value,
        source="api",
        payload_json={"driver_national_code": "1234567890"},
        max_retries=3,
        priority=5,
    )
    async_session.add(job)
    await async_session.commit()
    async_session.flush()

    yield async_session, job, client, driver

    await async_session.close()
    await engine.dispose()


def _bot_result(bot_status: str, bot_result_payload: dict | None) -> dict:
    return {
        "status": bot_status,
        "result": bot_result_payload,
        "error": None,
        "error_category": None,
        "steps": [],
    }


async def _run_with_mocks(async_db, bot_result_dict):
    """Drive _execute_single_job with the browser session and bot mocked out.

    The bot is invoked exactly once per _execute_single_job call, so a
    recursive retry would show up as a second call.
    """
    session, job, client, driver = async_db
    job.status = TaskStatus.IN_PROGRESS.value
    session.add(job)
    await session.commit()

    bot_calls = []

    async def _fake_execute(**kwargs):
        bot_calls.append(kwargs)
        return bot_result_dict

    gate_mock = AsyncMock()
    gate_mock.is_submission_allowed = AsyncMock(return_value=True)
    gate_mock.get_state = AsyncMock(return_value=MagicMock(value="otp_free"))

    browser_session_ctx = MagicMock()
    browser_session_ctx.__aenter__ = AsyncMock(return_value=("sess-1", MagicMock()))
    browser_session_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "app.services.scheduled_waybill_executor.utcms_submission_gate.is_submission_allowed",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "app.services.scheduled_waybill_executor.managed_browser_session",
            return_value=browser_session_ctx,
        ),
        patch(
            "app.services.scheduled_waybill_executor.browser_manager.new_page",
            AsyncMock(return_value=MagicMock()),
        ),
        patch(
            "app.services.scheduled_waybill_executor.decrypt_driver_password",
            return_value="pw",
        ),
        patch(
            "app.services.scheduled_waybill_executor.get_proxy_rotator",
            return_value=MagicMock(get_next=AsyncMock(return_value=None)),
        ),
        patch(
            "app.services.scheduled_waybill_executor.WaybillAutomationBot"
        ) as bot_cls,
    ):
        bot_instance = MagicMock()
        bot_instance.execute_waybill_job = AsyncMock(side_effect=_fake_execute)
        bot_cls.return_value = bot_instance

        result = await _execute_single_job(
            client, driver, job, session, attempt=1, driver_password="pw"
        )

    return result, job, bot_calls


@pytest.mark.asyncio
async def test_tracking_received_persisted_without_reconciliation(async_db):
    ack = build_tracking_received_result("UTC-123")
    result, job, calls = await _run_with_mocks(async_db, _bot_result("success", ack))

    assert job.status == TaskStatus.UNKNOWN.value
    assert job.result_json["tracking_code"] == "UTC-123"
    assert job.result_json["confirmation_status"] == "tracking_received"
    assert job.result_json["operator_acknowledged"] is True
    assert job.mutation_status == "dispatched"
    assert job.next_retry_at is None
    assert job.last_error is None
    assert result["operator_acknowledged"] is True
    assert result.get("needs_reconciliation") is not True
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_missing_code_schedules_history_only_reconciliation(async_db):
    result, job, calls = await _run_with_mocks(
        async_db,
        {
            "status": "success",
            "result": {"document_id": "214000001"},
            "error": None,
            "error_category": None,
            "steps": [],
        },
    )

    assert job.status == TaskStatus.UNKNOWN.value
    assert job.result_json["confirmation_status"] == "tracking_missing_history_required"
    assert job.result_json["reconciliation_mode"] == "history_only"
    assert job.result_json["requires_reconciliation"] is True
    assert job.result_json["requires_resubmission"] is False
    assert job.next_retry_at is not None
    # Read-only History reconciliation is bounded (+15s), never a resubmission.
    assert job.next_retry_at - datetime.now(UTC).replace(tzinfo=None) <= timedelta(seconds=60)
    assert len(calls) == 1  # no recursive execution


@pytest.mark.asyncio
async def test_unknown_bot_result_never_retries(async_db):
    result, job, calls = await _run_with_mocks(
        async_db,
        {
            "status": "unknown",
            "result": None,
            "error": "Submit dispatched but post-dispatch exception",
            "error_category": "submission_unconfirmed",
            "mutation_status": "ambiguous",
            "steps": [],
        },
    )

    assert len(calls) == 1  # never a recursive retry
    assert job.status == TaskStatus.UNKNOWN.value
    assert job.result_json["requires_reconciliation"] is True
    assert job.result_json["reconciliation_mode"] == "history_only"
    assert job.result_json["requires_resubmission"] is False
    assert job.next_retry_at is not None


@pytest.mark.asyncio
async def test_executor_ack_matches_worker_contract(async_db):
    """Parity: executor-persisted ack equals the shared contract output."""
    ack = build_tracking_received_result("UTC-123")
    result, job, _ = await _run_with_mocks(async_db, _bot_result("success", ack))

    persisted = job.result_json
    assert persisted["tracking_code"] == ack["tracking_code"]
    assert persisted["confirmation_status"] == ack["confirmation_status"]
    assert persisted["operator_acknowledged"] == ack["operator_acknowledged"]
    assert persisted["requires_reconciliation"] == ack["requires_reconciliation"]
    assert persisted["requires_resubmission"] == ack["requires_resubmission"]
