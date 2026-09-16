import pytest

from app.travel.state import (
    ACTIVE_STATES,
    TERMINAL_STATES,
    TRANSITIONS,
    IllegalTransitionError,
    TravelStatus,
    assert_transition,
    can_transition,
)


@pytest.mark.unit
def test_travel_status_values():
    assert TravelStatus.IDLE == "IDLE"
    assert TravelStatus.ROUTE_READY == "ROUTE_READY"
    assert TravelStatus.TRAVEL_STARTED == "TRAVEL_STARTED"
    assert TravelStatus.MOVING == "MOVING"
    assert TravelStatus.PAUSED == "PAUSED"
    assert TravelStatus.RESUMED == "RESUMED"
    assert TravelStatus.ARRIVED == "ARRIVED"
    assert TravelStatus.CANCELLED == "CANCELLED"
    assert TravelStatus.ERROR == "ERROR"
    assert TravelStatus.RECOVERY == "RECOVERY"


@pytest.mark.unit
def test_transitions_table():
    assert TRANSITIONS[TravelStatus.IDLE] == {TravelStatus.ROUTE_READY, TravelStatus.CANCELLED, TravelStatus.ERROR}
    assert TRANSITIONS[TravelStatus.ROUTE_READY] == {
        TravelStatus.TRAVEL_STARTED,
        TravelStatus.CANCELLED,
        TravelStatus.ERROR,
    }
    assert TRANSITIONS[TravelStatus.TRAVEL_STARTED] == {
        TravelStatus.MOVING,
        TravelStatus.PAUSED,
        TravelStatus.CANCELLED,
        TravelStatus.ERROR,
        TravelStatus.ARRIVED,
    }
    assert TRANSITIONS[TravelStatus.MOVING] == {
        TravelStatus.PAUSED,
        TravelStatus.ARRIVED,
        TravelStatus.CANCELLED,
        TravelStatus.ERROR,
        TravelStatus.RECOVERY,
    }
    assert TRANSITIONS[TravelStatus.PAUSED] == {
        TravelStatus.RESUMED,
        TravelStatus.CANCELLED,
        TravelStatus.ERROR,
        TravelStatus.RECOVERY,
    }
    assert TRANSITIONS[TravelStatus.RESUMED] == {
        TravelStatus.MOVING,
        TravelStatus.PAUSED,
        TravelStatus.ARRIVED,
        TravelStatus.CANCELLED,
        TravelStatus.ERROR,
        TravelStatus.RECOVERY,
    }
    assert TRANSITIONS[TravelStatus.RECOVERY] == {
        TravelStatus.MOVING,
        TravelStatus.PAUSED,
        TravelStatus.ARRIVED,
        TravelStatus.CANCELLED,
        TravelStatus.ERROR,
    }
    assert TRANSITIONS[TravelStatus.ERROR] == {TravelStatus.RECOVERY, TravelStatus.CANCELLED}
    assert TRANSITIONS[TravelStatus.ARRIVED] == frozenset()
    assert TRANSITIONS[TravelStatus.CANCELLED] == frozenset()


@pytest.mark.unit
def test_can_transition():
    for source, targets in TRANSITIONS.items():
        for target in TravelStatus:
            if target in targets:
                assert can_transition(source, target) is True
            else:
                assert can_transition(source, target) is False


@pytest.mark.unit
def test_assert_transition():
    # Legal transition
    assert assert_transition(TravelStatus.IDLE, TravelStatus.ROUTE_READY) == TravelStatus.ROUTE_READY

    # Illegal transition
    with pytest.raises(IllegalTransitionError) as exc_info:
        assert_transition(TravelStatus.IDLE, TravelStatus.ARRIVED)

    error = exc_info.value
    assert error.current == TravelStatus.IDLE
    assert error.target == TravelStatus.ARRIVED
    assert "illegal travel transition IDLE -> ARRIVED" in str(error)
    assert "allowed from IDLE" in str(error)


@pytest.mark.unit
def test_active_states():
    assert TravelStatus.TRAVEL_STARTED in ACTIVE_STATES
    assert TravelStatus.MOVING in ACTIVE_STATES
    assert TravelStatus.PAUSED in ACTIVE_STATES
    assert TravelStatus.RESUMED in ACTIVE_STATES
    assert TravelStatus.RECOVERY in ACTIVE_STATES

    assert TravelStatus.IDLE not in ACTIVE_STATES
    assert TravelStatus.ROUTE_READY not in ACTIVE_STATES
    assert TravelStatus.ARRIVED not in ACTIVE_STATES
    assert TravelStatus.CANCELLED not in ACTIVE_STATES
    assert TravelStatus.ERROR not in ACTIVE_STATES


@pytest.mark.unit
def test_terminal_states():
    assert TravelStatus.ARRIVED in TERMINAL_STATES
    assert TravelStatus.CANCELLED in TERMINAL_STATES

    for state in TravelStatus:
        if state not in (TravelStatus.ARRIVED, TravelStatus.CANCELLED):
            assert state not in TERMINAL_STATES
