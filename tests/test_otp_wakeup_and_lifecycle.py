"""Rigorous tests for OTP event-driven wakeup, late SMS resolution, lease locking, and lifecycle cleanup."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.routes import otp_forwarder
from app.automation.otp_keys import (
    OTP_ACTIVE_PENDING_JOBS_SET,
    consume_scoped_otp,
    otp_job_key,
    otp_pending_phone_key,
    otp_phone_key,
    release_otp_issue_lease,
    reserve_otp_issue_lease,
)
from app.automation.waybill_enhanced import fetch_scoped_otp
from app.core.config import utcms_config
from app.models_multitenant import TaskStatus, WaybillJob
from app.services.otp_wakeup_consumer import (
    process_otp_stream_events,
    resolve_and_complete_pending_job_for_otp,
    resolve_single_flight_pending_phone,
)


class MemoryRedis:
    """Async Redis in-memory double supporting strings, sets, pub/sub, and streams."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}
        self.streams: dict[str, list[tuple[str, dict[str, str]]]] = {}
        self.published: list[tuple[str, str]] = []
        self.stream_seq = 0

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ex=None, **kwargs):
        if kwargs.get("nx") and key in self.store:
            return False
        self.store[key] = value
        return True

    async def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                count += 1
            if k in self.sets:
                del self.sets[k]
                count += 1
        return count

    async def sadd(self, key: str, *members: str) -> int:
        if key not in self.sets:
            self.sets[key] = set()
        initial_len = len(self.sets[key])
        for m in members:
            self.sets[key].add(str(m))
        return len(self.sets[key]) - initial_len

    async def srem(self, key: str, *members: str) -> int:
        if key not in self.sets:
            return 0
        initial_len = len(self.sets[key])
        for m in members:
            self.sets[key].discard(str(m))
        return initial_len - len(self.sets[key])

    async def smembers(self, key: str) -> set[str]:
        return set(self.sets.get(key, set()))

    async def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1

    async def eval(self, script: str, numkeys: int, *args):
        # Emulate STORE_FORWARDED_OTP
        phone_key = args[0]
        seen_key = args[1]
        payload_json = args[2]
        _ttl = args[3]
        received_at = float(args[4])
        _seen_ttl = args[5]
        channel = args[6]

        if seen_key in self.store:
            return 0  # duplicate

        prev = self.store.get(phone_key)
        if prev:
            try:
                prev_data = json.loads(prev)
                if float(prev_data.get("received_at", 0)) > received_at:
                    return -1  # older than existing
            except Exception:
                pass

        self.store[phone_key] = payload_json
        self.store[seen_key] = "1"
        self.published.append((channel, payload_json))
        # Stream XADD
        self.stream_seq += 1
        msg_id = f"{int(time.time() * 1000)}-{self.stream_seq}"
        if "rpa:otp:stream" not in self.streams:
            self.streams["rpa:otp:stream"] = []
        self.streams["rpa:otp:stream"].append(
            (msg_id, {"payload": payload_json, "phone": phone_key, "message_id": seen_key})
        )
        return 1

    async def xreadgroup(self, group: str, consumer: str, streams: dict, count=10, block=None):
        res = []
        for stream_name, _ in streams.items():
            msgs = self.streams.get(stream_name, [])
            if msgs:
                batch = msgs[:count]
                self.streams[stream_name] = msgs[count:]
                res.append((stream_name, batch))
        return res

    async def xgroup_create(self, stream: str, group: str, id="$", mkstream=False):
        return True

    async def xack(self, stream: str, group: str, *ids):
        return len(ids)


