"""OTP lifecycle boundaries with real Redis/SQLite and a mocked UTCMS transport."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes import otp_forwarder
from app.automation import otp_keys
from app.automation.waybill_enhanced import fetch_scoped_otp
from app.models_multitenant import Client, WaybillJob
from app.services import otp_wakeup_consumer as consumer
from app.services.waybill_job_service import WaybillJobService
from tests.test_mobile_waybill_bot import async_db as async_db
from tests.test_otp_delivery_contract import delivery_api as delivery_api

PHONE = "09120000001"
PROXY = "http://owning-worker-squid:3128"


@pytest.fixture
async def otp_scenario(async_db, delivery_api, monkeypatch):
    session, job, _, driver = async_db
    api, redis = delivery_api
    now = time.time()
    driver.phone = PHONE
    job.status = "unknown"
    job.worker_id = "worker_2@test"
    job.result_json = {
        "document_id": "901",
        "otp_required": True,
        "_otp_challenge": {
            "document_id": "901",
            "created_at": now - 125,
            "worker_id": "2",
            "egress_digest": hashlib.sha256(PROXY.encode()).hexdigest(),
            "allow_live_submit": True,
        },
    }
    session.add_all([job, driver])
    await session.commit()

    def session_factory():
        return AsyncSession(session.bind, expire_on_commit=False)

    monkeypatch.setattr(consumer, "async_session_factory", session_factory)
    monkeypatch.setattr(otp_forwarder, "async_session_factory", session_factory)
    monkeypatch.setenv("WORKER_ID", "2")
    monkeypatch.setattr("app.automation.worker_proxy.get_worker_proxy_url", lambda: PROXY)
    client = MagicMock()
    client.token = "test-token"
    client.issue_document_by_otp = AsyncMock(return_value={"obj": {"docNo": "1359998888"}})
    client.extract_tracking_code = MagicMock(return_value="1359998888")
    constructor = MagicMock(return_value=client)
    monkeypatch.setattr("app.automation.utcms_mobile_client.UtcmsMobileClient", constructor)
    monkeypatch.setattr(
        "app.automation.gps_shipping_manager.init_shipping",
        AsyncMock(return_value=SimpleNamespace(origin_lat=0, origin_lng=0)),
    )
    await redis.set(
        f"rpa:job:pending_doc:{job.job_id}",
        json.dumps(
            {
                **job.result_json["_otp_challenge"],
                "job_id": job.job_id,
                "driver_phone": PHONE,
                "token": "test-token",
                "client_id": job.client_id,
            }
        ),
        ex=3600,
    )
    await redis.set(otp_keys.otp_pending_phone_key(PHONE), job.job_id, ex=3600)
    await redis.sadd(otp_keys.OTP_ACTIVE_PENDING_JOBS_SET, job.job_id)
    event = {
        "job_id": job.job_id,
        "document_id": "901",
        "phone": PHONE,
        "code": "65432",
        "received_at": now,
        "ingested_at": now,
        "expires_at": now + 300,
        "message_id": "event-1",
    }
    return SimpleNamespace(
        session=session,
        job=job,
        driver=driver,
        api=api,
        redis=redis,
        client=client,
        constructor=constructor,
        event=event,
        factory=session_factory,
    )


async def execute(scenario, **event_changes):
    return await WaybillJobService.submit_otp(
        {"role": "master_admin"},
        scenario.job.job_id,
        scenario.session,
        "65432",
        _execute=True,
        otp_event=(scenario.event | event_changes) if event_changes else scenario.event,
    )


async def test_lease_locking_prevents_concurrent_issue(delivery_api):
    _, redis = delivery_api
    token = await otp_keys.reserve_otp_issue_lease(redis, "lease")
    assert isinstance(token, str) and token
    assert await otp_keys.reserve_otp_issue_lease(redis, "lease") is None
    await otp_keys.release_otp_issue_lease(redis, "lease", token)
    assert await otp_keys.reserve_otp_issue_lease(redis, "lease")


async def test_consume_scoped_otp_cleans_only_own_challenge(delivery_api):
    _, redis = delivery_api
    await redis.set(otp_keys.otp_job_key("old"), "old-code")
    await redis.set("rpa:job:pending_doc:old", "old-session")
    await redis.sadd(otp_keys.OTP_ACTIVE_PENDING_JOBS_SET, "old", "new")
    await redis.set(otp_keys.otp_pending_phone_key(PHONE), "new")
    await redis.set(otp_keys.otp_phone_key(PHONE), json.dumps({"job_id": "new", "code": "22222"}))
    assert await otp_keys.consume_scoped_otp(redis, job_id="old", driver_phone=PHONE) == 2
    assert await redis.get(otp_keys.otp_job_key("old")) is None
    assert await redis.get(otp_keys.otp_pending_phone_key(PHONE)) == "new"
    assert json.loads(await redis.get(otp_keys.otp_phone_key(PHONE)))["code"] == "22222"
    assert await redis.smembers(otp_keys.OTP_ACTIVE_PENDING_JOBS_SET) == {"new"}


async def test_fetch_scoped_otp_handles_device_clock_skew(delivery_api):
    _, redis = delivery_api
    now = time.time()
    await redis.set(
        otp_keys.otp_job_key("skew"),
        json.dumps(
            {"code": "84729", "phone": PHONE, "received_at": now - 120, "ingested_at": now, "expires_at": now + 180}
        ),
    )
    found = await fetch_scoped_otp(redis, job_id="skew", driver_phone=PHONE, wait_start=now - 5)
    assert found and found[0] == "84729"


async def test_single_flight_attribution_prunes_stale_jobs(otp_scenario):
    s = otp_scenario
    await s.redis.sadd(otp_keys.OTP_ACTIVE_PENDING_JOBS_SET, "stale")
    assert await consumer.resolve_single_flight_pending_phone() == PHONE
    assert "stale" not in await s.redis.smembers(otp_keys.OTP_ACTIVE_PENDING_JOBS_SET)


async def test_all_stale_pending_jobs_reach_database_fallback(otp_scenario):
    s = otp_scenario
    await s.redis.delete(f"rpa:job:pending_doc:{s.job.job_id}")
    await s.redis.sadd(otp_keys.OTP_ACTIVE_PENDING_JOBS_SET, "stale")
    assert await consumer.resolve_single_flight_pending_phone() == PHONE
    assert await s.redis.smembers(otp_keys.OTP_ACTIVE_PENDING_JOBS_SET) == set()


async def test_ambiguous_otp_attribution_rejected_when_multiple_jobs_pending(otp_scenario):
    s = otp_scenario
    await s.redis.sadd(otp_keys.OTP_ACTIVE_PENDING_JOBS_SET, "other")
    await s.redis.set("rpa:job:pending_doc:other", json.dumps({"driver_phone": "09120000002"}))
    assert await consumer.resolve_single_flight_pending_phone() == "AMBIGUOUS"
    response = await s.api.post(
        "/api/v1/otp/sms-forwarder", json={"text": "کد تایید صدور بارنامه: 54321", "sender": "20007777"}
    )
    assert response.status_code == 422 and "AMBIGUOUS_OTP" in response.text
    s.client.issue_document_by_otp.assert_not_awaited()


async def test_late_sms_routes_then_owning_worker_commits_and_acknowledges(otp_scenario, monkeypatch, caplog):
    """Real HTTP/Lua/stream/SQLite flow; only the external broker and UTCMS are mocked."""
    from app.workers import tasks

    caplog.set_level(logging.DEBUG, logger="app.services.otp_wakeup_consumer")
    caplog.set_level(logging.DEBUG, logger="app.services.waybill_job_service")
    s = otp_scenario
    dispatched = MagicMock()
    monkeypatch.setattr(tasks.complete_otp_event, "apply_async", dispatched)
    response = await s.api.post(
        "/api/v1/otp/sms-forwarder",
        json={
            "driver_phone": PHONE,
            "sender": "20007777",
            "text": "کد تایید صدور بارنامه: 65432",
            "timestamp": time.time(),
        },
    )
    assert response.status_code == 200
    s.client.issue_document_by_otp.assert_not_awaited()
    assert await consumer.process_otp_stream_events() == 1
    dispatched.assert_called_once()
    assert dispatched.call_args.kwargs["queue"] == "rpa_submit_2"
    s.client.issue_document_by_otp.assert_not_awaited()
    assert (await s.redis.xpending(consumer.OTP_STREAM_KEY, consumer.OTP_STREAM_GROUP))["pending"] == 1
    entry = dispatched.call_args.kwargs["kwargs"]["entry"]

    async def issued_after_durable_fence(*args, **kwargs):
        async with s.factory() as fresh:
            persisted = await fresh.get(WaybillJob, s.job.id)
            assert persisted.result_json["_otp_issue"]["state"] == "dispatching"
        return {"obj": {"docNo": "1359998888"}}

    s.client.issue_document_by_otp.side_effect = issued_after_durable_fence
    # Exercise the Celery task body in this event loop with the same isolated Redis.
    monkeypatch.setattr(tasks, "_run_async", lambda coroutine: coroutine)
    result = await tasks.complete_otp_event(entry=entry)
    assert result["success"] and result["terminal"]
    await s.session.refresh(s.job)
    assert s.job.status == "success" and s.job.mutation_status == "confirmed"
    assert s.job.result_json["tracking_code"] == "1359998888"
    s.client.issue_document_by_otp.assert_awaited_once_with("901", "65432", allow_live_submit=True)
    assert await s.redis.get(f"rpa:job:pending_doc:{s.job.job_id}") is None
    assert await s.redis.get(otp_keys.otp_phone_key(PHONE)) is None
    assert (await s.redis.xpending(consumer.OTP_STREAM_KEY, consumer.OTP_STREAM_GROUP))["pending"] == 0
    assert await s.redis.xlen(consumer.OTP_STREAM_KEY) == 0
    assert (await tasks.complete_otp_event(entry=entry))["already_completed"] is True
    assert s.client.issue_document_by_otp.await_count == 1
    logged = caplog.text + repr([record.__dict__ for record in caplog.records])
    assert "65432" not in logged


async def test_api_submission_is_durable_without_inline_network(otp_scenario):
    s = otp_scenario
    response = await WaybillJobService.submit_otp({"role": "master_admin"}, s.job.job_id, s.session, "65432")
    assert response.status == "unknown"
    assert await s.redis.xlen(consumer.OTP_STREAM_KEY) == 1
    event = json.loads((await s.redis.xrange(consumer.OTP_STREAM_KEY))[0][1]["payload"])
    assert event["job_id"] == s.job.job_id and event["document_id"] == "901" and event["phone"] == PHONE
    s.constructor.assert_not_called()


@pytest.mark.parametrize("state", ["unknown", "needs_review", "reconciling"])
async def test_submit_otp_uses_worker_proxy_and_legal_state_transition(otp_scenario, state):
    s = otp_scenario
    s.job.status = state
    s.session.add(s.job)
    await s.session.commit()
    result = await execute(s)
    assert result.status == "success"
    s.constructor.assert_called_once_with(token="test-token", proxy_url=PROXY)
    await s.session.refresh(s.job)
    assert s.job.result_json["_otp_issue"]["state"] == "issued"


@pytest.mark.parametrize(
    "start_outcome,expected_state",
    [
        ({"resultCode": 200, "resultMessage": "ثبت شد"}, "in_transit"),
        ({"resultCode": 4006, "resultMessage": "برای بارنامه نمی توان شروع حمل ثبت کرد"}, "in_transit"),
        ({"resultCode": 4025, "resultMessage": "رد شد"}, "unknown"),
        (RuntimeError("shipping response lost"), "unknown"),
    ],
)
async def test_otp_shipping_start_requires_acknowledgement(otp_scenario, monkeypatch, start_outcome, expected_state):
    """Issuance survives a shipping failure, but only an ACK proves the origin."""
    from app.automation.gps_shipping_manager import ShippingState, auto_complete_shipping

    s = otp_scenario
    state = ShippingState(
        job_id=s.job.job_id,
        doc_no="1359998888",
        doc_id="901",
        origin_lat=35.7,
        origin_lng=51.4,
        dest_lat=35.8,
        dest_lng=51.5,
    )
    monkeypatch.setattr("app.automation.gps_shipping_manager.init_shipping", AsyncMock(return_value=state))
    saved = AsyncMock()
    monkeypatch.setattr("app.automation.gps_shipping_manager.save_shipping_state", saved)
    s.client.register_start_of_shipping = AsyncMock()
    if isinstance(start_outcome, Exception):
        s.client.register_start_of_shipping.side_effect = start_outcome
    else:
        s.client.register_start_of_shipping.return_value = start_outcome

    assert (await execute(s)).status == "success"
    await s.session.refresh(s.job)
    assert s.job.result_json["tracking_code"] == "1359998888"
    assert state.status == expected_state
    saved.assert_awaited_once_with(state)
    s.client.register_start_of_shipping.assert_awaited_once()
    if expected_state == "in_transit":
        assert len(state.gps_list) == 1
        assert state.gps_list[0]["Provenance"] == "registered_start_of_shipping"
        assert state.gps_list[0]["Latitude"] == 35.7
        assert state.gps_list[0]["Longitude"] == 51.4
    else:
        assert state.gps_list == []
        monkeypatch.setattr("app.automation.gps_shipping_manager.load_shipping_state", AsyncMock(return_value=state))
        acquire = AsyncMock()
        monkeypatch.setattr("app.automation.gps_shipping_manager._acquire_completion_claim", acquire)
        assert await auto_complete_shipping(state.job_id, force=True) == {
            "status": "skipped",
            "reason": "not_in_transit",
        }
        acquire.assert_not_awaited()
    if isinstance(start_outcome, Exception):
        assert state.last_error_message == "shipping response lost"

    # A replay sees the durable tracking code and cannot issue or start again.
    assert (await execute(s)).status == "success"
    s.client.issue_document_by_otp.assert_awaited_once()
    s.client.register_start_of_shipping.assert_awaited_once()


async def test_driver_fallback_by_national_code_in_submit_otp(otp_scenario, monkeypatch):
    s = otp_scenario
    await s.redis.delete(f"rpa:job:pending_doc:{s.job.job_id}")
    s.job.driver_id = None
    s.job.payload_json = {"driver_national_code": s.driver.driver_national_code, "driver_phone": PHONE}
    s.session.add(s.job)
    await s.session.commit()
    monkeypatch.setattr("app.auth_multitenant.decrypt_driver_password", lambda _: "test-password")
    login = AsyncMock(return_value=s.client)
    monkeypatch.setattr("app.automation.gps_shipping_manager.get_or_login_client", login)
    assert (await execute(s)).status == "success"
    assert s.job.driver_id == s.driver.id
    assert login.await_args.kwargs["proxy_url"] == PROXY


@pytest.mark.parametrize("change", ["worker", "egress", "unauthorized", "document", "phone", "expired"])
async def test_wrong_worker_challenge_or_expired_event_never_reaches_network(otp_scenario, monkeypatch, change):
    s = otp_scenario
    event = {}
    if change == "worker":
        monkeypatch.setenv("WORKER_ID", "1")
    elif change == "egress":
        monkeypatch.setattr("app.automation.worker_proxy.get_worker_proxy_url", lambda: "http://wrong:3128")
    elif change == "unauthorized":
        s.job.result_json = {
            **s.job.result_json,
            "_otp_challenge": {**s.job.result_json["_otp_challenge"], "allow_live_submit": False},
        }
        s.session.add(s.job)
        await s.session.commit()
    elif change == "document":
        event = {"document_id": "other"}
    elif change == "phone":
        event = {"phone": "09120000002"}
    else:
        event = {"expires_at": time.time() - 1}
    with pytest.raises(HTTPException):
        await execute(s, **event)
    s.constructor.assert_not_called()


async def test_stale_orm_snapshot_is_refreshed_under_lease(otp_scenario):
    s = otp_scenario
    async with s.factory() as another:
        updated = await another.get(WaybillJob, s.job.id)
        updated.result_json = {**updated.result_json, "tracking_code": "already-issued"}
        another.add(updated)
        await another.commit()
    assert "tracking_code" not in s.job.result_json
    assert (await execute(s)).result_json["tracking_code"] == "already-issued"
    s.constructor.assert_not_called()


@pytest.mark.parametrize("failure", [TimeoutError("response lost"), None])
async def test_ambiguous_mutation_persists_fence_and_never_reposts(otp_scenario, failure):
    s = otp_scenario
    if failure:
        s.client.issue_document_by_otp.side_effect = failure
    else:
        s.client.extract_tracking_code.return_value = None
    with pytest.raises((TimeoutError, HTTPException)):
        await execute(s)
    await s.session.refresh(s.job)
    assert s.job.status == "needs_review"
    assert s.job.result_json["_otp_issue"]["state"] == "unknown"
    with pytest.raises(HTTPException, match="409"):
        await execute(s, message_id="second-event")
    assert s.client.issue_document_by_otp.await_count == 1


async def test_expiry_is_rechecked_after_login(otp_scenario, monkeypatch):
    s = otp_scenario
    await s.redis.delete(f"rpa:job:pending_doc:{s.job.job_id}")
    monkeypatch.setattr("app.auth_multitenant.decrypt_driver_password", lambda _: "test-password")

    async def login(**kwargs):
        s.event["expires_at"] = time.time() - 1
        return s.client

    monkeypatch.setattr("app.automation.gps_shipping_manager.get_or_login_client", login)
    with pytest.raises(HTTPException):
        await execute(s)
    s.client.issue_document_by_otp.assert_not_awaited()


@pytest.mark.parametrize("channel", ["path", "query", "header", "form", "android_aliases"])
async def test_phone_attribution_channels(delivery_api, channel):
    api, redis = delivery_api
    url = "/api/v1/otp/sms-forwarder"
    kwargs = {"json": {"text": "کد تایید: 65432", "sender": "20007777"}}
    if channel == "path":
        url += "/" + PHONE
    elif channel == "query":
        url += "?driver_phone=" + PHONE
    elif channel == "header":
        kwargs["headers"] = {"X-Driver-Phone": PHONE}
    elif channel == "form":
        url += "/" + PHONE
        kwargs = {"data": {"text": "کد تایید: 65432", "from": "20007777"}}
    else:
        kwargs = {"json": {"smsBody": "کد تایید: 65432", "phoneNumber": "20007777", "receiver": PHONE}}
    response = await api.post(url, **kwargs)
    assert response.status_code == 200
    value = json.loads(await redis.get(otp_keys.otp_phone_key(PHONE)))
    assert value["code"] == "65432" and value["phone"] == PHONE


async def test_webhook_header_auth_supported_query_token_rejected(delivery_api):
    api, _ = delivery_api
    token = api.headers.pop("X-OTP-Webhook-Token")
    url = "/api/v1/otp/sms-forwarder/" + PHONE
    payload = {"text": "کد تایید: 65432", "sender": "20007777"}
    assert (await api.post(url, json=payload, headers={"Authorization": f"Bearer {token}"})).status_code == 200
    assert (await api.post(url + "?token=" + token, json=payload)).status_code == 401
    assert (await api.post(url, json=payload, headers={"X-Webhook-Token": token})).status_code == 200


async def test_otp_ping_and_health_endpoints(delivery_api):
    api, _ = delivery_api
    assert (await api.get("/api/v1/otp/ping")).json()["status"] == "ok"
    response = await api.get("/api/v1/otp/health")
    assert response.status_code == 200 and response.json()["redis_connected"] is True


async def test_manual_otp_submission_uses_authenticated_job_scope(otp_scenario):
    s = otp_scenario
    app = FastAPI()
    app.include_router(otp_forwarder.router)
    app.dependency_overrides[otp_forwarder.get_current_user_or_admin] = lambda: {
        "role": "client",
        "user": SimpleNamespace(id=s.job.client_id),
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as api:
        response = await api.post(
            "/api/v1/otp/submit-manual", json={"code": "65432", "job_id": s.job.job_id, "phone": "09120000002"}
        )
    assert response.status_code == 200 and response.json()["status"] == "accepted"
    entry = json.loads((await s.redis.xrange(consumer.OTP_STREAM_KEY))[0][1]["payload"])
    assert entry["phone"] == PHONE
    s.client.issue_document_by_otp.assert_not_awaited()


async def test_owned_completed_job_cannot_delete_another_tenants_otp(otp_scenario):
    """Replay the baseline exploit through tenant HTTP auth and real SQLite/Redis."""
    s = otp_scenario
    victim_phone = "09120000002"
    victim = Client(
        client_code="OTP_VICTIM",
        name="OTP victim",
        email="otp-victim@example.invalid",
        username="otp-victim",
        full_name="OTP victim",
        hashed_password="unused",
    )
    s.session.add(victim)
    await s.session.flush()
    assert victim.id != s.job.client_id
    victim_job = WaybillJob(
        job_id="other-tenant-pending-otp",
        idempotency_key="other-tenant-pending-otp",
        client_id=victim.id,
        status="unknown",
        payload_json={"driver_phone": victim_phone},
        result_json={"document_id": "902", "otp_required": True},
    )
    s.job.status = "success"
    s.job.result_json = {**s.job.result_json, "tracking_code": "1359998888"}
    s.session.add_all([s.job, victim_job])
    await s.session.commit()
    victim_values = {
        otp_keys.otp_phone_key(victim_phone): json.dumps({"job_id": victim_job.job_id, "code": "54321"}),
        otp_keys.otp_pending_phone_key(victim_phone): victim_job.job_id,
        f"rpa:job:pending_doc:{victim_job.job_id}": json.dumps({"document_id": "902"}),
    }
    for key, value in victim_values.items():
        await s.redis.set(key, value)
    await s.redis.sadd(otp_keys.OTP_ACTIVE_PENDING_JOBS_SET, victim_job.job_id)
    app = FastAPI()
    app.include_router(otp_forwarder.router)
    app.dependency_overrides[otp_forwarder.get_current_user_or_admin] = lambda: {
        "role": "client",
        "user": SimpleNamespace(id=s.job.client_id),
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as api:
        response = await api.post(
            "/api/v1/otp/submit-manual",
            json={"code": "65432", "job_id": s.job.job_id, "phone": victim_phone},
        )
    assert response.status_code == 200
    assert response.json()["job_status"] == "success"
    assert await consumer.process_otp_stream_events() == 0
    for key, value in victim_values.items():
        assert await s.redis.get(key) == value
    assert await s.redis.sismember(otp_keys.OTP_ACTIVE_PENDING_JOBS_SET, victim_job.job_id)
    s.client.issue_document_by_otp.assert_not_awaited()


def test_safe_json_dict():
    assert consumer._safe_json_dict('{"b": "hello"}') == {"b": "hello"}
    for value in [None, "", "{broken", ["list"], 12345]:
        assert consumer._safe_json_dict(value) == {}


async def test_sweep_otp_stream_celery_task(monkeypatch):
    from app.workers import tasks

    process = AsyncMock(return_value=2)
    monkeypatch.setattr(consumer, "process_otp_stream_events", process)
    monkeypatch.setattr(tasks, "_run_async", lambda coroutine: coroutine)
    assert await tasks.sweep_otp_stream() == 2
    process.assert_awaited_once_with(batch_size=10)


async def test_waybill_job_otp_route_alias(otp_scenario, monkeypatch):
    from app.api.routes import multitenant
    from app.auth_multitenant import get_current_user_or_admin
    from app.core.database import get_session

    s = otp_scenario
    app = FastAPI()
    app.include_router(multitenant.router)
    app.dependency_overrides[get_current_user_or_admin] = lambda: {"role": "master_admin"}
    app.dependency_overrides[get_session] = lambda: s.session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as api:
        response = await api.post(f"/api/v1/waybill-jobs/{s.job.job_id}/otp", json={"otp_code": "65432"})
    assert response.status_code == 200 and response.json()["status"] == "unknown"
    assert await s.redis.xlen(consumer.OTP_STREAM_KEY) == 1


async def test_lease_lost_during_login_never_writes_fence_or_posts(otp_scenario, monkeypatch):
    s = otp_scenario
    await s.redis.delete(f"rpa:job:pending_doc:{s.job.job_id}")
    monkeypatch.setattr("app.auth_multitenant.decrypt_driver_password", lambda _: "test-password")

    async def login(**kwargs):
        await s.redis.set(otp_keys.otp_issue_lock_key(s.job.job_id), "successor", ex=30)
        return s.client

    monkeypatch.setattr("app.automation.gps_shipping_manager.get_or_login_client", login)
    with pytest.raises(HTTPException):
        await execute(s)
    s.client.issue_document_by_otp.assert_not_awaited()
    assert "_otp_issue" not in s.job.result_json
    assert await s.redis.get(otp_keys.otp_issue_lock_key(s.job.job_id)) == "successor"


async def test_lease_lost_during_fence_commit_never_posts_or_retries(otp_scenario, monkeypatch):
    s = otp_scenario
    real_commit = s.session.commit

    async def delayed_commit():
        await real_commit()
        if s.job.result_json.get("_otp_issue", {}).get("state") == "dispatching":
            await s.redis.set(otp_keys.otp_issue_lock_key(s.job.job_id), "successor", ex=30)

    monkeypatch.setattr(s.session, "commit", delayed_commit)
    with pytest.raises(HTTPException):
        await execute(s)
    assert s.job.result_json["_otp_issue"]["state"] == "dispatching"
    s.client.issue_document_by_otp.assert_not_awaited()
    assert await s.redis.get(otp_keys.otp_issue_lock_key(s.job.job_id)) == "successor"
    await s.redis.delete(otp_keys.otp_issue_lock_key(s.job.job_id))
    with pytest.raises(HTTPException):
        await execute(s, message_id="successor-event")
    s.client.issue_document_by_otp.assert_not_awaited()


@pytest.mark.parametrize("change", ["phone", "worker", "challenge_time", "tracking", "fence"])
async def test_final_locked_read_revalidates_changes_during_login(otp_scenario, monkeypatch, change):
    s = otp_scenario
    await s.redis.delete(f"rpa:job:pending_doc:{s.job.job_id}")
    monkeypatch.setattr("app.auth_multitenant.decrypt_driver_password", lambda _: "test-password")

    async def login(**kwargs):
        async with s.factory() as another:
            updated = await another.get(WaybillJob, s.job.id)
            if change == "phone":
                from app.models_multitenant import Driver

                driver = await another.get(Driver, s.driver.id)
                driver.phone = "09120000002"
                another.add(driver)
            elif change == "worker":
                updated.result_json = {
                    **updated.result_json,
                    "_otp_challenge": {**updated.result_json["_otp_challenge"], "worker_id": "3"},
                }
            elif change == "challenge_time":
                updated.result_json = {
                    **updated.result_json,
                    "_otp_challenge": {**updated.result_json["_otp_challenge"], "created_at": time.time() + 1},
                }
            elif change == "tracking":
                updated.result_json = {**updated.result_json, "tracking_code": "issued-elsewhere"}
            else:
                updated.result_json = {
                    **updated.result_json,
                    "_otp_issue": {"state": "dispatching", "message_id": "other"},
                }
            another.add(updated)
            await another.commit()
        return s.client

    monkeypatch.setattr("app.automation.gps_shipping_manager.get_or_login_client", login)
    if change == "tracking":
        assert (await execute(s)).result_json["tracking_code"] == "issued-elsewhere"
    else:
        with pytest.raises(HTTPException):
            await execute(s)
    s.client.issue_document_by_otp.assert_not_awaited()


@pytest.mark.parametrize(
    "field,value", [("job_id", "other"), ("document_id", "902"), ("client_id", 999), ("egress_digest", "wrong")]
)
async def test_cached_token_cannot_cross_job_document_tenant_or_egress(otp_scenario, monkeypatch, field, value):
    s = otp_scenario
    key = f"rpa:job:pending_doc:{s.job.job_id}"
    cached = json.loads(await s.redis.get(key))
    cached[field] = value
    await s.redis.set(key, json.dumps(cached))
    monkeypatch.setattr("app.auth_multitenant.decrypt_driver_password", lambda _: "test-password")
    login = AsyncMock(return_value=s.client)
    monkeypatch.setattr("app.automation.gps_shipping_manager.get_or_login_client", login)
    assert (await execute(s)).status == "success"
    s.constructor.assert_not_called()
    login.assert_awaited_once()
    assert login.await_args.kwargs["national_code"] == s.driver.utcms_username


async def test_http_server_error_with_business_code_remains_ambiguous(otp_scenario):
    from app.automation.utcms_mobile_client import UtcmsMobileApiError

    s = otp_scenario
    s.client.issue_document_by_otp.side_effect = UtcmsMobileApiError(
        "upstream failure", status_code=500, result_code=4004, response_body={"resultCode": 4004}
    )
    with pytest.raises(HTTPException):
        await execute(s)
    assert s.job.result_json["_otp_issue"]["state"] == "unknown"
    with pytest.raises(HTTPException):
        await execute(s, message_id="retry")
    assert s.client.issue_document_by_otp.await_count == 1


async def test_explicit_rejection_is_visible_and_only_new_event_can_retry(otp_scenario):
    from app.automation.utcms_mobile_client import UtcmsMobileApiError

    s = otp_scenario
    s.client.issue_document_by_otp.side_effect = UtcmsMobileApiError(
        "business rejection", result_code=4004, response_body={"resultCode": 4004}
    )
    with pytest.raises(HTTPException) as failure:
        await execute(s)
    assert failure.value.status_code == 400
    await s.session.refresh(s.job)
    assert s.job.status == "needs_review" and s.job.error_category == "otp_rejected"
    assert s.job.result_json["_otp_issue"]["state"] == "rejected"
    with pytest.raises(HTTPException):
        await execute(s)
    assert s.client.issue_document_by_otp.await_count == 1
    s.client.issue_document_by_otp.side_effect = None
    assert (await execute(s, message_id="new-sms")).status == "success"
    assert s.client.issue_document_by_otp.await_count == 2


async def test_stream_waits_for_durable_challenge_commit(otp_scenario):
    s = otp_scenario
    s.job.result_json = {"document_id": "901", "otp_required": True}
    s.session.add(s.job)
    await s.session.commit()
    result = await consumer.resolve_and_complete_pending_job_for_otp(entry=s.event)
    assert result["retryable"] is True and not result.get("terminal")
    s.constructor.assert_not_called()


async def test_redis_outage_blocks_manual_acknowledgement(otp_scenario, monkeypatch):
    s = otp_scenario
    monkeypatch.setattr(consumer.redis_manager, "get", AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as failure:
        await WaybillJobService.submit_otp({"role": "master_admin"}, s.job.job_id, s.session, "65432")
    assert failure.value.status_code == 503
    s.constructor.assert_not_called()


@pytest.mark.parametrize("manual", [False, True])
async def test_stream_append_failure_cannot_acknowledge_or_hide_delivery(otp_scenario, manual):
    s = otp_scenario
    await s.redis.set(consumer.OTP_STREAM_KEY, "wrong-type")
    if manual:
        with pytest.raises(HTTPException, match="503"):
            await WaybillJobService.submit_otp({"role": "master_admin"}, s.job.job_id, s.session, "65432")
        assert await s.redis.get(otp_keys.otp_job_key(s.job.job_id)) is None
    else:
        response = await s.api.post(
            "/api/v1/otp/sms-forwarder",
            json={
                "driver_phone": PHONE,
                "sender": "20007777",
                "text": "کد تایید صدور بارنامه: 65432",
                "timestamp": time.time(),
            },
        )
        assert response.status_code == 503
        assert await s.redis.keys("rpa:otp:seen:*") == []
        assert await s.redis.get(otp_keys.otp_phone_key(PHONE)) is None
    s.constructor.assert_not_called()


async def test_same_driver_pending_challenge_blocks_scheduler_and_scheduled_worker(otp_scenario, monkeypatch):
    from app.orchestrator.scheduler_service import SchedulerService
    from app.services.scheduled_waybill_executor import _execute_single_job

    s = otp_scenario
    another = WaybillJob(
        job_id="second-driver-job",
        idempotency_key="second-driver-job",
        client_id=s.job.client_id,
        driver_id=s.driver.id,
        status="pending",
        payload_json={"driver_national_code": s.driver.driver_national_code},
    )
    s.session.add(another)
    await s.session.commit()
    monkeypatch.setattr("app.orchestrator.scheduler_service.async_session_factory", s.factory)
    assert await SchedulerService().run() == 0
    await s.session.refresh(another)
    assert another.status == "pending"
    another.status = "in_progress"
    s.session.add(another)
    await s.session.commit()
    from app.models_multitenant import Client

    tenant = await s.session.get(Client, s.job.client_id)
    bot = MagicMock()
    monkeypatch.setattr("app.services.scheduled_waybill_executor.WaybillAutomationBot", bot)
    result = await _execute_single_job(tenant, s.driver, another, s.session, driver_password="unused")
    assert result["status"] == "waiting_retry" and result["error_category"] == "driver_otp_pending"
    bot.assert_not_called()


async def test_driver_challenge_guard_ignores_history_without_doc_and_resolves_on_tracking(otp_scenario):
    from app.services.otp_challenge_guard import find_unresolved_driver_otp_job

    s = otp_scenario
    kwargs = {"client_id": s.job.client_id, "driver_id": s.driver.id}
    assert (await find_unresolved_driver_otp_job(s.session, **kwargs)).job_id == s.job.job_id
    assert await find_unresolved_driver_otp_job(s.session, client_id=999, driver_id=s.driver.id) is None
    s.job.result_json = {"otp_required": True}
    s.job.document_id = None
    s.session.add(s.job)
    await s.session.commit()
    assert await find_unresolved_driver_otp_job(s.session, **kwargs) is None
    s.job.result_json = {"otp_required": True, "document_id": "901", "tracking_code": "issued"}
    s.session.add(s.job)
    await s.session.commit()
    assert await find_unresolved_driver_otp_job(s.session, **kwargs) is None


async def test_main_worker_checks_pending_challenge_after_driver_lock(otp_scenario, monkeypatch):
    from app.workers import waybill_worker

    s = otp_scenario
    another = WaybillJob(
        job_id="second-worker-job",
        idempotency_key="second-worker-job",
        client_id=s.job.client_id,
        driver_id=s.driver.id,
        status="queued",
        payload_json={"driver_national_code": s.driver.driver_national_code},
    )
    s.session.add(another)
    await s.session.commit()
    monkeypatch.setattr(waybill_worker, "async_session_factory", s.factory)
    monkeypatch.setattr(waybill_worker, "decrypt_driver_password", lambda _: "test-password")
    acquire = AsyncMock(return_value=True)
    monkeypatch.setattr(waybill_worker.rpa_runtime, "acquire_lock", acquire)
    monkeypatch.setattr(waybill_worker.rpa_runtime, "release_lock", AsyncMock(return_value=True))
    bot = MagicMock()
    monkeypatch.setattr(waybill_worker, "WaybillAutomationBot", bot)
    task = SimpleNamespace(request=SimpleNamespace(id="test-task", hostname="worker_2@test"))
    result = await waybill_worker._execute_job(task, another.job_id)
    assert result["status"] == "waiting_retry" and result["error_category"] == "driver_otp_pending"
    bot.assert_not_called()
    assert acquire.await_count == 2
    await s.session.refresh(another)
    assert another.mutation_status is None
    assert another.mutation_at is None
    assert another.next_retry_at is not None


async def test_late_transport_error_cannot_overwrite_reconciled_tracking(otp_scenario):
    s = otp_scenario

    async def reconciled_while_post_inflight(*args, **kwargs):
        async with s.factory() as another:
            updated = await another.get(WaybillJob, s.job.id)
            updated.result_json = {**updated.result_json, "tracking_code": "reconciled-proof"}
            another.add(updated)
            await another.commit()
        raise TimeoutError("response lost")

    s.client.issue_document_by_otp.side_effect = reconciled_while_post_inflight
    with pytest.raises(TimeoutError):
        await execute(s)
    await s.session.refresh(s.job)
    assert s.job.result_json["tracking_code"] == "reconciled-proof"
    assert s.job.status != "needs_review"
