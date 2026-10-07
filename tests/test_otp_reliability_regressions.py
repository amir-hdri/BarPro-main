"""OTP delivery/issuance regressions, using real isolated Redis command semantics."""

import asyncio
import json
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.automation import otp_keys
from app.models_multitenant import WaybillJob
from app.services import otp_wakeup_consumer as consumer
from app.services.waybill_job_service import WaybillJobService
from tests.test_otp_delivery_contract import delivery_api as delivery_api


def pending_job(status="unknown", tracking=None):
    result = {"document_id": "901", "otp_required": True}
    if tracking:
        result["tracking_code"] = tracking
    return WaybillJob(
        id=901,
        job_id="otp-regression",
        client_id=901,
        driver_id=901,
        status=status,
        worker_id="worker_2@test",
        result_json=result,
        payload_json={"vehicle": {"driver_mobile": "09120000001"}},
        created_at=datetime.now(UTC).replace(tzinfo=None),
        updated_at=datetime.now(UTC).replace(tzinfo=None),
    )


def db_for(job):
    db = MagicMock()
    db.exec = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=job)))
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    return db


async def test_expired_owner_cannot_release_successor(delivery_api):
    _, redis = delivery_api
    first = await otp_keys.reserve_otp_issue_lease(redis, "lease")
    assert isinstance(first, str) and first
    await redis.pexpire(otp_keys.otp_issue_lock_key("lease"), 1)
    await asyncio.sleep(0.02)
    second = await otp_keys.reserve_otp_issue_lease(redis, "lease")
    assert second and second != first
    await otp_keys.release_otp_issue_lease(redis, "lease", first)
    assert await redis.get(otp_keys.otp_issue_lock_key("lease")) == second
    assert not await otp_keys.reserve_otp_issue_lease(redis, "lease")


async def test_stream_backlog_is_dispatched(delivery_api, monkeypatch):
    _, redis = delivery_api
    await redis.xadd(
        consumer.OTP_STREAM_KEY,
        {
            "payload": json.dumps(
                {"phone": "09120000001", "code": "12345", "received_at": time.time(), "expires_at": time.time() + 60}
            )
        },
    )
    resolve = AsyncMock(return_value={"success": True, "terminal": True})
    monkeypatch.setattr(consumer, "resolve_and_complete_pending_job_for_otp", resolve)
    assert await consumer.process_otp_stream_events() == 1
    resolve.assert_awaited_once()


async def test_stream_retryable_failure_is_not_acknowledged(delivery_api, monkeypatch):
    _, redis = delivery_api
    await redis.xgroup_create(consumer.OTP_STREAM_KEY, consumer.OTP_STREAM_GROUP, id="0", mkstream=True)
    await redis.xadd(
        consumer.OTP_STREAM_KEY,
        {
            "payload": json.dumps(
                {"phone": "09120000001", "code": "12345", "received_at": time.time(), "expires_at": time.time() + 60}
            )
        },
    )
    monkeypatch.setattr(
        consumer,
        "resolve_and_complete_pending_job_for_otp",
        AsyncMock(return_value={"success": False, "retryable": True}),
    )
    await consumer.process_otp_stream_events()
    assert (await redis.xpending(consumer.OTP_STREAM_KEY, consumer.OTP_STREAM_GROUP))["pending"] == 1


async def test_pending_stream_event_is_reclaimed(delivery_api, monkeypatch):
    _, redis = delivery_api
    await redis.xgroup_create(consumer.OTP_STREAM_KEY, consumer.OTP_STREAM_GROUP, id="0", mkstream=True)
    await redis.xadd(
        consumer.OTP_STREAM_KEY,
        {
            "payload": json.dumps(
                {"phone": "09120000001", "code": "12345", "received_at": time.time(), "expires_at": time.time() + 60}
            )
        },
    )
    await redis.xreadgroup(consumer.OTP_STREAM_GROUP, "crashed", {consumer.OTP_STREAM_KEY: ">"}, count=1)
    monkeypatch.setattr(consumer, "OTP_STREAM_CLAIM_IDLE_MS", 0, raising=False)
    resolve = AsyncMock(return_value={"success": True, "terminal": True})
    monkeypatch.setattr(consumer, "resolve_and_complete_pending_job_for_otp", resolve)
    assert await consumer.process_otp_stream_events() == 1
    resolve.assert_awaited_once()


async def test_expired_stream_event_is_discarded(delivery_api, monkeypatch):
    _, redis = delivery_api
    await redis.xgroup_create(consumer.OTP_STREAM_KEY, consumer.OTP_STREAM_GROUP, id="0", mkstream=True)
    await redis.xadd(
        consumer.OTP_STREAM_KEY,
        {
            "payload": json.dumps(
                {
                    "phone": "09120000001",
                    "code": "12345",
                    "received_at": time.time() - 301,
                    "expires_at": time.time() - 1,
                }
            )
        },
    )
    resolve = AsyncMock()
    monkeypatch.setattr(consumer, "resolve_and_complete_pending_job_for_otp", resolve)
    await consumer.process_otp_stream_events()
    resolve.assert_not_awaited()
    assert (await redis.xpending(consumer.OTP_STREAM_KEY, consumer.OTP_STREAM_GROUP))["pending"] == 0


async def test_tracking_received_prevents_any_otp_mutation(monkeypatch):
    job = pending_job(tracking="901001")
    db = db_for(job)
    issue = AsyncMock()
    monkeypatch.setattr("app.automation.utcms_mobile_client.UtcmsMobileClient.issue_document_by_otp", issue)
    response = await WaybillJobService.submit_otp({"role": "master_admin"}, job.job_id, db, "12345")
    assert response.result_json["tracking_code"] == "901001"
    issue.assert_not_awaited()


@pytest.mark.parametrize("state", ["pending", "cancelled", "dead_letter", "failed"])
async def test_ineligible_status_rejected_before_network(state, monkeypatch):
    job = pending_job(state)
    issue = AsyncMock()
    monkeypatch.setattr("app.automation.utcms_mobile_client.UtcmsMobileClient.issue_document_by_otp", issue)
    with pytest.raises(HTTPException) as failure:
        await WaybillJobService.submit_otp({"role": "master_admin"}, job.job_id, db_for(job), "12345")
    assert failure.value.status_code == 409
    issue.assert_not_awaited()
