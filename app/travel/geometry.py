"""Spherical geometry primitives for route handling.

Pure functions plus one index structure. No I/O, no globals, no randomness —
everything here is unit-testable in isolation and must stay that way, because
the whole travel engine derives its position from :class:`PathIndex`.

Distances are kilometres, angles are degrees, and coordinates are always
``(latitude, longitude)`` in that order. Encoded polylines use the Google
algorithm, which is what Neshan's ``/v4/direction`` returns.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import NamedTuple

EARTH_RADIUS_KM = 6371.0088  # IUGG mean radius; matches OSRM/Neshan conventions

__all__ = [
    "EARTH_RADIUS_KM",
    "GeoPoint",
    "PathIndex",
    "PathPosition",
    "cross_track_km",
    "decode_polyline",
    "densify",
    "encode_polyline",
    "haversine_km",
    "initial_bearing",
    "intermediate_point",
    "path_length_km",
]


class GeoPoint(NamedTuple):
    """An immutable ``(lat, lon)`` pair."""

    lat: float
    lon: float


def _validate_lat_lon(lat: float, lon: float) -> None:
    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"latitude out of range: {lat}")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError(f"longitude out of range: {lon}")


# ──────────────────────────── distance & bearing ────────────────────────────


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    # atan2 form stays accurate for antipodal points where asin(sqrt(a)) degrades.
    return 2 * EARTH_RADIUS_KM * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))


def initial_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Forward azimuth from point 1 to point 2, in degrees clockwise from north."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def intermediate_point(lat1: float, lon1: float, lat2: float, lon2: float, fraction: float) -> GeoPoint:
    """Spherical-linear interpolation between two points.

    ``fraction`` is clamped to ``[0, 1]``. Great-circle rather than naive lat/lon
    interpolation: on Iranian intercity routes the two agree to well under a
    metre per node, but the spherical form stays correct at any node spacing, so
    densification resolution never silently changes the answer.
    """
    fraction = min(1.0, max(0.0, fraction))
    phi1, lam1 = math.radians(lat1), math.radians(lon1)
    phi2, lam2 = math.radians(lat2), math.radians(lon2)

    # Angular separation via the haversine form (numerically stable when small).
    dphi, dlam = phi2 - phi1, lam2 - lam1
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    delta = 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))
    if delta < 1e-12:  # coincident endpoints — slerp is undefined, return the start
        return GeoPoint(lat1, lon1)

    sin_delta = math.sin(delta)
    ka = math.sin((1 - fraction) * delta) / sin_delta
    kb = math.sin(fraction * delta) / sin_delta
    x = ka * math.cos(phi1) * math.cos(lam1) + kb * math.cos(phi2) * math.cos(lam2)
    y = ka * math.cos(phi1) * math.sin(lam1) + kb * math.cos(phi2) * math.sin(lam2)
    z = ka * math.sin(phi1) + kb * math.sin(phi2)
    return GeoPoint(
        lat=math.degrees(math.atan2(z, math.hypot(x, y))),
        lon=math.degrees(math.atan2(y, x)),
    )


def cross_track_km(lat: float, lon: float, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Shortest distance from a point to the **segment** ``(1 -> 2)``.

    Unlike the textbook cross-track formula this clamps to the segment ends, so
    a point beyond the segment reports its distance to the nearer endpoint
    rather than to the infinite great circle. That is what route-adherence
    checking needs (PHASE 33).
    """
    seg_len = haversine_km(lat1, lon1, lat2, lon2)
    if seg_len < 1e-9:
        return haversine_km(lat, lon, lat1, lon1)

    d13 = haversine_km(lat1, lon1, lat, lon) / EARTH_RADIUS_KM  # angular
    theta13 = math.radians(initial_bearing(lat1, lon1, lat, lon))
    theta12 = math.radians(initial_bearing(lat1, lon1, lat2, lon2))

    dxt = math.asin(max(-1.0, min(1.0, math.sin(d13) * math.sin(theta13 - theta12))))
    # Along-track distance: how far the projection falls along the segment.
    cos_dxt = math.cos(dxt)
    if abs(cos_dxt) < 1e-12:
        return abs(dxt) * EARTH_RADIUS_KM
    ratio = max(-1.0, min(1.0, math.cos(d13) / cos_dxt))
    dat = math.acos(ratio) * EARTH_RADIUS_KM
    # acos() loses the sign, so recover "behind the start" from the bearing.
    if abs(theta13 - theta12) > math.pi / 2 and abs(theta13 - theta12) < 3 * math.pi / 2:
        dat = -dat

    if dat < 0:
        return haversine_km(lat, lon, lat1, lon1)
    if dat > seg_len:
        return haversine_km(lat, lon, lat2, lon2)
    return abs(dxt) * EARTH_RADIUS_KM


# ──────────────────────────── polyline codec ────────────────────────────


def decode_polyline(encoded: str, precision: int = 5) -> list[GeoPoint]:
    """Decode a Google-algorithm encoded polyline into ``(lat, lon)`` points.

    Raises ``ValueError`` on truncated input rather than silently returning a
    short path — a half-decoded route would produce a plausible-looking but
    wrong distance.
    """
    if not encoded:
        return []
    factor = float(10**precision)
    points: list[GeoPoint] = []
    index = 0
    lat = 0
    lon = 0
    length = len(encoded)

    while index < length:
        for axis in ("lat", "lon"):
            shift = 0
            result = 0
            while True:
                if index >= length:
                    raise ValueError("truncated polyline: value ended mid-chunk")
                byte = ord(encoded[index]) - 63
                if byte < 0:
                    raise ValueError(f"invalid polyline character at index {index}")
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
                if shift > 35:
                    raise ValueError("invalid polyline: varint too long")
            delta = ~(result >> 1) if (result & 1) else (result >> 1)
            if axis == "lat":
                lat += delta
            else:
                lon += delta
        points.append(GeoPoint(lat=lat / factor, lon=lon / factor))
    return points


