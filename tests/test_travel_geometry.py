import math

import pytest

from app.travel.geometry import (
    GeoPoint,
    PathIndex,
    _validate_lat_lon,
    cross_track_km,
    decode_polyline,
    densify,
    encode_polyline,
    haversine_km,
    initial_bearing,
    intermediate_point,
    path_length_km,
)

# ── Iranian city coordinates ──
TEHRAN = GeoPoint(35.6892, 51.389)
ISFAHAN = GeoPoint(32.6546, 51.6680)
QOM = GeoPoint(34.6416, 50.8746)
MASHHAD = GeoPoint(36.2972, 59.6067)


@pytest.mark.unit
class TestGeoPoint:
    def test_geopoint_namedtuple(self) -> None:
        p = GeoPoint(35.6892, 51.389)
        assert p.lat == 35.6892
        assert p.lon == 51.389


@pytest.mark.unit
class TestHaversineKm:
    def test_tehran_to_isfahan(self) -> None:
        dist = haversine_km(TEHRAN.lat, TEHRAN.lon, ISFAHAN.lat, ISFAHAN.lon)
        assert dist == pytest.approx(338.0, rel=1e-2)

    def test_identical_points(self) -> None:
        assert haversine_km(TEHRAN.lat, TEHRAN.lon, TEHRAN.lat, TEHRAN.lon) == 0.0

    def test_antipodal_points(self) -> None:
        dist = haversine_km(90.0, 0.0, -90.0, 0.0)
        assert dist == pytest.approx(20015.08, rel=1e-2)
        assert not math.isnan(dist)

    def test_short_distance(self) -> None:
        dist = haversine_km(35.6892, 51.389, 35.6900, 51.390)
        assert 0.0 < dist < 1.0


@pytest.mark.unit
class TestInitialBearing:
    def test_due_north(self) -> None:
        assert initial_bearing(0.0, 0.0, 10.0, 0.0) == pytest.approx(0.0, abs=1e-5)

    def test_due_east(self) -> None:
        assert initial_bearing(0.0, 0.0, 0.0, 10.0) == pytest.approx(90.0, abs=1e-5)

    def test_due_south(self) -> None:
        assert initial_bearing(10.0, 0.0, 0.0, 0.0) == pytest.approx(180.0, abs=1e-5)


@pytest.mark.unit
class TestIntermediatePoint:
    def test_fraction_zero_returns_start(self) -> None:
        start = intermediate_point(TEHRAN.lat, TEHRAN.lon, ISFAHAN.lat, ISFAHAN.lon, 0.0)
        assert start.lat == pytest.approx(TEHRAN.lat, abs=1e-5)
        assert start.lon == pytest.approx(TEHRAN.lon, abs=1e-5)

    def test_fraction_one_returns_end(self) -> None:
        end = intermediate_point(TEHRAN.lat, TEHRAN.lon, ISFAHAN.lat, ISFAHAN.lon, 1.0)
        assert end.lat == pytest.approx(ISFAHAN.lat, abs=1e-5)
        assert end.lon == pytest.approx(ISFAHAN.lon, abs=1e-5)

    def test_fraction_half_midpoint(self) -> None:
        mid = intermediate_point(0.0, 0.0, 0.0, 10.0, 0.5)
        assert mid.lat == pytest.approx(0.0, abs=1e-5)
        assert mid.lon == pytest.approx(5.0, abs=1e-5)

    def test_coincident_endpoints(self) -> None:
        res = intermediate_point(TEHRAN.lat, TEHRAN.lon, TEHRAN.lat, TEHRAN.lon, 0.5)
        assert res.lat == TEHRAN.lat
        assert res.lon == TEHRAN.lon

    def test_clamping(self) -> None:
        below = intermediate_point(TEHRAN.lat, TEHRAN.lon, ISFAHAN.lat, ISFAHAN.lon, -0.5)
        above = intermediate_point(TEHRAN.lat, TEHRAN.lon, ISFAHAN.lat, ISFAHAN.lon, 1.5)
        assert below.lat == pytest.approx(TEHRAN.lat, abs=1e-5)
        assert above.lat == pytest.approx(ISFAHAN.lat, abs=1e-5)


@pytest.mark.unit
class TestCrossTrackKm:
    def test_point_on_segment(self) -> None:
        assert cross_track_km(0.0, 5.0, 0.0, 0.0, 0.0, 10.0) == pytest.approx(0.0, abs=1e-5)

    def test_point_perpendicular(self) -> None:
        assert cross_track_km(1.0, 5.0, 0.0, 0.0, 0.0, 10.0) > 0.0

    def test_point_beyond_segment(self) -> None:
        """Clamped to endpoint distance."""
        d = cross_track_km(0.0, 15.0, 0.0, 0.0, 0.0, 10.0)
        assert d == pytest.approx(haversine_km(0.0, 15.0, 0.0, 10.0), rel=1e-2)

    def test_zero_length_segment(self) -> None:
        d = cross_track_km(0.0, 5.0, 0.0, 0.0, 0.0, 0.0)
        assert d == pytest.approx(haversine_km(0.0, 5.0, 0.0, 0.0), rel=1e-2)


