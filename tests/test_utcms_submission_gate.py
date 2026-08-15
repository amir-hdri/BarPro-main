"""Unit and integration tests for UTCMSSubmissionGate."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

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
async def test_predicted_free_window(gate):
    # Within 18:00 - 08:00 window
    dt_evening = datetime(2026, 8, 15, 20, 0, tzinfo=TEHRAN_TZ)
    dt_night = datetime(2026, 8, 15, 2, 0, tzinfo=TEHRAN_TZ)
    dt_morning = datetime(2026, 8, 15, 7, 59, tzinfo=TEHRAN_TZ)
    # Outside window
    dt_day = datetime(2026, 8, 15, 12, 0, tzinfo=TEHRAN_TZ)
    dt_afternoon = datetime(2026, 8, 15, 17, 59, tzinfo=TEHRAN_TZ)

    assert gate.is_in_predicted_free_window(dt_evening) is True
    assert gate.is_in_predicted_free_window(dt_night) is True
    assert gate.is_in_predicted_free_window(dt_morning) is True
    assert gate.is_in_predicted_free_window(dt_day) is False
    assert gate.is_in_predicted_free_window(dt_afternoon) is False


@pytest.mark.asyncio
async def test_is_submission_allowed(gate):
    with patch.object(gate, "get_state", new=AsyncMock(return_value=GateStateValue.OTP_FREE)):
        assert await gate.is_submission_allowed() is True

    with patch.object(gate, "get_state", new=AsyncMock(return_value=GateStateValue.OTP_REQUIRED)):
        assert await gate.is_submission_allowed() is False

    with patch.object(gate, "get_state", new=AsyncMock(return_value=GateStateValue.UNKNOWN)):
        with patch.object(utcms_config, "ALLOW_LIVE_SUBMIT", False):
            assert await gate.is_submission_allowed() is False
        with patch.object(utcms_config, "ALLOW_LIVE_SUBMIT", True):
            assert await gate.is_submission_allowed() is True


@pytest.mark.asyncio
async def test_dispatch_jitter(gate):
    jitter = gate.get_dispatch_jitter()
    assert 0.8 <= jitter <= max(0.8, utcms_config.GATE_BURST_DISPATCH_JITTER_MAX_SECONDS)


@pytest.mark.asyncio
async def test_probe_lock_mocked(gate):
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(side_effect=[True, False])
    mock_redis.delete = AsyncMock(return_value=1)

    with patch("app.services.utcms_submission_gate.redis_manager.get", return_value=mock_redis):
        # Worker 1 acquires lock
        acquired_1 = await gate.acquire_probe_lock("worker-1")
        assert acquired_1 is True

        # Worker 2 fails to acquire lock
        acquired_2 = await gate.acquire_probe_lock("worker-2")
        assert acquired_2 is False

        # Release lock
        await gate.release_probe_lock()
        mock_redis.delete.assert_called_once_with(gate.KEY_PROBE_LOCK)
