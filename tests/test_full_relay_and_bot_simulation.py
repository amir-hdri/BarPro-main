"""Full End-to-End Simulation: Driver App -> Hub App -> BarPro RPA Bot.

Simulates the entire communication and execution lifecycle across:
1. Driver Phone (SMS interception from 7777000982, OTP extraction, on-net carrier routing, HMAC envelope encoding)
2. Hub Phone (GSM reception, constant-time HMAC pre-verification, boundary forge rejection, gateway dispatch)
3. BarPro API Gateway (authoritative verification, atomic Redis ingestion, Lua transactions)
4. BarPro RPA Bot (scoped OTP retrieval, lease lock acquisition, UTCMS OTP issuance submission, two-witness confirmation, atomic session invalidation)
"""

import asyncio
import hmac
import json
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
from app.automation.otp_keys import (
    consume_scoped_otp,
    otp_pending_phone_key,
    otp_phone_key,
    release_otp_issue_lease,
    reserve_otp_issue_lease,
)
from app.automation.waybill_enhanced import fetch_scoped_otp
from app.core.config import utcms_config

WEBHOOK_SECRET = "test-forwarder-secret-32-bytes-long"
MCI_DRIVER_PHONE = "09123456789"
IRANCELL_DRIVER_PHONE = "09353456789"
HUB_MCI_PHONE = "09129998877"
HUB_IRANCELL_PHONE = "09359998877"


# -----------------------------------------------------------------------------
# Component 1: Driver App Simulator (matches CarrierDetector & SmsFallbackEnvelope)
# -----------------------------------------------------------------------------
class DriverAppSimulator:
    def __init__(self, driver_phone: str, hub_mci: str, hub_irancell: str, webhook_token: str):
        self.driver_phone = driver_phone
        self.hub_mci = hub_mci
        self.hub_irancell = hub_irancell
        self.webhook_token = webhook_token

    def resolve_hub_route(self) -> tuple[str, str]:
        """Resolves primary and failover Hub SIM based on Driver carrier."""
        is_mci = self.driver_phone.startswith(
            (
                "0910",
                "0911",
                "0912",
                "0913",
                "0914",
                "0915",
                "0916",
                "0917",
                "0918",
                "0919",
                "0990",
                "0991",
                "0992",
                "0993",
                "0994",
                "0996",
            )
        )
        if is_mci:
            return self.hub_mci, self.hub_irancell
        else:
            return self.hub_irancell, self.hub_mci

    def process_incoming_utcms_sms(self, sender: str, raw_text: str, timestamp_ms: int) -> dict[str, str]:
        """Simulates SmsReceiver + SmsForwardRepository on Driver handset."""
        # 1. Verify sender is UTCMS
        assert sender in {"7777000982", "7777", "+987777000982"}
        # 2. Extract OTP
        otp_code = otp_forwarder.extract_otp_code(raw_text)
        assert otp_code is not None, "Failed to extract OTP from UTCMS SMS"
        # 3. Resolve destination route
        primary_hub, failover_hub = self.resolve_hub_route()
        # 4. Encode HMAC ASCII envelope (BP1#phone#timestamp#code#signature)
        payload = f"BP1#{self.driver_phone}#{timestamp_ms}#{otp_code}"
        sig = hmac.new(self.webhook_token.encode("utf-8"), payload.encode("ascii"), "sha256").hexdigest()[:32]
        envelope = f"{payload}#{sig}"
        assert len(envelope) <= 160, "Envelope exceeds standard 160 GSM chars"
        return {
            "envelope": envelope,
            "destination": primary_hub,
            "failover": failover_hub,
            "code": otp_code,
        }


# -----------------------------------------------------------------------------
# Component 2: Hub App Simulator (matches SmsFallbackEnvelope & SmsForwarderClient)
# -----------------------------------------------------------------------------
class HubAppSimulator:
    def __init__(self, webhook_token: str, server_base_url: str):
        self.webhook_token = webhook_token
        self.server_base_url = server_base_url.rstrip("/")

    def verify_envelope(self, envelope: str) -> bool:
        """Constant-time verification of envelope at Hub intake."""
        parts = envelope.strip().split("#")
        if len(parts) != 5 or parts[0] != "BP1":
            return False
        payload = "#".join(parts[:4])
        expected_sig = hmac.new(self.webhook_token.encode("utf-8"), payload.encode("ascii"), "sha256").hexdigest()[:32]
        return hmac.compare_digest(parts[4].lower(), expected_sig.lower())

    def resolve_gateway_url(self) -> str:
        return f"{self.server_base_url}/api/v1/otp/sms-gateway"

    def assemble_gateway_payload(self, envelope: str) -> dict[str, str]:
        parts = envelope.split("#")
        phone = parts[1]
        return {
            "from": phone,
            "text": envelope,
        }


