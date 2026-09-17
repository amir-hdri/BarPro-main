"""Shared browser/backend examples prevent conflicting route anchors."""

import json
from pathlib import Path

import pytest

from app.automation.gps_shipping_manager import extract_coordinates_from_payload

CASES = json.loads((Path(__file__).parent / "fixtures/gps_anchor_cases.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_backend_anchor_contract(case):
    result = extract_coordinates_from_payload(case["payload"])
    for label, prefix in (("origin", "origin"), ("destination", "dest")):
        expected = case[label]
        assert (result[f"{prefix}_lat"], result[f"{prefix}_lng"]) == (
            (expected["lat"], expected["lng"]) if expected else (None, None)
        )
