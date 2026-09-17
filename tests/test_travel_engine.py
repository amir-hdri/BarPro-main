from datetime import UTC, datetime, timedelta

import pytest

from app.travel.engine import (
    NOMINAL_ALTITUDE_M,
    ConsistencyReport,
    TravelEngine,
    TravelSample,
)
from app.travel.geometry import GeoPoint
from app.travel.route import RouteGeometry, RouteSegment
from app.travel.speed import SpeedProfile
from app.travel.state import IllegalTransitionError, TravelStatus

# Use Tehran → Isfahan route (~340km)
TEHRAN = GeoPoint(35.6892, 51.389)
ISFAHAN = GeoPoint(32.6546, 51.668)
QOM = GeoPoint(34.6416, 50.8746)


@pytest.fixture
def mock_clock():
    class MockClock:
        def __init__(self) -> None:
            self.current_time = datetime(2026, 9, 16, 12, 0, 0, tzinfo=UTC)

        def now(self) -> datetime:
            return self.current_time

        def advance(self, seconds: float) -> None:
            self.current_time += timedelta(seconds=seconds)

    return MockClock()


@pytest.fixture
def test_route() -> RouteGeometry:
    return RouteGeometry.from_points([TEHRAN, QOM, ISFAHAN])


@pytest.fixture
def test_engine(test_route: RouteGeometry, mock_clock) -> TravelEngine:
    return TravelEngine.build(
        route=test_route,
        preset="truck_intercity",
        time_scale=1.0,
        now_fn=mock_clock.now,
    )


@pytest.mark.unit
def test_engine_build_preset(test_route: RouteGeometry) -> None:
    engine = TravelEngine.build(route=test_route, preset="truck_intercity")
    assert engine.status == TravelStatus.ROUTE_READY
    assert engine.profile.name == "truck_intercity"


@pytest.mark.unit
def test_engine_build_explicit_profile(test_route: RouteGeometry) -> None:
    profile = SpeedProfile.preset("urban", total_km=test_route.total_distance_km)
    profile.name = "custom"
    engine = TravelEngine.build(route=test_route, profile=profile)
    assert engine.status == TravelStatus.ROUTE_READY
    assert engine.profile.name == "custom"


@pytest.mark.unit
def test_engine_build_provider_segments(test_route: RouteGeometry) -> None:
    tot = test_route.total_distance_km
    test_route.segments = [RouteSegment(index=0, start_km=0.0, end_km=tot, distance_km=tot, duration_s=7200.0)]
    engine = TravelEngine.build(route=test_route)
    assert engine.status == TravelStatus.ROUTE_READY
    assert engine.profile.name == "provider_derived"


@pytest.mark.unit
def test_engine_properties(test_engine: TravelEngine) -> None:
    assert test_engine.route_distance_km > 0
    assert test_engine.estimated_duration_s > 0
    assert test_engine.route is not None
    assert test_engine.profile is not None
    assert test_engine.solution is not None
    assert test_engine.status == TravelStatus.ROUTE_READY


@pytest.mark.unit
def test_engine_lifecycle(test_engine: TravelEngine) -> None:
    # ROUTE_READY -> TRAVEL_STARTED -> MOVING
    sample = test_engine.start()
    assert isinstance(sample, TravelSample)
    assert test_engine.status == TravelStatus.MOVING

    # MOVING -> PAUSED
    test_engine.pause()
    assert test_engine.status == TravelStatus.PAUSED

    # PAUSED -> RESUMED -> MOVING
    test_engine.resume()
    assert test_engine.status == TravelStatus.MOVING

    # MOVING -> RECOVERY
    test_engine.enter_recovery()
    assert test_engine.status == TravelStatus.RECOVERY

    # RECOVERY -> MOVING
    test_engine.complete_recovery()
    assert test_engine.status == TravelStatus.MOVING

    # MOVING -> ERROR
    test_engine.fail("test error")
    assert test_engine.status == TravelStatus.ERROR
    assert test_engine.error_reason == "test error"

    # ERROR -> CANCELLED
    test_engine.cancel()
    assert test_engine.status == TravelStatus.CANCELLED

    # Illegal transition from CANCELLED
    with pytest.raises(IllegalTransitionError):
        test_engine.start()


@pytest.mark.unit
def test_engine_recovery_when_paused(test_engine: TravelEngine) -> None:
    test_engine.start()
    test_engine.pause()
    test_engine.enter_recovery()
    assert test_engine.status == TravelStatus.RECOVERY
    test_engine.complete_recovery()
    assert test_engine.status == TravelStatus.PAUSED


@pytest.mark.unit
def test_sample_consistency(test_engine: TravelEngine, mock_clock) -> None:
    sample = test_engine.start()
    assert sample.progress == pytest.approx(0.0, abs=1e-3)
    assert sample.distance_traveled_km + sample.remaining_distance_km == pytest.approx(test_engine.route_distance_km)
    assert sample.elapsed_s + sample.remaining_s == pytest.approx(test_engine.estimated_duration_s)
    assert sample.altitude_m == NOMINAL_ALTITUDE_M

    test_engine.pause()
    mock_clock.advance(10)
    sample_paused = test_engine.sample()
    assert sample_paused.speed_kmh == 0.0


