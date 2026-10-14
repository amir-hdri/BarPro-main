"""Regression: /sms-gateway must self-heal future clock-skew like /sms-forwarder does."""

import hmac
import shutil
import subprocess
import tempfile
import time
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis

from app.api.routes import otp_forwarder
from app.automation.otp_keys import otp_phone_key
from app.core.config import utcms_config


@pytest.fixture
async def gateway_api(tmp_path, monkeypatch):
    binary = shutil.which("redis-server")
    if binary is None:
        pytest.skip("redis-server is required for the isolated gateway skew test")
    socket_dir = tempfile.TemporaryDirectory(prefix="barpro-gateway-skew-")
    socket = socket_dir.name + "/redis.sock"
    process = subprocess.Popen(
        [binary, "--port", "0", "--unixsocket", socket, "--save", "", "--appendonly", "no"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    redis = Redis(unix_socket_path=socket, decode_responses=True)
    try:
        import asyncio

        for _ in range(100):
            if process.poll() is not None:
                pytest.skip("isolated Redis exited before accepting connections")
            try:
                if await redis.ping():
                    break
            except Exception as exc:
                from redis.exceptions import ConnectionError as RedisConnectionError

                if not isinstance(exc, (OSError, ConnectionError, RedisConnectionError)):
                    raise
            await asyncio.sleep(0.02)
        else:
            pytest.skip("isolated Redis failed to start")
        monkeypatch.setattr(
            "app.services.otp_wakeup_consumer.trigger_job_completion_on_otp_received", lambda **kwargs: None
        )
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


async def test_sms_gateway_accepts_future_skew_via_now_fallback(gateway_api):
    """Driver clock +90s fast must not yield terminal 422 on the offline-fallback path."""
    client, redis = gateway_api
    phone = "09120000001"
    timestamp_ms = int((time.time() + 90) * 1000)
    envelope = f"BP1#{phone}#{timestamp_ms}#39182"
    signature = hmac.new(b"test-forwarder-secret-32-bytes-long", envelope.encode(), "sha256").hexdigest()[:32]
    response = await client.post(
        "/api/v1/otp/sms-gateway", json={"from": "+989120000001", "text": f"{envelope}#{signature}"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    stored = await redis.get(otp_phone_key(phone))
    assert stored is not None