@pytest.mark.unit
class TestPolyline:
    def test_round_trip(self) -> None:
        points = [TEHRAN, ISFAHAN]
        encoded = encode_polyline(points)
        decoded = decode_polyline(encoded)
        assert len(decoded) == 2
        for p1, p2 in zip(points, decoded, strict=True):
            assert p1.lat == pytest.approx(p2.lat, abs=1e-5)
            assert p1.lon == pytest.approx(p2.lon, abs=1e-5)

    def test_empty_string(self) -> None:
        assert decode_polyline("") == []

    def test_truncated_input(self) -> None:
        with pytest.raises(ValueError):
            decode_polyline("truncated_")

    def test_known_polyline(self) -> None:
        encoded = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
        decoded = decode_polyline(encoded)
        assert len(decoded) == 3


@pytest.mark.unit
class TestPathLengthKm:
    def test_triangle_inequality(self) -> None:
        path = [TEHRAN, QOM, ISFAHAN]
        total_len = path_length_km(path)
        direct_len = haversine_km(TEHRAN.lat, TEHRAN.lon, ISFAHAN.lat, ISFAHAN.lon)
        assert total_len >= direct_len

    def test_single_point(self) -> None:
        assert path_length_km([TEHRAN]) == 0.0


@pytest.mark.unit
class TestDensify:
    def test_max_step_invalid(self) -> None:
        path = [GeoPoint(0.0, 0.0), GeoPoint(0.0, 10.0)]
        with pytest.raises(ValueError):
            densify(path, max_step_km=0.0)
        with pytest.raises(ValueError):
            densify(path, max_step_km=-1.0)

    def test_short_segments_untouched(self) -> None:
        path = [GeoPoint(35.6892, 51.389), GeoPoint(35.6900, 51.390)]
        dense = densify(path, max_step_km=10.0)
        assert len(dense) == 2

    def test_long_segments_split(self) -> None:
        path = [GeoPoint(0.0, 0.0), GeoPoint(0.0, 10.0)]
        dist = haversine_km(0.0, 0.0, 0.0, 10.0)
        dense = densify(path, max_step_km=dist / 3.0)
        assert len(dense) > 2
        assert dense[0] == path[0]
        assert dense[-1] == path[-1]

    def test_single_point(self) -> None:
        path = [TEHRAN]
        dense = densify(path, max_step_km=1.0)
        assert dense == path
        assert dense is not path


@pytest.mark.unit
class TestPathIndex:
    def test_too_few_points(self) -> None:
        with pytest.raises(ValueError):
            PathIndex([GeoPoint(0.0, 0.0)])

    def test_zero_length(self) -> None:
        with pytest.raises(ValueError):
            PathIndex([GeoPoint(0.0, 0.0), GeoPoint(0.0, 0.0)])

    def test_out_of_range_lat(self) -> None:
        with pytest.raises(ValueError):
            PathIndex([GeoPoint(100.0, 0.0), GeoPoint(0.0, 0.0)])

    def test_position_at_start_and_end(self) -> None:
        pi = PathIndex([GeoPoint(0.0, 0.0), GeoPoint(0.0, 10.0)])
        start = pi.position_at(0)
        assert start.point.lat == pytest.approx(0.0, abs=1e-5)
        assert start.point.lon == pytest.approx(0.0, abs=1e-5)
        end = pi.position_at(pi.total_km)
        assert end.point.lat == pytest.approx(0.0, abs=1e-5)
        assert end.point.lon == pytest.approx(10.0, abs=1e-5)

    def test_position_at_clamping(self) -> None:
        pi = PathIndex([GeoPoint(0.0, 0.0), GeoPoint(0.0, 10.0)])
        neg = pi.position_at(-10.0)
        assert neg.point.lon == pytest.approx(0.0, abs=1e-5)
        over = pi.position_at(pi.total_km + 10.0)
        assert over.point.lon == pytest.approx(10.0, abs=1e-5)

    def test_distance_to_path_km(self) -> None:
        pi = PathIndex([GeoPoint(0.0, 0.0), GeoPoint(0.0, 10.0)])
        assert pi.distance_to_path_km(0.0, 5.0) == pytest.approx(0.0, abs=1e-5)
        assert pi.distance_to_path_km(1.0, 5.0) > 0.0

    def test_binary_search_correctness(self) -> None:
        points = [GeoPoint(0.0, float(i)) for i in range(10)]
        pi = PathIndex(points)
        mid = pi.position_at(pi.total_km / 2.0)
        assert mid.point.lon == pytest.approx(4.5, abs=5e-2)

    def test_properties(self) -> None:
        pi = PathIndex([GeoPoint(0.0, 0.0), GeoPoint(0.0, 10.0)])
        assert pi.total_km > 0
        assert len(pi.cumulative_km) == 2
        assert len(pi.points) == 2


@pytest.mark.unit
class TestValidateLatLon:
    def test_lat_out_of_range(self) -> None:
        with pytest.raises(ValueError):
            _validate_lat_lon(91.0, 0.0)
        with pytest.raises(ValueError):
            _validate_lat_lon(-91.0, 0.0)

    def test_lon_out_of_range(self) -> None:
        with pytest.raises(ValueError):
            _validate_lat_lon(0.0, 181.0)
        with pytest.raises(ValueError):
            _validate_lat_lon(0.0, -181.0)

    def test_boundary_values_ok(self) -> None:
        _validate_lat_lon(90.0, 180.0)
        _validate_lat_lon(-90.0, -180.0)
