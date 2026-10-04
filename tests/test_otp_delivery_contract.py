"""Exercise the actual API and Lua delivery transaction against an isolated Redis."""

import asyncio
import hmac
import json
import shutil
import subprocess
import tempfile
import time
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis

from app.api.routes import otp_forwarder
from app.automation.otp_keys import otp_phone_key
from app.automation.waybill_enhanced import fetch_scoped_otp
from app.core.config import utcms_config
from app.services.otp_delivery import sms_received_at


@pytest.fixture
async def delivery_api(tmp_path, monkeypatch):
    binary = shutil.which("redis-server")
    if binary is None:
        pytest.skip("redis-server is required for the real Lua contract test")
    # Honour $TMPDIR instead of hard-coding /tmp: a restrictive sandbox (and some
    # CI runners) only grant write access to the system temp dir, and the AF_UNIX
    # socket path stays well under the 104-byte limit there either way.
    socket_dir = tempfile.TemporaryDirectory(prefix="barpro-otp-")
    socket = socket_dir.name + "/redis.sock"
    process = subprocess.Popen(
        [binary, "--port", "0", "--unixsocket", socket, "--save", "", "--appendonly", "no"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    redis = Redis(unix_socket_path=socket, decode_responses=True)
    try:
        for _ in range(100):
            if process.poll() is not None:
                pytest.skip(
                    "isolated Redis exited before accepting connections (environment cannot bind a local socket)"
                )
            try:
                if await redis.ping():
                    break
            except (OSError, ConnectionError):
                pass
            except Exception as exc:
                # redis-py raises its own ConnectionError during startup.
                from redis.exceptions import ConnectionError as RedisConnectionError

                if not isinstance(exc, RedisConnectionError):
                    raise
            await asyncio.sleep(0.02)
        else:
            pytest.skip("isolated Redis failed to start (environment cannot bind a local socket)")
        monkeypatch.setattr(utcms_config, "OTP_WEBHOOK_SECRET", "test-forwarder-secret-32-bytes-long")
        monkeypatch.setattr(otp_forwarder.redis_manager, "get", AsyncMock(return_value=redis))
        app = FastAPI()
        app.include_router(otp_forwarder.router)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://barpro.test") as client:
            client.headers["X-OTP-Webhook-Token"] = "test-forwarder-secret-32-bytes-long"
            yield client, redis
    finally:
        await redis.aclose()
        process.terminate()
        process.wait(timeout=5)
        socket_dir.cleanup()


def sms(**changes):
    payload = {
        "event": "SMS_RECEIVED",
        "driver_phone": "۰۹۱۲۰۰۰۰۰۰۱",
        "sender": "20007777",
        "text": "سامانه بارنامه شهرداری: کد ورود شما ۳۹۱۸۲ می باشد.",
        "timestamp": int(time.time() * 1000),
        "device_id": "test-device",
        "sim_slot": "SIM 1",
    }
    return payload | changes


async def test_android_payload_reaches_only_recipient_and_worker(delivery_api):
    client, redis = delivery_api
    payload = sms()
    response = await client.post("/api/v1/otp/sms-forwarder", json=payload)
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "39182" not in response.text
    assert await redis.get(otp_phone_key("20007777")) is None
    found = await fetch_scoped_otp(redis, job_id="job-a", driver_phone="+989120000001", wait_start=time.time())
    assert found is not None and found[0] == "39182"
    assert await fetch_scoped_otp(redis, job_id="job-b", driver_phone="09120000002", wait_start=time.time()) is None
    stored = json.loads(await redis.get(otp_phone_key("09120000001")))
    assert "raw_text" not in stored


async def test_retries_do_not_refresh_ttl_or_resurrect_consumed_otp(delivery_api):
    client, redis = delivery_api
    payload = sms(timestamp=int((time.time() - 240) * 1000))
    assert (await client.post("/api/v1/otp/sms-forwarder", json=payload)).status_code == 200
    key = otp_phone_key("09120000001")
    assert 0 < await redis.ttl(key) <= 60
    await redis.delete(key)  # The robot has consumed the OTP.
    retry = await client.post("/api/v1/otp/sms-forwarder", json=payload)
    assert retry.json()["is_duplicate"] is True
    assert await redis.get(key) is None


async def test_old_arrival_does_not_replace_newer_otp(delivery_api):
    client, redis = delivery_api
    assert (await client.post("/api/v1/otp/sms-forwarder", json=sms())).status_code == 200
    old = sms(text="کد تایید: 12345", timestamp=int((time.time() - 60) * 1000))
    assert (await client.post("/api/v1/otp/sms-forwarder", json=old)).status_code == 409
    assert json.loads(await redis.get(otp_phone_key("09120000001")))["code"] == "39182"


async def test_health_probe_does_not_insert_a_synthetic_otp(delivery_api):
    client, redis = delivery_api
    response = await client.post("/api/v1/otp/sms-forwarder", json={"event": "HEALTH_CHECK"})
    assert response.json() == {"success": True, "status": "ready", "protocol": "barpro-otp-v1"}
    assert await redis.dbsize() == 0


@pytest.mark.parametrize(
    "changes,status",
    [
        ({"driver_phone": ""}, 422),
        ({"driver_phone": "20007777"}, 422),
        ({"timestamp": 1}, 410),
        ({"timestamp": True}, 422),
        ({"timestamp": "nan"}, 422),
        ({"encrypted": True}, 422),
        ({"event": "HEARTBEAT"}, 422),
        ({"text": "a" * 17_000}, 413),
    ],
)
async def test_invalid_input_never_creates_an_otp(delivery_api, changes, status):
    client, redis = delivery_api
    response = await client.post("/api/v1/otp/sms-forwarder", json=sms(**changes))
    assert response.status_code == status
    assert await redis.dbsize() == 0


async def test_redis_failure_never_acknowledges_delivery(delivery_api, monkeypatch):
    client, _ = delivery_api
    monkeypatch.setattr(otp_forwarder.redis_manager, "get", AsyncMock(return_value=None))
    for payload in (sms(), {"event": "HEALTH_CHECK"}):
        response = await client.post("/api/v1/otp/sms-forwarder", json=payload)
        assert response.status_code == 503


@pytest.mark.parametrize(
    "text",
    [
        "کد رهگیری بارنامه: 12345678",
        "شماره بارنامه 12345 ثبت شد",
        "کد ورود: 09123456789",
        "کد تایید: 123456789",
        "رمز دوم کارت: 12345",
        "کد تخفیف: 12345",
    ],
)
def test_parser_does_not_convert_tracking_or_phone_numbers_to_otp(text):
    assert otp_forwarder.extract_otp_code(text) is None


@pytest.mark.parametrize("phone", ["+989120000001", "00989120000001", "9120000001", "۰۹۱۲۰۰۰۰۰۰۱"])
def test_key_normalization_matches_android(phone):
    assert otp_phone_key(phone) == "rpa:otp:phone:09120000001"


def test_source_timestamp_expiry_and_clock_skew():
    now = 1_800_000_000.0
    assert sms_received_at((now - 12) * 1000, now=now) == now - 12
    for value, status in ((now - 300, 410), (now + 31, 422)):
        with pytest.raises(HTTPException) as exc:
            sms_received_at(value, now=now)
        assert exc.value.status_code == status


async def test_signed_gateway_and_http_share_delivery_identity(delivery_api):
    client, redis = delivery_api
    payload = sms()
    envelope = f"BP1#09120000001#{payload['timestamp']}#39182"
    signature = hmac.new(b"test-forwarder-secret-32-bytes-long", envelope.encode(), "sha256").hexdigest()[:32]
    relay = await client.post(
        "/api/v1/otp/sms-gateway", json={"from": "+989120000001", "text": f"{envelope}#{signature}"}
    )
    assert relay.status_code == 200
    first = await redis.get(otp_phone_key("09120000001"))
    direct = await client.post("/api/v1/otp/sms-forwarder", json=payload)
    assert direct.json()["is_duplicate"] is True
    assert await redis.get(otp_phone_key("09120000001")) == first


async def test_gateway_rejects_unsigned_or_mismatched_sender(delivery_api):
    client, redis = delivery_api
    for text in ("BARPRO#driver#09120000001#OTP#12345", "BP1#09120000001#1800000000000#12345#wrong"):
        response = await client.post("/api/v1/otp/sms-gateway", json={"from": "09120000001", "text": text})
        assert response.status_code in (401, 422)
    envelope = f"BP1#09120000001#{int(time.time() * 1000)}#12345"
    signature = hmac.new(b"test-forwarder-secret-32-bytes-long", envelope.encode(), "sha256").hexdigest()[:32]
    response = await client.post(
        "/api/v1/otp/sms-gateway", json={"from": "09120000002", "text": f"{envelope}#{signature}"}
    )
    assert response.status_code == 422
    assert await redis.dbsize() == 0
