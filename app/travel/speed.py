"""Segment-based speed profile with kinematically feasible smoothing.

The profile is the *only* source of "how fast" and therefore of "how long".
ETA is never ``distance / constant_speed`` (PHASE 5): it is the time integral
of a speed curve that respects acceleration and deceleration limits.

The solver is a standard forward/backward pass, the same shape used by motion
planners:

1. Start from the per-band target speed at every node.
2. Pin the first and last node to rest.
3. Forward pass — clamp each node so acceleration never exceeds ``accel_mps2``.
4. Backward pass — clamp each node so braking never exceeds ``decel_mps2``.

The result is continuous in distance, so a vehicle cannot jump 40 -> 90 km/h
(PHASE 8), and it is monotonic in time, so position, speed, distance and ETA
can all be derived from a single clock without drift (PHASE 10-12).
"""

from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "DEFAULT_ACCEL_MPS2",
    "DEFAULT_DECEL_MPS2",
    "MAX_SUPPORTED_KMH",
    "SpeedProfile",
    "SpeedRule",
    "SpeedSolution",
]

KMH_TO_MPS = 1000.0 / 3600.0
MPS_TO_KMH = 3.6

# A loaded truck accelerates far more gently than a car. These are the
# defaults, not a hard limit — a profile may override both.
DEFAULT_ACCEL_MPS2 = 0.45
DEFAULT_DECEL_MPS2 = 0.70
MAX_SUPPORTED_KMH = 200.0
MIN_MOVING_KMH = 1.0


@dataclass(frozen=True, slots=True)
class SpeedRule:
    """Target cruising speed over the distance band ``[start_km, end_km)``."""

    start_km: float
    end_km: float
    target_kmh: float

    def __post_init__(self) -> None:
        if self.start_km < 0:
            raise ValueError("start_km must be >= 0")
        if self.end_km <= self.start_km:
            raise ValueError(f"empty speed band: [{self.start_km}, {self.end_km}]")
        if not (MIN_MOVING_KMH <= self.target_kmh <= MAX_SUPPORTED_KMH):
            raise ValueError(f"target_kmh out of range: {self.target_kmh}")

    def to_dict(self) -> dict[str, float]:
        return {"start_km": self.start_km, "end_km": self.end_km, "target_kmh": self.target_kmh}