@pytest.mark.asyncio
async def test_lease_locking_prevents_concurrent_issue():
    """Verify single-flight lease locking prevents double submission."""
    fake_redis = MemoryRedis()
    job_id = "test-lease-job-1"

    # Acquire lease first time -> True
    acquired = await reserve_otp_issue_lease(fake_redis, job_id, ttl_seconds=30)
    assert acquired is True

    # Try acquiring second time while held -> False
    second_try = await reserve_otp_issue_lease(fake_redis, job_id, ttl_seconds=30)
    assert second_try is False

    # Release lease
    await release_otp_issue_lease(fake_redis, job_id)

    # Now can acquire again
    reacquired = await reserve_otp_issue_lease(fake_redis, job_id, ttl_seconds=30)
    assert reacquired is True


@pytest.mark.asyncio
async def test_consume_scoped_otp_cleans_all_keys():
    """Verify consume_scoped_otp cleans up job keys, phone keys, and pending pointers."""
    fake_redis = MemoryRedis()
    job_id = "job-cleanup-1"
    driver_phone = "09121112233"

    # Set up keys
    fake_redis.store[otp_job_key(job_id)] = json.dumps({"code": "12345"})
    fake_redis.store[otp_phone_key(driver_phone)] = json.dumps({"code": "12345"})
    fake_redis.store[f"rpa:job:pending_doc:{job_id}"] = json.dumps({"doc_id": "999"})
    fake_redis.store[otp_pending_phone_key(driver_phone)] = job_id
    await fake_redis.sadd(OTP_ACTIVE_PENDING_JOBS_SET, job_id)

    # Consume
    deleted = await consume_scoped_otp(fake_redis, job_id=job_id, driver_phone=driver_phone)
    assert deleted >= 3

    # Verify keys deleted
    assert await fake_redis.get(otp_job_key(job_id)) is None
    assert await fake_redis.get(otp_phone_key(driver_phone)) is None
    assert await fake_redis.get(f"rpa:job:pending_doc:{job_id}") is None
    assert await fake_redis.get(otp_pending_phone_key(driver_phone)) is None
    active = await fake_redis.smembers(OTP_ACTIVE_PENDING_JOBS_SET)
    assert job_id not in active


@pytest.mark.asyncio
async def test_fetch_scoped_otp_handles_device_clock_skew():
    """Verify that an OTP with device clock skew is accepted using ingested_at."""
    fake_redis = MemoryRedis()
    job_id = "job-skew-1"
    now = time.time()

    # Device clock was 120 seconds in the past!
    device_past_time = now - 120.0
    payload = {
        "code": "84729",
        "sender": "20007777",
        "phone": "09129998877",
        "received_at": device_past_time,
        "ingested_at": now,  # Server received it NOW
        "expires_at": now + 300,
    }
    fake_redis.store[otp_job_key(job_id)] = json.dumps(payload)

    # Worker started waiting 5 seconds ago
    wait_start = now - 5.0
    found = await fetch_scoped_otp(fake_redis, job_id=job_id, driver_phone="09129998877", wait_start=wait_start)

    assert found is not None
    code, key, entry = found
    assert code == "84729"
    assert entry["ingested_at"] == now


@pytest.mark.asyncio
async def test_single_flight_phone_attribution_from_redis():
    """Verify single-flight fallback derives driver phone when forwarder sends no phone."""
    fake_redis = MemoryRedis()
    job_id = "job-single-flight-1"
    driver_phone = "09127778899"

    # Exactly one job awaiting OTP
    await fake_redis.sadd(OTP_ACTIVE_PENDING_JOBS_SET, job_id)
    fake_redis.store[f"rpa:job:pending_doc:{job_id}"] = json.dumps(
        {
            "job_id": job_id,
            "document_id": "228074398",
            "driver_phone": driver_phone,
        }
    )

    with patch("app.services.otp_wakeup_consumer.redis_manager.get", AsyncMock(return_value=fake_redis)):
        resolved = await resolve_single_flight_pending_phone()
        assert resolved == driver_phone


