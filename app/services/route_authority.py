"""Route Authority — single source of truth for road routes.

Replaces the four independent route/distance computations:
- app/services/distance_service.py (Neshan + haversine fallback)
- app/api/routes/waybill_map.py calculate-route (raw haversine)
- app/automation/gps_shipping_manager.py (1.25 detour factor + 65 km/h)
- app/travel/route.py (real RouteGeometry, previously orphaned)

Every caller (Map, Route Template, Waybill Job, TravelEngine, GPS
simulation, History, Finish) must resolve through here so:

    Map Anchor == Route Snapshot == TravelEngine endpoint
    == Android readback == UTCMS payload == UTCMS readback

Fallback is explicit: source == "neshan" means real road geometry,
source == "haversine_fallback" means straight-line estimate and must
never be presented as real road GPS simulation.
"""

from __future__ import annotations

import hashlib
import logging
import math
from datetime import UTC, datetime
from typing import Any

from app.core.distance import estimate_time, road_estimate
from app.travel.geometry import GeoPoint, haversine_km
from app.travel.route import FALLBACK_SOURCE, RouteGeometry

logger = logging.getLogger(__name__)

ROUTE_VERSION = "route-authority/v1"
NESHAN_SOURCE = "neshan"
# Local planning policy, not an upstream acceptance claim. User-approved road
# snapping retains the requested pin separately and never invents a connector.
MAX_ROAD_SNAP_KM = 0.25


def _validate_anchor(lat: Any, lng: Any) -> None:
    for value, limit in ((lat, 90.0), (lng, 180.0)):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or abs(value) > limit
        ):
            raise ValueError("invalid route anchor coordinates")


def _validate_geometry(geometry: RouteGeometry) -> None:
    for point in geometry.points:
        _validate_anchor(point.lat, point.lon)