def encode_polyline(points: list[GeoPoint] | list[tuple[float, float]], precision: int = 5) -> str:
    """Encode ``(lat, lon)`` points with the Google polyline algorithm."""
    factor = float(10**precision)
    out: list[str] = []
    prev_lat = 0
    prev_lon = 0
    for point in points:
        lat, lon = float(point[0]), float(point[1])
        elat = int(round(lat * factor))
        elon = int(round(lon * factor))
        for delta in (elat - prev_lat, elon - prev_lon):
            value = ~(delta << 1) if delta < 0 else (delta << 1)
            while value >= 0x20:
                out.append(chr((0x20 | (value & 0x1F)) + 63))
                value >>= 5
            out.append(chr(value + 63))
        prev_lat, prev_lon = elat, elon
    return "".join(out)


# ──────────────────────────── path utilities ────────────────────────────


def path_length_km(points: list[GeoPoint]) -> float:
    """Total along-path length of a coordinate sequence."""
    return sum(
        haversine_km(points[i].lat, points[i].lon, points[i + 1].lat, points[i + 1].lon) for i in range(len(points) - 1)
    )


def densify(points: list[GeoPoint], max_step_km: float) -> list[GeoPoint]:
    """Subdivide any leg longer than ``max_step_km``.

    The kinematic solver in :mod:`app.travel.speed` integrates per node, so its
    accuracy is bounded by node spacing. Densifying first lets a coarse
    provider geometry (or a two-point fallback) yield a smooth profile.
    """
    if max_step_km <= 0:
        raise ValueError("max_step_km must be positive")
    if len(points) < 2:
        return list(points)

    out: list[GeoPoint] = [points[0]]
    for i in range(len(points) - 1):
        start, end = points[i], points[i + 1]
        leg = haversine_km(start.lat, start.lon, end.lat, end.lon)
        if leg > max_step_km:
            splits = int(math.ceil(leg / max_step_km))
            for step in range(1, splits):
                out.append(intermediate_point(start.lat, start.lon, end.lat, end.lon, step / splits))
        out.append(end)
    return out


@dataclass(frozen=True, slots=True)
class PathPosition:
    """A resolved point on the path, with the leg it fell on."""

    point: GeoPoint
    bearing_deg: float
    distance_km: float
    node_index: int


class PathIndex:
    """Cumulative-distance index over a polyline, for O(log n) lookups.

    This is the single source of *where* — the travel engine converts elapsed
    time to a distance and asks this index for the coordinate. Nothing else in
    the system is allowed to invent a position.
    """

    __slots__ = ("_bearings", "_cumulative", "_points")

    def __init__(self, points: list[GeoPoint]) -> None:
        if len(points) < 2:
            raise ValueError("a path needs at least two points")
        for point in points:
            _validate_lat_lon(point.lat, point.lon)

        self._points: list[GeoPoint] = list(points)
        cumulative = [0.0]
        bearings: list[float] = []
        for i in range(len(self._points) - 1):
            a, b = self._points[i], self._points[i + 1]
            cumulative.append(cumulative[-1] + haversine_km(a.lat, a.lon, b.lat, b.lon))
            bearings.append(initial_bearing(a.lat, a.lon, b.lat, b.lon))
        self._cumulative: list[float] = cumulative
        self._bearings: list[float] = bearings

        if self._cumulative[-1] <= 0.0:
            raise ValueError("path has zero length")

    @property
    def points(self) -> list[GeoPoint]:
        return list(self._points)

    @property
    def total_km(self) -> float:
        return self._cumulative[-1]

    @property
    def cumulative_km(self) -> list[float]:
        return list(self._cumulative)

    def position_at(self, distance_km: float) -> PathPosition:
        """Resolve an along-path distance to a coordinate and heading.

        The distance is clamped to ``[0, total_km]``: the engine never asks for
        a point past the destination, and clamping keeps a rounding error at
        the final tick from raising instead of arriving.
        """
        total = self.total_km
        target = min(max(distance_km, 0.0), total)

        # Binary search for the leg containing `target`.
        lo, hi = 0, len(self._cumulative) - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if self._cumulative[mid] <= target:
                lo = mid
            else:
                hi = mid
        leg_start = self._cumulative[lo]
        leg_end = self._cumulative[lo + 1]
        leg_len = leg_end - leg_start
        fraction = 0.0 if leg_len <= 0 else (target - leg_start) / leg_len

        a, b = self._points[lo], self._points[lo + 1]
        return PathPosition(
            point=intermediate_point(a.lat, a.lon, b.lat, b.lon, fraction),
            bearing_deg=self._bearings[lo],
            distance_km=target,
            node_index=lo,
        )

    def distance_to_path_km(self, lat: float, lon: float) -> float:
        """Shortest distance from an arbitrary point to this path.

        Used by the route-adherence check (PHASE 33) to prove that emitted
        positions actually lie on the route rather than merely near its ends.
        """
        _validate_lat_lon(lat, lon)
        best = float("inf")
        for i in range(len(self._points) - 1):
            a, b = self._points[i], self._points[i + 1]
            # Cheap reject: a point cannot be closer than |d(a) - leg| allows.
            if haversine_km(lat, lon, a.lat, a.lon) - best > self._cumulative[i + 1] - self._cumulative[i]:
                continue
            best = min(best, cross_track_km(lat, lon, a.lat, a.lon, b.lat, b.lon))
            if best < 1e-9:
                break
        return best
