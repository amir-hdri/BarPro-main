"""Unit tests for pure distance/time helpers (no Postgres/Redis/Neshan needed)."""

import math

import pytest

from app.core.distance import estimate_time, haversine, road_estimate


def test_haversine_isfahan_kashan():
    # Isfahan (32.65, 51.66) → Kashan (33.98, 51.47) ≈ 148.9 km great-circle.
    # (The roadmap's original assertion of 80–90 km was numerically wrong.)
    distance = haversine(32.65, 51.66, 33.98, 51.47)
    assert 145 < distance < 155


def test_haversine_is_symmetric():
    assert haversine(35.0, 51.0, 36.0, 52.0) == pytest.approx(
        haversine(36.0, 52.0, 35.0, 51.0)
    )


def test_haversine_zero_distance():
    assert haversine(35.0, 51.0, 35.0, 51.0) == pytest.approx(0.0)


def test_road_estimate_is_longer_than_airline():
    air = haversine(32.65, 51.66, 33.98, 51.47)
    road = road_estimate(32.65, 51.66, 33.98, 51.47)
    assert road > air
    assert road == pytest.approx(air * 1.35)


def test_estimate_time_intercity():
    # 55 km/h: 36.6 km → ~39.9 min + 10 min buffer ≈ 50 min.
    minutes = estimate_time(36.6, is_urban=False)
    assert 45 <= minutes <= 55


def test_estimate_time_urban_is_slower():
    road = estimate_time(36.6, is_urban=True)
    intercity = estimate_time(36.6, is_urban=False)
    assert road > intercity


def test_estimate_time_non_positive_returns_zero():
    assert estimate_time(0.0) == 0.0
    assert estimate_time(-5.0) == 0.0
