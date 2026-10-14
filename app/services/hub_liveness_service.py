"""Hub phone (SMS relay) liveness evaluation.

Splits the Hub heartbeat concern into two explicit halves:

* :func:`read_hub_state` / :func:`evaluate_hub_liveness` — pure, read-only
  computation used by the admin ``GET /hub-status`` endpoint.
* :func:`sweep_hub_liveness` — the mutating half (raise / auto-acknowledge the
  ``hub:disconnected`` admin alert), driven by Celery beat.

Why the split: the alert previously lived inside the admin GET, so a Hub outage
only produced an alert while an administrator happened to have the dashboard
open. Monitoring that cannot fire unattended is not monitoring. The sweep now
runs on beat, and the GET is a side-effect-free read.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import InstrumentedAttribute
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import utcms_config
from app.core.redis_client import redis_manager
from app.models.admin import AdminAlert
from app.orchestrator.alert_manager import admin_alert_service

logger = logging.getLogger(__name__)

HUB_STATE_KEY = "rpa:forwarder:hub:connected"
HUB_DISCONNECTED_DEDUPE_KEY = "hub:disconnected"

_alert_dedupe_key_col = cast(InstrumentedAttribute[str], AdminAlert.dedupe_key)
_alert_is_acknowledged_col = cast(InstrumentedAttribute[bool], AdminAlert.is_acknowledged)


@dataclass(frozen=True)
class HubLiveness:
    """Immutable snapshot of Hub connectivity derived from the Redis heartbeat."""

    is_connected: bool
    last_seen: float | None
    seconds_ago: int | None
    last_heartbeat_iso: str | None
    device_id: str
    hub_numbers: list[str]
    permissions: dict[str, Any]
    stale_after_seconds: int

    @property
    def status(self) -> str:
        return "connected" if self.is_connected else "disconnected"

    @property
    def message(self) -> str:
        return "گوشی هاب آنلاین و متصل است" if self.is_connected else "ارتباط گوشی هاب قطع شده است"

    def to_payload(self) -> dict[str, Any]:
        """Serialise for the admin API. Key set is part of the frontend contract."""
        return {
            "status": self.status,
            "is_connected": self.is_connected,
            "last_seen": self.last_seen,
            "seconds_ago": self.seconds_ago,
            "seconds_since_last_heartbeat": self.seconds_ago,
            "last_heartbeat_at": self.last_heartbeat_iso,
            "last_heartbeat_iso": self.last_heartbeat_iso,
            "device_id": self.device_id,
            "hub_numbers": self.hub_numbers,
            "permissions": self.permissions,
            "stale_after_seconds": self.stale_after_seconds,
            "message": self.message,
        }


async def read_hub_state() -> dict[str, Any]:
    """Fetch the raw Hub heartbeat blob from Redis. Never raises."""
    try:
        r = await redis_manager.get()
        if r:
            raw = await r.get(HUB_STATE_KEY)
            if raw:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
    except Exception as exc:
        logger.warning("Failed to fetch hub status from Redis: %s", exc)
    return {}


def evaluate_hub_liveness(hub_state: dict[str, Any], *, now: float | None = None) -> HubLiveness:
    """Pure projection of a heartbeat blob onto a :class:`HubLiveness`.

    `stale_after` is deliberately a *multiple* of the Hub ping interval (see
    ``utcms_config.HUB_HEARTBEAT_STALE_SECONDS``). Using the bare interval makes the
    check flap on every healthy cycle.
    """
    moment = time.time() if now is None else now
    stale_after = max(1, utcms_config.HUB_HEARTBEAT_STALE_SECONDS)

    raw_last_seen = hub_state.get("last_seen")
    last_seen = float(raw_last_seen) if isinstance(raw_last_seen, int | float) else None

    seconds_ago = int(moment - last_seen) if last_seen is not None else None
    is_connected = last_seen is not None and (moment - last_seen) < stale_after
    last_heartbeat_iso = datetime.fromtimestamp(last_seen, UTC).isoformat() if last_seen is not None else None

    raw_numbers = hub_state.get("hub_numbers")
    hub_numbers = (
        [str(n) for n in raw_numbers]
        if isinstance(raw_numbers, list) and raw_numbers
        else list(utcms_config.HUB_NUMBERS)
    )

    raw_permissions = hub_state.get("permissions")
    device_id = hub_state.get("device_id")

    return HubLiveness(
        is_connected=is_connected,
        last_seen=last_seen,
        seconds_ago=seconds_ago,
        last_heartbeat_iso=last_heartbeat_iso,
        device_id=str(device_id) if isinstance(device_id, str) else "",
        hub_numbers=hub_numbers,
        permissions=raw_permissions if isinstance(raw_permissions, dict) else {},
        stale_after_seconds=stale_after,
    )


async def get_hub_liveness() -> HubLiveness:
    """Read-only convenience wrapper: Redis fetch + pure evaluation."""
    return evaluate_hub_liveness(await read_hub_state())


async def _auto_acknowledge_disconnect_alert(session: AsyncSession, liveness: HubLiveness) -> bool:
    """Acknowledge an open ``hub:disconnected`` alert, leaving an audit trail.

    `AdminAlert.acknowledged_by` is an operator id, so a system acknowledgement
    must not borrow it — otherwise an auto-ack is indistinguishable from a human
    one. The provenance goes into ``details`` instead.
    """
    stmt = select(AdminAlert).where(
        _alert_dedupe_key_col == HUB_DISCONNECTED_DEDUPE_KEY,
        _alert_is_acknowledged_col.is_(False),
    )
    alert = (await session.execute(stmt)).scalars().first()
    if alert is None:
        return False

    acknowledged_at = datetime.now(UTC).replace(tzinfo=None)
    alert.is_acknowledged = True
    alert.acknowledged_at = acknowledged_at
    # Preserve operator provenance: never impersonate a human acknowledger.
    alert.acknowledged_by = None
    details = dict(alert.details or {})
    details.update(
        {
            "auto_resolved": True,
            "auto_resolved_by": "monitor.hub_liveness",
            "auto_resolved_at": acknowledged_at.isoformat(),
            "recovered_seconds_ago": liveness.seconds_ago,
        }
    )
    alert.details = details
    session.add(alert)
    await session.commit()
    logger.info(
        "Hub reconnected; auto-acknowledged alert %s (last heartbeat %ss ago)",
        alert.id,
        liveness.seconds_ago,
    )
    return True


async def sweep_hub_liveness(session: AsyncSession) -> dict[str, Any]:
    """Beat-driven sweep: raise or auto-acknowledge the Hub disconnect alert.

    Returns a small result dict for task observability. Never raises: a
    monitoring sweep must not crash the beat worker.
    """
    liveness = await get_hub_liveness()
    result: dict[str, Any] = {
        "status": liveness.status,
        "seconds_ago": liveness.seconds_ago,
        "stale_after_seconds": liveness.stale_after_seconds,
        "alert_raised": False,
        "alert_auto_acknowledged": False,
    }

    if liveness.is_connected:
        try:
            result["alert_auto_acknowledged"] = await _auto_acknowledge_disconnect_alert(session, liveness)
        except Exception as exc:
            logger.warning("Failed to auto-acknowledge hub disconnect alert: %s", exc)
        return result

    message = (
        f"هشدار: ارتباط گوشی هاب با سرور قطع شده است! (آخرین ارتباط: {liveness.seconds_ago} ثانیه پیش)"
        if liveness.seconds_ago is not None
        else "هشدار: گوشی هاب تا کنون به سرور متصل نشده است!"
    )
    try:
        await admin_alert_service.create_alert(
            session=session,
            severity="high",
            category="hub_connection",
            message=message,
            dedupe_key=HUB_DISCONNECTED_DEDUPE_KEY,
            details={
                "last_seen": liveness.last_seen,
                "seconds_ago": liveness.seconds_ago,
                "stale_after_seconds": liveness.stale_after_seconds,
                "hub_numbers": liveness.hub_numbers,
            },
        )
        result["alert_raised"] = True
    except Exception as exc:
        logger.warning("Failed to create hub disconnect alert: %s", exc)
    return result
