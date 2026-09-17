import pytest

from app.travel.speed import (
    MAX_SUPPORTED_KMH,
    MIN_MOVING_KMH,
    SpeedProfile,
    SpeedRule,
)


@pytest.mark.unit
class TestSpeedRule:
    def test_valid_construction(self) -> None:
        rule = SpeedRule(start_km=10.0, end_km=20.0, target_kmh=80.0)
        assert rule.start_km == 10.0
        assert rule.end_km == 20.0
        assert rule.target_kmh == 80.0

    def test_start_km_negative(self) -> None:
        with pytest.raises(ValueError):
            SpeedRule(start_km=-5.0, end_km=10.0, target_kmh=80.0)

    def test_end_km_less_than_start_km(self) -> None:
        with pytest.raises(ValueError):
            SpeedRule(start_km=10.0, end_km=10.0, target_kmh=80.0)
        with pytest.raises(ValueError):
            SpeedRule(start_km=15.0, end_km=10.0, target_kmh=80.0)

    def test_target_kmh_too_low(self) -> None:
        with pytest.raises(ValueError):
            SpeedRule(start_km=0.0, end_km=10.0, target_kmh=MIN_MOVING_KMH - 0.1)

    def test_target_kmh_too_high(self) -> None:
        with pytest.raises(ValueError):
            SpeedRule(start_km=0.0, end_km=10.0, target_kmh=MAX_SUPPORTED_KMH + 0.1)

    def test_to_dict(self) -> None:
        rule = SpeedRule(start_km=10.0, end_km=20.0, target_kmh=80.0)
        d = rule.to_dict()
        assert d == {"start_km": 10.0, "end_km": 20.0, "target_kmh": 80.0}


@pytest.mark.unit
class TestSpeedProfile:
    def test_valid_construction(self) -> None:
        rules = [SpeedRule(start_km=0.0, end_km=100.0, target_kmh=90.0)]
        profile = SpeedProfile(rules=rules)
        assert profile.rules == rules

    def test_validate_empty_rules(self) -> None:
        with pytest.raises(ValueError):
            SpeedProfile(rules=[])

    def test_validate_accel_invalid(self) -> None:
        rules = [SpeedRule(start_km=0.0, end_km=100.0, target_kmh=90.0)]
        with pytest.raises(ValueError):
            SpeedProfile(rules=rules, accel_mps2=0.0)
        with pytest.raises(ValueError):
            SpeedProfile(rules=rules, accel_mps2=5.1)

    def test_validate_decel_invalid(self) -> None:
        rules = [SpeedRule(start_km=0.0, end_km=100.0, target_kmh=90.0)]
        with pytest.raises(ValueError):
            SpeedProfile(rules=rules, decel_mps2=0.0)
        with pytest.raises(ValueError):
            SpeedProfile(rules=rules, decel_mps2=8.1)

    def test_validate_min_max_invalid(self) -> None:
        rules = [SpeedRule(start_km=0.0, end_km=100.0, target_kmh=90.0)]
        with pytest.raises(ValueError):
            SpeedProfile(rules=rules, min_kmh=100.0, max_kmh=90.0)

    def test_validate_overlapping_rules(self) -> None:
        rules = [
            SpeedRule(start_km=0.0, end_km=50.0, target_kmh=90.0),
            SpeedRule(start_km=40.0, end_km=100.0, target_kmh=80.0),
        ]
        with pytest.raises(ValueError):
            SpeedProfile(rules=rules)

    def test_target_kmh_at(self) -> None:
        rules = [
            SpeedRule(start_km=0.0, end_km=50.0, target_kmh=90.0),
            SpeedRule(start_km=60.0, end_km=100.0, target_kmh=100.0),
        ]
        profile = SpeedProfile(rules=rules, min_kmh=10.0, max_kmh=120.0)
        assert profile.target_kmh_at(25.0) == 90.0
        assert profile.target_kmh_at(80.0) == 100.0
        # In the gap (55.0), the nearest band past start is the tail rule
        assert profile.target_kmh_at(55.0) == 100.0

    def test_serialization(self) -> None:
        rules = [SpeedRule(start_km=0.0, end_km=50.0, target_kmh=90.0)]
        profile = SpeedProfile(
            rules=rules,
            accel_mps2=1.0,
            decel_mps2=1.5,
            min_kmh=20.0,
            max_kmh=100.0,
        )
        d = profile.to_dict()
        restored = SpeedProfile.from_dict(d)
        assert restored.accel_mps2 == 1.0
        assert restored.decel_mps2 == 1.5
        assert restored.min_kmh == 20.0
        assert restored.max_kmh == 100.0
        assert len(restored.rules) == 1
        assert restored.rules[0].start_km == 0.0


@pytest.mark.unit
class TestSpeedProfileFromSegments:
    def test_valid_segments(self) -> None:
        segments = [
            (0.0, 10.0, 60.0),
            (10.0, 30.0, 120.0),
        ]
        profile = SpeedProfile.from_segments(segments, min_kmh=30.0, max_kmh=100.0)
        assert len(profile.rules) == 2
        assert profile.rules[0].start_km == 0.0
        assert profile.rules[0].end_km == 10.0
        assert profile.rules[0].target_kmh == 60.0
        assert profile.rules[1].start_km == 10.0
        assert profile.rules[1].end_km == 30.0
        # Clamped to max_kmh
        assert profile.rules[1].target_kmh == 100.0

    def test_empty_segments(self) -> None:
        with pytest.raises(ValueError):
            SpeedProfile.from_segments([])