@dataclass(frozen=True, slots=True)
class SpeedSolution:
    """A solved speed curve: node distances, speeds and cumulative times.

    All three arrays share an index. ``speeds_mps[i]`` is the speed at
    ``distances_km[i]``, reached at ``times_s[i]`` seconds after departure.
    """

    distances_km: tuple[float, ...]
    speeds_mps: tuple[float, ...]
    times_s: tuple[float, ...]

    @property
    def total_km(self) -> float:
        return self.distances_km[-1]

    @property
    def total_seconds(self) -> float:
        return self.times_s[-1]

    # ── forward lookups: distance -> everything ──

    def speed_kmh_at_distance(self, distance_km: float) -> float:
        """Speed at an along-route distance.

        Interpolates ``v**2`` linearly, which is the exact relation under the
        constant acceleration the solver assumes between nodes.
        """
        idx = self._interval_for_distance(distance_km)
        s0, s1 = self.distances_km[idx], self.distances_km[idx + 1]
        v0, v1 = self.speeds_mps[idx], self.speeds_mps[idx + 1]
        span = s1 - s0
        if span <= 0:
            return v0 * MPS_TO_KMH
        frac = min(1.0, max(0.0, (distance_km - s0) / span))
        return math.sqrt(max(0.0, v0 * v0 + (v1 * v1 - v0 * v0) * frac)) * MPS_TO_KMH

    def time_at_distance(self, distance_km: float) -> float:
        """Seconds from departure needed to reach an along-route distance."""
        target = min(max(distance_km, 0.0), self.total_km)
        idx = self._interval_for_distance(target)
        s0 = self.distances_km[idx]
        v0, v1 = self.speeds_mps[idx], self.speeds_mps[idx + 1]
        ds = (target - s0) * 1000.0
        if ds <= 0:
            return self.times_s[idx]
        span_m = (self.distances_km[idx + 1] - s0) * 1000.0
        if span_m <= 0:
            return self.times_s[idx]
        accel = (v1 * v1 - v0 * v0) / (2 * span_m)
        if abs(accel) < 1e-12:
            return self.times_s[idx] + (ds / v0 if v0 > 0 else 0.0)
        v_at = math.sqrt(max(0.0, v0 * v0 + 2 * accel * ds))
        return self.times_s[idx] + (v_at - v0) / accel

    # ── inverse lookup: time -> distance. This is what the clock drives. ──

    def distance_at_time(self, elapsed_s: float) -> float:
        """Along-route distance reached after ``elapsed_s`` seconds of motion.

        Clamped at both ends: negative elapsed time yields 0, and any time past
        the ETA yields the full route length (arrival).
        """
        if elapsed_s <= 0:
            return 0.0
        if elapsed_s >= self.total_seconds:
            return self.total_km

        idx = bisect_right(self.times_s, elapsed_s) - 1
        idx = min(max(idx, 0), len(self.times_s) - 2)
        tau = elapsed_s - self.times_s[idx]
        v0, v1 = self.speeds_mps[idx], self.speeds_mps[idx + 1]
        s0, s1 = self.distances_km[idx], self.distances_km[idx + 1]
        dt = self.times_s[idx + 1] - self.times_s[idx]
        if dt <= 0:
            return s1
        accel = (v1 - v0) / dt
        metres = v0 * tau + 0.5 * accel * tau * tau
        return min(s1, s0 + metres / 1000.0)

    def speed_kmh_at_time(self, elapsed_s: float) -> float:
        """Instantaneous speed ``elapsed_s`` seconds after departure."""
        if elapsed_s <= 0 or elapsed_s >= self.total_seconds:
            return 0.0
        idx = bisect_right(self.times_s, elapsed_s) - 1
        idx = min(max(idx, 0), len(self.times_s) - 2)
        tau = elapsed_s - self.times_s[idx]
        v0, v1 = self.speeds_mps[idx], self.speeds_mps[idx + 1]
        dt = self.times_s[idx + 1] - self.times_s[idx]
        if dt <= 0:
            return v1 * MPS_TO_KMH
        return max(0.0, v0 + (v1 - v0) / dt * tau) * MPS_TO_KMH

    def _interval_for_distance(self, distance_km: float) -> int:
        target = min(max(distance_km, 0.0), self.total_km)
        idx = bisect_right(self.distances_km, target) - 1
        return min(max(idx, 0), len(self.distances_km) - 2)

    def sample_table(self, step_km: float) -> list[dict[str, float]]:
        """Debug/verification view: speed and time every ``step_km``."""
        if step_km <= 0:
            raise ValueError("step_km must be positive")
        rows: list[dict[str, float]] = []
        distance = 0.0
        while distance < self.total_km:
            rows.append(
                {
                    "distance_km": round(distance, 3),
                    "speed_kmh": round(self.speed_kmh_at_distance(distance), 2),
                    "elapsed_s": round(self.time_at_distance(distance), 1),
                }
            )
            distance += step_km
        rows.append(
            {
                "distance_km": round(self.total_km, 3),
                "speed_kmh": round(self.speed_kmh_at_distance(self.total_km), 2),
                "elapsed_s": round(self.total_seconds, 1),
            }
        )
        return rows


