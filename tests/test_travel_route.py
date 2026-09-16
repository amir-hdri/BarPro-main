import pytest

from app.travel.geometry import GeoPoint, encode_polyline
from app.travel.route import FALLBACK_SOURCE, RouteGeometry, RouteSegment

TEHRAN = GeoPoint(35.6892, 51.389)
QOM = GeoPoint(34.6416, 50.8746)
ISFAHAN = GeoPoint(32.6546, 51.668)
MASHHAD = GeoPoint(36.2972, 59.6067)


@pytest.mark.unit
class TestRouteSegment:
    def test_average_kmh_positive_duration(self) -> None:
        segment = RouteSegment(index=0, start_km=0.0, end_km=100.0, distance_km=100.0, duration_s=3600.0)
        assert segment.average_kmh == pytest.approx(100.0)

    def test_average_kmh_zero_duration(self) -> None:
        segment = RouteSegment(index=0, start_km=0.0, end_km=100.0, distance_km=100.0, duration_s=0.0)
        assert segment.average_kmh == 0.0

    def test_to_from_dict(self) -> None:
        segment = RouteSegment(index=1, start_km=10.0, end_km=20.0, distance_km=10.0, duration_s=600.0)
        data = segment.to_dict()
        assert data["index"] == 1
        assert data["start_km"] == 10.0
        assert data["end_km"] == 20.0
        assert data["distance_km"] == 10.0
        assert data["duration_s"] == 600.0
        new_segment = RouteSegment.from_dict(data)
        assert new_segment == segment


@pytest.mark.unit
class TestRouteGeometryFromPoints:
    def test_valid_3_point_route(self) -> None:
        route = RouteGeometry.from_points([TEHRAN, QOM, ISFAHAN])
        assert len(route.points) == 3
        assert route.start == TEHRAN
        assert route.end == ISFAHAN

    def test_less_than_2_distinct_points(self) -> None:
        with pytest.raises(ValueError):
            RouteGeometry.from_points([TEHRAN])

    def test_zero_length(self) -> None:
        with pytest.raises(ValueError):
            RouteGeometry.from_points([TEHRAN, TEHRAN])

    def test_exceeds_max_route_km(self) -> None:
        p1 = GeoPoint(0.0, 0.0)
        p2 = GeoPoint(0.0, 180.0)
        with pytest.raises(ValueError):
            RouteGeometry.from_points([p1, p2])

    def test_consecutive_duplicate_nodes_deduplicated(self) -> None:
        route = RouteGeometry.from_points([TEHRAN, TEHRAN, QOM, ISFAHAN, ISFAHAN])
        assert len(route.points) == 3
        assert route.start == TEHRAN
        assert route.end == ISFAHAN


@pytest.mark.unit
class TestRouteGeometryFromEncoded:
    def test_from_encoded(self) -> None:
        points = [TEHRAN, QOM, ISFAHAN]
        encoded = encode_polyline(points)
        route = RouteGeometry.from_encoded(encoded)
        assert len(route.points) == 3
        assert route.start.lat == pytest.approx(TEHRAN.lat, abs=1e-5)
        assert route.end.lat == pytest.approx(ISFAHAN.lat, abs=1e-5)

    def test_less_than_2_points_decoded(self) -> None:
        encoded = encode_polyline([TEHRAN])
        with pytest.raises(ValueError):
            RouteGeometry.from_encoded(encoded)


@pytest.mark.unit
class TestRouteGeometryStraightLineFallback:
    def test_fallback(self) -> None:
        route = RouteGeometry.straight_line_fallback(TEHRAN, ISFAHAN, road_factor=1.2)
        assert route.source == FALLBACK_SOURCE
        assert not route.is_real_route
        assert len(route.segments) == 1
        assert route.segments[0].start_km == 0.0
        assert route.segments[0].end_km == pytest.approx(route.total_distance_km)

    def test_road_factor_invalid(self) -> None:
        with pytest.raises(ValueError):
            RouteGeometry.straight_line_fallback(TEHRAN, ISFAHAN, road_factor=0.9)