@pytest.mark.unit
class TestSpeedProfilePreset:
    def test_truck_intercity(self) -> None:
        profile = SpeedProfile.preset("truck_intercity", total_km=100.0)
        assert len(profile.rules) > 0

    def test_truck_mountain(self) -> None:
        profile = SpeedProfile.preset("truck_mountain", total_km=100.0)
        assert len(profile.rules) > 0

    def test_urban(self) -> None:
        profile = SpeedProfile.preset("urban", total_km=10.0)
        assert len(profile.rules) > 0

    def test_unknown_preset(self) -> None:
        with pytest.raises(ValueError):
            SpeedProfile.preset("unknown_preset", total_km=100.0)

    def test_invalid_total_km(self) -> None:
        with pytest.raises(ValueError):
            SpeedProfile.preset("truck_intercity", total_km=0.0)

    def test_short_route(self) -> None:
        profile = SpeedProfile.preset("truck_intercity", total_km=3.0)
        assert len(profile.rules) == 1
        assert profile.rules[0].target_kmh == 45.0


@pytest.mark.unit
class TestSpeedSolution:
    @staticmethod
    def _make_nodes(total_km: float, step_km: float = 0.5) -> list[float]:
        count = int(total_km / step_km) + 1
        nodes = [i * step_km for i in range(count)]
        if nodes[-1] < total_km:
            nodes.append(total_km)
        return nodes

    def test_rest_to_rest(self) -> None:
        profile = SpeedProfile.preset("truck_intercity", total_km=10.0)
        nodes = self._make_nodes(10.0)
        solution = profile.solve(nodes)
        assert solution.speed_kmh_at_time(0.0) == pytest.approx(0.0, abs=1e-3)
        assert solution.speed_kmh_at_time(solution.total_seconds) == pytest.approx(0.0, abs=1e-3)
        assert solution.distance_at_time(0.0) == pytest.approx(0.0, abs=1e-3)
        assert solution.distance_at_time(solution.total_seconds) == pytest.approx(10.0, abs=1e-3)

    def test_time_at_distance(self) -> None:
        profile = SpeedProfile.preset("truck_intercity", total_km=20.0)
        nodes = self._make_nodes(20.0)
        solution = profile.solve(nodes)
        mid_time = solution.total_seconds / 2.0
        d = solution.distance_at_time(mid_time)
        t = solution.time_at_distance(d)
        assert t == pytest.approx(mid_time, abs=1.0)

    def test_sample_table_invalid_step(self) -> None:
        profile = SpeedProfile.preset("truck_intercity", total_km=10.0)
        nodes = self._make_nodes(10.0)
        solution = profile.solve(nodes)
        with pytest.raises(ValueError):
            solution.sample_table(step_km=0.0)

    def test_monotonicity(self) -> None:
        profile = SpeedProfile.preset("urban", total_km=5.0)
        nodes = self._make_nodes(5.0)
        solution = profile.solve(nodes)
        prev_d = -1.0
        for t in range(0, int(solution.total_seconds) + 1, 10):
            d = solution.distance_at_time(float(t))
            assert d >= prev_d
            prev_d = d


@pytest.mark.unit
class TestKinematicConsistency:
    def test_two_node_short_route_accelerates_and_brakes(self) -> None:
        profile = SpeedProfile(rules=[SpeedRule(0, 0.1, 120)], min_kmh=1, max_kmh=120, accel_mps2=0.5, decel_mps2=0.5)
        solution = profile.solve([0, 0.1])
        # A symmetric rest-to-rest 100 m trip at 0.5 m/s² takes sqrt(800) s.
        assert solution.total_seconds == pytest.approx(28.2842712475)
        assert solution.distance_at_time(14.1421356237) == pytest.approx(0.05)
        assert solution.speed_kmh_at_time(14.1421356237) == pytest.approx(25.4558441227)
        assert solution.time_at_distance(0.05) == pytest.approx(14.1421356237)

    def test_two_node_route_cruises_between_acceleration_and_braking(self) -> None:
        profile = SpeedProfile(rules=[SpeedRule(0, 1, 36)], min_kmh=1, max_kmh=36, accel_mps2=0.5, decel_mps2=0.5)
        solution = profile.solve([0, 1])
        # 20 s/100 m accelerating, 80 s/800 m cruising, 20 s/100 m braking.
        assert solution.total_seconds == pytest.approx(120)
        assert solution.distance_at_time(60) == pytest.approx(0.5)
        assert solution.speed_kmh_at_time(60) == pytest.approx(36)

    def test_very_short_route(self) -> None:
        profile = SpeedProfile(
            rules=[SpeedRule(start_km=0.0, end_km=2.0, target_kmh=120.0)],
            accel_mps2=0.5,
            decel_mps2=0.5,
            min_kmh=10.0,
            max_kmh=120.0,
        )
        nodes = [i * 0.1 for i in range(21)]
        solution = profile.solve(nodes)
        max_speed = max(solution.speed_kmh_at_time(float(t)) for t in range(int(solution.total_seconds)))
        assert max_speed > 10.0

    def test_normal_route(self) -> None:
        profile = SpeedProfile(
            rules=[SpeedRule(start_km=0.0, end_km=200.0, target_kmh=90.0)],
            accel_mps2=0.5,
            decel_mps2=0.5,
            min_kmh=10.0,
            max_kmh=120.0,
        )
        nodes = [i * 0.5 for i in range(401)]
        solution = profile.solve(nodes)
        mid_speed = solution.speed_kmh_at_time(solution.total_seconds / 2.0)
        assert mid_speed == pytest.approx(90.0, abs=5.0)