@pytest.mark.asyncio
async def test_late_sms_125_second_auto_completion():
    """THE 125-SECOND SCENARIO: Worker timed out at 120s, SMS arrives at 125s -> Auto completes!"""
    fake_redis = MemoryRedis()
    job_id = "job-late-sms-125"
    driver_phone = "09125554433"
    document_id = "228074398"
    otp_code = "654321"

    # 1. Job was left in UNKNOWN by Celery worker timeout
    mock_job = WaybillJob(
        id=1,
        job_id=job_id,
        client_id=1,
        driver_id=1,
        driver_national_code="0012345678",
        status=TaskStatus.UNKNOWN.value,
        error_category="otp_required",
        result_json={"document_id": document_id},
        payload_json={"vehicle": {"driver_mobile": driver_phone}},
        last_error=f"سند با شناسه {document_id} ایجاد شد",
        created_at=datetime.now(UTC).replace(tzinfo=None),
        updated_at=datetime.now(UTC).replace(tzinfo=None),
    )

    # 2. Redis has the pending doc token session
    session_data = {
        "doc_id": document_id,
        "token": "cached_utcms_token_xyz",
        "username": "driver_user",
        "job_id": job_id,
        "driver_phone": driver_phone,
    }
    fake_redis.store[f"rpa:job:pending_doc:{job_id}"] = json.dumps(session_data)
    fake_redis.store[otp_pending_phone_key(driver_phone)] = job_id
    await fake_redis.sadd(OTP_ACTIVE_PENDING_JOBS_SET, job_id)

    # Mock DB session
    mock_db = MagicMock()
    mock_db.exec = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=mock_job)))
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.add = MagicMock()

    # Mock UtcmsMobileClient.issue_document_by_otp
    with (
        patch("app.services.otp_wakeup_consumer.redis_manager.get", AsyncMock(return_value=fake_redis)),
        patch("app.core.redis_client.redis_manager.get", AsyncMock(return_value=fake_redis)),
        patch("app.automation.worker_proxy.get_worker_proxy_url", return_value="http://127.0.0.1:3128"),
        patch("app.services.otp_wakeup_consumer.async_session_factory", return_value=mock_db),
        patch("app.automation.utcms_mobile_client.UtcmsMobileClient.issue_document_by_otp") as mock_issue,
        patch("app.automation.utcms_mobile_client.UtcmsMobileClient.extract_tracking_code", return_value="1359998888"),
    ):
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)
        mock_issue.return_value = {"meta": {"message": "Success"}, "obj": {"docNo": "1359998888"}}

        # At T=125s, resolve_and_complete_pending_job_for_otp is called
        result = await resolve_and_complete_pending_job_for_otp(phone=driver_phone, code=otp_code)

        assert result is not None
        assert result["success"] is True
        assert result["job_id"] == job_id
        assert result["tracking_code"] == "1359998888"

        # Verify IssueDocumentByOtp was called with document_id and otp_code
        mock_issue.assert_called_once_with(document_id, otp_code, allow_live_submit=True)

        # Verify keys were cleaned up
        assert await fake_redis.get(otp_phone_key(driver_phone)) is None
        assert await fake_redis.get(f"rpa:job:pending_doc:{job_id}") is None
        active = await fake_redis.smembers(OTP_ACTIVE_PENDING_JOBS_SET)
        assert job_id not in active


@pytest.mark.asyncio
async def test_redis_stream_event_processing():
    """Verify durable Redis Stream messages are consumed and processed."""
    fake_redis = MemoryRedis()
    driver_phone = "09123332211"
    otp_code = "778899"

    # Seed stream with an event
    payload = {
        "code": otp_code,
        "phone": driver_phone,
        "sender": "20007777",
        "received_at": time.time(),
    }
    fake_redis.streams["rpa:otp:stream"] = [
        ("1728150000000-1", {"payload": json.dumps(payload), "phone": driver_phone})
    ]

    with (
        patch("app.services.otp_wakeup_consumer.redis_manager.get", AsyncMock(return_value=fake_redis)),
        patch("app.services.otp_wakeup_consumer.resolve_and_complete_pending_job_for_otp") as mock_resolve,
    ):
        mock_resolve.return_value = {"success": True}
        processed = await process_otp_stream_events(batch_size=5)

        assert processed == 1
        mock_resolve.assert_called_once_with(phone=driver_phone, code=otp_code)


