"""Travel state machine (PHASE 13).

A single explicit transition table, so an illegal move is a loud error rather
than a silently inconsistent row. The states follow the lifecycle the spec
requires::

    IDLE -> ROUTE_READY -> TRAVEL_STARTED -> MOVING -> PAUSED -> RESUMED
                                                 -> MOVING -> ARRIVED

with ``CANCELLED``, ``ERROR`` and ``RECOVERY`` reachable from the live states.

``RESUMED`` is kept as a distinct state rather than folded into ``MOVING``
because the spec names it, and because an observer watching the event stream
needs to be able to tell "still moving" from "just came back". The engine
advances it to ``MOVING`` on the next tick.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "ACTIVE_STATES",
    "TERMINAL_STATES",
    "TRANSITIONS",
    "TravelStatus",
    "assert_transition",
    "can_transition",
]


class TravelStatus(StrEnum):
    """Lifecycle state of one travel execution.

    ``str`` mixin so the value serialises directly into JSON payloads, Redis
    hashes and DB columns without a converter on every boundary.
    """

    IDLE = "IDLE"
    ROUTE_READY = "ROUTE_READY"
    TRAVEL_STARTED = "TRAVEL_STARTED"
    MOVING = "MOVING"
    PAUSED = "PAUSED"
    RESUMED = "RESUMED"
    ARRIVED = "ARRIVED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"
    RECOVERY = "RECOVERY"


#: Legal transitions. Anything absent here is a bug, not a special case.
TRANSITIONS: dict[TravelStatus, frozenset[TravelStatus]] = {
    TravelStatus.IDLE: frozenset({TravelStatus.ROUTE_READY, TravelStatus.CANCELLED, TravelStatus.ERROR}),
    TravelStatus.ROUTE_READY: frozenset({TravelStatus.TRAVEL_STARTED, TravelStatus.CANCELLED, TravelStatus.ERROR}),
    TravelStatus.TRAVEL_STARTED: frozenset(
        {
            TravelStatus.MOVING,
            TravelStatus.PAUSED,
            TravelStatus.CANCELLED,
            TravelStatus.ERROR,
            # A zero-length or already-complete route arrives on the first tick.
            TravelStatus.ARRIVED,
        }
    ),
    TravelStatus.MOVING: frozenset(
        {
            TravelStatus.PAUSED,
            TravelStatus.ARRIVED,
            TravelStatus.CANCELLED,
            TravelStatus.ERROR,
            TravelStatus.RECOVERY,
        }
    ),
    TravelStatus.PAUSED: frozenset(
        {TravelStatus.RESUMED, TravelStatus.CANCELLED, TravelStatus.ERROR, TravelStatus.RECOVERY}
    ),
    TravelStatus.RESUMED: frozenset(
        {
            TravelStatus.MOVING,
            TravelStatus.PAUSED,
            TravelStatus.ARRIVED,
            TravelStatus.CANCELLED,
            TravelStatus.ERROR,
            TravelStatus.RECOVERY,
        }
    ),
    # Recovery re-enters the lifecycle at the state it left, or gives up.
    TravelStatus.RECOVERY: frozenset(
        {
            TravelStatus.MOVING,
            TravelStatus.PAUSED,
            TravelStatus.ARRIVED,
            TravelStatus.CANCELLED,
            TravelStatus.ERROR,
        }
    ),
    # ERROR is recoverable — a worker crash must not permanently strand a job.
    TravelStatus.ERROR: frozenset({TravelStatus.RECOVERY, TravelStatus.CANCELLED}),
    TravelStatus.ARRIVED: frozenset(),
    TravelStatus.CANCELLED: frozenset(),
}

#: States in which a travel holds a lease and is expected to heartbeat.
ACTIVE_STATES: frozenset[TravelStatus] = frozenset(
    {
        TravelStatus.TRAVEL_STARTED,
        TravelStatus.MOVING,
        TravelStatus.PAUSED,
        TravelStatus.RESUMED,
        TravelStatus.RECOVERY,
    }
)

#: States from which nothing further happens.
TERMINAL_STATES: frozenset[TravelStatus] = frozenset({TravelStatus.ARRIVED, TravelStatus.CANCELLED})


class IllegalTransitionError(RuntimeError):
    """Raised when code attempts a transition the lifecycle does not allow."""

    def __init__(self, current: TravelStatus, target: TravelStatus) -> None:
        allowed = ", ".join(sorted(s.value for s in TRANSITIONS.get(current, frozenset())))
        super().__init__(
            f"illegal travel transition {current.value} -> {target.value}; "
            f"allowed from {current.value}: [{allowed or 'none — terminal state'}]"
        )
        self.current = current
        self.target = target


def can_transition(current: TravelStatus, target: TravelStatus) -> bool:
    """Whether ``current -> target`` is a legal move."""
    return target in TRANSITIONS.get(current, frozenset())


def assert_transition(current: TravelStatus, target: TravelStatus) -> TravelStatus:
    """Return ``target`` if the move is legal, else raise.

    Returning the target lets call sites write ``self._status =
    assert_transition(self._status, TravelStatus.MOVING)`` so the check can
    never be accidentally skipped.
    """
    if not can_transition(current, target):
        raise IllegalTransitionError(current, target)
    return target
