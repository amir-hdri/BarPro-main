"""The travel engine: one clock in, a fully consistent sample out.

This is the object PHASE 9-12 describe. The pipeline is::

    elapsed time (the one clock)
        -> distance travelled      (SpeedSolution.distance_at_time)
            -> position            (PathIndex.position_at)
            -> bearing             (the leg the position landed on)
        -> speed                   (SpeedSolution.speed_kmh_at_time)
        -> remaining / ETA / %     (arithmetic on the two totals)

Every field of :class:`TravelSample` is a pure function of a single elapsed
time. That is the whole trick: position cannot disagree with distance, and
speed cannot disagree with either, because none of them is stored — they are
all recomputed from the same number on every tick. Drift is not "handled"
here; it is unrepresentable.

Direction of control is strictly one-way (PHASE 23): the engine produces
coordinates, and a GPS provider consumes them. A provider never feeds anything
back into route state.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.travel.clock import TravelClock
from app.travel.route import RouteGeometry
from app.travel.speed import SpeedProfile, SpeedSolution
from app.travel.state import TravelStatus, assert_transition

__all__ = [
    "ARRIVAL_TOLERANCE_KM",
    "ConsistencyReport",
    "TravelEngine",
    "TravelSample",
]

#: Within this distance of the end the travel is considered arrived. Larger
#: than float noise, smaller than a city block.
ARRIVAL_TOLERANCE_KM = 0.010

#: Altitude is *nominal*. BarPro has no elevation source, and CRITICAL_RULES
#: forbids presenting a synthesised value as a measurement, so the engine emits
#: a declared constant and every consumer labels it as such.
NOMINAL_ALTITUDE_M = 0.0


@dataclass(frozen=True, slots=True)
class TravelSample:
    """One fully-consistent instant of travel state.

    ``altitude_m`` is nominal (see :data:`NOMINAL_ALTITUDE_M`), not measured.
    Every other field is derived from :attr:`elapsed_s`.
    """

    timestamp: datetime
    status: TravelStatus
    latitude: float
    longitude: float
    bearing_deg: float
    altitude_m: float
    speed_kmh: float
    distance_traveled_km: float
    remaining_distance_km: float
    route_distance_km: float
    elapsed_s: float
    remaining_s: float
    total_duration_s: float
    progress: float
    eta: datetime

    def to_dict(self) -> dict[str, Any]:
        """Wire format for WebSocket events and telemetry rows."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "status": self.status.value,
            "lat": round(self.latitude, 7),
            "lon": round(self.longitude, 7),
            "bearing_deg": round(self.bearing_deg, 2),
            "altitude_m": self.altitude_m,
            "altitude_source": "nominal",
            "speed_kmh": round(self.speed_kmh, 2),
            "distance_traveled_km": round(self.distance_traveled_km, 4),
            "remaining_distance_km": round(self.remaining_distance_km, 4),
            "route_distance_km": round(self.route_distance_km, 4),
            "elapsed_s": round(self.elapsed_s, 2),
            "remaining_s": round(self.remaining_s, 2),
            "total_duration_s": round(self.total_duration_s, 2),
            "progress": round(self.progress, 6),
            "eta": self.eta.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class ConsistencyReport:
    """Result of the PHASE 12 synchronisation audit on a single sample."""

    ok: bool
    distance_to_route_km: float
    distance_sum_error_km: float
    time_sum_error_s: float
    progress_error: float
    speed_vs_displacement_error_kmh: float
    failures: tuple[str, ...]


