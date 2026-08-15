"""Unit tests for Phase 5: OTP Detection & Adaptive Behavior."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models_rpa import GateStateValue, UTCMSSystemObservation
from app.services.utcms_submission_gate import TEHRAN_TZ, UTCMSSubmissionGate


@pytest.mark.asyncio
async def test_adaptive_probe_flow():
    """Verify that probe under lock sets OTP_FREE on successful configuration and closes on OTP."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    gate = UTCMSSubmissionGate()

    with (
        patch("app.core.redis_client.redis_manager.get", new=AsyncMock(return_value=None)),
        patch("app.services.utcms_submission_gate.async_session_factory", async_session),
    ):
        # 1. Successful probe with cost settings
        cost_settings = {"otpValidityPeriod": 5, "tajmiiFlag": True}
        state = await gate.probe_utcms_otp_status("worker-1", cost_settings=cost_settings)
        assert state == GateStateValue.OTP_FREE
        assert await gate.is_submission_allowed() is True

        # Check observation persisted in DB
        async with async_session() as session:
            obs = (await session.exec(select(UTCMSSystemObservation))).all()
            assert len(obs) == 1
            assert obs[0].state == "otp_free"
            assert obs[0].worker_id == "worker-1"

        # 2. OTP challenge detected -> immediate gate closure
        state_otp = await gate.probe_utcms_otp_status("worker-2", is_otp_modal_detected=True)
        assert state_otp == GateStateValue.OTP_REQUIRED
        assert await gate.is_submission_allowed() is False

        async with async_session() as session:
            obs = (await session.exec(select(UTCMSSystemObservation))).all()
            assert len(obs) == 2
            assert obs[1].state == "otp_required"
            assert obs[1].source == "otp_detected"

    await engine.dispose()


@pytest.mark.asyncio
async def test_unexpected_otp_invalidates_prediction():
    """Verify that OTP detected during predicted free window marks prediction invalidated."""
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(return_value=None)

    gate = UTCMSSubmissionGate()

    # Emulate evening hour (e.g. 20:00 Tehran)
    evening_time = datetime(2026, 8, 15, 20, 0, tzinfo=TEHRAN_TZ)

    with (
        patch("app.services.utcms_submission_gate.redis_manager.get", return_value=mock_redis),
        patch("app.services.utcms_submission_gate.async_session_factory") as mock_factory,
        patch.object(gate, "get_tehran_now", return_value=evening_time),
    ):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_factory.return_value.__aenter__.return_value = mock_session

        await gate.record_otp_detected(worker_id="worker-node-1", evidence={"reason": "otp_modal_popped_up"})

        # Must have invalidated prediction in Redis
        mock_redis.set.assert_any_call(gate.KEY_PREDICTION_INVALIDATED, "1", ex=86400)