@dataclass(slots=True)
class SpeedProfile:
    """A named, validated set of speed rules plus acceleration limits."""

    rules: list[SpeedRule]
    accel_mps2: float = DEFAULT_ACCEL_MPS2
    decel_mps2: float = DEFAULT_DECEL_MPS2
    max_kmh: float = 95.0
    min_kmh: float = 25.0
    name: str = "custom"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.validate()

    # ── validation (PHASE 27) ──

    def validate(self) -> None:
        if not self.rules:
            raise ValueError("speed profile needs at least one rule")
        if self.accel_mps2 <= 0 or self.accel_mps2 > 5.0:
            raise ValueError(f"accel_mps2 out of range: {self.accel_mps2}")
        if self.decel_mps2 <= 0 or self.decel_mps2 > 8.0:
            raise ValueError(f"decel_mps2 out of range: {self.decel_mps2}")
        if not (MIN_MOVING_KMH <= self.min_kmh <= self.max_kmh <= MAX_SUPPORTED_KMH):
            raise ValueError(f"invalid speed bounds: min={self.min_kmh} max={self.max_kmh}")

        ordered = sorted(self.rules, key=lambda r: r.start_km)
        for rule in ordered:
            if rule.target_kmh > self.max_kmh:
                raise ValueError(f"rule target {rule.target_kmh} exceeds profile max {self.max_kmh}")
            if rule.target_kmh < self.min_kmh:
                raise ValueError(f"rule target {rule.target_kmh} is below profile min {self.min_kmh}")
        for prev, nxt in zip(ordered, ordered[1:], strict=False):
            if nxt.start_km < prev.end_km - 1e-9:
                raise ValueError(f"overlapping speed bands at {nxt.start_km} km")
        self.rules = ordered

    def target_kmh_at(self, distance_km: float) -> float:
        """Target cruise speed at a distance; the nearest band wins past the end."""
        for rule in self.rules:
            if rule.start_km - 1e-9 <= distance_km < rule.end_km:
                return rule.target_kmh
        if distance_km < self.rules[0].start_km:
            return self.rules[0].target_kmh
        return self.rules[-1].target_kmh

    # ── the solver ──

    def solve(self, cumulative_km: list[float]) -> SpeedSolution:
        """Produce a feasible, smooth speed curve over the given node distances.

        ``cumulative_km`` must be non-decreasing and start at 0 — it comes from
        :attr:`app.travel.geometry.PathIndex.cumulative_km`, so the speed curve
        and the geometry always share a parameterisation.
        """
        if len(cumulative_km) < 2:
            raise ValueError("need at least two nodes to solve a speed profile")
        if abs(cumulative_km[0]) > 1e-9:
            raise ValueError("cumulative distances must start at 0")

        # Collapse duplicate nodes: a zero-length leg has no kinematics and
        # would divide by zero in the time integral.
        nodes: list[float] = [0.0]
        for value in cumulative_km[1:]:
            if value < nodes[-1] - 1e-9:
                raise ValueError("cumulative distances must be non-decreasing")
            if value - nodes[-1] > 1e-9:
                nodes.append(value)
        if len(nodes) < 2:
            raise ValueError("path has zero length; cannot solve a speed profile")

        count = len(nodes)
        # 1. per-node target, in m/s
        speeds = [min(self.target_kmh_at(s), self.max_kmh) * KMH_TO_MPS for s in nodes]
        # 2. pin the endpoints to rest — every trip starts and ends stationary
        speeds[0] = 0.0
        speeds[-1] = 0.0

        # 3. forward pass: v_i <= sqrt(v_{i-1}^2 + 2*a*ds)
        for i in range(1, count):
            ds = (nodes[i] - nodes[i - 1]) * 1000.0
            reachable = math.sqrt(speeds[i - 1] ** 2 + 2 * self.accel_mps2 * ds)
            speeds[i] = min(speeds[i], reachable)

        # 4. backward pass: v_i <= sqrt(v_{i+1}^2 + 2*d*ds)
        for i in range(count - 2, -1, -1):
            ds = (nodes[i + 1] - nodes[i]) * 1000.0
            stoppable = math.sqrt(speeds[i + 1] ** 2 + 2 * self.decel_mps2 * ds)
            speeds[i] = min(speeds[i], stoppable)

        # 5. integrate time. dt = 2*ds/(v0+v1) is exact for constant acceleration.
        times = [0.0]
        for i in range(1, count):
            ds = (nodes[i] - nodes[i - 1]) * 1000.0
            v_sum = speeds[i - 1] + speeds[i]
            if v_sum <= 1e-9:
                # Both ends at rest across a real gap: only possible on a route
                # too short to accelerate out of. Fall back to the crawl speed
                # so the trip still terminates.
                crawl = MIN_MOVING_KMH * KMH_TO_MPS
                times.append(times[-1] + ds / crawl)
            else:
                times.append(times[-1] + 2 * ds / v_sum)

        return SpeedSolution(
            distances_km=tuple(nodes),
            speeds_mps=tuple(speeds),
            times_s=tuple(times),
        )

    # ── serialisation (snapshots must round-trip exactly) ──

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "rules": [rule.to_dict() for rule in self.rules],
            "accel_mps2": self.accel_mps2,
            "decel_mps2": self.decel_mps2,
            "max_kmh": self.max_kmh,
            "min_kmh": self.min_kmh,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpeedProfile:
        return cls(
            rules=[SpeedRule(**rule) for rule in data["rules"]],
            accel_mps2=float(data.get("accel_mps2", DEFAULT_ACCEL_MPS2)),
            decel_mps2=float(data.get("decel_mps2", DEFAULT_DECEL_MPS2)),
            max_kmh=float(data.get("max_kmh", 95.0)),
            min_kmh=float(data.get("min_kmh", 25.0)),
            name=str(data.get("name", "custom")),
            metadata=dict(data.get("metadata") or {}),
        )

    # ── constructors ──

    @classmethod
    def from_segments(
        cls,
        segments: list[tuple[float, float, float]],
        *,
        name: str = "provider_derived",
        accel_mps2: float = DEFAULT_ACCEL_MPS2,
        decel_mps2: float = DEFAULT_DECEL_MPS2,
        min_kmh: float = 25.0,
        max_kmh: float = 95.0,
    ) -> SpeedProfile:
        """Build a profile from ``(start_km, end_km, observed_kmh)`` triples.

        This is the preferred constructor: the speeds come from the routing
        provider's own per-step distance and duration, so the profile varies
        with the real road rather than with a number we invented. Speeds are
        clamped into the profile's bounds instead of being rejected, because a
        provider step through a toll plaza can legitimately report 4 km/h.
        """
        if not segments:
            raise ValueError("no segments supplied")
        rules: list[SpeedRule] = []
        for start_km, end_km, observed_kmh in segments:
            if end_km - start_km <= 1e-9:
                continue
            rules.append(
                SpeedRule(
                    start_km=start_km,
                    end_km=end_km,
                    target_kmh=min(max(observed_kmh, min_kmh), max_kmh),
                )
            )
        if not rules:
            raise ValueError("every supplied segment had zero length")
        return cls(
            rules=rules,
            accel_mps2=accel_mps2,
            decel_mps2=decel_mps2,
            max_kmh=max_kmh,
            min_kmh=min_kmh,
            name=name,
        )

    @classmethod
    def preset(cls, preset_name: str, total_km: float) -> SpeedProfile:
        """A named fallback profile for when the provider gives no step detail.

        The shape is deliberate rather than random (PHASE 41 forbids random
        speed): slow out of the origin, cruise on the open road, slow into the
        destination, with a mid-route dip standing in for terrain and towns.
        """
        if total_km <= 0:
            raise ValueError("total_km must be positive")
        presets = {
            # name: (urban_out, cruise, dip, urban_in, max)
            "truck_intercity": (45.0, 82.0, 62.0, 40.0, 95.0),
            "truck_mountain": (35.0, 60.0, 45.0, 35.0, 70.0),
            "urban": (28.0, 45.0, 30.0, 25.0, 55.0),
        }
        if preset_name not in presets:
            raise ValueError(f"unknown speed preset: {preset_name}; known: {sorted(presets)}")
        out_kmh, cruise_kmh, dip_kmh, in_kmh, max_kmh = presets[preset_name]

        # Short hops never reach cruise: one band, and the kinematic solver
        # clips it to whatever the distance actually allows.
        if total_km <= 4.0:
            return cls(
                rules=[SpeedRule(0.0, total_km, min(out_kmh, max_kmh))],
                max_kmh=max_kmh,
                min_kmh=min(20.0, out_kmh),
                name=preset_name,
            )

        edge = min(total_km * 0.08, 12.0)
        mid_start = total_km * 0.45
        mid_end = min(total_km * 0.62, total_km - edge)
        rules = [SpeedRule(0.0, edge, out_kmh)]
        if mid_end > mid_start and mid_start > edge:
            rules.append(SpeedRule(edge, mid_start, cruise_kmh))
            rules.append(SpeedRule(mid_start, mid_end, dip_kmh))
            rules.append(SpeedRule(mid_end, total_km - edge, cruise_kmh))
        else:
            rules.append(SpeedRule(edge, total_km - edge, cruise_kmh))
        rules.append(SpeedRule(total_km - edge, total_km, in_kmh))

        return cls(
            rules=rules,
            max_kmh=max_kmh,
            min_kmh=min(20.0, in_kmh, out_kmh, dip_kmh),
            name=preset_name,
        )
