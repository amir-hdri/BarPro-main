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


DEFAULT_TRUCK_INTERCITY_SPEED_KMH = 60.0
DEFAULT_TRUCK_URBAN_SPEED_KMH = 28.0
DEFAULT_CYCLING_BUFFER_MINUTES = 45.0


def calculate_cycling_times(
    distance_km: float,
    buffer_minutes: float = DEFAULT_CYCLING_BUFFER_MINUTES,
    is_urban: bool = False,
    truck_speed_kmh: float | None = None,
) -> dict[str, float]:
    """Calculate driving duration and safe buffers for multi-route cycling and deadhead return.

    Parameters:
        distance_km: One-way road distance in kilometers.
        buffer_minutes: Safety/rest/unloading buffer in minutes between consecutive waybills.
        is_urban: If True, uses urban truck speed profile; otherwise intercity.
        truck_speed_kmh: Optional custom truck speed override.

    Returns:
        Dictionary with:
          - distance_km
          - driving_minutes (one-way transit time)
          - buffer_minutes (rest/unloading buffer)
          - leg_total_minutes (one-way driving + buffer)
          - deadhead_return_minutes (unloaded return driving time)
          - cycle_total_minutes (driving + buffer + deadhead_return + buffer)
    """
    speed = truck_speed_kmh or (DEFAULT_TRUCK_URBAN_SPEED_KMH if is_urban else DEFAULT_TRUCK_INTERCITY_SPEED_KMH)
    buffer = max(0.0, float(buffer_minutes))
    dist = max(0.0, float(distance_km))

    driving_min = (dist / speed * 60.0) if speed > 0 and dist > 0 else 0.0
    leg_total = driving_min + buffer
    deadhead_return = driving_min  # same physical distance for empty return
    cycle_total = driving_min + buffer + deadhead_return + buffer

    return {
        "distance_km": round(dist, 2),
        "driving_minutes": round(driving_min, 1),
        "buffer_minutes": round(buffer, 1),
        "leg_total_minutes": round(leg_total, 1),
        "deadhead_return_minutes": round(deadhead_return, 1),
        "cycle_total_minutes": round(cycle_total, 1),
    }
