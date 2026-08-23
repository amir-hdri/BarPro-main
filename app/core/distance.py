"""Pure distance/time calculation helpers for multi-route waybills.

These functions are intentionally side-effect-free and dependency-free so they
can be unit-tested hermetically (no Postgres/Redis/Neshan required). The
roadmap's original estimates are preserved: haversine * 1.35 road factor,
55 km/h intercity / 28 km/h urban, plus a 10-minute traffic/loading buffer.
"""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0
ROAD_FACTOR = 1.35  # ایران: ضریب تبدیل فاصله هوایی به جاده‌ای
INTERCITY_SPEED_KMH = 55.0
URBAN_SPEED_KMH = 28.0
BUFFER_MINUTES = 10.0  # ترافیک / بارگیری


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometers between two coordinates."""
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))


def road_estimate(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Road-distance estimate in km (haversine inflated by the Iranian road factor)."""
    return haversine(lat1, lon1, lat2, lon2) * ROAD_FACTOR


def estimate_time(distance_km: float, is_urban: bool = False) -> float:
    """Estimated driving time in minutes."""
    speed = URBAN_SPEED_KMH if is_urban else INTERCITY_SPEED_KMH
    if distance_km <= 0 or speed <= 0:
        return 0.0
    return (distance_km / speed * 60.0) + BUFFER_MINUTES