@pytest.mark.asyncio
async def test_ambiguous_otp_attribution_rejected_when_multiple_jobs_pending():
    """When multiple jobs are pending without a specified phone, reject with AMBIGUOUS_OTP."""
    fake_redis = MemoryRedis()
    await fake_redis.sadd(OTP_ACTIVE_PENDING_JOBS_SET, "job_1", "job_2")

    # 1. resolve_single_flight_pending_phone returns "AMBIGUOUS"
    with patch("app.services.otp_wakeup_consumer.redis_manager.get", AsyncMock(return_value=fake_redis)):
        resolved = await resolve_single_flight_pending_phone()
        assert resolved == "AMBIGUOUS"

    # 2. HTTP Webhook without driver_phone returns 422 AMBIGUOUS_OTP
    app = FastAPI()
    app.include_router(otp_forwarder.router)
    secret = "test-secret-at-least-32-bytes-long"

    with (
        patch("app.api.routes.otp_forwarder.redis_manager.get", AsyncMock(return_value=fake_redis)),
        patch("app.services.otp_wakeup_consumer.redis_manager.get", AsyncMock(return_value=fake_redis)),
        patch.object(utcms_config, "OTP_WEBHOOK_SECRET", secret),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/otp/sms-forwarder",
                json={"text": "کد تایید صدور بارنامه: 54321", "sender": "20007777"},
                headers={"X-OTP-Webhook-Token": secret},
            )
            assert resp.status_code == 422
            assert "AMBIGUOUS_OTP" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_full_e2e_http_webhook_to_job_completion():
    """Full E2E test: HTTP webhook -> Redis streams/intake -> auto-completion -> SUCCESS in DB."""
    fake_redis = MemoryRedis()
    job_id = "job-e2e-real-flow-999"
    document_id = "22998877"
    driver_phone = "09121113355"
    otp_code = "65432"
    secret = "test-secret-at-least-32-bytes-long"

    mock_job = WaybillJob(
        id=999,
        job_id=job_id,
        client_id=1,
        driver_national_code="0012345678",
        status=TaskStatus.UNKNOWN.value,
        error_category="otp_required",
        result_json={"document_id": document_id},
        payload_json={"vehicle": {"driver_mobile": driver_phone}},
        last_error=f"سند با شناسه {document_id} ایجاد شد",
        created_at=datetime.now(UTC).replace(tzinfo=None),
        updated_at=datetime.now(UTC).replace(tzinfo=None),
    )

    # Pending session in Redis
    session_data = {
        "doc_id": document_id,
        "token": "cached_utcms_token_xyz",
        "username": "driver_user",
        "job_id": job_id,
        "driver_phone": driver_phone,
    }
    fake_redis.store[f"rpa:job:pending_doc:{job_id}"] = json.dumps(session_data)
    fake_redis.store[otp_pending_phone_key(driver_phone)] = job_id
    await fake_redis.sadd(OTP_ACTIVE_PENDING_JOBS_SET, job_id)

    mock_db = MagicMock()
    mock_db.exec = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=mock_job)))
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=None)

    app = FastAPI()
    app.include_router(otp_forwarder.router)

    with (
        patch("app.api.routes.otp_forwarder.redis_manager.get", AsyncMock(return_value=fake_redis)),
        patch("app.services.otp_delivery.redis_manager.get", AsyncMock(return_value=fake_redis)),
        patch("app.services.otp_wakeup_consumer.redis_manager.get", AsyncMock(return_value=fake_redis)),
        patch("app.core.redis_client.redis_manager.get", AsyncMock(return_value=fake_redis)),
        patch("app.automation.worker_proxy.get_worker_proxy_url", return_value="http://127.0.0.1:3128"),
        patch("app.services.otp_wakeup_consumer.async_session_factory", return_value=mock_db),
        patch.object(utcms_config, "OTP_WEBHOOK_SECRET", secret),
        patch("app.automation.utcms_mobile_client.UtcmsMobileClient.issue_document_by_otp") as mock_issue,
        patch("app.automation.utcms_mobile_client.UtcmsMobileClient.extract_tracking_code", return_value="1359998888"),
    ):
        mock_issue.return_value = {"meta": {"message": "Success"}, "obj": {"docNo": "1359998888"}}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/otp/sms-forwarder",
                json={
                    "phone": driver_phone,
                    "text": f"کد تایید صدور بارنامه شما: {otp_code}",
                    "sender": "20007777",
                },
                headers={"X-OTP-Webhook-Token": secret},
            )
            assert resp.status_code == 200
            assert resp.json()["success"] is True

            # Yield control to let background task run
            await asyncio.sleep(0.05)

            # Verify completion
            assert mock_job.status == TaskStatus.SUCCESS.value
            assert mock_job.result_json["tracking_code"] == "1359998888"
            assert mock_job.mutation_status == "confirmed"
            mock_issue.assert_called_once_with(document_id, otp_code, allow_live_submit=True)

            # Verify cleanup
            assert await fake_redis.get(otp_phone_key(driver_phone)) is None
            assert await fake_redis.get(f"rpa:job:pending_doc:{job_id}") is None
            active = await fake_redis.smembers(OTP_ACTIVE_PENDING_JOBS_SET)
            assert job_id not in active


