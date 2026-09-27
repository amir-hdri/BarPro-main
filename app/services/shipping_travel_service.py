"""Shipping ↔ TravelEngine wiring (Phases 6/8/10/12/13).

Single pipeline:

    Map Anchor → Route Authority snapshot → TravelExecution
    → TravelEngine → FakeGpsProvider → Android readback
    → UTCMS START / FINISH

Fail-closed: any Redroid / FakeTraveler / ADB / readback / tolerance
failure blocks START/FINISH. Operator anchors alone never claim to be
Android observations — provenance is carried explicitly.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

from app.automation.gps_shipping_manager import ShippingState
from app.services.route_authority import geometry_from_snapshot, resolve_route, utc_now_iso
from app.travel.engine import TravelEngine
from app.travel.geometry import haversine_km
from app.travel.providers import FakeGpsProvider, build_gps_provider

logger = logging.getLogger(__name__)

READBACK_TOLERANCE_KM = 0.005  # ~5 m, mirrors AndroidFakeGpsProvider gate


def provider_kind_for_env() -> str:
    """Select provider without ever silently downgrading an enabled bridge."""
    from app.android_bridge.client import BridgeConfig

    try:
        cfg = BridgeConfig.from_env()
    except Exception:
        return "operator_anchor"
    if cfg.enabled and cfg.serial:
        return "redroid"
    requested = (os.environ.get("SHIPPING_GPS_PROVIDER") or "auto").strip().lower()
    if requested in ("recording", "test", "memory"):
        return "recording"
    if requested in ("android", "redroid"):
        return requested
    return "operator_anchor"


def build_provider(kind: str = "", **kwargs: Any) -> FakeGpsProvider | None:
    """Build a FakeGpsProvider, or None for pure operator-anchor legacy path."""
    resolved = (kind or provider_kind_for_env()).strip().lower()
    if resolved in ("", "operator_anchor", "none", "off"):
        return None
    if resolved == "auto":
        resolved = provider_kind_for_env()
        if resolved == "operator_anchor":
            return None
    return build_gps_provider(resolved, **kwargs)


async def ensure_route_snapshot(state: ShippingState) -> dict[str, Any]:
    """Freeze a Route Authority snapshot on the state (idempotent)."""
    if isinstance(state.route_snapshot, dict) and state.route_snapshot.get("polyline"):
        return state.route_snapshot
    snapshot = await resolve_route(state.origin_lat, state.origin_lng, state.dest_lat, state.dest_lng)
    state.route_snapshot = snapshot
    state.route_source = str(snapshot.get("source") or "")
    state.route_distance_km = float(snapshot.get("distance_km") or 0.0)
    state.route_duration_s = float(snapshot.get("duration_s") or 0.0)
    state.anchor_hash = str(snapshot.get("anchor_hash") or "")
    if not state.distance_km:
        state.distance_km = state.route_distance_km
    return snapshot


def build_engine_for_state(state: ShippingState, *, preset: str = "truck_intercity") -> TravelEngine:
    """Rebuild the exact engine the job started with (no re-fetch)."""
    snapshot = state.route_snapshot
    if not isinstance(snapshot, dict) or not (snapshot.get("points") or snapshot.get("polyline")):
        raise ValueError("route snapshot missing — call ensure_route_snapshot first")
    geometry = geometry_from_snapshot(snapshot)
    return TravelEngine.build(geometry, preset=preset)


def compute_measured_distance_km(state: ShippingState) -> float:
    """Derive measured distance from telemetry/route — never trust manual input alone.

    Priority: accepted GPS telemetry span → TravelEngine route distance →
    Route Authority distance → legacy state distance.
    """
    points: list[tuple[float, float]] = []
    for pt in state.gps_list or []:
        if not isinstance(pt, dict):
            continue
        lat = pt.get("Latitude", pt.get("lat"))
        lon = pt.get("Longitude", pt.get("lon", pt.get("lng")))
        try:
            lat_f, lon_f = float(lat), float(lon)
        except (TypeError, ValueError):
            continue
        if -90 <= lat_f <= 90 and -180 <= lon_f <= 180:
            points.append((lat_f, lon_f))
    if len(points) >= 2:
        total = sum(haversine_km(a[0], a[1], b[0], b[1]) for a, b in zip(points, points[1:], strict=False))
        route_ref = state.route_distance_km or state.distance_km or total
        # Sanity: telemetry spanning 0.5×–1.8× the road route is plausible;
        # otherwise fall back to the authoritative route distance.
        if route_ref > 0 and 0.5 * route_ref <= total <= 1.8 * route_ref:
            return round(total, 2)
    if state.route_distance_km > 0:
        return round(state.route_distance_km, 2)
    return round(float(state.distance_km or 0.0), 2)


def is_arrival_reached(state: ShippingState) -> bool:
    """True only when the travel execution itself reports ARRIVED."""
    return (state.travel_status or "").upper() == "ARRIVED" or float(state.travel_progress or 0.0) >= 1.0


def advance_travel_execution(state: ShippingState, *, now: datetime | None = None) -> dict[str, Any]:
    """Advance the persisted travel execution clock and record ARRIVED/progress.

    Pure CPU: rebuilds the engine from the frozen snapshot, samples at *now*,
    and writes travel_status/travel_progress/traveled_km back onto the state.
    Never touches devices or UTCMS — auto-complete decides FINISH from this.
    """
    stamp = now or datetime.now(UTC)
    try:
        engine = build_engine_for_state(state)
    except Exception as exc:
        logger.warning("travel_advance_no_geometry job=%s err=%s", state.job_id, exc)
        return {"advanced": False, "reason": "no_route_snapshot"}
    # Rebuild clock origin from created_at so progress is deterministic.
    try:
        started_at = datetime.fromisoformat(state.created_at)
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=UTC)
    except Exception:
        started_at = stamp
    engine.start(now=started_at)
    sample = engine.sample(now=stamp)
    state.travel_status = sample.status.value
    state.travel_progress = round(float(sample.progress), 6)
    state.traveled_km = round(float(sample.distance_traveled_km), 2)
    state.measured_distance_km = compute_measured_distance_km(state)
    return {
        "advanced": True,
        "status": sample.status.value,
        "progress": state.travel_progress,
        "traveled_km": state.traveled_km,
        "remaining_s": round(float(sample.remaining_s), 1),
    }


async def verify_android_anchor(
    *,
    expected_lat: float,
    expected_lng: float,
    tolerance_km: float = READBACK_TOLERANCE_KM,
) -> dict[str, Any]:
    """Inject nothing — only read back Android and compare to the anchor.

    Returns {"verified": True, "observation": {...}} or
    {"verified": False, "reason": ...}. Fail-closed: any error → not verified.
    """
    from app.android_bridge.client import BridgeConfig
    from app.travel.android_observer import AdbLocationObserver

    try:
        observer = AdbLocationObserver(BridgeConfig.from_env())
        observation = await observer.observe()
    except Exception as exc:  # noqa: BLE001 — fail closed, reason only
        return {"verified": False, "reason": str(exc) or "readback_unavailable"}
    gap_km = haversine_km(observation.latitude, observation.longitude, expected_lat, expected_lng)
    if gap_km > tolerance_km:
        return {
            "verified": False,
            "reason": "location_readback_mismatch",
            "gap_m": round(gap_km * 1000.0, 1),
        }
    return {
        "verified": True,
        "observation": {
            "lat": observation.latitude,
            "lon": observation.longitude,
            "provider": observation.provider,
            "serial": observation.serial,
            "is_mock": observation.is_mock,
            "sampled_at": observation.sampled_at.isoformat(),
            "observed_at": observation.observed_at.isoformat(),
            "gap_m": round(gap_km * 1000.0, 1),
        },
    }


def snapshot_summary(state: ShippingState) -> dict[str, Any]:
    return {
        "route_source": state.route_source,
        "is_real_route": state.route_source == "neshan",
        "route_distance_km": state.route_distance_km,
        "travel_status": state.travel_status,
        "travel_progress": state.travel_progress,
        "measured_distance_km": state.measured_distance_km or compute_measured_distance_km(state),
        "anchor_hash": state.anchor_hash,
        "generated_at": utc_now_iso(),
    }


__all__ = [
    "READBACK_TOLERANCE_KM",
    "advance_travel_execution",
    "build_engine_for_state",
    "build_provider",
    "compute_measured_distance_km",
    "ensure_route_snapshot",
    "is_arrival_reached",
    "provider_kind_for_env",
    "snapshot_summary",
    "verify_android_anchor",
]
