"""Offline regression cases using invented data, never captured credentials."""

import json
from copy import deepcopy

import pytest

from app.automation.benchmark_payload_adapter import build_benchmark_import_draft, read_benchmark_model
from app.automation.mobile_payload_adapter import build_mobile_document_payload
from app.automation.multitenant_payload_adapter import (
    build_enhanced_waybill_payload,
    validate_live_waybill_payload,
)


@pytest.fixture
def benchmark_model():
    # Exact captured field vocabulary; all values below are synthetic.
    return {
        "sender_national_code": "",
        "sender_firstname": "آزمایش",
        "sender_lastname": "فرستنده",
        "sender_mobile": "9121234567",
        "receiver_national_code": "",
        "receiver_firstname": "آزمایش",
        "receiver_lastname": "گیرنده",
        "receiver_mobile": "۰۹۱۲۹۸۷۶۵۴۳",
        "source_address": "نشانی آزمایشی مبدا",
        "source_lat": "35.70",
        "source_lng": "51.40",
        "source_city": "تهران",
        "dest_address": "نشانی آزمایشی مقصد",
        "dest_lat": "35.71",
        "dest_lng": "51.41",
        "dest_city": "تهران",
        "load": "مصالح",
        "box": "فله",
        "load_count": "2",
        "load_weight": "1500",
        "load_price": "35,000,000",
        "cost": "5,000,000",
        # Constructed synthetic national code: the digits were chosen so the
        # Iranian checksum validates. Not a captured identifier.
        "driver_national_code": "3720285359",
        "plack_region": "51",
        "plack_2": "86",
        "plack_char": "ع",
        "plack_3": "335",
    }


def build_draft(source, **kwargs):
    options = {"origin_province": "تهران", "destination_province": "تهران", "weight_unit": "kg"}
    options.update(kwargs)
    return build_benchmark_import_draft(source, **options)


def test_saved_baseline_creates_reviewable_barpro_draft(benchmark_model):
    original = deepcopy(benchmark_model)
    draft = build_draft({"model": json.dumps(benchmark_model)})
    assert benchmark_model == original
    assert draft.requires_review is True
    assert draft.validation_errors == ()
    assert draft.payload["sender"]["phone"] == "09121234567"
    assert draft.payload["receiver"]["phone"] == "09129876543"
    assert draft.payload["cargo"]["weight"] == "1.5"
    assert draft.payload["cargo"]["value"] == "35000000"
    assert draft.payload["financial"]["cost"] == "5000000"
    assert draft.payload["vehicle"]["plate"] == "86ع335ایران51"
    assert draft.sent_coordinate_reference == {}
    normalized = build_enhanced_waybill_payload(draft.payload)
    assert normalized["origin"]["coordinates"] == {"lat": 35.7, "lng": 51.4}
    assert validate_live_waybill_payload(normalized) == []


def test_enriched_model_keeps_sent_coordinates_out_of_execution_payload(benchmark_model):
    enriched = {
        **benchmark_model,
        "sent_source_lat": "35.72",
        "sent_source_lng": "51.42",
        "sent_dest_lat": "35.73",
        "sent_dest_lng": "51.43",
    }
    assert len(read_benchmark_model(enriched)) == 31
    draft = build_draft(enriched)
    assert draft.payload["origin"]["coordinates"] == {"lat": 35.7, "lng": 51.4}
    assert draft.payload["destination"]["coordinates"] == {"lat": 35.71, "lng": 51.41}
    assert draft.sent_coordinate_reference["sent_source_lat"] == "35.72"
    assert "sent_" not in json.dumps(draft.payload)


def test_credentials_and_upstream_execution_state_cannot_enter_draft(benchmark_model):
    draft = build_draft(
        {
            "model": benchmark_model,
            "driver": {"password": "SYNTHETIC_PASSWORD_DO_NOT_COPY", "mobile": "09120000000"},
            "token": "SYNTHETIC_TOKEN_DO_NOT_COPY",
            "secret": "SYNTHETIC_SECRET_DO_NOT_COPY",
            "status": 3,
            "barname_id": 123,
            "tracking_code": "SYNTHETIC_TRACKING_DO_NOT_COPY",
            "shipping_type": 2,
            "shipping_status": 3,
            "retryable": True,
        }
    )
    rendered = json.dumps(draft.payload) + repr(draft)
    assert "DO_NOT_COPY" not in rendered
    assert "shipping" not in rendered
    assert "password" not in rendered
    assert "token" not in rendered
    assert "tracking" not in rendered
    assert "sender_mobile" not in repr(draft)


def test_dead_description_input_is_ignored_without_changing_schema(benchmark_model):
    source = {**benchmark_model, "load_description": "THIS_WAS_NEVER_SERIALIZED"}
    assert len(read_benchmark_model(source)) == 27
    assert build_draft(source).payload == build_draft(benchmark_model).payload


@pytest.mark.parametrize("key", ["load", "sender_mobile", "source_city"])
def test_missing_baseline_key_is_not_silently_defaulted(benchmark_model, key):
    del benchmark_model[key]
    with pytest.raises(ValueError, match="keys do not match"):
        build_draft(benchmark_model)


def test_unrecognized_or_partial_enrichment_is_not_accepted(benchmark_model):
    with pytest.raises(ValueError, match="keys do not match"):
        build_draft({**benchmark_model, "password": "SYNTHETIC_PASSWORD"})
    with pytest.raises(ValueError, match="all four"):
        build_draft({**benchmark_model, "sent_source_lat": "35.8"})