@pytest.mark.unit
class TestRouteGeometryProperties:
    def test_properties(self) -> None:
        route = RouteGeometry.from_points([TEHRAN, QOM, ISFAHAN])
        assert route.start == TEHRAN
        assert route.end == ISFAHAN
        assert route.total_distance_km > 0
        assert route.raw_length_km == pytest.approx(route.total_distance_km, rel=1e-2)


@pytest.mark.unit
class TestRouteGeometrySpeedSegments:
    def test_no_timing(self) -> None:
        route = RouteGeometry.from_points([TEHRAN, QOM, ISFAHAN])
        assert len(route.speed_segments()) == 0

    def test_with_timing(self) -> None:
        route = RouteGeometry.from_points([TEHRAN, QOM, ISFAHAN])
        tot = route.total_distance_km
        half = tot / 2
        route.segments = [
            RouteSegment(index=0, start_km=0.0, end_km=half, distance_km=half, duration_s=3600.0),
            RouteSegment(index=1, start_km=half, end_km=tot, distance_km=half, duration_s=3600.0),
        ]
        speeds = route.speed_segments()
        assert len(speeds) == 2
        assert speeds[0][0] == pytest.approx(0.0)
        assert speeds[1][1] == pytest.approx(tot)

    def test_zero_duration_skipped(self) -> None:
        route = RouteGeometry.from_points([TEHRAN, QOM, ISFAHAN])
        tot = route.total_distance_km
        half = tot / 2
        route.segments = [
            RouteSegment(index=0, start_km=0.0, end_km=half, distance_km=half, duration_s=0.0),
            RouteSegment(index=1, start_km=half, end_km=tot, distance_km=half, duration_s=3600.0),
        ]
        speeds = route.speed_segments()
        assert len(speeds) == 1

    def test_tail_gap_closure(self) -> None:
        route = RouteGeometry.from_points([TEHRAN, QOM, ISFAHAN])
        tot = route.total_distance_km
        route.segments = [
            RouteSegment(index=0, start_km=0.0, end_km=tot - 10.0, distance_km=tot - 10.0, duration_s=3600.0),
        ]
        speeds = route.speed_segments()
        assert speeds[-1][1] == pytest.approx(tot)


@pytest.mark.unit
class TestRouteGeometryValidate:
    def test_valid_route(self) -> None:
        route = RouteGeometry.from_points([TEHRAN, QOM, ISFAHAN])
        route.validate()

    def test_negative_segment_distance(self) -> None:
        route = RouteGeometry.from_points([TEHRAN, QOM, ISFAHAN])
        route.segments = [RouteSegment(index=0, start_km=-10.0, end_km=10.0, distance_km=-20.0, duration_s=3600.0)]
        with pytest.raises(ValueError):
            route.validate()

    def test_negative_segment_duration(self) -> None:
        route = RouteGeometry.from_points([TEHRAN, QOM, ISFAHAN])
        route.segments = [RouteSegment(index=0, start_km=0.0, end_km=10.0, distance_km=10.0, duration_s=-3600.0)]
        with pytest.raises(ValueError):
            route.validate()

    def test_end_before_start(self) -> None:
        route = RouteGeometry.from_points([TEHRAN, QOM, ISFAHAN])
        route.segments = [RouteSegment(index=0, start_km=10.0, end_km=5.0, distance_km=5.0, duration_s=3600.0)]
        with pytest.raises(ValueError):
            route.validate()


@pytest.mark.unit
class TestRouteGeometryToFromDict:
    def test_round_trip(self) -> None:
        route = RouteGeometry.from_points([TEHRAN, QOM, ISFAHAN])
        route.segments = [
            RouteSegment(
                index=0,
                start_km=0.0,
                end_km=route.total_distance_km,
                distance_km=route.total_distance_km,
                duration_s=7200.0,
            )
        ]
        route.source = "test_source"

        data = route.to_dict()
        new_route = RouteGeometry.from_dict(data)

        assert new_route.source == "test_source"
        assert new_route.is_real_route
        assert len(new_route.points) == 3
        assert len(new_route.segments) == 1
        assert new_route.segments[0].duration_s == 7200.0
