"""Route geometry and segments — the PHASE 3 route model.

A route here is never a straight line between two pins. It carries the ordered
coordinates a routing engine returned, the per-step segments with their own
distance and duration, and the totals derived from them.

The only exception is an explicitly-labelled fallback (``source =
"haversine_fallback"``), which exists so an outage in the routing provider
degrades to a usable estimate instead of a 500. A fallback route is flagged in
its ``source`` and in :attr:`RouteGeometry.is_real_route`, so no caller can
mistake it for real road geometry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.travel.geometry import (
    GeoPoint,
    PathIndex,
    decode_polyline,
    densify,
    encode_polyline,
    haversine_km,
    path_length_km,
)

__all__ = [
    "FALLBACK_SOURCE",
    "MAX_NODE_SPACING_KM",
    "RouteGeometry",
    "RouteSegment",
]

FALLBACK_SOURCE = "haversine_fallback"

#: Provider geometry is dense on turns but sparse on long straights. The
#: kinematic solver integrates per node, so cap the spacing before solving.
MAX_NODE_SPACING_KM = 0.5

#: Hard sanity ceiling — anything beyond this is a bad request or a bad decode.
MAX_ROUTE_KM = 20_000.0


@dataclass(frozen=True, slots=True)
class RouteSegment:
    """One leg of the route as the provider described it.

    ``distance_km`` and ``duration_s`` come from the provider, not from us:
    they are what makes the speed profile reflect the real road (a mountain
    pass is slow because the provider said so) rather than a number we chose.
    """

    index: int
    start_km: float
    end_km: float
    distance_km: float
    duration_s: float
    instruction: str = ""
    name: str = ""

    @property
    def average_kmh(self) -> float:
        """Provider-implied average speed over this leg; 0 when it has no duration."""
        if self.duration_s <= 0:
            return 0.0
        return self.distance_km / (self.duration_s / 3600.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "start_km": round(self.start_km, 6),
            "end_km": round(self.end_km, 6),
            "distance_km": round(self.distance_km, 6),
            "duration_s": round(self.duration_s, 3),
            "instruction": self.instruction,
            "name": self.name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RouteSegment:
        return cls(
            index=int(data["index"]),
            start_km=float(data["start_km"]),
            end_km=float(data["end_km"]),
            distance_km=float(data["distance_km"]),
            duration_s=float(data["duration_s"]),
            instruction=str(data.get("instruction") or ""),
            name=str(data.get("name") or ""),
        )


@dataclass(slots=True)
class RouteGeometry:
    """Ordered coordinates plus segments, distance and provider duration.

    Construct via :meth:`from_points`, :meth:`from_encoded` or
    :meth:`straight_line_fallback` — the raw constructor does not validate.
    """

    points: list[GeoPoint]
    segments: list[RouteSegment] = field(default_factory=list)
    source: str = "unknown"
    provider_duration_s: float = 0.0
    _index: PathIndex | None = field(default=None, repr=False, compare=False)

    # ── construction ──

    @classmethod
    def from_points(
        cls,
        points: list[GeoPoint] | list[tuple[float, float]],
        *,
        segments: list[RouteSegment] | None = None,
        source: str = "unknown",
        provider_duration_s: float = 0.0,
    ) -> RouteGeometry:
        """Build from an ordered coordinate list, validating shape and length."""
        coerced = [p if isinstance(p, GeoPoint) else GeoPoint(float(p[0]), float(p[1])) for p in points]
        # Drop consecutive duplicates: providers repeat the junction node
        # between steps, which would otherwise create zero-length legs.
        deduped: list[GeoPoint] = []
        for point in coerced:
            if deduped and haversine_km(deduped[-1].lat, deduped[-1].lon, point.lat, point.lon) < 1e-7:
                continue
            deduped.append(point)
        if len(deduped) < 2:
            raise ValueError("route geometry needs at least two distinct points")

        length = path_length_km(deduped)
        if length <= 0:
            raise ValueError("route geometry has zero length")
        if length > MAX_ROUTE_KM:
            raise ValueError(f"route length {length:.1f} km exceeds the {MAX_ROUTE_KM:.0f} km ceiling")

        return cls(
            points=deduped,
            segments=list(segments or []),
            source=source,
            provider_duration_s=float(provider_duration_s),
        )

    @classmethod
    def from_encoded(
        cls,
        encoded: str,
        *,
        segments: list[RouteSegment] | None = None,
        source: str = "unknown",
        provider_duration_s: float = 0.0,
        precision: int = 5,
    ) -> RouteGeometry:
        """Build from a Google-encoded polyline (what Neshan returns)."""
        points = decode_polyline(encoded, precision=precision)
        if len(points) < 2:
            raise ValueError("encoded polyline decoded to fewer than two points")
        return cls.from_points(points, segments=segments, source=source, provider_duration_s=provider_duration_s)

    @classmethod
    def straight_line_fallback(cls, start: GeoPoint, end: GeoPoint, *, road_factor: float = 1.35) -> RouteGeometry:
        """Last-resort geometry when the routing provider is unavailable.

        Explicitly flagged so nothing downstream reports it as a real route.
        ``road_factor`` inflates the reported distance to approximate road
        length; the drawn geometry is still a straight line and says so.
        """
        if road_factor < 1.0:
            raise ValueError("road_factor must be >= 1.0")
        geometry = cls.from_points(
            densify([start, end], MAX_NODE_SPACING_KM),
            source=FALLBACK_SOURCE,
        )
        geometry.segments = [
            RouteSegment(
                index=0,
                start_km=0.0,
                end_km=geometry.raw_length_km,
                distance_km=geometry.raw_length_km,
                duration_s=0.0,
                instruction="straight-line fallback (routing provider unavailable)",
            )
        ]
        geometry.source = FALLBACK_SOURCE
        # Stash the factor so callers reporting a road-distance estimate can
        # apply it without re-deriving the constant.
        geometry.provider_duration_s = 0.0
        return geometry

    # ── derived values ──

    @property
    def index(self) -> PathIndex:
        """Cumulative-distance index, built once and cached."""
        if self._index is None:
            self._index = PathIndex(densify(self.points, MAX_NODE_SPACING_KM))
        return self._index

    @property
    def raw_length_km(self) -> float:
        """Along-geometry length before densification (identical up to rounding)."""
        return path_length_km(self.points)

    @property
    def total_distance_km(self) -> float:
        """Authoritative route distance — measured from the geometry itself.

        PHASE 4: this is the only value allowed to be called "route distance".
        It is *not* a straight line unless :attr:`is_real_route` is False.
        """
        return self.index.total_km

    @property
    def start(self) -> GeoPoint:
        return self.points[0]

    @property
    def end(self) -> GeoPoint:
        return self.points[-1]

    @property
    def is_real_route(self) -> bool:
        """False for the straight-line fallback; True for provider geometry."""
        return self.source != FALLBACK_SOURCE

    @property
    def has_segment_timing(self) -> bool:
        """Whether the provider gave per-segment durations we can build a profile from."""
        return any(seg.duration_s > 0 and seg.distance_km > 0 for seg in self.segments)

    def encode(self) -> str:
        """Re-encode the original (undensified) geometry for transport."""
        return encode_polyline(self.points)

    def speed_segments(self) -> list[tuple[float, float, float]]:
        """``(start_km, end_km, observed_kmh)`` triples for the speed profile.

        Rescaled onto the densified index so the bands line up exactly with the
        distances the solver will see — otherwise a 0.3 % difference between
        raw and densified length would leave the last band short.
        """
        if not self.has_segment_timing:
            return []
        declared_end = max(seg.end_km for seg in self.segments)
        if declared_end <= 0:
            return []
        scale = self.total_distance_km / declared_end

        triples: list[tuple[float, float, float]] = []
        for seg in self.segments:
            speed = seg.average_kmh
            if speed <= 0:
                continue
            triples.append((seg.start_km * scale, seg.end_km * scale, speed))
        if not triples:
            return []
        # Close any gap at the tail caused by a skipped zero-duration segment.
        last_start, last_end, last_speed = triples[-1]
        if last_end < self.total_distance_km - 1e-6:
            triples[-1] = (last_start, self.total_distance_km, last_speed)
        return triples

    # ── validation (PHASE 27) ──

    def validate(self) -> None:
        """Raise if the geometry violates the route invariants."""
        if len(self.points) < 2:
            raise ValueError("route geometry needs at least two points")
        if self.total_distance_km <= 0:
            raise ValueError("route distance must be > 0")
        for seg in self.segments:
            if seg.distance_km < 0:
                raise ValueError(f"segment {seg.index} has negative distance")
            if seg.duration_s < 0:
                raise ValueError(f"segment {seg.index} has negative duration")
            if seg.end_km < seg.start_km:
                raise ValueError(f"segment {seg.index} ends before it starts")

    # ── serialisation (execution snapshots round-trip through this) ──

    def to_dict(self) -> dict[str, Any]:
        return {
            "polyline": self.encode(),
            # Polyline5 is convenient for display but loses user-pin precision.
            # Recovery must rebuild the original geometry and speed solution.
            "points": [[point.lat, point.lon] for point in self.points],
            "source": self.source,
            "provider_duration_s": round(self.provider_duration_s, 3),
            "total_distance_km": round(self.total_distance_km, 6),
            "point_count": len(self.points),
            "segments": [seg.to_dict() for seg in self.segments],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RouteGeometry:
        if "points" in data:
            return cls.from_points(
                data["points"],
                segments=[RouteSegment.from_dict(seg) for seg in data.get("segments") or []],
                source=str(data.get("source") or "unknown"),
                provider_duration_s=float(data.get("provider_duration_s") or 0.0),
            )
        return cls.from_encoded(
            data["polyline"],
            segments=[RouteSegment.from_dict(seg) for seg in data.get("segments") or []],
            source=str(data.get("source") or "unknown"),
            provider_duration_s=float(data.get("provider_duration_s") or 0.0),
        )