class TravelEngine:
    """Owns route, speed profile and clock; emits consistent samples."""

    __slots__ = (
        "_altitude_m",
        "_clock",
        "_error_reason",
        "_profile",
        "_route",
        "_solution",
        "_status",
    )

    def __init__(
        self,
        *,
        route: RouteGeometry,
        profile: SpeedProfile,
        clock: TravelClock | None = None,
        status: TravelStatus = TravelStatus.ROUTE_READY,
        altitude_m: float = NOMINAL_ALTITUDE_M,
        error_reason: str | None = None,
    ) -> None:
        route.validate()
        profile.validate()
        self._route = route
        self._profile = profile
        # Solving against the route's own cumulative distances is what binds
        # the speed curve to the geometry (PHASE 7).
        self._solution: SpeedSolution = profile.solve(route.index.cumulative_km)
        self._clock = clock or TravelClock()
        self._status = status
        self._altitude_m = float(altitude_m)
        self._error_reason = error_reason

    # ── construction ──

    @classmethod
    def build(
        cls,
        route: RouteGeometry,
        *,
        profile: SpeedProfile | None = None,
        preset: str = "truck_intercity",
        time_scale: float = 1.0,
        now_fn: Callable[[], datetime] | None = None,
    ) -> TravelEngine:
        """Build an engine, deriving the speed profile from the route if needed.

        Preference order for the profile, most real first:

        1. one supplied explicitly by the caller (a saved template profile),
        2. one derived from the provider's own per-segment timings,
        3. a named preset shaped for the route length.
        """
        resolved = profile
        if resolved is None:
            segments = route.speed_segments()
            if segments:
                resolved = SpeedProfile.from_segments(segments, name="provider_derived")
            else:
                resolved = SpeedProfile.preset(preset, route.total_distance_km)
        return cls(
            route=route,
            profile=resolved,
            clock=TravelClock(time_scale=time_scale, now_fn=now_fn),
            status=TravelStatus.ROUTE_READY,
        )

    # ── read-only accessors ──

    @property
    def route(self) -> RouteGeometry:
        return self._route

    @property
    def profile(self) -> SpeedProfile:
        return self._profile

    @property
    def solution(self) -> SpeedSolution:
        return self._solution

    @property
    def clock(self) -> TravelClock:
        return self._clock

    @property
    def status(self) -> TravelStatus:
        return self._status

    @property
    def error_reason(self) -> str | None:
        return self._error_reason

    @property
    def route_distance_km(self) -> float:
        """PHASE 4: the route's own length, never a straight line."""
        return self._route.total_distance_km

    @property
    def estimated_duration_s(self) -> float:
        """PHASE 5: ETA is the integral of the speed profile, not d/v."""
        return self._solution.total_seconds

    # ── lifecycle (PHASE 13) ──

    def start(self, *, now: datetime | None = None) -> TravelSample:
        """Begin travel. Resets the clock's origin to *now*."""
        self._status = assert_transition(self._status, TravelStatus.TRAVEL_STARTED)
        self._clock = TravelClock(
            started_at=now if now is not None else self._clock._now_fn(),
            time_scale=self._clock.time_scale,
            now_fn=self._clock._now_fn,
        )
        return self.sample(now=now)

    def pause(self, *, now: datetime | None = None) -> TravelSample:
        """Freeze every derived quantity (PHASE 14).

        Because the clock stops, distance, speed, ETA and progress stop with
        it — there is no separate "stop the GPS" step that could be forgotten.
        """
        self._status = assert_transition(self._status, TravelStatus.PAUSED)
        self._clock.pause(now=now)
        return self.sample(now=now)

    def resume(self, *, now: datetime | None = None) -> TravelSample:
        """Continue from the same route progress the pause froze."""
        self._status = assert_transition(self._status, TravelStatus.RESUMED)
        self._clock.resume(now=now)
        return self.sample(now=now)

    def cancel(self, *, now: datetime | None = None) -> TravelSample:
        self._status = assert_transition(self._status, TravelStatus.CANCELLED)
        self._clock.pause(now=now)
        return self.sample(now=now)

    def fail(self, reason: str, *, now: datetime | None = None) -> TravelSample:
        self._status = assert_transition(self._status, TravelStatus.ERROR)
        self._error_reason = reason
        self._clock.pause(now=now)
        return self.sample(now=now)

    def enter_recovery(self, *, now: datetime | None = None) -> TravelSample:
        """Mark the travel as being re-acquired by another worker."""
        self._status = assert_transition(self._status, TravelStatus.RECOVERY)
        return self.sample(now=now)

    def complete_recovery(self, *, now: datetime | None = None) -> TravelSample:
        """Return to the live lifecycle after a successful hand-over.

        Resumes into PAUSED if the clock is paused, otherwise into MOVING, so a
        travel that was paused when its worker died does not silently start
        moving again on the new one.
        """
        target = TravelStatus.PAUSED if self._clock.is_paused else TravelStatus.MOVING
        self._status = assert_transition(self._status, target)
        self._error_reason = None
        return self.sample(now=now)

    # ── the sample: everything, from one number ──

    def sample(self, *, now: datetime | None = None) -> TravelSample:
        """Current travel state, fully self-consistent.

        Also advances the lifecycle where the clock implies it:
        ``TRAVEL_STARTED``/``RESUMED`` become ``MOVING`` once motion is under
        way, and ``MOVING`` becomes ``ARRIVED`` at the end of the route.
        """
        stamp = now if now is not None else self._clock._now_fn()
        # Paused/terminal travels must not consume clock time.
        if self._status in (TravelStatus.PAUSED, TravelStatus.CANCELLED, TravelStatus.ERROR):
            elapsed = self._clock.peek_elapsed_s(now=stamp)
        else:
            elapsed = self._clock.elapsed_s(now=stamp)

        total_s = self._solution.total_seconds
        total_km = self._route.total_distance_km

        distance_km = self._solution.distance_at_time(elapsed)
        position = self._route.index.position_at(distance_km)
        speed_kmh = self._solution.speed_kmh_at_time(elapsed)
        remaining_km = max(0.0, total_km - distance_km)
        remaining_s = max(0.0, total_s - elapsed)
        progress = 0.0 if total_km <= 0 else min(1.0, distance_km / total_km)

        self._advance_status(remaining_km=remaining_km, elapsed=elapsed)
        # A paused or stopped vehicle is not moving, whatever the curve says.
        if self._status in (
            TravelStatus.PAUSED,
            TravelStatus.CANCELLED,
            TravelStatus.ERROR,
            TravelStatus.ARRIVED,
            TravelStatus.RECOVERY,
        ):
            speed_kmh = 0.0

        return TravelSample(
            timestamp=stamp,
            status=self._status,
            latitude=position.point.lat,
            longitude=position.point.lon,
            bearing_deg=position.bearing_deg,
            altitude_m=self._altitude_m,
            speed_kmh=speed_kmh,
            distance_traveled_km=distance_km,
            remaining_distance_km=remaining_km,
            route_distance_km=total_km,
            elapsed_s=elapsed,
            remaining_s=remaining_s,
            total_duration_s=total_s,
            progress=progress,
            eta=self._clock.wall_time_for_elapsed(total_s, now=stamp),
        )

    def _advance_status(self, *, remaining_km: float, elapsed: float) -> None:
        if self._status in (TravelStatus.TRAVEL_STARTED, TravelStatus.RESUMED):
            if remaining_km <= ARRIVAL_TOLERANCE_KM and elapsed >= self._solution.total_seconds:
                self._status = assert_transition(self._status, TravelStatus.ARRIVED)
            else:
                self._status = assert_transition(self._status, TravelStatus.MOVING)
            return
        if self._status is TravelStatus.MOVING and (
            remaining_km <= ARRIVAL_TOLERANCE_KM or elapsed >= self._solution.total_seconds
        ):
            self._status = assert_transition(self._status, TravelStatus.ARRIVED)

    # ── PHASE 12 / 33 / 34 verification ──

    def verify_sample(self, sample: TravelSample, *, tolerance_km: float = 0.05) -> ConsistencyReport:
        """Audit a sample against the synchronisation contract.

        Checks that are genuinely independent of how the sample was produced:

        * the emitted coordinate lies on the route geometry (PHASE 33);
        * travelled + remaining == route distance (PHASE 4);
        * elapsed + remaining == total duration;
        * progress matches the distance ratio;
        * the reported speed matches the distance the vehicle actually covers
          around that instant (PHASE 34) — a finite-difference check that would
          catch a speed field wired to anything other than the real curve.
        """
        failures: list[str] = []

        distance_to_route = self._route.index.distance_to_path_km(sample.latitude, sample.longitude)
        if distance_to_route > tolerance_km:
            failures.append(
                f"position is {distance_to_route * 1000:.1f} m off-route " f"(tolerance {tolerance_km * 1000:.0f} m)"
            )

        distance_error = abs(sample.distance_traveled_km + sample.remaining_distance_km - sample.route_distance_km)
        if distance_error > 1e-6:
            failures.append(f"travelled + remaining != route distance (off by {distance_error:.6f} km)")

        time_error = abs(sample.elapsed_s + sample.remaining_s - sample.total_duration_s)
        # Past the ETA both remaining values clamp to zero, which is correct.
        if sample.elapsed_s < sample.total_duration_s and time_error > 1e-6:
            failures.append(f"elapsed + remaining != total duration (off by {time_error:.6f} s)")

        expected_progress = (
            0.0 if sample.route_distance_km <= 0 else sample.distance_traveled_km / sample.route_distance_km
        )
        progress_error = abs(sample.progress - expected_progress)
        if progress_error > 1e-6:
            failures.append(f"progress != travelled/route (off by {progress_error:.8f})")

        speed_error = self._speed_vs_displacement_error(sample)
        if speed_error > 1.0 and sample.status is TravelStatus.MOVING:
            failures.append(f"reported speed disagrees with displacement by {speed_error:.2f} km/h")

        return ConsistencyReport(
            ok=not failures,
            distance_to_route_km=distance_to_route,
            distance_sum_error_km=distance_error,
            time_sum_error_s=time_error,
            progress_error=progress_error,
            speed_vs_displacement_error_kmh=speed_error,
            failures=tuple(failures),
        )

    def _speed_vs_displacement_error(self, sample: TravelSample) -> float:
        """|reported speed - central-difference speed| in km/h."""
        half_window = 0.5
        lo = max(0.0, sample.elapsed_s - half_window)
        hi = min(self._solution.total_seconds, sample.elapsed_s + half_window)
        window = hi - lo
        if window <= 0:
            return 0.0
        covered = self._solution.distance_at_time(hi) - self._solution.distance_at_time(lo)
        measured_kmh = covered / (window / 3600.0)
        return abs(measured_kmh - sample.speed_kmh)

    # ── persistence: a recovering worker rebuilds an identical engine ──

    def to_dict(self) -> dict[str, Any]:
        return {
            "route": self._route.to_dict(),
            "profile": self._profile.to_dict(),
            "clock": self._clock.to_dict(),
            "status": self._status.value,
            "altitude_m": self._altitude_m,
            "error_reason": self._error_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, now_fn: Callable[[], datetime] | None = None) -> TravelEngine:
        return cls(
            route=RouteGeometry.from_dict(data["route"]),
            profile=SpeedProfile.from_dict(data["profile"]),
            clock=TravelClock.from_dict(data["clock"], now_fn=now_fn),
            status=TravelStatus(data.get("status", TravelStatus.ROUTE_READY.value)),
            altitude_m=float(data.get("altitude_m", NOMINAL_ALTITUDE_M)),
            error_reason=data.get("error_reason"),
        )