def _anchor_hash(origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float) -> str:
    raw = f"{origin_lat:.7f},{origin_lng:.7f}|{dest_lat:.7f},{dest_lng:.7f}|{ROUTE_VERSION}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def utc_now_iso() -> str:
    """Canonical UTC timestamp for all GPS internals (never Tehran-labelled-as-Z)."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _haversine_geometry(
    origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float
) -> tuple[RouteGeometry, float, float]:
    """Straight-line fallback geometry, explicitly flagged."""
    start = GeoPoint(origin_lat, origin_lng)
    end = GeoPoint(dest_lat, dest_lng)
    geometry = RouteGeometry.straight_line_fallback(start, end, road_factor=1.35)
    road_km = road_estimate(origin_lat, origin_lng, dest_lat, dest_lng)
    duration_min = estimate_time(road_km)
    return geometry, round(road_km, 2), round(duration_min, 1)


async def _fetch_neshan_route(
    origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float
) -> dict[str, Any] | None:
    """Fetch Neshan direction including polyline when available."""
    from app.core.config import utcms_config

    api_key = (utcms_config.NESHAN_API_KEY or "").strip()
    if not api_key:
        return None
    try:
        import httpx

        async with httpx.AsyncClient(timeout=utcms_config.NESHAN_TIMEOUT_SECONDS, trust_env=False) as client:
            resp = await client.get(
                "https://api.neshan.org/v4/direction",
                params={
                    "type": "car",
                    "origin": f"{origin_lat},{origin_lng}",
                    "destination": f"{dest_lat},{dest_lng}",
                },
                headers={"Api-Key": api_key},
            )
            resp.raise_for_status()
            data = resp.json()
            route = (data.get("routes") or [{}])[0]
            leg = ((route.get("legs") or [{}])[0]) or {}
            distance_m = ((leg.get("distance") or {}).get("value")) if isinstance(leg, dict) else None
            duration_s = ((leg.get("duration") or {}).get("value")) if isinstance(leg, dict) else None
            # Neshan returns overview polyline under several possible keys.
            polyline = (
                ((route.get("overview_polyline") or {}).get("points"))
                or route.get("overviewPolyline")
                or route.get("polyline")
                or ""
            )
            steps = leg.get("steps") or [] if isinstance(leg, dict) else []
            return {
                "distance_m": distance_m,
                "duration_s": duration_s,
                "polyline": polyline if isinstance(polyline, str) else "",
                "steps": steps,
                "raw": route,
            }
    except Exception as exc:  # noqa: BLE001 — provider failure degrades to fallback
        logger.warning("route_authority_neshan_failed: %s", exc)
        return None


def _geometry_from_neshan(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    neshan: dict[str, Any],
) -> tuple[RouteGeometry | None, float | None, float | None]:
    """Build RouteGeometry from a Neshan response; None when unusable."""
    from app.travel.route import RouteSegment

    raw_polyline = neshan.get("polyline")
    polyline = raw_polyline.strip() if isinstance(raw_polyline, str) else ""
    distance_m = neshan.get("distance_m")
    duration_s = neshan.get("duration_s")
    try:
        if polyline:
            geometry = RouteGeometry.from_encoded(polyline, source=NESHAN_SOURCE)
            _validate_geometry(geometry)
            for value in (distance_m, duration_s):
                if value is not None and (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or value <= 0
                ):
                    raise ValueError("invalid provider route distance/duration")
            # Attach provider totals as segments when available so the speed
            # profile reflects the real road rather than a chosen number.
            if isinstance(distance_m, (int, float)) and isinstance(duration_s, (int, float)):
                total = geometry.total_distance_km
                geometry.segments = [
                    RouteSegment(
                        index=0,
                        start_km=0.0,
                        end_km=total,
                        distance_km=total,
                        duration_s=float(duration_s),
                        instruction="neshan overview",
                    )
                ]
                geometry.provider_duration_s = float(duration_s)
            distance_km = round(float(distance_m) / 1000.0, 2) if distance_m else round(geometry.total_distance_km, 2)
            duration_min = round(float(duration_s) / 60.0, 1) if duration_s else None
            return geometry, distance_km, duration_min
    except Exception as exc:  # noqa: BLE001 — corrupt polyline degrades to fallback
        logger.warning("route_authority_polyline_invalid: %s", exc)
    return None, None, None


async def resolve_route(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
) -> dict[str, Any]:
    """Resolve one canonical route snapshot for the given anchors.

    Returns a JSON-serialisable snapshot persisted on the job so a future
    Neshan response can never silently rewrite history:

        {
          "origin": {...}, "destination": {...},
          "source": "neshan" | "haversine_fallback",
          "is_real_route": bool,
          "polyline": str, "points": [[lat, lng], ...],
          "distance_km": float, "duration_min": float, "duration_s": float,
          "segments": [...], "anchor_hash": str,
          "created_at": UTC-Z, "route_version": str,
        }
    """
    _validate_anchor(origin_lat, origin_lng)
    _validate_anchor(dest_lat, dest_lng)

    neshan = await _fetch_neshan_route(origin_lat, origin_lng, dest_lat, dest_lng)
    geometry: RouteGeometry | None = None
    distance_km: float | None = None
    duration_min: float | None = None
    source = FALLBACK_SOURCE
    fallback_reason = "provider_unavailable"
    snap_metadata: dict[str, Any] = {}
    if neshan:
        geometry, distance_km, duration_min = _geometry_from_neshan(origin_lat, origin_lng, dest_lat, dest_lng, neshan)
        if geometry is not None:
            start, end = GeoPoint(origin_lat, origin_lng), GeoPoint(dest_lat, dest_lng)
            origin_gap = haversine_km(*start, *geometry.start)
            dest_gap = haversine_km(*end, *geometry.end)
            if max(origin_gap, dest_gap) > MAX_ROAD_SNAP_KM:
                geometry = None
                fallback_reason = "provider_anchor_mismatch"
            else:
                from app.travel.route import RouteSegment

                for label, gap in (("origin", origin_gap), ("destination", dest_gap)):
                    snap_metadata[label] = {"distance_m": round(gap * 1000.0, 3), "source": "neshan_road_endpoint"}
                distance_km = max(float(distance_km or 0), geometry.total_distance_km)
                duration_min = max(float(duration_min or 0), distance_km / 65.0 * 60.0)
                geometry.provider_duration_s = duration_min * 60.0
                geometry.segments = [
                    RouteSegment(
                        0,
                        0.0,
                        geometry.total_distance_km,
                        geometry.total_distance_km,
                        geometry.provider_duration_s,
                        "provider road route with bounded road-snapped endpoints",
                    )
                ]
                source = NESHAN_SOURCE
        else:
            fallback_reason = "provider_geometry_invalid"

    if geometry is None:
        geometry, distance_km, duration_min = _haversine_geometry(origin_lat, origin_lng, dest_lat, dest_lng)
        source = FALLBACK_SOURCE
        # Spherical interpolation can introduce floating-point endpoint drift.
        geometry.points[0] = GeoPoint(origin_lat, origin_lng)
        geometry.points[-1] = GeoPoint(dest_lat, dest_lng)

    assert geometry is not None and distance_km is not None
    duration_s = round(float(duration_min or 0.0) * 60.0, 1)
    snapshot = {
        "requested_origin": {"lat": float(origin_lat), "lng": float(origin_lng)},
        "requested_destination": {"lat": float(dest_lat), "lng": float(dest_lng)},
        "origin": {"lat": geometry.start.lat, "lng": geometry.start.lon},
        "destination": {"lat": geometry.end.lat, "lng": geometry.end.lon},
        "source": source,
        "is_real_route": source == NESHAN_SOURCE,
        "road_anchor_verified": source == NESHAN_SOURCE,
        "snap_metadata": snap_metadata,
        "coordinate_source": "road_snapped" if source == NESHAN_SOURCE else "map_pin_unverified",
        "requires_reselection": (
            fallback_reason in {"provider_anchor_mismatch", "provider_geometry_invalid"}
            if source == FALLBACK_SOURCE
            else False
        ),
        "fallback_reason": fallback_reason if source == FALLBACK_SOURCE else None,
        "polyline": geometry.encode(),
        "points": [[p.lat, p.lon] for p in geometry.points],
        "distance_km": float(distance_km),
        "duration_min": float(duration_min or 0.0),
        "duration_s": duration_s,
        "segments": [s.to_dict() for s in geometry.segments],
        "provider_duration_s": round(float(geometry.provider_duration_s or duration_s), 1),
        "anchor_hash": _anchor_hash(origin_lat, origin_lng, dest_lat, dest_lng),
        "created_at": utc_now_iso(),
        "route_version": ROUTE_VERSION,
    }
    return snapshot


def geometry_from_snapshot(snapshot: dict[str, Any]) -> RouteGeometry:
    """Rebuild the exact RouteGeometry a job started with (no re-fetch)."""
    points = snapshot.get("points")
    if isinstance(points, list) and len(points) >= 2:
        from app.travel.route import RouteSegment

        for point in points:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                raise ValueError("invalid route snapshot point")
            _validate_anchor(point[0], point[1])
        segments = [RouteSegment.from_dict(s) for s in (snapshot.get("segments") or []) if isinstance(s, dict)]
        geometry = RouteGeometry.from_points(
            [(float(p[0]), float(p[1])) for p in points],
            segments=segments,
            source=str(snapshot.get("source") or "unknown"),
            provider_duration_s=float(snapshot.get("provider_duration_s") or 0.0),
        )
    else:
        polyline = str(snapshot.get("polyline") or "")
        if not polyline:
            raise ValueError("route snapshot has no polyline/points")
        geometry = RouteGeometry.from_encoded(polyline, source=str(snapshot.get("source") or "unknown"))
    _validate_geometry(geometry)
    return geometry


__all__ = ["ROUTE_VERSION", "geometry_from_snapshot", "resolve_route", "utc_now_iso"]
