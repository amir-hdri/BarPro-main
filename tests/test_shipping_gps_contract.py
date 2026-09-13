"""Regression tests for server-managed shipping GPS semantics."""

import pytest
from fastapi import HTTPException

from app.api.routes.shipping_gps import _assert_route_anchor
from app.automation.gps_shipping_manager import init_shipping


def test_route_anchor_accepts_only_decimal_rounding() -> None:
    _assert_route_anchor(
        latitude=35.6892001,
        longitude=51.3890001,
        expected_lat=35.6892,
        expected_lng=51.389,
        label="مبدأ",
    )

    with pytest.raises(HTTPException) as exc_info:
        _assert_route_anchor(
            latitude=35.70,
            longitude=51.40,
            expected_lat=35.6892,
            expected_lng=51.389,
            label="مبدأ",
        )
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_planned_waypoints_are_not_gps_evidence() -> None:
    state = await init_shipping(
        "job-1",
        "doc-1",
        {
            "originLat": 35.6892,
            "originLng": 51.389,
            "destLat": 32.6546,
            "destLng": 51.668,
            "originAddress": "مبدأ آزمون",
            "destAddress": "مقصد آزمون",
        },
        num_steps=3,
        persist=False,
    )
    assert len(state.waypoints) == 5
    assert state.gps_list == []
    assert all(point["type"] in {1, 2, 3} for point in state.waypoints)
