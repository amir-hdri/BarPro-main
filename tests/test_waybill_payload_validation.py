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


def test_live_preflight_requires_real_party_mobiles():
    payload = valid_payload_sample()
    errors = validate_enhanced_waybill_payload(payload, enforce_live_party_phones=True)
    assert "موبایل فرستنده" in errors
    assert "موبایل گیرنده" in errors

    payload["sender"]["phone"] = "۰۹۱۲۳۴۵۶۷۸۹"
    payload["receiver"]["phone"] = "09129876543"
    assert validate_enhanced_waybill_payload(payload, enforce_live_party_phones=True) == []


def test_live_preflight_rejects_invalid_party_mobile():
    payload = valid_payload_sample()
    payload["sender"]["phone"] = "0912"
    payload["receiver"]["phone"] = "12345678901"
    errors = validate_enhanced_waybill_payload(payload, enforce_live_party_phones=True)
    assert any("موبایل فرستنده" in err for err in errors)
    assert any("موبایل گیرنده" in err for err in errors)


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


def test_waybill_job_create_request_strict_union_rejection():
    """Verify A1: raw/invalid dicts cannot bypass validation."""
    from pydantic import ValidationError

    from app.schemas.multitenant import WaybillJobCreateRequest

    # 1. Invalid flat payload with bad plate must be rejected
    with pytest.raises(ValidationError):
        WaybillJobCreateRequest(
            driver_national_code="0084575948",
            payload={
                "driver_national_code": "0084575948",
                "origin": "تهران",
                "destination": "اصفهان",
                "cargo_type": "سیمان",
                "cargo_weight": 10,
                "plate_number": "BAD_PLATE_FORMAT",
            },
        )

    # 2. Invalid flat payload with negative weight must be rejected
    with pytest.raises(ValidationError):
        WaybillJobCreateRequest(
            driver_national_code="0084575948",
            payload={
                "driver_national_code": "0084575948",
                "origin": "تهران",
                "destination": "اصفهان",
                "cargo_type": "سیمان",
                "cargo_weight": -5,
                "plate_number": "12ب345ایران67",
            },
        )

    # 3. Empty dictionary payload must be rejected
    with pytest.raises(ValidationError):
        WaybillJobCreateRequest(
            driver_national_code="0084575948",
            payload={},
        )

    # 4. Valid flat payload must succeed
    req_flat = WaybillJobCreateRequest(
        driver_national_code="0084575948",
        payload={
            "driver_national_code": "0084575948",
            "origin": "تهران",
            "destination": "اصفهان",
            "cargo_type": "سیمان",
            "cargo_packaging": "کیسه",
            "cargo_weight": 12.5,
            "cargo_value": "1000000",
            "plate_number": "12ب345ایران67",
        },
    )
    assert req_flat.payload.cargo_weight == 12.5

    # 5. Valid nested payload must succeed
    req_nested = WaybillJobCreateRequest(
        driver_national_code="0084575948",
        payload={
            "sender": {"name": "حمید رضایی", "national_id": "0084575948"},
            "receiver": {"name": "محسن کاظمی", "national_id": "0084575948"},
            "origin": {"province": "تهران", "city": "تهران", "address": "خیابان آزادی پلاک ۱"},
            "destination": {"province": "البرز", "city": "کرج", "address": "بلوار جمهوری پلاک ۵"},
            "cargo": {"cargo_title": "آهن", "packaging_title": "شاخه", "cargo_weight": 2.5, "cargo_value": "1000000"},
            "vehicle": {"driver_national_code": "0084575948", "plate": "12ب345ایران11"},
            "financial": {"fare_amount": 5000000, "fare_type": "نقدی"},
        },
    )
    assert req_nested.payload.cargo.type == "آهن"
    assert req_nested.payload.cargo.weight == 2.5


@pytest.mark.parametrize("missing_field", ["cargo_packaging", "cargo_value"])
def test_flat_waybill_payload_requires_all_live_utcms_cargo_fields(missing_field):
    """Flat payloads must not bypass the live UTCMS packaging/value contract."""
    from pydantic import ValidationError

    from app.schemas.multitenant import WaybillJobCreateRequest

    payload = {
        "driver_national_code": "0084575948",
        "origin": "تهران",
        "destination": "اصفهان",
        "cargo_type": "سیمان",
        "cargo_packaging": "کیسه",
        "cargo_weight": 12.5,
        "cargo_value": "1000000",
        "plate_number": "12ب345ایران67",
    }
    payload.pop(missing_field)

    with pytest.raises(ValidationError):
        WaybillJobCreateRequest(driver_national_code="0084575948", payload=payload)


@pytest.mark.parametrize(
    "payload",
    [
        {
            "driver_national_code": "0012345679",
            "origin": "تهران",
            "destination": "اصفهان",
            "cargo_type": "سیمان",
            "cargo_packaging": "کیسه",
            "cargo_weight": 12.5,
            "cargo_value": "1000000",
            "plate_number": "12ب345ایران67",
        },
        {
            "sender": {"name": "حمید رضایی"},
            "receiver": {"name": "محسن کاظمی"},
            "origin": {"province": "تهران", "city": "تهران", "address": "خیابان آزادی"},
            "destination": {"province": "البرز", "city": "کرج", "address": "بلوار جمهوری"},
            "cargo": {
                "cargo_title": "آهن",
                "packaging_title": "شاخه",
                "cargo_weight": 2.5,
                "cargo_value": "1000000",
            },
            "vehicle": {"driver_national_code": "0012345679", "plate": "12ب345ایران11"},
        },
    ],
)
def test_waybill_create_rejects_payload_driver_identity_mismatch(payload):
    from pydantic import ValidationError

    from app.schemas.multitenant import WaybillJobCreateRequest

    with pytest.raises(ValidationError, match="payload"):
        WaybillJobCreateRequest(driver_national_code="0084575948", payload=payload)


@pytest.mark.parametrize("extra_field", [{"status": "success"}, {"notes": "manual override"}])
def test_waybill_update_rejects_unknown_or_state_machine_fields(extra_field):
    from pydantic import ValidationError

    from app.schemas.multitenant import WaybillJobUpdateRequest

    with pytest.raises(ValidationError):
        WaybillJobUpdateRequest.model_validate(extra_field)
