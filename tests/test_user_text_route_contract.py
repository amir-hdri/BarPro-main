"""
Tests for user_text route contract (Phase 1.6).
"""

from app.automation.multitenant_payload_adapter import (
    build_enhanced_waybill_payload,
    compute_canonical_route_key,
    validate_enhanced_waybill_payload,
)


def test_payload_without_coordinates():
    raw_payload = {
        "sender": {"name": "علی رضایی", "type": "individual"},
        "receiver": {"name": "حسن محمدی", "type": "individual"},
        "origin": {
            "province": "تهران",
            "city": "تهران",
            "address": "خیابان کارگر شمالی پلاک ۱",
            "coordinates": None,
        },
        "destination": {
            "province": "البرز",
            "city": "کرج",
            "address": "میدان شهدا پلاک ۱۰",
            "coordinates": None,
        },
        "cargo": {
            "type": "آهن آلات",
            "packaging": "شاخه",
            "weight": 5.0,
            "value": "50000000",
        },
        "vehicle": {
            "driver_national_code": "0084575948",
            "plate": "12ب345ایران11",
        },
        "financial": {},
    }

    errors = validate_enhanced_waybill_payload(raw_payload)
    assert not errors

    enhanced = build_enhanced_waybill_payload(raw_payload)
    assert enhanced["route_source"] == "user_text"
    assert enhanced["location_mode"] == "user_text"
    assert enhanced["origin"]["coordinates"] is None
    assert enhanced["destination"]["coordinates"] is None
    assert enhanced["origin"]["province"] == "تهران"
    assert enhanced["origin"]["city"] == "تهران"
    assert enhanced["origin"]["address"] == "خیابان کارگر شمالی پلاک ۱"


def test_payload_with_wrong_coordinates_ignores_them():
    """Even if invalid/wrong coordinates are provided, user_text mode nullifies them and uses text only."""
    raw_payload = {
        "sender": {"name": "رضا احمدی", "type": "individual"},
        "receiver": {"name": "مجید صالحی", "type": "individual"},
        "origin": {
            "province": "اصفهان",
            "city": "اصفهان",
            "address": "خیابان چهارباغ پلاک ۱۲",
            "coordinates": {"lat": 99.9999, "lng": -199.9999},  # Invalid coordinates
        },
        "destination": {
            "province": "فارس",
            "city": "شیراز",
            "address": "بلوار زند پلاک ۲۰",
            "coordinates": {"lat": 0.0, "lng": 0.0},
        },
        "cargo": {
            "type": "کاشی",
            "packaging": "کارتن",
            "weight": 2.5,
            "value": "20000000",
        },
        "vehicle": {
            "driver_national_code": "0084575948",
            "plate": "12ب345ایران11",
        },
        "financial": {},
    }

    enhanced = build_enhanced_waybill_payload(raw_payload)
    assert enhanced["origin"]["coordinates"] is None
    assert enhanced["destination"]["coordinates"] is None
    assert enhanced["origin"]["province"] == "اصفهان"
    assert enhanced["origin"]["city"] == "اصفهان"
    assert enhanced["origin"]["address"] == "خیابان چهارباغ پلاک ۱۲"
    assert enhanced["destination"]["province"] == "فارس"
    assert enhanced["destination"]["city"] == "شیراز"
    assert enhanced["destination"]["address"] == "بلوار زند پلاک ۲۰"


def test_route_key_generation_and_distinct_addresses():
    origin_a = {"province": "تهران", "city": "تهران", "district": "منطقه ۱", "address": "خیابان ولیعصر پلاک ۱۰۰"}
    origin_b = {"province": "تهران", "city": "تهران", "district": "منطقه ۱", "address": "خیابان ولیعصر پلاک ۲۰۰"}
    dest = {"province": "البرز", "city": "کرج", "district": "", "address": "میدان مادر"}

    key_a = compute_canonical_route_key(origin_a, dest)
    key_b = compute_canonical_route_key(origin_b, dest)

    assert key_a.startswith("route-")
    assert key_b.startswith("route-")
    # Different addresses in same city must have distinct route keys
    assert key_a != key_b

    # Exact same canonical inputs must produce identical route key
    origin_a_duplicate = {"province": " تهران ", "city": "تهران", "district": "منطقه ۱", "address": "خیابان ولیعصر  پلاک ۱۰۰"}
    assert compute_canonical_route_key(origin_a_duplicate, dest) == key_a


def test_incomplete_location_fails_validation():
    incomplete_origin = {
        "sender": {"name": "علی رضایی", "type": "individual"},
        "receiver": {"name": "حسن محمدی", "type": "individual"},
        "origin": {
            "province": "",  # Missing province
            "city": "تهران",
            "address": "خیابان آزادی",
        },
        "destination": {
            "province": "البرز",
            "city": "کرج",
            "address": "بلوار چمران",
        },
        "cargo": {"type": "سنگ", "packaging": "فله", "weight": 10.0, "value": "1000000"},
        "vehicle": {"driver_national_code": "0084575948", "plate": "12ب345ایران11"},

    }

    errors = validate_enhanced_waybill_payload(incomplete_origin)
    assert any("استان مبدا" in err for err in errors)
