"""Regression tests for the canonical submission-identity extractor.

Covers the reconciliation fixes: flat + nested payload layouts, driver
national-code fallback, and string-encoded payloads.
"""

import json

from app.core.submission_identity import (
    extract_reconciliation_identity,
    identity_fields_for_fingerprint,
)


class _FakeDriver:
    driver_national_code = "0012345678"


NESTED_PAYLOAD = {
    "driver_national_code": "0012345678",
    "vehicle": {"plate_number": "12A345-19", "driver_plate": "12A345-19"},
    "origin": {"city": "تهران", "address": "خیابان آزادی"},
    "destination": {"city": "کرج", "address": "خیابان اصلی"},
    "cargo": {"weight": "2500", "cargo_weight": "2500"},
    "business_date": "1404-05-01",
}

FLAT_PAYLOAD = {
    "plate_number": "12B678-11",
    "origin_city": "شیراز",
    "destination_city": "اصفهان",
    "cargo_weight": "3000",
    "business_date": "1404-05-01",
}


def test_nested_payload_extraction():
    identity = extract_reconciliation_identity(NESTED_PAYLOAD)
    assert identity.plate_number == "12A345-19"
    assert identity.origin_city == "تهران"
    assert identity.origin_address == "خیابان آزادی"
    assert identity.dest_city == "کرج"
    assert identity.cargo_weight == "2500"
    assert identity.business_date == "1404-05-01"
    assert identity.national_code == "0012345678"


def test_flat_payload_extraction():
    identity = extract_reconciliation_identity(FLAT_PAYLOAD)
    assert identity.plate_number == "12B678-11"
    assert identity.origin_city == "شیراز"
    assert identity.dest_city == "اصفهان"
    assert identity.cargo_weight == "3000"


def test_national_code_fallback_from_driver():
    identity = extract_reconciliation_identity(FLAT_PAYLOAD, driver=_FakeDriver())
    assert identity.national_code == "0012345678"


def test_string_encoded_payload():
    identity = extract_reconciliation_identity(json.dumps(NESTED_PAYLOAD))
    assert identity.plate_number == "12A345-19"
    assert identity.dest_city == "کرج"


def test_garbage_payload_does_not_raise():
    for bad in (None, 42, "not json {{{"):
        identity = extract_reconciliation_identity(bad)
        assert identity.plate_number is None
        assert identity.national_code is None


def test_fingerprint_field_order_is_stable():
    identity = extract_reconciliation_identity(NESTED_PAYLOAD)
    parts = identity_fields_for_fingerprint(identity)
    assert parts[0] == "0012345678"
    assert parts[1] == "12A345-19"
    assert parts[2] == "تهران"
    assert parts[6] == "2500"
    assert parts[7] == "1404-05-01"
