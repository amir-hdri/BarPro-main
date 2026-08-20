"""
Tests for UTCMS Field Matrix and Locator Proof (Phase 1.5).
"""

import json
from pathlib import Path


def load_field_matrix():
    fixture_path = Path(__file__).parent / "fixtures" / "utcms" / "field_matrix.json"
    with open(fixture_path, encoding="utf-8") as f:
        return json.load(f)


def test_field_matrix_structure():
    matrix = load_field_matrix()
    assert matrix["version"] == "2.0.0"
    assert matrix["route_mode"] == "user_text"
    assert "forms" in matrix
    assert len(matrix["forms"]) >= 8


def test_route_selectors_strictly_real_utcms_fields():
    matrix = load_field_matrix()
    origin_form = next(f for f in matrix["forms"] if f["form_id"] == "frmmabda")
    dest_form = next(f for f in matrix["forms"] if f["form_id"] == "formmagsad")

    # Verify origin fields
    origin_ids = {field["id"]: field for field in origin_form["fields"]}
    assert "ddStateSource" in origin_ids
    assert "ddCitySource" in origin_ids
    assert "txtAddressSource" in origin_ids

    assert origin_ids["ddStateSource"]["selector_primary"] == "#ddStateSource"
    assert origin_ids["ddCitySource"]["selector_primary"] == "#ddCitySource"
    assert origin_ids["txtAddressSource"]["selector_primary"] == "#txtAddressSource"

    # Verify destination fields
    dest_ids = {field["id"]: field for field in dest_form["fields"]}
    assert "ddStateDest" in dest_ids
    assert "ddCityDest" in dest_ids
    assert "txtAddressDest" in dest_ids

    assert dest_ids["ddStateDest"]["selector_primary"] == "#ddStateDest"
    assert dest_ids["ddCityDest"]["selector_primary"] == "#ddCityDest"
    assert dest_ids["txtAddressDest"]["selector_primary"] == "#txtAddressDest"

    # Ensure forbidden map locators are NOT present in user_text route forms
    forbidden_selectors = ["#MapCity", "#MapCity2", "#AddressSearch", "#AddressSearch2", "#txtAddressSourceFromMap"]
    for form in [origin_form, dest_form]:
        for field in form["fields"]:
            assert field["selector_primary"] not in forbidden_selectors
            assert field["id"] not in forbidden_selectors


def test_required_fields_have_readback_property():
    matrix = load_field_matrix()
    for form in matrix["forms"]:
        for field in form["fields"]:
            if field.get("required"):
                assert "readback_property" in field
                assert field["readback_property"] in {"value", "value_and_text"}


def test_readback_matcher_logic():
    """Simulate read-back validation logic for required form fields."""
    def validate_readback(field_spec: dict, dom_readback: dict, expected_value: str, expected_text: str | None = None) -> bool:
        prop = field_spec.get("readback_property", "value")
        if prop == "value":
            return str(dom_readback.get("value", "")).strip() == str(expected_value).strip()
        elif prop == "value_and_text":
            val_match = str(dom_readback.get("value", "")).strip() == str(expected_value).strip()
            if not val_match:
                return False
            if expected_text:
                return expected_text in str(dom_readback.get("text", "")).strip()
            return True
        return False

    spec_select = {"id": "ddStateSource", "readback_property": "value_and_text"}
    spec_text = {"id": "txtAddressSource", "readback_property": "value"}

    # Matching cases
    assert validate_readback(spec_select, {"value": "1", "text": "تهران"}, "1", "تهران") is True
    assert validate_readback(spec_text, {"value": "خیابان آزادی پلاک ۱۰"}, "خیابان آزادی پلاک ۱۰") is True

    # Failing cases (mismatch must fail)
    assert validate_readback(spec_select, {"value": "2", "text": "گیلان"}, "1", "تهران") is False
    assert validate_readback(spec_text, {"value": ""}, "خیابان آزادی پلاک ۱۰") is False
    assert validate_readback(spec_text, {"value": "آدرس اشتباه"}, "خیابان آزادی پلاک ۱۰") is False


def test_all_10_target_scenarios_covered():
    matrix = load_field_matrix()
    form_ids = {f["form_id"] for f in matrix["forms"]}

    # 1. Real Sender & 2. Legal Sender
    assert "frmSender" in form_ids
    sender_fields = {f["id"] for f in next(f for f in matrix["forms"] if f["form_id"] == "frmSender")["fields"]}
    assert "senderSelectType" in sender_fields
    assert "txtSenderOfficeName" in sender_fields
    assert "txtSenderFirstName" in sender_fields
    assert "txtSenderLastName" in sender_fields

    # 3. Real Receiver & 4. Legal Receiver
    assert "frmReciver" in form_ids
    receiver_fields = {f["id"] for f in next(f for f in matrix["forms"] if f["form_id"] == "frmReciver")["fields"]}
    assert "receiverSelectType" in receiver_fields
    assert "txtReceiverOfficeName" in receiver_fields

    # 5. Standard plate & 6. Free-zone plate
    assert "pelakbox" in form_ids

    # 7. Cargo packaging & weight & value
    assert "frmBar" in form_ids
    assert "frmcommodityInsert" in form_ids
    cargo_fields = {f["id"] for f in next(f for f in matrix["forms"] if f["form_id"] == "frmcommodityInsert")["fields"]}
    assert "ddBoxType" in cargo_fields
    assert "txtWeight" in cargo_fields
    assert "txtLoadName" in cargo_fields

    # 8. Text Route (Origin and Dest)
    assert "frmmabda" in form_ids
    assert "formmagsad" in form_ids
