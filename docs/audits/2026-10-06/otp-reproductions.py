"""Audit reproductions: synthetic jobs, mocked UTCMS, private Redis Unix socket.

Run from repo root: .venv/bin/python docs/audits/2026-10-06/otp-reproductions.py
Assertions describe the observed defects, not desired production behavior.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
os.environ.update({
    "ENVIRONMENT": "test", "DATABASE_URL": "sqlite+aiosqlite:////tmp/barpro-otp-audit-unused.db",
    "REDIS_URL": "redis://127.0.0.1:1/0", "ALLOW_LIVE_SUBMIT": "false",
    "JWT_SECRET": "audit-synthetic-secret-key-32bytes-padding",
})

import redis.asyncio as aioredis
from fastapi import HTTPException
from app.automation.otp_keys import (
    OTP_ACTIVE_PENDING_JOBS_SET, otp_issue_lock_key,
    release_otp_issue_lease, reserve_otp_issue_lease,
)
from app.models_multitenant import WaybillJob
from app.services import otp_wakeup_consumer as consumer
from app.services.waybill_job_service import WaybillJobService

RESULTS = []


def record(case, **facts):
    result = {"case": case, **facts}
    RESULTS.append(result)
    print(json.dumps(result, ensure_ascii=False), flush=True)


def job(status="unknown"):
    return WaybillJob(
        id=991, job_id="audit-otp-job", client_id=991, driver_id=991,
        driver_national_code="0000000000", status=status,
        result_json={"document_id": "991"},
        payload_json={"vehicle": {"driver_mobile": "09120000000"}},
        created_at=datetime.now(UTC).replace(tzinfo=None),
        updated_at=datetime.now(UTC).replace(tzinfo=None),
    )


def database(instance):
    session = MagicMock()
    session.exec = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=instance)))
    session.get = AsyncMock(return_value=SimpleNamespace(
        id=991, phone="09120000000", utcms_username="audit-driver",
        driver_national_code="0000000000", utcms_password_encrypted="synthetic-encrypted",
    ))
    session.refresh = AsyncMock()
    session.commit = AsyncMock()
    return session


def mobile():
    client = MagicMock()
    client.token = "synthetic-token"
    client.issue_document_by_otp = AsyncMock(return_value={"obj": {"docNo": "99100001"}})
    client.extract_tracking_code = MagicMock(return_value="99100001")
    return client


def submit_patches(redis, client, stack, *, mock_proxy=True):
    stack.enter_context(patch("app.core.redis_client.redis_manager.get", AsyncMock(return_value=redis)))
    if mock_proxy:
        stack.enter_context(patch("app.automation.worker_proxy.get_worker_proxy_url", return_value="http://audit.invalid:3128"))
    stack.enter_context(patch("app.automation.utcms_mobile_client.UtcmsMobileClient", return_value=client))
    stack.enter_context(patch("app.auth_multitenant.decrypt_driver_password", return_value="synthetic-password"))
    stack.enter_context(patch("app.automation.gps_shipping_manager.get_or_login_client", AsyncMock(return_value=client)))
    stack.enter_context(patch("app.automation.gps_shipping_manager.init_shipping", AsyncMock(return_value=SimpleNamespace(origin_lat=0, origin_lng=0))))


async def submit(session):
    return await WaybillJobService.submit_otp(
        user_context={"role": "master_admin"}, job_id="audit-otp-job", session=session, otp_code="00000",
    )


async def stream_cases(redis):
    key, group = consumer.OTP_STREAM_KEY, consumer.OTP_STREAM_GROUP
    payload = json.dumps({"phone": "09120000000", "code": "00000", "job_id": "audit-otp-job"})
    await redis.flushdb()
    await redis.xadd(key, {"payload": payload})
    callback = AsyncMock(return_value={"success": True})
    with patch.object(consumer.redis_manager, "get", AsyncMock(return_value=redis)), patch.object(consumer, "resolve_and_complete_pending_job_for_otp", callback):
        count = await consumer.process_otp_stream_events()
    assert count == 0 and callback.await_count == 0 and await redis.xlen(key) == 1
    record("group_created_at_tail_skips_backlog", processed=count, resolver_calls=callback.await_count, stream_length=1)

    await redis.flushdb()
    await redis.xgroup_create(key, group, id="0", mkstream=True)
    await redis.xadd(key, {"payload": payload})
    instance = job()
    db = database(instance)
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=db)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    transient = AsyncMock(side_effect=HTTPException(503, "synthetic proxy unavailable"))
    with patch.object(consumer.redis_manager, "get", AsyncMock(return_value=redis)), patch.object(consumer, "async_session_factory", factory), patch.object(WaybillJobService, "submit_otp", transient):
        count = await consumer.process_otp_stream_events()
        pending = (await redis.xpending(key, group))["pending"]
        again = await consumer.process_otp_stream_events()
    assert count == 1 and pending == 0 and again == 0 and transient.await_count == 1
    record("failed_completion_is_acknowledged", processed=count, pending=pending, next_sweep_processed=again, mutation_attempts=transient.await_count)

    await redis.flushdb()
    await redis.xgroup_create(key, group, id="0", mkstream=True)
    await redis.xadd(key, {"payload": payload})
    await redis.xreadgroup(group, "consumer_1", {key: ">"}, count=1)
    callback = AsyncMock(return_value={"success": True})
    with patch.object(consumer.redis_manager, "get", AsyncMock(return_value=redis)), patch.object(consumer, "resolve_and_complete_pending_job_for_otp", callback):
        count = await consumer.process_otp_stream_events()
    pending = (await redis.xpending(key, group))["pending"]
    assert count == 0 and pending == 1 and callback.await_count == 0
    record("pending_after_crash_not_recovered", processed=count, pending=pending, resolver_calls=callback.await_count)

    await redis.flushdb()
    await redis.xgroup_create(key, group, id="0", mkstream=True)
    old = json.dumps({"phone": "09120000000", "code": "00000", "expires_at": time.time() - 3600, "received_at": time.time() - 3900})
    await redis.xadd(key, {"payload": old})
    callback = AsyncMock(return_value={"success": True})
    with patch.object(consumer.redis_manager, "get", AsyncMock(return_value=redis)), patch.object(consumer, "resolve_and_complete_pending_job_for_otp", callback):
        count = await consumer.process_otp_stream_events()
    assert count == 1 and callback.await_count == 1
    record("expired_stream_code_is_dispatched", processed=count, resolver_calls=callback.await_count, expiry_age_seconds=3600)


async def lease_cases(redis):
    await redis.flushdb()
    acquired_a = await reserve_otp_issue_lease(redis, "audit-lock", ttl_seconds=1)
    await asyncio.sleep(1.1)
    acquired_b = await reserve_otp_issue_lease(redis, "audit-lock", ttl_seconds=30)
    await release_otp_issue_lease(redis, "audit-lock")
    acquired_c = await reserve_otp_issue_lease(redis, "audit-lock", ttl_seconds=30)
    assert acquired_a and acquired_b and acquired_c
    record("expired_owner_deletes_successor_lease", first_owner=acquired_a, second_owner=acquired_b, third_owner_while_second_active=acquired_c)

    client = mobile()
    db = database(job())
    with ExitStack() as stack:
        submit_patches(None, client, stack)
        response = await submit(db)
    assert response.status == "success" and client.issue_document_by_otp.await_count == 1
    record("redis_absent_does_not_stop_mutation", redis_available=False, issue_calls=client.issue_document_by_otp.await_count, status=response.status)

    await redis.flushdb()
    reached_issue, finish_issue = asyncio.Event(), asyncio.Event()
    contender_paused, resume_contender = asyncio.Event(), asyncio.Event()

    class GatedRedis:
        def __getattr__(self, name):
            return getattr(redis, name)

        async def set(self, key, value, **kwargs):
            if asyncio.current_task().get_name() == "audit-contender" and key == "rpa:otp:job:audit-otp-job":
                contender_paused.set()
                await resume_contender.wait()
            return await redis.set(key, value, **kwargs)

    client = mobile()
    issue_calls = []

    async def issue(*args, **kwargs):
        issue_calls.append({"task": asyncio.current_task().get_name(), "document_id": args[0]})
        if len(issue_calls) == 1:
            reached_issue.set()
            await finish_issue.wait()
        return {"obj": {"docNo": "99100001"}}

    client.issue_document_by_otp = AsyncMock(side_effect=issue)
    first_db, second_db = database(job()), database(job())
    with ExitStack() as stack:
        submit_patches(GatedRedis(), client, stack)
        first = asyncio.create_task(submit(first_db), name="audit-first")
        await reached_issue.wait()
        second = asyncio.create_task(submit(second_db), name="audit-contender")
        await contender_paused.wait()
        finish_issue.set()
        first_response = await first
        resume_contender.set()
        second_response = await second
    assert len(issue_calls) == 2 and first_response.status == second_response.status == "success"
    record("stale_prelease_job_allows_repeat_mutation", issue_calls=issue_calls, first_status=first_response.status, second_status=second_response.status)


async def state_cases(redis):
    await redis.flushdb()
    issued = job("unknown")
    issued.result_json = {"document_id": "991", "tracking_code": "99100001", "confirmation_status": "tracking_received"}
    client = mobile()
    db = database(issued)
    with ExitStack() as stack:
        submit_patches(redis, client, stack)
        response = await submit(db)
    assert client.issue_document_by_otp.await_count == 1 and response.status == "success"
    record("persisted_tracking_does_not_prevent_reissue", existing_tracking_code="99100001", initial_status="unknown", issue_calls=client.issue_document_by_otp.await_count, final_status=response.status)

    await redis.flushdb()
    await redis.sadd(OTP_ACTIVE_PENDING_JOBS_SET, "stale-job-a", "stale-job-b")
    with patch.object(consumer.redis_manager, "get", AsyncMock(return_value=redis)):
        result = await consumer.resolve_single_flight_pending_phone()
    remaining = sorted(await redis.smembers(OTP_ACTIVE_PENDING_JOBS_SET))
    assert result == "AMBIGUOUS" and len(remaining) == 2
    record("all_stale_jobs_not_pruned", result=result, stale_members_retained=remaining)

    await redis.flushdb()
    client = mobile()
    db = database(job("pending"))
    error = None
    with ExitStack() as stack:
        submit_patches(redis, client, stack)
        try:
            await submit(db)
        except Exception as exc:
            error = type(exc).__name__ + ": " + str(exc)
    assert client.issue_document_by_otp.await_count == 1 and "StateTransitionError" in error and db.commit.await_count == 0
    record("pending_job_issued_before_state_validation", issue_calls=client.issue_document_by_otp.await_count, error=error, db_commits=db.commit.await_count)


async def affinity_case(redis):
    from app.automation import worker_proxy
    from app.core.config import utcms_config
    await redis.flushdb()
    assigned = job()
    assigned.worker_id = "2"
    await redis.set("rpa:job:pending_doc:audit-otp-job", json.dumps({"token": "synthetic-token", "document_id": "991"}))
    client = mobile()
    db = database(assigned)
    with ExitStack() as stack:
        submit_patches(redis, client, stack, mock_proxy=False)
        constructor = stack.enter_context(patch("app.automation.utcms_mobile_client.UtcmsMobileClient", return_value=client))
        stack.enter_context(patch.dict(os.environ, {"WORKER_ID": "scheduler", "WORKER_IP_INDEX": "", "RPA_PROXIES": "http://192.0.2.10:3128", "WORKER_2_PROXY": "http://192.0.2.20:3128"}))
        stack.enter_context(patch.object(utcms_config, "EGRESS_PROXY_MODE", "worker_first"))
        stack.enter_context(patch.object(worker_proxy, "_resolve_to_ip", side_effect=lambda url: url))
        stack.enter_context(patch.object(worker_proxy.socket, "create_connection", MagicMock()))
        stack.enter_context(patch("app.automation.clean_ip_pool.clean_ip_pool.get_clean_ip_sync", return_value=None))
        worker_proxy.invalidate_worker_proxy_cache()
        await submit(db)
        selected = constructor.call_args.kwargs["proxy_url"]
        worker_proxy.invalidate_worker_proxy_cache()
    assert selected == "http://192.0.2.10:3128"
    record("otp_completion_ignores_assigned_worker_proxy", job_worker="2", process_worker="scheduler", selected_proxy=selected, assigned_worker_proxy="http://192.0.2.20:3128")


async def main():
    with tempfile.TemporaryDirectory(prefix="bp-otp-audit-") as temporary:
        socket = str(Path(temporary) / "redis.sock")
        with open(Path(temporary) / "server.log", "w") as server_log:
            proc = subprocess.Popen([shutil.which("redis-server"), "--port", "0", "--unixsocket", socket, "--save", "", "--appendonly", "no", "--dir", temporary], stdout=server_log, stderr=subprocess.STDOUT)
            redis = None
            try:
                for _ in range(100):
                    if Path(socket).exists():
                        break
                    await asyncio.sleep(0.05)
                redis = aioredis.Redis(unix_socket_path=socket, decode_responses=True)
                await redis.ping()
                await stream_cases(redis)
                await lease_cases(redis)
                await state_cases(redis)
                await affinity_case(redis)
                record("summary", reproduced=len(RESULTS), live_utcms_calls=0, redis_scope="private Unix socket; temporary data")
            finally:
                if redis:
                    await redis.aclose()
                proc.terminate()
                proc.wait(timeout=5)


if __name__ == "__main__":
    asyncio.run(main())
