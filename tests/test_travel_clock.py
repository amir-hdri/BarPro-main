from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from app.travel.clock import MAX_TIME_SCALE, TravelClock


def make_clock_fn() -> tuple[Callable[[], datetime], Callable[[float], datetime]]:
    current = datetime(2026, 9, 16, 12, 0, 0, tzinfo=UTC)

    def advance(seconds: float = 0.0) -> datetime:
        nonlocal current
        current += timedelta(seconds=seconds)
        return current

    def get() -> datetime:
        return current

    return get, advance


@pytest.mark.unit
class TestTravelClockConstruction:
    def test_default_construction(self) -> None:
        clock = TravelClock()
        assert clock.time_scale == 1.0
        assert clock.paused_total_s == 0.0
        assert not clock.is_paused

    def test_custom_started_at(self) -> None:
        started_at = datetime(2026, 9, 16, 12, 0, 0, tzinfo=UTC)
        clock = TravelClock(started_at=started_at)
        assert clock.started_at == started_at

    def test_invalid_time_scale(self) -> None:
        with pytest.raises(ValueError, match="time_scale"):
            TravelClock(time_scale=0.0)
        with pytest.raises(ValueError, match="time_scale"):
            TravelClock(time_scale=MAX_TIME_SCALE + 1.0)

    def test_invalid_paused_total(self) -> None:
        with pytest.raises(ValueError, match="paused_total_s"):
            TravelClock(paused_total_s=-1.0)

    def test_naive_datetime_normalized(self) -> None:
        naive_dt = datetime(2026, 9, 16, 12, 0, 0)
        clock = TravelClock(started_at=naive_dt)
        assert clock.started_at.tzinfo == UTC


@pytest.mark.unit
class TestTravelClockElapsed:
    def test_elapsed_increases_with_wall_time(self) -> None:
        get_now, advance_now = make_clock_fn()
        clock = TravelClock(started_at=get_now(), now_fn=get_now)

        assert clock.elapsed_s() == 0.0
        advance_now(10.0)
        assert clock.elapsed_s() == pytest.approx(10.0, abs=1e-3)

    def test_time_scale(self) -> None:
        get_now, advance_now = make_clock_fn()
        clock = TravelClock(started_at=get_now(), time_scale=2.0, now_fn=get_now)

        advance_now(10.0)
        assert clock.elapsed_s() == pytest.approx(20.0, abs=1e-3)

    def test_monotonicity_backwards_clock(self) -> None:
        get_now, advance_now = make_clock_fn()
        clock = TravelClock(started_at=get_now(), now_fn=get_now)

        advance_now(10.0)
        e1 = clock.elapsed_s()
        advance_now(-5.0)
        e2 = clock.elapsed_s()
        assert e2 == e1

    def test_peek_elapsed_s(self) -> None:
        get_now, advance_now = make_clock_fn()
        clock = TravelClock(started_at=get_now(), now_fn=get_now)

        advance_now(10.0)
        assert clock.peek_elapsed_s() == pytest.approx(10.0, abs=1e-3)
        # Going back in time before elapsed_s was called should not be clamped by peek
        advance_now(-5.0)
        assert clock.elapsed_s() == pytest.approx(5.0, abs=1e-3)


@pytest.mark.unit
class TestTravelClockPauseResume:
    def test_pause_resume(self) -> None:
        get_now, advance_now = make_clock_fn()
        clock = TravelClock(started_at=get_now(), now_fn=get_now)

        advance_now(10.0)
        clock.pause()
        assert clock.is_paused

        advance_now(20.0)
        assert clock.elapsed_s() == pytest.approx(10.0, abs=1e-3)

        clock.resume()
        assert not clock.is_paused
        advance_now(10.0)
        assert clock.elapsed_s() == pytest.approx(20.0, abs=1e-3)
        assert clock.paused_total_s == pytest.approx(20.0, abs=1e-3)

    def test_idempotent_pause_resume(self) -> None:
        get_now, advance_now = make_clock_fn()
        clock = TravelClock(started_at=get_now(), now_fn=get_now)

        clock.pause()
        clock.pause()
        assert clock.is_paused

        clock.resume()
        clock.resume()
        assert not clock.is_paused


@pytest.mark.unit
class TestTravelClockWallTime:
    def test_wall_time_for_elapsed(self) -> None:
        get_now, advance_now = make_clock_fn()
        start = get_now()
        clock = TravelClock(started_at=start, time_scale=2.0, now_fn=get_now)

        wt = clock.wall_time_for_elapsed(20.0)
        assert wt == start + timedelta(seconds=10.0)


@pytest.mark.unit
class TestTravelClockSerialization:
    def test_serialization(self) -> None:
        get_now, advance_now = make_clock_fn()
        clock = TravelClock(started_at=get_now(), time_scale=1.5, now_fn=get_now)

        advance_now(10.0)
        clock.pause()
        advance_now(5.0)

        d = clock.to_dict()
        assert "started_at" in d
        assert "paused_at" in d
        assert "paused_total_s" in d
        assert "time_scale" in d

        restored = TravelClock.from_dict(d, now_fn=get_now)
        assert restored.is_paused
        assert restored.time_scale == 1.5
        assert restored.paused_total_s == clock.paused_total_s
        assert restored.started_at == clock.started_at

    def test_recovery_preserves_progress_after_backwards_clock_step(self) -> None:
        get_now, advance_now = make_clock_fn()
        clock = TravelClock(now_fn=get_now)
        advance_now(100)
        assert clock.elapsed_s() == 100
        advance_now(-50)
        assert clock.elapsed_s() == 100
        restored = TravelClock.from_dict(clock.to_dict(), now_fn=get_now)
        assert restored.elapsed_s() == 100

    def test_pause_freezes_progress_before_next_sample(self) -> None:
        get_now, advance_now = make_clock_fn()
        clock = TravelClock(now_fn=get_now)
        advance_now(10)
        clock.elapsed_s()
        advance_now(90)
        clock.pause()
        advance_now(10)
        assert clock.peek_elapsed_s() == 100
        advance_now(-60)
        assert clock.peek_elapsed_s() == 100
        restored = TravelClock.from_dict(clock.to_dict(), now_fn=get_now)
        assert restored.peek_elapsed_s() == 100
