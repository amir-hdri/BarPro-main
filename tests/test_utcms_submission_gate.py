"""Unit and integration tests for UTCMSSubmissionGate."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import utcms_config
from app.models_rpa import GateStateValue
from app.services.utcms_submission_gate import TEHRAN_TZ, UTCMSSubmissionGate


@pytest.fixture
def gate():
    return UTCMSSubmissionGate()


@pytest.mark.asyncio
async def test_evidence_sanitization(gate):
    evidence = {
        "password": "secret_password_123",
        "otp_code": "123456",
        "token": "bearer_xyz",
        "national_code": "0012345678",
        "mobile": "09120000000",
        "status_code": 200,
        "is_otp_needed": True,
        "nested": {
            "auth_token": "secret_abc",
            "driver_name": "Test Driver",
        },
    }
    sanitized = gate._sanitize_evidence(evidence)
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["otp_code"] == "[REDACTED]"
    assert sanitized["token"] == "[REDACTED]"
    assert sanitized["national_code"] == "[REDACTED]"
    assert sanitized["mobile"] == "[REDACTED]"
    assert sanitized["status_code"] == 200
    assert sanitized["is_otp_needed"] is True
    assert sanitized["nested"]["auth_token"] == "[REDACTED]"


@pytest.mark.asyncio
async def test_predicted_otp_required_window(gate):
    # Within 17:30 - 08:00 window (predicted OTP_REQUIRED)
    dt_evening = datetime(2026, 8, 15, 17, 30, tzinfo=TEHRAN_TZ)
    dt_night = datetime(2026, 8, 15, 2, 0, tzinfo=TEHRAN_TZ)
    dt_morning = datetime(2026, 8, 15, 7, 59, tzinfo=TEHRAN_TZ)
    # Outside window
    dt_day = datetime(2026, 8, 15, 12, 0, tzinfo=TEHRAN_TZ)
    dt_afternoon = datetime(2026, 8, 15, 17, 29, tzinfo=TEHRAN_TZ)

    assert gate.is_in_predicted_otp_required_window(dt_evening) is True
    assert gate.is_in_predicted_otp_required_window(dt_night) is True
    assert gate.is_in_predicted_otp_required_window(dt_morning) is True
    assert gate.is_in_predicted_otp_required_window(dt_day) is False
    assert gate.is_in_predicted_otp_required_window(dt_afternoon) is False


@pytest.mark.asyncio
async def test_is_submission_allowed(gate):
    with patch.object(gate, "get_state", new=AsyncMock(return_value=GateStateValue.OTP_FREE)):
        assert await gate.is_submission_allowed() is True

    with patch.object(gate, "get_state", new=AsyncMock(return_value=GateStateValue.OTP_REQUIRED)):
        assert await gate.is_submission_allowed() is False

    with patch.object(gate, "get_state", new=AsyncMock(return_value=GateStateValue.UNKNOWN)):
        assert await gate.is_submission_allowed() is False

    with patch.object(gate, "get_state", new=AsyncMock(return_value=GateStateValue.DEGRADED)):
        assert await gate.is_submission_allowed() is False


@pytest.mark.asyncio
async def test_dispatch_jitter(gate):
    jitter = gate.get_dispatch_jitter()
    assert 0.8 <= jitter <= max(0.8, utcms_config.GATE_BURST_DISPATCH_JITTER_MAX_SECONDS)


@pytest.mark.asyncio
async def test_probe_lock_owner_token_and_compare_and_delete(gate):
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(side_effect=[True, False])
    mock_redis.eval = AsyncMock(return_value=1)

    with patch("app.services.utcms_submission_gate.redis_manager.get", return_value=mock_redis):
        # Worker 1 acquires lock
        token_1 = await gate.acquire_probe_lock("worker-1")
        assert token_1 is not None
        assert "worker-1" in token_1

        # Worker 2 fails to acquire lock
        token_2 = await gate.acquire_probe_lock("worker-2")
        assert token_2 is None

        # Release lock with token
        released = await gate.release_probe_lock(token_1)
        assert released is True
        mock_redis.eval.assert_called_once()


@pytest.mark.asyncio
async def test_probe_lock_fail_closed_when_redis_none(gate):
    with patch("app.services.utcms_submission_gate.redis_manager.get", return_value=None):
        token = await gate.acquire_probe_lock("worker-1")
        assert token is None


@pytest.mark.asyncio
async def test_cost_settings_alone_does_not_open_gate(gate):
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.eval = AsyncMock(return_value=1)

    with (
        patch("app.services.utcms_submission_gate.redis_manager.get", return_value=mock_redis),
        patch.object(gate, "record_observation", new=AsyncMock()) as mock_record,
        patch.object(gate, "get_state", new=AsyncMock(return_value=GateStateValue.UNKNOWN)),
    ):
        state = await gate.probe_utcms_otp_status(
            worker_id="worker-1",
            cost_settings={"cost": 1000},
            is_otp_needed=None,
        )
        assert state == GateStateValue.UNKNOWN
        mock_record.assert_not_called()


@pytest.mark.asyncio
async def test_explicit_otp_needed_false_opens_gate(gate):
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.eval = AsyncMock(return_value=1)

    with (
        patch("app.services.utcms_submission_gate.redis_manager.get", return_value=mock_redis),
        patch.object(gate, "record_observation", new=AsyncMock()) as mock_record,
    ):
        state = await gate.probe_utcms_otp_status(
            worker_id="worker-1",
            is_otp_needed=False,
        )
        assert state == GateStateValue.OTP_FREE
        mock_record.assert_called_once()
