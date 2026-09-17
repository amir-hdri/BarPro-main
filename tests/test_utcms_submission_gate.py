"""Unit and integration tests for UTCMSSubmissionGate."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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
async def test_daytime_state_fails_closed_without_redis_or_observation(gate):
    daytime = datetime(2026, 8, 15, 12, 0, tzinfo=TEHRAN_TZ)
    with (
        patch("app.services.utcms_submission_gate.redis_manager.get", return_value=None),
        patch("app.services.utcms_submission_gate.async_session_factory", side_effect=RuntimeError("db unavailable")),
        patch.object(gate, "get_tehran_now", return_value=daytime),
    ):
        assert await gate.get_state() == GateStateValue.UNKNOWN
        assert await gate.is_submission_allowed() is False


@pytest.mark.asyncio
async def test_missing_live_evidence_is_unknown_even_inside_predicted_window(gate):
    predicted_night = datetime(2026, 8, 15, 2, 0, tzinfo=TEHRAN_TZ)
    with (
        patch("app.services.utcms_submission_gate.redis_manager.get", return_value=None),
        patch("app.services.utcms_submission_gate.async_session_factory", side_effect=RuntimeError("db unavailable")),
        patch.object(gate, "get_tehran_now", return_value=predicted_night),
    ):
        assert gate.is_in_predicted_otp_required_window(predicted_night) is True
        assert await gate.get_state() == GateStateValue.UNKNOWN
        assert await gate.is_submission_allowed() is False


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


@pytest.mark.parametrize(
    "ttl,meta_kind", [(-1, "fresh"), (0, "fresh"), (300, "missing"), (300, "expired"), (300, "mismatch")]
)
async def test_unverified_cached_exemption_cannot_open_gate(gate, ttl, meta_kind):
    now = datetime.now(UTC)
    meta = {
        "state": "otp_required" if meta_kind == "mismatch" else "otp_free",
        "observed_at": (now - timedelta(minutes=1)).isoformat(),
        "valid_until": (now + timedelta(seconds=-1 if meta_kind == "expired" else 300)).isoformat(),
    }
    cache = {gate.KEY_STATE: "otp_free", gate.KEY_META: None if meta_kind == "missing" else json.dumps(meta)}
    redis = AsyncMock()
    redis.get.side_effect = lambda key: cache.get(key)
    redis.ttl.return_value = ttl
    with (
        patch("app.services.utcms_submission_gate.redis_manager.get", return_value=redis),
        patch("app.services.utcms_submission_gate.async_session_factory", side_effect=RuntimeError("db unavailable")),
    ):
        assert await gate.is_submission_allowed() is False


async def test_fresh_expiring_observation_opens_gate(gate):
    now = datetime.now(UTC)
    cache = {
        gate.KEY_STATE: "otp_free",
        gate.KEY_META: json.dumps(
            {
                "state": "otp_free",
                "observed_at": now.isoformat(),
                "valid_until": (now + timedelta(minutes=5)).isoformat(),
            }
        ),
    }
    redis = AsyncMock()
    redis.get.side_effect = lambda key: cache.get(key)
    redis.ttl.return_value = 300
    with patch("app.services.utcms_submission_gate.redis_manager.get", return_value=redis):
        assert await gate.is_submission_allowed() is True


async def test_production_manual_override_cannot_grant_exemption(gate, monkeypatch):
    monkeypatch.setattr(utcms_config, "ENVIRONMENT", "production")
    redis = AsyncMock()
    redis.get.side_effect = lambda key: "otp_free" if key == gate.KEY_MANUAL_OVERRIDE else None
    with (
        patch("app.services.utcms_submission_gate.redis_manager.get", return_value=redis),
        patch("app.services.utcms_submission_gate.async_session_factory", side_effect=RuntimeError("db unavailable")),
    ):
        assert await gate.is_submission_allowed() is False


def observation_session(observation):
    session = AsyncMock()
    result = MagicMock()
    result.first.return_value = observation
    session.exec.return_value = result
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory


async def test_database_observation_does_not_extend_memory_expiry(gate):
    now = datetime.now(UTC)
    valid_until = now + timedelta(seconds=1)
    observation = SimpleNamespace(
        state="otp_free",
        observed_at=(now - timedelta(minutes=1)).replace(tzinfo=None),
        valid_until=valid_until.replace(tzinfo=None),
        source="probe_confirmed",
        worker_id="test-worker",
    )
    with (
        patch("app.services.utcms_submission_gate.redis_manager.get", return_value=None),
        patch("app.services.utcms_submission_gate.async_session_factory", observation_session(observation)),
    ):
        assert await gate.is_submission_allowed() is True
    assert gate._memory_state_expires_at <= valid_until.timestamp()
    with (
        patch("app.services.utcms_submission_gate.redis_manager.get", return_value=None),
        patch("app.services.utcms_submission_gate.async_session_factory", side_effect=RuntimeError("db unavailable")),
        patch("app.services.utcms_submission_gate.time.time", return_value=valid_until.timestamp() + 1),
    ):
        assert await gate.is_submission_allowed() is False


@pytest.mark.parametrize("observed_offset,valid_offset", [(300, 600), (300, 100), (-300, -1)])
async def test_database_requires_current_consistent_observation(gate, observed_offset, valid_offset):
    now = datetime.now(UTC).replace(tzinfo=None)
    observation = SimpleNamespace(
        state="otp_free",
        observed_at=now + timedelta(seconds=observed_offset),
        valid_until=now + timedelta(seconds=valid_offset),
        source="probe_confirmed",
        worker_id="test-worker",
    )
    with (
        patch("app.services.utcms_submission_gate.redis_manager.get", return_value=None),
        patch("app.services.utcms_submission_gate.async_session_factory", observation_session(observation)),
    ):
        assert await gate.is_submission_allowed() is False


@pytest.mark.parametrize("meta_kind", ["missing", "expired", "future", "mismatch", "inconsistent"])
async def test_memory_flag_cannot_open_gate_without_current_matching_evidence(gate, meta_kind):
    now = datetime.now(UTC)
    gate._memory_state = "otp_free"
    gate._memory_state_expires_at = now.timestamp() + 300
    gate._memory_meta = (
        {}
        if meta_kind == "missing"
        else {
            "state": "otp_required" if meta_kind == "mismatch" else "otp_free",
            "observed_at": (
                now + timedelta(seconds=600 if meta_kind in {"future", "inconsistent"} else -60)
            ).isoformat(),
            "valid_until": (
                now + timedelta(seconds=-1 if meta_kind == "expired" else 900 if meta_kind == "future" else 300)
            ).isoformat(),
        }
    )
    with (
        patch("app.services.utcms_submission_gate.redis_manager.get", return_value=None),
        patch("app.services.utcms_submission_gate.async_session_factory", side_effect=RuntimeError("db unavailable")),
    ):
        assert await gate.is_submission_allowed() is False


async def test_valid_memory_evidence_remains_available_during_redis_outage(gate):
    now = datetime.now(UTC)
    observation = SimpleNamespace(
        state="otp_free",
        observed_at=(now - timedelta(seconds=1)).replace(tzinfo=None),
        valid_until=(now + timedelta(seconds=30)).replace(tzinfo=None),
        source="probe_confirmed",
        worker_id="test-worker",
    )
    with (
        patch("app.services.utcms_submission_gate.redis_manager.get", return_value=None),
        patch("app.services.utcms_submission_gate.async_session_factory", observation_session(observation)),
    ):
        assert await gate.is_submission_allowed() is True
    with (
        patch("app.services.utcms_submission_gate.redis_manager.get", return_value=None),
        patch("app.services.utcms_submission_gate.async_session_factory", side_effect=RuntimeError("db unavailable")),
    ):
        assert await gate.is_submission_allowed() is True