@pytest.mark.unit
def test_arrival_detection(test_route: RouteGeometry, mock_clock) -> None:
    engine = TravelEngine.build(
        route=test_route,
        preset="truck_intercity",
        time_scale=1.0,
        now_fn=mock_clock.now,
    )
    engine.start()

    # Advance time beyond estimated duration
    mock_clock.advance(engine.estimated_duration_s + 10.0)
    sample = engine.sample()
    assert engine.status == TravelStatus.ARRIVED
    assert sample.progress == pytest.approx(1.0, abs=1e-3)
    assert sample.speed_kmh == 0.0


@pytest.mark.unit
def test_verify_sample(test_engine: TravelEngine, mock_clock) -> None:
    test_engine.start()
    mock_clock.advance(10.0)
    sample = test_engine.sample()
    report = test_engine.verify_sample(sample)
    assert isinstance(report, ConsistencyReport)
    assert report.ok is True
    assert not report.failures

    # Off-route sample
    off_route_sample = TravelSample(
        timestamp=sample.timestamp,
        status=sample.status,
        latitude=sample.latitude + 1.0,
        longitude=sample.longitude,
        bearing_deg=sample.bearing_deg,
        altitude_m=sample.altitude_m,
        speed_kmh=sample.speed_kmh,
        distance_traveled_km=sample.distance_traveled_km,
        remaining_distance_km=sample.remaining_distance_km,
        route_distance_km=sample.route_distance_km,
        elapsed_s=sample.elapsed_s,
        remaining_s=sample.remaining_s,
        total_duration_s=sample.total_duration_s,
        progress=sample.progress,
        eta=sample.eta,
    )
    report2 = test_engine.verify_sample(off_route_sample)
    assert report2.ok is False
    assert len(report2.failures) > 0


@pytest.mark.unit
def test_serialization(test_engine: TravelEngine, mock_clock) -> None:
    test_engine.start()
    mock_clock.advance(60)
    test_engine.sample()

    data = test_engine.to_dict()
    restored_engine = TravelEngine.from_dict(data, now_fn=mock_clock.now)

    assert restored_engine.status == test_engine.status
    assert restored_engine.route_distance_km == pytest.approx(test_engine.route_distance_km)
    assert restored_engine.estimated_duration_s == pytest.approx(test_engine.estimated_duration_s)


@pytest.mark.unit
def test_travel_sample_to_dict(test_engine: TravelEngine) -> None:
    sample = test_engine.start()
    d = sample.to_dict()

    assert "timestamp" in d
    assert "lat" in d
    assert "lon" in d
    assert "speed_kmh" in d
    assert "bearing_deg" in d
    assert "altitude_m" in d
    assert "altitude_source" in d
    assert "progress" in d
    assert "distance_traveled_km" in d
    assert "remaining_distance_km" in d
    assert "elapsed_s" in d
    assert "remaining_s" in d
    assert "status" in d
    assert "eta" in d

    assert d["altitude_source"] == "nominal"
    assert round(d["lat"], 7) == d["lat"]
    assert round(d["lon"], 7) == d["lon"]


def test_ready_route_stays_at_origin_until_start(mock_clock) -> None:
    engine = TravelEngine.build(RouteGeometry.from_points([(35, 51), (35.01, 51)]), now_fn=mock_clock.now)
    mock_clock.advance(30)
    sample = engine.sample()
    assert sample.status == TravelStatus.ROUTE_READY
    assert sample.distance_traveled_km == 0
    assert sample.elapsed_s == 0
    assert sample.speed_kmh == 0
    assert (sample.latitude, sample.longitude) == (35, 51)
    cancelled = engine.cancel()
    assert cancelled.distance_traveled_km == 0


def test_arrival_waits_for_endpoint_and_terminal_sample_stays_fixed(mock_clock) -> None:
    engine = TravelEngine.build(RouteGeometry.from_points([(35, 51), (35.01, 51)]), now_fn=mock_clock.now)
    engine.start()
    mock_clock.advance(engine.solution.time_at_distance(engine.route_distance_km - 0.005))
    approaching = engine.sample()
    assert approaching.status == TravelStatus.MOVING
    assert approaching.speed_kmh > 0
    mock_clock.advance(approaching.remaining_s + 1)
    arrived = engine.sample()
    assert arrived.status == TravelStatus.ARRIVED
    assert (arrived.latitude, arrived.longitude) == (35.01, 51)
    assert arrived.remaining_distance_km == 0
    assert arrived.elapsed_s == arrived.total_duration_s
    mock_clock.advance(60)
    later = engine.sample()
    assert later.distance_traveled_km == arrived.distance_traveled_km
    assert later.elapsed_s == arrived.elapsed_s
    assert later.eta == arrived.eta