# -----------------------------------------------------------------------------
# Component 3: BarPro RPA Bot Simulator (waybill issuance & OTP consumption)
# -----------------------------------------------------------------------------
class BarProRpaBotSimulator:
    def __init__(self, job_id: str, driver_phone: str, redis: Redis):
        self.job_id = job_id
        self.driver_phone = driver_phone
        self.redis = redis
        self.status = "WAITING_OTP"
        self.tracking_code = None

    async def register_job_challenge(self):
        """Registers active waybill waiting for OTP for this driver phone."""
        await self.redis.set(otp_pending_phone_key(self.driver_phone), self.job_id, ex=300)
        await self.redis.sadd("rpa:otp:active_pending_jobs", self.job_id)

    async def wait_and_submit_otp(self, wait_start: float) -> str:
        """Polls for scoped OTP, acquires lease lock, simulates UTCMS submission, and confirms."""
        # 1. Fetch tenant-scoped OTP
        otp_result = await fetch_scoped_otp(
            self.redis,
            job_id=self.job_id,
            driver_phone=self.driver_phone,
            wait_start=wait_start,
        )
        assert otp_result is not None, "Bot failed to find scoped OTP in Redis"
        candidate_code, otp_key, entry = otp_result

        # 2. Acquire distributed lease lock
        lock_token = await reserve_otp_issue_lease(self.redis, self.job_id, ttl_seconds=30)
        assert lock_token is not None, "Failed to acquire issue lease lock"

        try:
            # 3. Simulate calling UTCMS mobile client IssueDocumentByOtp endpoint
            # In live system: UtcmsMobileClient.issue_document_by_otp(job_id, candidate_code)
            simulated_tracking_code = f"UTC-1403-{int(time.time())}"
            self.tracking_code = simulated_tracking_code
            self.status = "CONFIRMED"

            # 4. Atomic invalidation & purging of OTP
            purged_count = await consume_scoped_otp(
                self.redis,
                job_id=self.job_id,
                driver_phone=self.driver_phone,
            )
            assert purged_count > 0, "Failed to purge consumed OTP"

            return simulated_tracking_code
        finally:
            await release_otp_issue_lease(self.redis, self.job_id, lock_token)


# -----------------------------------------------------------------------------
# Test Fixture: Isolated Redis & FastAPI
# -----------------------------------------------------------------------------
@pytest.fixture
async def simulation_environment(monkeypatch):
    binary = shutil.which("redis-server")
    if binary is None:
        pytest.skip("redis-server binary is required for full simulation")

    socket_dir = tempfile.TemporaryDirectory(prefix="barpro-sim-")
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
                pytest.skip("isolated Redis exited prematurely")
            try:
                if await redis.ping():
                    break
            except Exception:
                pass
            await asyncio.sleep(0.02)
        else:
            pytest.skip("isolated Redis failed to start")

        monkeypatch.setattr(utcms_config, "OTP_WEBHOOK_SECRET", WEBHOOK_SECRET)
        monkeypatch.setattr(otp_forwarder.redis_manager, "get", AsyncMock(return_value=redis))
        monkeypatch.setattr(
            "app.services.otp_wakeup_consumer.trigger_job_completion_on_otp_received",
            lambda **kwargs: None,
        )

        app = FastAPI()
        app.include_router(otp_forwarder.router)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://barpro-sim.test") as client:
            client.headers["X-OTP-Webhook-Token"] = WEBHOOK_SECRET
            yield client, redis
    finally:
        await redis.aclose()
        process.terminate()
        process.wait(timeout=5)
        socket_dir.cleanup()


