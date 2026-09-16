"""Travel simulation: route geometry, speed profile, unified clock, fake GPS.

The package is deliberately dependency-free at import time (no DB, Redis, HTTP
or Playwright) so the engine can be unit-tested hermetically and reused from a
Celery worker, the API process or the Android bridge host.

Layering — the arrows are one-directional on purpose (PHASE 23):

    geometry  ->  route  ->  speed  ->  clock  ->  engine  ->  providers

``engine`` owns every derived quantity (position, speed, distance, ETA) and
``providers`` only transports a coordinate to a device. A provider never
computes route state.
"""

from __future__ import annotations

from app.travel.clock import TravelClock
from app.travel.engine import ConsistencyReport, TravelEngine, TravelSample
from app.travel.geometry import (
    GeoPoint,
    PathIndex,
    cross_track_km,
    decode_polyline,
    densify,
    encode_polyline,
    haversine_km,
    initial_bearing,
    intermediate_point,
)
from app.travel.providers import (
    AndroidFakeGpsProvider,
    FakeGpsProvider,
    GpsDispatch,
    RecordingGpsProvider,
    RedroidFakeGpsProvider,
    build_gps_provider,
)
from app.travel.route import RouteGeometry, RouteSegment
from app.travel.speed import SpeedProfile, SpeedRule, SpeedSolution
from app.travel.state import TravelStatus, assert_transition, can_transition

__all__ = [
    "AndroidFakeGpsProvider",
    "ConsistencyReport",
    "FakeGpsProvider",
    "GeoPoint",
    "GpsDispatch",
    "PathIndex",
    "RecordingGpsProvider",
    "RedroidFakeGpsProvider",
    "RouteGeometry",
    "RouteSegment",
    "SpeedProfile",
    "SpeedRule",
    "SpeedSolution",
    "TravelClock",
    "TravelEngine",
    "TravelSample",
    "TravelStatus",
    "assert_transition",
    "build_gps_provider",
    "can_transition",
    "cross_track_km",
    "decode_polyline",
    "densify",
    "encode_polyline",
    "haversine_km",
    "initial_bearing",
    "intermediate_point",
]
