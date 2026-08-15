"""Global UTCMS Submission Gate service for adaptive OTP detection and scheduling control."""

from __future__ import annotations

import json
import logging
import random
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlmodel import col, desc, select

from app.core.config import utcms_config
from app.core.database import async_session_factory
from app.core.redis_client import redis_manager
from app.models_rpa import GateStateValue, UTCMSSystemObservation

logger = logging.getLogger(__name__)

TEHRAN_TZ = ZoneInfo("Asia/Tehran")


class UTCMSSubmissionGate:
    """Controls whether waybill submission to UTCMS is permitted based on live OTP state.

    Guarantees:
    1. Submissions are gated by adaptive OTP detection, not hardcoded time laws.
    2. 18:00 - 08:00 window is strictly a configurable prediction; at boundary transitions
       the gate reverts to UNKNOWN to force active verification.
    3. Distributed Redis lock ensures single-worker probing.
    4. State is cached in Redis (sub-millisecond decisions) and audited in PostgreSQL.
    """

    KEY_STATE = "rpa:gate:state"
    KEY_META = "rpa:gate:meta"
    KEY_PROBE_LOCK = "rpa:gate:probe_lock"
    KEY_PREDICTION_INVALIDATED = "rpa:gate:prediction_invalidated"
    KEY_MANUAL_OVERRIDE = "rpa:gate:manual_override"

    def __init__(self) -> None:
        self._memory_state: str = GateStateValue.UNKNOWN.value
        self._memory_state_expires_at: float = 0.0
        self._memory_meta: dict[str, Any] = {}

    def get_tehran_now(self) -> datetime:
        """Return current datetime in Asia/Tehran timezone."""
        return datetime.now(TEHRAN_TZ)

    def is_in_predicted_free_window(self, dt: datetime | None = None) -> bool:
        """Check if given Tehran datetime is within the predicted OTP-free window (default 18:00 - 08:00)."""
        tehran_dt = dt or self.get_tehran_now()
        hour = tehran_dt.hour
        start = utcms_config.PREDICTED_OTP_FREE_START_HOUR
        end = utcms_config.PREDICTED_OTP_FREE_END_HOUR

        if start > end:
            # Over-night window (e.g. 18:00 to 08:00)
            return hour >= start or hour < end
        return start <= hour < end

    async def get_state(self) -> GateStateValue:
        """Get the current gate state (from Redis cache, DB observation, or prediction)."""
        redis = await redis_manager.get()

        # 1. Check manual override
        if redis is not None:
            override = await redis.get(self.KEY_MANUAL_OVERRIDE)
            if override and override in GateStateValue:
                return GateStateValue(override)

        # 2. Check fast Redis cache
        if redis is not None:
            cached = await redis.get(self.KEY_STATE)
            if cached and cached in GateStateValue:
                return GateStateValue(cached)
        else:
            if time.time() < self._memory_state_expires_at:
                return GateStateValue(self._memory_state)

        # 3. Check latest observation in DB
        try:
            async with async_session_factory() as session:
                stmt = (
                    select(UTCMSSystemObservation)
                    .order_by(desc(col(UTCMSSystemObservation.observed_at)))
                    .limit(1)
                )
                result = await session.exec(stmt)
                latest_obs = result.first()

                now_utc = datetime.now(UTC).replace(tzinfo=None)
                if latest_obs and latest_obs.valid_until and latest_obs.valid_until > now_utc:
                    state_val = GateStateValue(latest_obs.state)
                    # Prime Redis cache
                    ttl = max(10, int((latest_obs.valid_until - now_utc).total_seconds()))
                    if redis is not None:
                        await redis.set(self.KEY_STATE, state_val.value, ex=ttl)
                    else:
                        self._memory_state = state_val.value
                        self._memory_state_expires_at = time.time() + ttl
                    return state_val
        except Exception:
            logger.debug("failed_to_query_utcms_system_observations_db", exc_info=True)

        # 4. Fallback to adaptive evaluation
        tehran_now = self.get_tehran_now()
        # If at boundary hour (e.g. exactly 08:00), force UNKNOWN
        if tehran_now.hour == utcms_config.PREDICTED_OTP_FREE_END_HOUR and tehran_now.minute < 30:
            return GateStateValue.UNKNOWN

        # Check if prediction is invalidated
        is_invalidated = False
        if redis is not None:
            is_invalidated = bool(await redis.get(self.KEY_PREDICTION_INVALIDATED))

        if self.is_in_predicted_free_window(tehran_now) and not is_invalidated:
            # Inside prediction window without recent probe -> UNKNOWN until confirmed
            return GateStateValue.UNKNOWN

        return GateStateValue.OTP_REQUIRED

    async def is_submission_allowed(self) -> bool:
        """Check if submitting a waybill is currently permitted."""
        state = await self.get_state()
        if state == GateStateValue.OTP_FREE:
            return True
        if state == GateStateValue.OTP_REQUIRED:
            return False
        # If UNKNOWN or DEGRADED, only allowed if operator explicitly enabled live submit
        return utcms_config.ALLOW_LIVE_SUBMIT and state != GateStateValue.OTP_REQUIRED

    async def record_observation(
        self,
        state: GateStateValue,
        source: str,
        worker_id: str | None = None,
        evidence: dict[str, Any] | None = None,
        valid_duration_seconds: int | None = None,
    ) -> None:
        """Persist a new UTCMS system observation and update fast cache."""
        now_utc = datetime.now(UTC).replace(tzinfo=None)
        validity = valid_duration_seconds or utcms_config.GATE_OBSERVATION_VALIDITY_SECONDS
        valid_until = now_utc + timedelta(seconds=validity)
        next_probe_at = now_utc + timedelta(seconds=utcms_config.GATE_PROBE_INTERVAL_SECONDS)

        # Sanitize evidence (no passwords, tokens, full names, or OTP values)
        sanitized_evidence = self._sanitize_evidence(evidence or {})

        async with async_session_factory() as session:
            obs = UTCMSSystemObservation(
                state=state.value,
                observed_at=now_utc,
                valid_until=valid_until,
                next_probe_at=next_probe_at,
                source=source,
                worker_id=worker_id,
                evidence_json=json.dumps(sanitized_evidence, ensure_ascii=False),
            )
            session.add(obs)
            await session.commit()

        # Update Redis cache
        redis = await redis_manager.get()
        if redis is not None:
            await redis.set(self.KEY_STATE, state.value, ex=validity)
            meta = {
                "state": state.value,
                "observed_at": now_utc.isoformat(),
                "valid_until": valid_until.isoformat(),
                "next_probe_at": next_probe_at.isoformat(),
                "source": source,
                "worker_id": worker_id,
            }
            await redis.set(self.KEY_META, json.dumps(meta), ex=validity)

            # If OTP appeared during predicted window, invalidate prediction
            if state == GateStateValue.OTP_REQUIRED and self.is_in_predicted_free_window():
                logger.warning(
                    "unexpected_otp_during_predicted_free_window",
                    extra={"extra_fields": {"worker_id": worker_id, "source": source}},
                )
                await redis.set(self.KEY_PREDICTION_INVALIDATED, "1", ex=86400)
        else:
            self._memory_state = state.value
            self._memory_state_expires_at = time.time() + validity
            self._memory_meta = {
                "state": state.value,
                "observed_at": now_utc.isoformat(),
                "valid_until": valid_until.isoformat(),
            }

    async def record_otp_detected(
        self,
        worker_id: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        """Shortcut to record OTP challenge detection (immediately closes Gate)."""
        logger.warning("utcms_gate_otp_detected_closing_gate", extra={"extra_fields": {"worker_id": worker_id}})
        await self.record_observation(
            state=GateStateValue.OTP_REQUIRED,
            source="otp_detected",
            worker_id=worker_id,
            evidence=evidence,
            valid_duration_seconds=utcms_config.GATE_OBSERVATION_VALIDITY_SECONDS,
        )

    async def record_otp_free(
        self,
        worker_id: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        """Shortcut to record confirmed OTP-free system state."""
        logger.info("utcms_gate_otp_free_opening_gate", extra={"extra_fields": {"worker_id": worker_id}})
        await self.record_observation(
            state=GateStateValue.OTP_FREE,
            source="probe_confirmed",
            worker_id=worker_id,
            evidence=evidence,
            valid_duration_seconds=utcms_config.GATE_OBSERVATION_VALIDITY_SECONDS,
        )

    async def acquire_probe_lock(self, worker_id: str) -> bool:
        """Acquire distributed lock for probing UTCMS."""
        redis = await redis_manager.get()
        ttl = utcms_config.GATE_PROBE_LOCK_TTL_SECONDS
        if redis is not None:
            return bool(await redis.set(self.KEY_PROBE_LOCK, worker_id, ex=ttl, nx=True))
        return True

    async def release_probe_lock(self) -> None:
        """Release distributed probe lock."""
        redis = await redis_manager.get()
        if redis is not None:
            await redis.delete(self.KEY_PROBE_LOCK)

    async def probe_utcms_otp_status(
        self,
        worker_id: str,
        cost_settings: dict[str, Any] | None = None,
        is_otp_modal_detected: bool = False,
    ) -> GateStateValue:
        """Perform an adaptive probe evaluation under distributed lock."""
        locked = await self.acquire_probe_lock(worker_id)
        if not locked:
            # Another worker is currently probing; return current gate state
            return await self.get_state()

        try:
            if is_otp_modal_detected:
                await self.record_otp_detected(worker_id=worker_id, evidence={"reason": "otp_modal_detected"})
                return GateStateValue.OTP_REQUIRED

            if cost_settings:
                evidence = {"cost_settings": cost_settings, "probed_at": datetime.now(UTC).isoformat()}
                await self.record_otp_free(worker_id=worker_id, evidence=evidence)
                return GateStateValue.OTP_FREE

            return await self.get_state()
        finally:
            await self.release_probe_lock()

    def get_dispatch_jitter(self) -> float:
        """Generate randomized jitter delay (seconds) to prevent submit thundering herd."""
        max_jitter = max(0.8, utcms_config.GATE_BURST_DISPATCH_JITTER_MAX_SECONDS)
        return random.uniform(0.8, max_jitter)

    @staticmethod
    def _sanitize_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
        """Strip credentials, OTP values, cookies, tokens, and PII from evidence."""
        sanitized: dict[str, Any] = {}
        blocked_keys = {
            "password",
            "passwd",
            "pwd",
            "otp",
            "otp_code",
            "token",
            "access_token",
            "auth_token",
            "cookie",
            "session",
            "authorization",
            "secret",
            "national_code",
            "nationalcode",
            "mobile",
            "phone",
        }
        for k, v in evidence.items():
            k_lower = str(k).lower()
            is_blocked = (
                k_lower in blocked_keys
                or any(k_lower.endswith(f"_{s}") for s in ("password", "token", "secret", "cookie", "otp", "mobile"))
                or any(k_lower.startswith(f"{s}_") for s in ("token", "secret", "cookie", "otp"))
            )
            # Do not redact operational boolean flags or configs
            if k_lower in {"is_otp_needed", "is_otp_active", "otp_validity_period", "otpvalidityperiod"}:
                is_blocked = False

            if is_blocked:
                sanitized[k] = "[REDACTED]"
            elif isinstance(v, dict):
                sanitized[k] = UTCMSSubmissionGate._sanitize_evidence(v)
            elif isinstance(v, (str, int, float, bool)) or v is None:
                sanitized[k] = v
            else:
                sanitized[k] = str(v)
        return sanitized


utcms_submission_gate = UTCMSSubmissionGate()
