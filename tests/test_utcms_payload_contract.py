from app.automation.multitenant_payload_adapter import (
    build_enhanced_waybill_payload,
    validate_enhanced_waybill_payload,
)
from app.schemas.waybill import CargoModel, ReceiverModel, SenderModel


def test_legacy_model_allows_missing_party_fields_but_live_preflight_does_not() -> None:
    sender = SenderModel(name="علی فلاح")
    receiver = ReceiverModel(name="احمد مومنی")

    assert sender.phone is None
    assert sender.address is None
    assert sender.national_code is None
    assert receiver.phone is None
    assert receiver.address is None


def test_cargo_requires_packaging_and_value() -> None:
    cargo = CargoModel(type="مصالح", packaging="فله", weight="15", value="35000000")
    assert cargo.packaging == "فله"
    assert cargo.value == "35000000"


def test_compact_payload_does_not_invent_party_or_location_data() -> None:
    normalized = build_enhanced_waybill_payload(
        {
            "origin": "کردستان، سقز، بزرگراه سقز-دیواندره",
            "destination": "کردستان، سقز، خیابان بهارستان",
            "cargo_type": "مصالح",
            "cargo_weight": 15,
            "cargo_value": "35000000",
            "cargo_description": "فله",
            "plate_number": "86ع335ایران51",
            "driver_national_code": "3720285359",
            "metadata_json": {
                "sender": {"name": "امید صالحی"},
                "receiver": {"name": "حامد حسین زاده"},
                "cargo": {"packaging": "فله"},
            },
        }
    )

    assert normalized["sender"]["phone"] is None
    assert normalized["receiver"]["phone"] is None
    assert normalized["origin"]["province"] == "کردستان"
    assert normalized["origin"]["city"] == "سقز"
    assert normalized["origin"]["district"] is None
    assert normalized["origin"]["address"] == "بزرگراه سقز-دیواندره"
    assert normalized["origin"]["coordinates"] is None

    assert normalized["destination"]["province"] == "کردستان"
    assert normalized["destination"]["city"] == "سقز"


def test_preflight_accepts_only_live_required_fields() -> None:
    payload = {
        "sender": {"name": "امید صالحی", "entity_type": "individual"},
        "receiver": {"name": "حامد حسین زاده", "entity_type": "individual"},
        "origin": {"province": "کردستان", "city": "سقز", "address": "بزرگراه سقز-دیواندره"},
        "destination": {"province": "کردستان", "city": "سقز", "address": "خیابان بهارستان"},
        "cargo": {"type": "مصالح", "packaging": "فله", "weight": "15", "value": "35000000"},
        "vehicle": {"driver_national_code": "3720285359", "plate": "86ع335ایران51"},
    }

    assert validate_enhanced_waybill_payload(payload) == []
    assert validate_enhanced_waybill_payload(payload, enforce_live_party_phones=True)


def test_preflight_rejects_missing_live_required_fields() -> None:
    errors = validate_enhanced_waybill_payload(
        {
            "sender": {"name": "تک‌نام"},
            "receiver": {},
            "origin": {"province": "کردستان"},
            "destination": {},
            "cargo": {"type": "مصالح", "weight": "15"},
            "vehicle": {"driver_national_code": "3720285359"},
        }
    )

    assert "نام و نام خانوادگی فرستنده" in errors
    assert "نام و نام خانوادگی گیرنده" in errors
    assert "نوع بسته‌بندی" in errors
    assert "ارزش تقریبی بار" in errors
    assert "پلاک خودرو" in errors
