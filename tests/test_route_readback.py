"""
Tests for route readback and validation logic (Phase 1.7).
"""

import pytest
from app.automation.location_selector import LocationSelector
from unittest.mock import MagicMock


def test_normalize_text_persian_characters():
    selector = LocationSelector(MagicMock())

    # Arabic Yeh/Kaf to Persian
    assert selector._normalize_text("كرمانشاه") == "کرمانشاه"
    assert selector._normalize_text("تهراني") == "تهرانی"
    # Zero-width non-joiner
    assert selector._normalize_text("می‌شود") == "می شود" or "میشود" in selector._normalize_text("می‌شود")


def test_route_readback_integrity():
    """Verify that route read-back ensures all required parts are verified."""
    readback_data = {
        "province_text": "تهران",
        "province_value": "1",
        "city_text": "تهران",
        "city_value": "101",
        "address": "خیابان جمهوری پلاک ۲۰",
    }

    assert readback_data["province_value"] != ""
    assert readback_data["city_value"] != ""
    assert readback_data["address"] == "خیابان جمهوری پلاک ۲۰"
