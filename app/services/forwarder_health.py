"""Recorded setup and observed health, never a guarantee of current SMS readiness."""

from __future__ import annotations

import json
import re
import time
from typing import Any

from fastapi import HTTPException

# A single transaction prevents simultaneous HTTP/SMS writes losing observations.
# Setup has no inactivity expiry; probe receipts expire after the acceptance window.
MERGE_OBSERVATION = """
local receipt = nil
if ARGV[2] ~= '' then
    local existing = redis.call('GET', KEYS[2])
    if existing then return {existing, 1} end
    receipt = cjson.decode(ARGV[2])
end
local raw = redis.call('GET', KEYS[1])
local state = {}
if raw then state = cjson.decode(raw) end
local incoming = cjson.decode(ARGV[1])
if not state.connected_at then state.connected_at = incoming.last_seen end
if not state.last_seen or incoming.last_seen >= state.last_seen then
    if incoming.device_id and state.device_id and incoming.device_id ~= state.device_id then
        state.permissions = nil
        state.permissions_observed_at = nil
    end
    for key, value in pairs(incoming) do state[key] = value end
end
redis.call('SET', KEYS[1], cjson.encode(state))
if receipt then redis.call('SET', KEYS[2], ARGV[2], 'EX', 600) end
return {ARGV[2], 0}
"""


def probe_timestamp_ms(value: Any) -> int:
    """Strict probe freshness: no legacy OTP timezone compensation for a new test."""
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]{1,16}", str(value)):
        raise HTTPException(status_code=422, detail="Invalid probe timestamp")
    timestamp = int(value)
    if timestamp <= 100_000_000_000:
        timestamp *= 1000
    age_ms = time.time() * 1000 - timestamp
    if age_ms >= 300_000:
        raise HTTPException(status_code=410, detail="SMS probe has expired")
    if age_ms < -30_000:
        raise HTTPException(status_code=422, detail="Probe timestamp is in the future; check device clock")
    return timestamp


def probe_key(phone: str, timestamp: int) -> str:
    return f"rpa:forwarder:probe:{phone}:{timestamp}"


def permission_observation(value: Any) -> dict[str, bool]:
    allowed = {"receive_sms", "send_sms", "battery_optimization_ignored"}
    if not isinstance(value, dict) or any(k not in allowed or type(v) is not bool for k, v in value.items()):
        raise HTTPException(status_code=422, detail="Invalid permission observation")
    return value


async def record_observation(
    redis: Any,
    phone: str,
    *,
    via: str,
    permissions: dict[str, bool] | None = None,
    device_id: str = "",
    probe_timestamp: int | None = None,
) -> dict[str, Any]:
    if redis is None:
        raise ConnectionError("Redis unavailable")
    now = time.time()
    observation: dict[str, Any] = {"phone": phone, "last_seen": now, "via": via}
    observation["last_health_at" if via == "http_health_check" else "last_sms_at"] = now
    if permissions:
        observation.update(permissions=permissions, permissions_observed_at=now)
    if device_id:
        observation["device_id"] = device_id
    receipt = (
        {"phone": phone, "probe_timestamp": probe_timestamp, "received_at": now} if probe_timestamp is not None else {}
    )
    if hasattr(redis, "eval") and callable(redis.eval):
        try:
            result = await redis.eval(
                MERGE_OBSERVATION,
                2,
                f"rpa:forwarder:connected:{phone}",
                (
                    probe_key(phone, probe_timestamp)
                    if probe_timestamp is not None
                    else f"rpa:forwarder:connected:{phone}"
                ),
                json.dumps(observation),
                json.dumps(receipt) if receipt else "",
            )
            return {**(json.loads(result[0]) if receipt else {}), "is_duplicate": bool(result[1])}
        except (NotImplementedError, AttributeError):
            pass

    # Fallback when redis.eval is not supported (e.g. in-memory test mocks)
    key1 = f"rpa:forwarder:connected:{phone}"
    raw = await redis.get(key1)
    state: dict[str, Any] = {}
    if raw:
        try:
            state = json.loads(raw)
        except Exception:
            state = {}
    if not state.get("connected_at"):
        state["connected_at"] = observation.get("last_seen")
    if not state.get("last_seen") or (observation.get("last_seen", 0) >= state.get("last_seen", 0)):
        if observation.get("device_id") and state.get("device_id") and observation["device_id"] != state["device_id"]:
            state.pop("permissions", None)
            state.pop("permissions_observed_at", None)
        state.update(observation)
    await redis.set(key1, json.dumps(state), ex=86400 * 90)

    is_duplicate = False
    if receipt and probe_timestamp is not None:
        key2 = probe_key(phone, probe_timestamp)
        existing = await redis.get(key2)
        if existing:
            is_duplicate = True
            try:
                receipt = json.loads(existing)
            except Exception:
                pass
        else:
            await redis.set(key2, json.dumps(receipt), ex=600)
    return {**receipt, "is_duplicate": is_duplicate}