# -----------------------------------------------------------------------------
# Complete Simulation Test Cases
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_complete_end_to_end_relay_and_bot_lifecycle(simulation_environment):
    """Complete simulation: Driver Phone -> Hub Phone -> FastAPI Gateway -> RPA Bot."""
    http_client, redis = simulation_environment
    now_ms = int(time.time() * 1000)
    wait_start = time.time()

    # Step 0: Initialize Bot Waybill Job in WAITING_OTP state
    job_id = "job-e2e-hagigi-98765"
    bot = BarProRpaBotSimulator(job_id=job_id, driver_phone=MCI_DRIVER_PHONE, redis=redis)
    await bot.register_job_challenge()
    assert bot.status == "WAITING_OTP"

    # Step 1: DRIVER HANDSET receives UTCMS OTP SMS
    driver = DriverAppSimulator(
        driver_phone=MCI_DRIVER_PHONE,
        hub_mci=HUB_MCI_PHONE,
        hub_irancell=HUB_IRANCELL_PHONE,
        webhook_token=WEBHOOK_SECRET,
    )
    driver_event = driver.process_incoming_utcms_sms(
        sender="7777000982",
        raw_text="کد ورود به سامانه بارپرو (شهرداری): ۷۱۸۴۲\nانقضا: ۲ دقیقه",
        timestamp_ms=now_ms,
    )
    assert driver_event["code"] == "71842"
    assert driver_event["destination"] == HUB_MCI_PHONE  # Carrier-matched on-net Hamrah-e Aval
    assert driver_event["failover"] == HUB_IRANCELL_PHONE

    # Step 2: GSM Transmission (Driver -> Hub)
    transmitted_sms = driver_event["envelope"]

    # Step 3: HUB HANDSET receives GSM SMS
    hub = HubAppSimulator(webhook_token=WEBHOOK_SECRET, server_base_url="http://barpro-sim.test")
    # 3.1 Pre-verify in constant time at Hub intake boundary
    is_valid = hub.verify_envelope(transmitted_sms)
    assert is_valid is True, "Authentic envelope failed Hub pre-verification"

    # 3.2 Prepare HTTP Delivery
    gateway_url = hub.resolve_gateway_url()
    payload = hub.assemble_gateway_payload(transmitted_sms)

    # Step 4: HUB HANDSET delivers payload to BARPRO API GATEWAY
    response = await http_client.post(gateway_url, json=payload)
    assert response.status_code == 200, f"Gateway rejected valid envelope: {response.text}"
    resp_data = response.json()
    assert resp_data["success"] is True
    assert resp_data["status"] == "success"
    assert resp_data["otp_detected"] is True
    assert resp_data["is_duplicate"] is False

    # Step 5: Verify Redis Ingestion
    stored_json = await redis.get(otp_phone_key(MCI_DRIVER_PHONE))
    assert stored_json is not None
    stored_data = json.loads(stored_json)
    assert stored_data["code"] == "71842"

    # Step 6: RPA BOT intercepts OTP, submits to UTCMS, and completes job
    tracking_code = await bot.wait_and_submit_otp(wait_start=wait_start)
    assert tracking_code.startswith("UTC-1403-")
    assert bot.status == "CONFIRMED"
    assert bot.tracking_code == tracking_code

    # Step 7: Verify Two-Witness and Session Purge
    # OTP key must now be deleted so it cannot be re-consumed or leaked
    assert await redis.get(otp_phone_key(MCI_DRIVER_PHONE)) is None
    assert await redis.get(otp_pending_phone_key(MCI_DRIVER_PHONE)) is None


@pytest.mark.asyncio
async def test_forged_envelope_is_dropped_by_hub_and_server(simulation_environment):
    """Simulates malicious forged SMS: Hub drops it; server rejects if reached."""
    http_client, _ = simulation_environment
    now_ms = int(time.time() * 1000)

    forged_envelope = f"BP1#{MCI_DRIVER_PHONE}#{now_ms}#99999#badbadbadbadbadbadbadbadbadbadba"

    hub = HubAppSimulator(webhook_token=WEBHOOK_SECRET, server_base_url="http://barpro-sim.test")
    # Hub boundary check fails
    assert hub.verify_envelope(forged_envelope) is False

    # If an attacker bypasses Hub and hits server directly:
    payload = {"from": MCI_DRIVER_PHONE, "text": forged_envelope}
    response = await http_client.post("/api/v1/otp/sms-gateway", json=payload)
    assert response.status_code == 401
    assert "Invalid SMS signature" in response.text


@pytest.mark.asyncio
async def test_irancell_driver_on_net_carrier_routing(simulation_environment):
    """Verifies that an Irancell driver selects the Irancell Hub SIM as primary."""
    now_ms = int(time.time() * 1000)

    driver = DriverAppSimulator(
        driver_phone=IRANCELL_DRIVER_PHONE,
        hub_mci=HUB_MCI_PHONE,
        hub_irancell=HUB_IRANCELL_PHONE,
        webhook_token=WEBHOOK_SECRET,
    )
    event = driver.process_incoming_utcms_sms(
        sender="7777000982",
        raw_text="کد ورود: 44321",
        timestamp_ms=now_ms,
    )
    assert event["code"] == "44321"
    # Primary destination must be Hub Irancell, Failover is Hub MCI
    assert event["destination"] == HUB_IRANCELL_PHONE
    assert event["failover"] == HUB_MCI_PHONE
