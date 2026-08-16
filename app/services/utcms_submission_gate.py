"""Global UTCMS Submission Gate service for adaptive OTP detection and scheduling control."""

from __future__ import annotations

import json
import logging
import random
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlmodel import col, desc, select

from app.core.config import utcms_config
from app.core.database import async_session_factory
from app.core.redis_client import redis_manager
from app.models_rpa import GateStateValue, UTCMSSystemObservation
from app.monitoring.metrics import set_gate_state_metric, track_otp_detected

logger = logging.getLogger(__name__)

TEHRAN_TZ = ZoneInfo("Asia/Tehran")

_COMPARE_AND_DELETE_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


class UTCMSSubmissionGate:
    """Controls whether waybill submission to UTCMS is permitted based on live OTP state.

    Guarantees:
    1. Submissions are gated by adaptive OTP detection, not hardcoded time laws.
    2. 18:00 - 08:00 window is strictly a configurable prediction of OTP_REQUIRED.
    3. ONLY confirmed OTP_FREE state allows submissions. UNKNOWN and DEGRADED are closed.
    4. Distributed Redis lock with owner token and compare-and-delete ensures single-worker probing.
    5. Probing and gate evaluation are fail-closed when Redis is unavailable.
    6. State is cached in Redis (sub-millisecond decisions) and audited in PostgreSQL.
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

    def is_in_predicted_otp_required_window(self, dt: datetime | None = None) -> bool:
        """Check if given Tehran datetime is within the predicted OTP_REQUIRED window (default 18:00 - 08:00)."""
        tehran_dt = dt or self.get_tehran_now()
        hour = tehran_dt.hour
        start = getattr(
            utcms_config,
            "PREDICTED_OTP_REQUIRED_START_HOUR",
            getattr(utcms_config, "PREDICTED_OTP_FREE_START_HOUR", 18),
        )
        end = getattr(
            utcms_config,
            "PREDICTED_OTP_REQUIRED_END_HOUR",
            getattr(utcms_config, "PREDICTED_OTP_FREE_END_HOUR", 8),
        )

        if start > end:
            # Over-night window (e.g. 18:00 to 08:00)
            return hour >= start or hour < end
        return start <= hour < end

    def is_in_predicted_free_window(self, dt: datetime | None = None) -> bool:
        """Compatibility alias. Returns the logical opposite of the OTP_REQUIRED window."""
        return not self.is_in_predicted_otp_required_window(dt)

    async def get_state(self) -> GateStateValue:
        """Get the current gate state (from Redis cache, DB observation, or prediction)."""
        redis = await redis_manager.get()

        # 1. Check manual override
        if redis is not None:
            override = await redis.get(self.KEY_MANUAL_OVERRIDE)
            if override and override in GateStateValue:
                state_val = GateStateValue(override)
                set_gate_state_metric(state_val.value)
                return state_val

        # 2. Check fast Redis cache
        if redis is not None:
            cached = await redis.get(self.KEY_STATE)
            if cached and cached in GateStateValue:
                state_val = GateStateValue(cached)
                set_gate_state_metric(state_val.value)
                return state_val
        else:
            if time.time() < self._memory_state_expires_at:
                state_val = GateStateValue(self._memory_state)
                set_gate_state_metric(state_val.value)
                return state_val

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
                    set_gate_state_metric(state_val.value)
                    return state_val
        except Exception:
            logger.debug("failed_to_query_utcms_system_observations_db", exc_info=True)

        # 4. Fallback to adaptive evaluation
        tehran_now = self.get_tehran_now()
        # If in predicted OTP required window -> OTP_REQUIRED
        if self.is_in_predicted_otp_required_window(tehran_now):
            set_gate_state_metric(GateStateValue.OTP_REQUIRED.value)
            return GateStateValue.OTP_REQUIRED

        # Outside predicted window without live observation -> UNKNOWN (fail-closed until probed)
        set_gate_state_metric(GateStateValue.UNKNOWN.value)
        return GateStateValue.UNKNOWN

    async def is_submission_allowed(self) -> bool:
        """Check if submitting a waybill is currently permitted.

        ONLY confirmed OTP_FREE state allows submissions.
        UNKNOWN, DEGRADED, and OTP_REQUIRED are strictly closed.
        """
        state = await self.get_state()
        return state == GateStateValue.OTP_FREE

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

            if state == GateStateValue.OTP_REQUIRED:
                await redis.set(self.KEY_PREDICTION_INVALIDATED, "1", ex=86400)
        else:
            self._memory_state = state.value
            self._memory_state_expires_at = time.time() + validity
            self._memory_meta = {
                "state": state.value,
                "observed_at": now_utc.isoformat(),
                "valid_until": valid_until.isoformat(),
            }

        set_gate_state_metric(state.value)

    async def record_otp_detected(
        self,
        worker_id: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        """Shortcut to record OTP challenge detection (immediately closes Gate)."""
        logger.warning("utcms_gate_otp_detected_closing_gate", extra={"extra_fields": {"worker_id": worker_id}})
        track_otp_detected()
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

    async def acquire_probe_lock(self, worker_id: str, owner_token: str | None = None) -> str | None:
        """Acquire distributed lock for probing UTCMS.

        Returns the owner_token if lock was acquired, or None if lock failed / Redis unavailable (fail-closed).
        """
        redis = await redis_manager.get()
        if redis is None:
            # Fail-closed: Cannot acquire distributed probe lock without Redis
            return None

        token = owner_token or f"{worker_id}:{uuid.uuid4().hex}"
        ttl = utcms_config.GATE_PROBE_LOCK_TTL_SECONDS
        try:
            acquired = bool(await redis.set(self.KEY_PROBE_LOCK, token, ex=ttl, nx=True))
            return token if acquired else None
        except Exception:
            logger.debug("utcms_gate_probe_lock_acquire_failed", exc_info=True)
            return None

    async def release_probe_lock(self, owner_token: str | None) -> bool:
        """Release distributed probe lock with compare-and-delete atomic safety."""
        if not owner_token:
            return False

        redis = await redis_manager.get()
        if redis is None:
            return False

        try:
            result = await redis.eval(_COMPARE_AND_DELETE_LUA, 1, self.KEY_PROBE_LOCK, owner_token)
            return bool(result)
        except Exception:
            logger.debug("utcms_gate_probe_lock_release_failed", exc_info=True)
            return False

    async def probe_utcms_otp_status(
        self,
        worker_id: str,
        cost_settings: dict[str, Any] | None = None,
        is_otp_modal_detected: bool = False,
        is_otp_needed: bool | None = None,
    ) -> GateStateValue:
        """Perform an adaptive probe evaluation under distributed lock."""
        owner_token = await self.acquire_probe_lock(worker_id)
        if not owner_token:
            # Another worker is currently probing or Redis down; return current gate state
            return await self.get_state()

        try:
            if is_otp_modal_detected:
                await self.record_otp_detected(worker_id=worker_id, evidence={"reason": "otp_modal_detected"})
                return GateStateValue.OTP_REQUIRED

            # GetCostSettings alone must NOT open Gate! Only explicit OTP exemption observation opens Gate.
            if is_otp_needed is False:
                evidence = {
                    "is_otp_needed": False,
                    "cost_settings_available": bool(cost_settings),
                    "probed_at": datetime.now(UTC).isoformat(),
                }
                await self.record_otp_free(worker_id=worker_id, evidence=evidence)
                return GateStateValue.OTP_FREE
            elif is_otp_needed is True:
                await self.record_otp_detected(worker_id=worker_id, evidence={"is_otp_needed": True})
                return GateStateValue.OTP_REQUIRED

            return await self.get_state()
        finally:
            await self.release_probe_lock(owner_token)

    async def perform_periodic_probe(self, worker_id: str) -> GateStateValue:
        """Low-rate production probe execution to refresh gate state."""
        owner_token = await self.acquire_probe_lock(worker_id)
        if not owner_token:
            logger.debug("periodic_probe_skipped_lock_held", extra={"extra_fields": {"worker_id": worker_id}})
            return await self.get_state()

        try:
            # Check current state from DB or Redis
            state = await self.get_state()
            logger.info(
                "periodic_probe_evaluated_state",
                extra={"extra_fields": {"worker_id": worker_id, "state": state.value}},
            )
            return state
        finally:
            await self.release_probe_lock(owner_token)

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