@pytest.mark.asyncio
async def test_path_based_driver_phone_webhook():
    """Verify Android forwarder URL with path-based phone /sms-forwarder/{phone} identifies driver."""
    fake_redis = MemoryRedis()
    driver_phone = "09129998877"
    app = FastAPI()
    app.include_router(otp_forwarder.router)
    secret = "test-secret-at-least-32-bytes-long"

    with (
        patch("app.api.routes.otp_forwarder.redis_manager.get", AsyncMock(return_value=fake_redis)),
        patch("app.services.otp_delivery.redis_manager.get", AsyncMock(return_value=fake_redis)),
        patch.object(utcms_config, "OTP_WEBHOOK_SECRET", secret),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/otp/sms-forwarder/{driver_phone}",
                json={"text": "کد ورود: 55443", "sender": "20007777"},
                headers={"X-OTP-Webhook-Token": secret},
            )
            assert resp.status_code == 200
            stored_raw = await fake_redis.get(otp_phone_key(driver_phone))
            assert stored_raw is not None
            assert json.loads(stored_raw)["code"] == "55443"
            assert json.loads(stored_raw)["phone"] == driver_phone


@pytest.mark.asyncio
async def test_query_param_driver_phone_webhook():
    """Verify query param ?driver_phone=... identifies driver even when JSON body omits it."""
    fake_redis = MemoryRedis()
    driver_phone = "09128887766"
    app = FastAPI()
    app.include_router(otp_forwarder.router)
    secret = "test-secret-at-least-32-bytes-long"

    with (
        patch("app.api.routes.otp_forwarder.redis_manager.get", AsyncMock(return_value=fake_redis)),
        patch("app.services.otp_delivery.redis_manager.get", AsyncMock(return_value=fake_redis)),
        patch.object(utcms_config, "OTP_WEBHOOK_SECRET", secret),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/otp/sms-forwarder?driver_phone={driver_phone}",
                json={"text": "رمز یکبار مصرف: 88776", "sender": "20007777"},
                headers={"X-OTP-Webhook-Token": secret},
            )
            assert resp.status_code == 200
            stored_raw = await fake_redis.get(otp_phone_key(driver_phone))
            assert stored_raw is not None
            assert json.loads(stored_raw)["code"] == "88776"
            assert json.loads(stored_raw)["phone"] == driver_phone