@pytest.mark.parametrize("raw", ['{"model":', "[]", '"model"', '{"load":"a","load":"b"}'])
def test_invalid_model_json_fails_without_echoing_input(raw):
    with pytest.raises(ValueError) as error:
        read_benchmark_model(raw)
    assert raw not in str(error.value)


def test_non_string_values_fail_on_contract_drift(benchmark_model):
    benchmark_model["cost"] = 5000000
    with pytest.raises(ValueError, match="must be strings"):
        build_draft(benchmark_model)


@pytest.mark.parametrize("field", ["origin_province", "destination_province"])
def test_province_is_never_guessed_from_city_or_coordinates(benchmark_model, field):
    with pytest.raises(ValueError, match="provinces"):
        build_draft(benchmark_model, **{field: " "})


def test_weight_conversion_uses_explicit_units_instead_of_magnitude(benchmark_model):
    benchmark_model["load_weight"] = "150"
    assert build_draft(benchmark_model, weight_unit="ton").payload["cargo"]["weight"] == "150"
    assert build_draft(benchmark_model, weight_unit="kg").payload["cargo"]["weight"] == "0.15"
    with pytest.raises(ValueError, match="explicitly ton or kg"):
        build_draft(benchmark_model, weight_unit="unknown")


@pytest.mark.parametrize(
    "field,value", [("load_weight", "nan"), ("cost", ""), ("load_price", "-1"), ("load_count", "1.5")]
)
def test_invalid_financial_and_cargo_values_are_not_repaired(benchmark_model, field, value):
    benchmark_model[field] = value
    with pytest.raises(ValueError):
        build_draft(benchmark_model)


@pytest.mark.parametrize("field,label", [("cost", "fare"), ("load_price", "cargo value")])
def test_fractional_rial_amount_is_rejected_not_forwarded(benchmark_model, field, label):
    # A fractional Rial amount used to format straight through with an empty
    # validation_errors; downstream `str(...).isdigit()` guards then forwarded
    # it verbatim to #txtkeraye and drew the UTCMS 4025 fare rejection.
    benchmark_model[field] = "5000000.50"
    with pytest.raises(ValueError, match=f"{label} must be a whole number"):
        build_draft(benchmark_model)


def test_integral_amounts_do_not_keep_a_trailing_fraction(benchmark_model):
    # Decimal("2.0") == Decimal("2") numerically, so the integrality check
    # passed while format(..., "f") still emitted "2.0".
    benchmark_model["load_count"] = "2.0"
    benchmark_model["cost"] = "5000000.00"
    benchmark_model["load_price"] = "35000000.0"
    payload = build_draft(benchmark_model).payload
    assert payload["cargo"]["count"] == "2"
    assert payload["financial"]["cost"] == "5000000"
    assert payload["cargo"]["value"] == "35000000"


def test_fractional_weight_is_still_allowed(benchmark_model):
    # Weight is tonnage, not currency — it must stay fractional.
    benchmark_model["load_weight"] = "1500"
    assert build_draft(benchmark_model, weight_unit="kg").payload["cargo"]["weight"] == "1.5"


@pytest.mark.parametrize("plack_char,expected", [("ي", "86ی335ایران51"), (" ع ", "86ع335ایران51")])
def test_plate_letter_is_canonicalized_for_the_draft(benchmark_model, plack_char, expected):
    # plack_char arrives unnormalized (Arabic yeh is common on Iranian
    # keyboards); the raw form would not match a stored BarPro plate.
    benchmark_model["plack_char"] = plack_char
    assert build_draft(benchmark_model).payload["vehicle"]["plate"] == expected


def test_unparseable_plate_stays_raw_for_review_instead_of_raising(benchmark_model):
    benchmark_model["plack_char"] = "??"
    draft = build_draft(benchmark_model)
    assert draft.payload["vehicle"]["plate"] == "86??335ایران51"
    assert draft.validation_errors


@pytest.mark.parametrize("value", ["NaN", "Infinity", "91", ""])
def test_invalid_coordinates_are_not_replaced_with_sent_values(benchmark_model, value):
    benchmark_model["source_lat"] = value
    with pytest.raises(ValueError, match="coordinates"):
        build_draft(benchmark_model)


def test_invalid_phone_stays_visible_for_review(benchmark_model):
    benchmark_model["sender_mobile"] = "invalid"
    draft = build_draft(benchmark_model)
    assert draft.validation_errors
    assert draft.payload["sender"]["phone"] == "invalid"


def test_existing_driver_identity_guard_still_applies(benchmark_model):
    draft = build_draft(benchmark_model)
    errors = validate_live_waybill_payload(draft.payload, expected_driver_mobile="09121234567")
    assert "موبایل فرستنده نباید با موبایل راننده یکسان باشد" in errors


def test_import_does_not_invent_fields_required_by_mobile_transport(benchmark_model):
    draft = build_draft(benchmark_model)
    with pytest.raises(ValueError):
        build_mobile_document_payload(draft.payload, token="synthetic-token", cap_token="synthetic-captcha")
    assert "insurance" not in draft.payload
    assert "postal_code" not in draft.payload["sender"]
    assert "product_id" not in draft.payload["cargo"]
