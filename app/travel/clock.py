"""The single travel clock (PHASE 10).

There is exactly one clock per travel execution. Position, speed, distance,
elapsed time, remaining time, ETA and progress are *all* derived from the
number this object returns. Nothing else in the system is permitted to call
``time.time()`` and use the result to advance travel state — that is what
produces the drift PHASE 11/12 forbid.

The clock is built on wall time rather than ``time.monotonic()`` because a
travel must survive a worker crash: recovery on a second worker reads the
persisted ``started_at`` and continues at the same elapsed offset, and a
monotonic reading from a dead process means nothing. Wall time brings the risk
of NTP steps, so readings are floored monotonically: elapsed time can stall,
but it can never run backwards and rewind the vehicle.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

__all__ = ["MAX_TIME_SCALE", "TravelClock"]

#: Upper bound on simulated-seconds-per-wall-second. A finite cap keeps a
#: mis-set scale from making a 4-hour trip "arrive" inside one tick.
MAX_TIME_SCALE = 3600.0


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    """Normalise to aware UTC; a naive datetime is read as UTC, not local."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class TravelClock:
    """Elapsed *travel* seconds: wall time minus paused time, times the scale."""

    __slots__ = (
        "_drift_corrections",
        "_floor_s",
        "_now_fn",
        "_paused_at",
        "_paused_total_s",
        "_started_at",
        "_time_scale",
    )

    def __init__(
        self,
        *,
        started_at: datetime | None = None,
        paused_at: datetime | None = None,
        paused_total_s: float = 0.0,
        time_scale: float = 1.0,
        elapsed_floor_s: float = 0.0,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        if time_scale <= 0 or time_scale > MAX_TIME_SCALE:
            raise ValueError(f"time_scale must be in (0, {MAX_TIME_SCALE}]; got {time_scale}")
        if paused_total_s < 0:
            raise ValueError("paused_total_s cannot be negative")
        if not math.isfinite(elapsed_floor_s) or elapsed_floor_s < 0:
            raise ValueError("elapsed_floor_s must be finite and non-negative")

        self._now_fn: Callable[[], datetime] = now_fn or _utcnow
        self._started_at: datetime = _as_utc(started_at) if started_at else self._now_fn()
        self._paused_at: datetime | None = _as_utc(paused_at) if paused_at else None
        self._paused_total_s: float = float(paused_total_s)
        self._time_scale: float = float(time_scale)
        self._floor_s: float = float(elapsed_floor_s)
        self._drift_corrections: int = 0

    # ── reading ──

    def elapsed_s(self, *, now: datetime | None = None) -> float:
        """Travel seconds since departure, excluding paused time.

        Monotonic: a backwards wall-clock step stalls the reading at its
        previous value and increments :attr:`drift_corrections` rather than
        moving the vehicle back down the route.
        """
        raw = self._raw_elapsed_s(now)
        if raw < self._floor_s - 1e-9:
            self._drift_corrections += 1
            return self._floor_s
        self._floor_s = raw
        return raw

    def peek_elapsed_s(self, *, now: datetime | None = None) -> float:
        """Read elapsed time without advancing the monotonic floor."""
        return max(self._floor_s, self._raw_elapsed_s(now))

    def _raw_elapsed_s(self, now: datetime | None = None) -> float:
        current = _as_utc(now) if now else self._now_fn()
        # A paused reading depends on the pause instant, never on current wall
        # time. In particular, a backwards NTP step must not move a parked point.
        effective = self._paused_at if self._paused_at is not None else current
        wall = (effective - self._started_at).total_seconds()
        return max(0.0, (wall - self._paused_total_s) * self._time_scale)

    # ── pause / resume (PHASE 14) ──

    def pause(self, *, now: datetime | None = None) -> None:
        """Stop the clock. Idempotent — pausing twice does not double-count."""
        if self._paused_at is not None:
            return
        current = _as_utc(now) if now else self._now_fn()
        self.elapsed_s(now=current)
        self._paused_at = current

    def resume(self, *, now: datetime | None = None) -> None:
        """Restart the clock, banking the paused interval. Idempotent."""
        if self._paused_at is None:
            return
        current = _as_utc(now) if now else self._now_fn()
        self._paused_total_s += max(0.0, (current - self._paused_at).total_seconds())
        self._paused_at = None

    # ── properties ──

    @property
    def is_paused(self) -> bool:
        return self._paused_at is not None

    @property
    def started_at(self) -> datetime:
        return self._started_at

    @property
    def paused_at(self) -> datetime | None:
        return self._paused_at

    @property
    def paused_total_s(self) -> float:
        """Paused wall seconds banked so far, excluding any pause in progress."""
        return self._paused_total_s

    @property
    def time_scale(self) -> float:
        return self._time_scale

    @property
    def now_fn(self) -> Callable[[], datetime]:
        """The wall-clock source, so a restarted clock can inherit it (tests)."""
        return self._now_fn

    @property
    def drift_corrections(self) -> int:
        """How many times a backwards wall-clock step was suppressed."""
        return self._drift_corrections

    def wall_time_for_elapsed(self, elapsed_s: float, *, now: datetime | None = None) -> datetime:
        """Wall-clock instant at which a given travel offset is (or was) reached.

        Used to turn "remaining travel seconds" into a real ETA timestamp for
        the UI. Accounts for the scale and for a pause in progress by
        projecting forward from *now* rather than from departure.
        """
        current = _as_utc(now) if now else self._now_fn()
        delta_travel = elapsed_s - self.peek_elapsed_s(now=current)
        return current.fromtimestamp(current.timestamp() + delta_travel / self._time_scale, tz=UTC)

    # ── persistence: a recovering worker rebuilds the same clock ──

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self._started_at.isoformat(),
            "paused_at": self._paused_at.isoformat() if self._paused_at else None,
            "paused_total_s": round(self._paused_total_s, 6),
            "time_scale": self._time_scale,
            "elapsed_floor_s": self._floor_s,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, now_fn: Callable[[], datetime] | None = None) -> TravelClock:
        paused_raw = data.get("paused_at")
        return cls(
            started_at=datetime.fromisoformat(data["started_at"]),
            paused_at=datetime.fromisoformat(paused_raw) if paused_raw else None,
            paused_total_s=float(data.get("paused_total_s") or 0.0),
            time_scale=float(data.get("time_scale") or 1.0),
            elapsed_floor_s=float(data.get("elapsed_floor_s", 0.0)),
            now_fn=now_fn,
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        state = "paused" if self.is_paused else "running"
        return (
            f"TravelClock({state}, started_at={self._started_at.isoformat()}, "
            f"elapsed={self.peek_elapsed_s():.1f}s, scale={self._time_scale})"
        )
