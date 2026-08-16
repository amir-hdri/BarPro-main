"""
Tests for Phase 1.8 Payload Validation.
"""

import pytest
from app.automation.multitenant_payload_adapter import (
    _validate_iranian_national_code,
    validate_enhanced_waybill_payload,
)


def valid_payload_sample():
    return {
        "sender": {"name": "حمید رضایی", "type": "individual"},
        "receiver": {"name": "محسن کاظمی", "type": "individual"},
        "origin": {"province": "تهران", "city": "تهران", "address": "خیابان آزادی پلاک ۱"},
        "destination": {"province": "البرز", "city": "کرج", "address": "بلوار جمهوری پلاک ۵"},
        "cargo": {"type": "آهن", "packaging": "شاخه", "weight": 2.5, "value": "1000000"},
        "vehicle": {"driver_national_code": "0084575948", "plate": "12ب345ایران11"},
    }


def test_national_code_checksum_validation():
    # Valid checksums
    assert _validate_iranian_national_code("0084575948") is True
    assert _validate_iranian_national_code("0012345679") is True


    # Invalid checksums
    assert _validate_iranian_national_code("1111111111") is False
    assert _validate_iranian_national_code("1234567890") is False
    assert _validate_iranian_national_code("0012345678") is False
    assert _validate_iranian_national_code("123") is False



def test_valid_payload_passes():
    payload = valid_payload_sample()
    errors = validate_enhanced_waybill_payload(payload)
    assert errors == []


def test_duplicate_single_word_name_fails():
    payload = valid_payload_sample()
    payload["sender"]["name"] = "علی علی"
    errors = validate_enhanced_waybill_payload(payload)
    assert any("تکراری" in err for err in errors)


def test_legal_entity_missing_office_name_fails():
    payload = valid_payload_sample()
    payload["sender"] = {"type": "company", "name": "", "office_name": ""}
    errors = validate_enhanced_waybill_payload(payload)
    assert any("نام حقوقی" in err for err in errors)


def test_driver_invalid_national_code_fails():
    payload = valid_payload_sample()
    payload["vehicle"]["driver_national_code"] = "1111111111"
    errors = validate_enhanced_waybill_payload(payload)
    assert any("کد ملی راننده" in err for err in errors)


def test_cargo_negative_weight_fails():
    payload = valid_payload_sample()
    payload["cargo"]["weight"] = -5
    errors = validate_enhanced_waybill_payload(payload)
    assert any("وزن کالا" in err for err in errors)


def test_cargo_missing_packaging_fails():
    payload = valid_payload_sample()
    payload["cargo"]["packaging"] = None
    errors = validate_enhanced_waybill_payload(payload)
    assert any("نوع بسته‌بندی" in err for err in errors)


def test_location_missing_fields_fails():
    payload = valid_payload_sample()
    payload["origin"]["city"] = ""
    payload["destination"]["address"] = ""
    errors = validate_enhanced_waybill_payload(payload)
    assert any("شهر مبدا" in err for err in errors)
    assert any("آدرس مقصد" in err for err in errors)