@pytest.mark.asyncio
async def test_header_driver_phone_webhook():
    """Verify header X-Driver-Phone identifies driver when body omits it."""
    fake_redis = MemoryRedis()
    driver_phone = "09127776655"
    app = FastAPI()
    app.include_router(otp_forwarder.router)
    secret = "test-secret-at-least-32-bytes-long"

    with (
        patch("app.api.routes.otp_forwarder.redis_manager.get", AsyncMock(return_value=fake_redis)),
        patch("app.services.otp_delivery.redis_manager.get", AsyncMock(return_value=fake_redis)),
        patch.object(utcms_config, "OTP_WEBHOOK_SECRET", secret),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/otp/sms-forwarder",
                json={"text": "کد تایید: 11223", "sender": "20007777"},
                headers={"X-OTP-Webhook-Token": secret, "X-Driver-Phone": driver_phone},
            )
            assert resp.status_code == 200
            stored_raw = await fake_redis.get(otp_phone_key(driver_phone))
            assert stored_raw is not None
            assert json.loads(stored_raw)["code"] == "11223"


def test_sweep_otp_stream_celery_task():
    """Verify the Celery periodic task barpro.otp.sweep_stream runs process_otp_stream_events."""
    from app.workers.tasks import sweep_otp_stream

    with patch("app.services.otp_wakeup_consumer.process_otp_stream_events", AsyncMock(return_value=2)) as mock_proc:
        res = sweep_otp_stream()
        assert res == 2
        mock_proc.assert_called_once_with(batch_size=10)


@pytest.mark.asyncio
async def test_submit_otp_uses_worker_proxy():
    """Verify that submit_otp creates UtcmsMobileClient using proxy_url."""
    from app.services.waybill_job_service import WaybillJobService

    fake_redis = MemoryRedis()
    job_id = "job-proxy-check-1"
    session_data = {
        "doc_id": "112233",
        "token": "test-token",
        "username": "driver1",
        "job_id": job_id,
        "driver_phone": "09121234567",
    }
    fake_redis.store[f"rpa:job:pending_doc:{job_id}"] = json.dumps(session_data)

    mock_job = WaybillJob(
        id=1,
        job_id=job_id,
        client_id=1,
        driver_national_code="0012345678",
        status=TaskStatus.UNKNOWN.value,
        result_json={"document_id": "112233"},
        payload_json={"vehicle": {"driver_mobile": "09121234567"}},
        created_at=datetime.now(UTC).replace(tzinfo=None),
        updated_at=datetime.now(UTC).replace(tzinfo=None),
    )

    mock_db = MagicMock()
    mock_db.exec = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=mock_job)))
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.add = MagicMock()

    captured_kwargs = {}

    def mock_init_client(*args, **kwargs):
        captured_kwargs.update(kwargs)
        mock_inst = MagicMock()
        mock_inst.token = kwargs.get("token")
        mock_inst.issue_document_by_otp = AsyncMock(return_value={"obj": {"docNo": "1351112222"}})
        mock_inst.extract_tracking_code = MagicMock(return_value="1351112222")
        return mock_inst

    with (
        patch("app.core.redis_client.redis_manager.get", AsyncMock(return_value=fake_redis)),
        patch("app.automation.worker_proxy.get_worker_proxy_url", return_value="http://squid-proxy:3128"),
        patch("app.automation.utcms_mobile_client.UtcmsMobileClient", side_effect=mock_init_client),
    ):
        res = await WaybillJobService.submit_otp(
            user_context={"role": "master_admin"},
            job_id=job_id,
            session=mock_db,
            otp_code="12345",
        )
        assert res.status == TaskStatus.SUCCESS.value
        assert captured_kwargs.get("proxy_url") == "http://squid-proxy:3128"
        assert captured_kwargs.get("token") == "test-token"
