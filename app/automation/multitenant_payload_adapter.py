"""Adapters that map the compact multi-tenant job payload into the full waybill schema."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

PLACEHOLDER_VALUES = {":x:", ":x", "x", "X", "", "-", "null", "None", "none"}


def _metadata_section(metadata: dict[str, Any], key: str) -> dict[str, Any]:
    value = metadata.get(key)
    return value if isinstance(value, dict) else {}


def _clean_optional(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned in PLACEHOLDER_VALUES:
            return None
        return cleaned
    return value


def _first_value(*values: Any) -> Any:
    for value in values:
        cleaned = _clean_optional(value)
        if cleaned is not None:
            return cleaned
    return None


def _normalize_canonical_text(value: Any) -> str:
    """Normalize Persian text for canonical route key comparisons."""
    if not value:
        return ""
    text = str(value).strip().lower()
    text = text.replace("ي", "ی").replace("ك", "ک").replace("‌", " ").replace("\u200c", " ")
    return re.sub(r"\s+", " ", text).strip()


def compute_canonical_route_key(origin: dict[str, Any], destination: dict[str, Any]) -> str:
    """
    Compute a deterministic canonical route key based exclusively on user text fields:
    province + city + district + address.

    GPS and coordinates are strictly excluded from the route identity.
    Two routes with different addresses have different route keys even if province and city match.
    """
    origin_province = _normalize_canonical_text(origin.get("province"))
    origin_city = _normalize_canonical_text(origin.get("city"))
    origin_district = _normalize_canonical_text(origin.get("district"))
    origin_address = _normalize_canonical_text(origin.get("address"))

    dest_province = _normalize_canonical_text(destination.get("province"))
    dest_city = _normalize_canonical_text(destination.get("city"))
    dest_district = _normalize_canonical_text(destination.get("district"))
    dest_address = _normalize_canonical_text(destination.get("address"))

    canonical_origin = f"{origin_province}|{origin_city}|{origin_district}|{origin_address}"
    canonical_dest = f"{dest_province}|{dest_city}|{dest_district}|{dest_address}"
    full_canonical = f"{canonical_origin}-->{canonical_dest}"

    digest = hashlib.sha256(full_canonical.encode("utf-8")).hexdigest()[:20]
    return f"route-{digest}"


def _location_parts(raw_text: Any, section: dict[str, Any], metadata: dict[str, Any]) -> tuple[str, str, str]:
    """Resolve compact ``province، city، address`` data without inventing values."""
    province = _first_value(section.get("province"), metadata.get("province"))
    city = _first_value(section.get("city"), metadata.get("city"))
    address = _first_value(section.get("address"), metadata.get("address"))
    raw = str(_clean_optional(raw_text) or "").strip()
    parts = [part.strip() for part in raw.replace(",", "،").split("،") if part.strip()]
    if not province and len(parts) >= 1:
        province = parts[0]
    if not city and len(parts) >= 2:
        city = parts[1]
    if not address and len(parts) >= 3:
        address = "، ".join(parts[2:])
    return str(province or ""), str(city or ""), str(address or "")


def _validate_iranian_national_code(code: str) -> bool:
    """Validate Iranian 10-digit national code checksum."""
    clean_code = re.sub(r"\D", "", _normalize_numeric(code)).strip()
    if len(clean_code) != 10:
        return False
    if clean_code in {
        "0000000000",
        "1111111111",
        "2222222222",
        "3333333333",
        "4444444444",
        "5555555555",
        "6666666666",
        "7777777777",
        "8888888888",
        "9999999999",
    }:
        return False
    checksum = sum(int(clean_code[i]) * (10 - i) for i in range(9))
    remainder = checksum % 11
    control = int(clean_code[9])
    return control == remainder if remainder < 2 else control == (11 - remainder)


def _normalize_mobile(value: Any) -> str:
    text = str(value or "")
    for index, digit in enumerate("۰۱۲۳۴۵۶۷۸۹"):
        text = text.replace(digit, str(index))
    for index, digit in enumerate("٠١٢٣٤٥٦٧٨٩"):
        text = text.replace(digit, str(index))
    return re.sub(r"\D", "", text)


def _normalize_numeric(value: Any) -> str:
    """Normalize Persian/Arabic digits and common thousands separators."""
    text = str(value or "")
    for index, digit in enumerate("۰۱۲۳۴۵۶۷۸۹"):
        text = text.replace(digit, str(index))
    for index, digit in enumerate("٠١٢٣٤٥٦٧٨٩"):
        text = text.replace(digit, str(index))
    return text.replace(",", "").replace("٬", "").strip()


def _canonical_plate(value: Any) -> str | None:
    """Return the canonical Iranian plate or ``None`` for an invalid value."""
    try:
        from app.schemas.multitenant import _normalize_plate

        return _normalize_plate(str(value or ""))
    except (TypeError, ValueError):
        return None


def validate_enhanced_waybill_payload(payload: dict[str, Any], *, enforce_live_party_phones: bool = False) -> list[str]:
    """Return missing/invalid fields that block a real UTCMS submission.

    This mirrors the live HagigiHogugi form instead of the older API schema.
    The live form requires a real Iranian mobile number for both parties.  The
    stricter check is opt-in so historical/read-only payload tooling can still
    inspect older records without pretending they are submit-ready.
    """
    errors: list[str] = []
    for party_key, label in (("sender", "فرستنده"), ("receiver", "گیرنده")):
        party = payload.get(party_key)
        if not isinstance(party, dict):
            errors.append(f"مشخصات {label}")
            continue
        entity_type = str(party.get("entity_type") or party.get("type") or "individual").strip().lower()
        if entity_type in {"company", "legal", "2", "حقوقی"}:
            office_name = str(party.get("office_name") or party.get("name") or "").strip()
            if not office_name or office_name in PLACEHOLDER_VALUES or len(office_name) < 2:
                errors.append(f"نام حقوقی {label}")
        else:
            first_name = str(party.get("first_name") or "").strip()
            last_name = str(party.get("last_name") or "").strip()
            full_name = str(party.get("name") or "").strip()

            if first_name and last_name:
                if first_name.lower() == last_name.lower() and len(first_name) <= 3:
                    errors.append(f"نام و نام خانوادگی {label} نمی‌تواند کلمات تکراری یکسان باشد")
            else:
                parts = [p for p in full_name.split() if p]
                if len(parts) < 2:
                    errors.append(f"نام و نام خانوادگی {label}")
                elif len(parts) == 2 and parts[0].lower() == parts[1].lower():
                    errors.append(f"نام و نام خانوادگی {label} نمی‌تواند کلمات تکراری یکسان باشد")

            if full_name and len(full_name) < 3:
                errors.append(f"طول نام {label} بسیار کوتاه است")

        nat_code = _clean_optional(party.get("national_code"))
        if nat_code:
            if not _validate_iranian_national_code(nat_code):
                errors.append(f"کد ملی {label} نامعتبر است")

        if enforce_live_party_phones:
            mobile = _normalize_mobile(party.get("phone"))
            if not mobile:
                errors.append(f"موبایل {label}")
            elif not re.fullmatch(r"09\d{9}", mobile):
                errors.append(f"موبایل {label} باید با ۰۹ شروع شود و ۱۱ رقم باشد")

    for location_key, label in (("origin", "مبدا"), ("destination", "مقصد")):
        location = payload.get(location_key)
        if not isinstance(location, dict):
            errors.append(f"مشخصات {label}")
            continue
        for field, field_label in (("province", "استان"), ("city", "شهر"), ("address", "آدرس")):
            val = str(location.get(field) or "").strip()
            minimum = 5 if field == "address" else 2
            if not val or val in PLACEHOLDER_VALUES or len(val) < minimum:
                errors.append(f"{field_label} {label}")

    cargo = payload.get("cargo")
    if not isinstance(cargo, dict):
        errors.append("مشخصات کالا")
    else:
        for field, label in (
            ("type", "نوع کالا"),
            ("packaging", "نوع بسته‌بندی"),
            ("weight", "وزن کالا"),
            ("value", "ارزش تقریبی بار"),
        ):
            val = _clean_optional(cargo.get(field))
            if val is None:
                errors.append(label)

        weight_val = cargo.get("weight")
        try:
            parsed_weight = float(_normalize_numeric(weight_val))
            if not math.isfinite(parsed_weight) or parsed_weight <= 0:
                errors.append("وزن کالا باید مثبت و بزرگتر از صفر باشد")
        except (ValueError, TypeError):
            errors.append("وزن کالا عددی نامعتبر است")

        value_val = cargo.get("value")
        try:
            parsed_value = float(_normalize_numeric(value_val))
            if not math.isfinite(parsed_value) or parsed_value <= 0:
                errors.append("ارزش تقریبی بار باید مثبت و بزرگتر از صفر باشد")
        except (ValueError, TypeError):
            errors.append("ارزش تقریبی بار عددی نامعتبر است")

    vehicle = payload.get("vehicle")
    if not isinstance(vehicle, dict):
        errors.append("مشخصات راننده و خودرو")
    else:
        driver_code = str(vehicle.get("driver_national_code") or "").strip()
        if not driver_code:
            errors.append("کد ملی راننده")
        elif not _validate_iranian_national_code(driver_code):
            errors.append("کد ملی راننده نامعتبر است (کنترل رقم نامعتبر)")

        plate_str = str(vehicle.get("plate") or "").strip()
        if not plate_str or plate_str in PLACEHOLDER_VALUES:
            errors.append("پلاک خودرو")
        elif enforce_live_party_phones and _canonical_plate(plate_str) is None:
            errors.append("فرمت پلاک خودرو نامعتبر است")

    return errors


def validate_live_waybill_payload(
    payload: dict[str, Any],
    *,
    expected_driver_national_code: str | None = None,
    expected_plate: str | None = None,
    expected_driver_mobile: str | None = None,
) -> list[str]:
    """Validate the complete user-supplied contract required before UTCMS mutation.

    This is the single strict gate used by API/job creation, batches, and workers.
    It deliberately does not invent missing values and it keeps account credentials
    outside the business payload; driver account readiness is checked by the caller.
    """
    errors = validate_enhanced_waybill_payload(payload, enforce_live_party_phones=True)
    vehicle = payload.get("vehicle") if isinstance(payload.get("vehicle"), dict) else {}

    driver_mobile = _normalize_mobile(expected_driver_mobile or vehicle.get("driver_phone"))
    if re.fullmatch(r"09\d{9}", driver_mobile):
        for party_key, label in (("sender", "فرستنده"), ("receiver", "گیرنده")):
            party = payload.get(party_key)
            party_mobile = _normalize_mobile(party.get("phone")) if isinstance(party, dict) else ""
            if party_mobile and party_mobile == driver_mobile:
                errors.append(f"موبایل {label} نباید با موبایل راننده یکسان باشد")

    if expected_driver_national_code:
        actual = _normalize_numeric(vehicle.get("driver_national_code"))
        expected = _normalize_numeric(expected_driver_national_code)
        if actual != expected:
            errors.append("کد ملی راننده با رانندهٔ انتخاب‌شده مطابقت ندارد")

    if expected_plate:
        actual_plate = _canonical_plate(vehicle.get("plate"))
        expected_canonical = _canonical_plate(expected_plate)
        if actual_plate is None or expected_canonical is None or actual_plate != expected_canonical:
            errors.append("پلاک خودرو با پلاک فعال راننده مطابقت ندارد")

    # Keep error output deterministic for API clients and UI rendering.
    return list(dict.fromkeys(errors))


def build_enhanced_waybill_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize the multi-tenant payload for EnhancedWaybillManager.

    The multi-tenant API stores either a compact payload or a full nested one.
    This adapter ensures we always return the richer `WaybillMapRequest`-style structure
    strictly adhering to user_text mode.
    """
    # If at least one party is already nested (from the new manual form), use
    # the richer shape as the base.  Older records can still contain compact
    # string locations alongside nested parties, so never call ``dict()`` on a
    # non-mapping value here (that used to raise ``ValueError`` before the
    # browser even opened).
    if isinstance(payload.get("sender"), dict) or isinstance(payload.get("receiver"), dict):
        raw_metadata = payload.get("metadata_json")
        metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}

        raw_origin = payload.get("origin")
        origin_meta = _metadata_section(metadata, "origin")
        if isinstance(raw_origin, dict):
            origin_dict = dict(raw_origin)
        else:
            province, city, address = _location_parts(raw_origin, origin_meta, metadata)
            origin_dict = {"province": province, "city": city, "address": address}

        raw_destination = payload.get("destination")
        destination_meta = _metadata_section(metadata, "destination")
        if isinstance(raw_destination, dict):
            dest_dict = dict(raw_destination)
        else:
            province, city, address = _location_parts(raw_destination, destination_meta, metadata)
            dest_dict = {"province": province, "city": city, "address": address}

        sender = dict(payload.get("sender")) if isinstance(payload.get("sender"), dict) else dict(_metadata_section(metadata, "sender"))
        receiver = (
            dict(payload.get("receiver"))
            if isinstance(payload.get("receiver"), dict)
            else dict(_metadata_section(metadata, "receiver"))
        )
        cargo = dict(payload.get("cargo")) if isinstance(payload.get("cargo"), dict) else dict(_metadata_section(metadata, "cargo"))
        vehicle = (
            dict(payload.get("vehicle"))
            if isinstance(payload.get("vehicle"), dict)
            else dict(_metadata_section(metadata, "vehicle"))
        )
        financial = (
            dict(payload.get("financial"))
            if isinstance(payload.get("financial"), dict)
            else dict(_metadata_section(metadata, "financial"))
        )
        shipping_options = (
            dict(payload.get("shipping_options"))
            if isinstance(payload.get("shipping_options"), dict)
            else dict(_metadata_section(metadata, "shipping_options"))
        )

        # Enforce user_text mode: coordinates are nullified
        origin_dict["coordinates"] = None
        origin_dict["location_mode"] = "user_text"
        origin_dict["route_source"] = "user_text"

        dest_dict["coordinates"] = None
        dest_dict["location_mode"] = "user_text"
        dest_dict["route_source"] = "user_text"

        base = {
            "route_source": "user_text",
            "location_mode": "user_text",
            "sender": sender,
            "receiver": receiver,
            "origin": origin_dict,
            "destination": dest_dict,
            "cargo": cargo,
            "vehicle": vehicle,
            "financial": financial,
            "shipping_options": shipping_options,
        }
        # If there's an outer driver_national_code, sync it to vehicle
        if payload.get("driver_national_code") and not base["vehicle"].get("driver_national_code"):
            base["vehicle"]["driver_national_code"] = payload["driver_national_code"]
        return base

    raw_metadata = payload.get("metadata_json")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    sender_meta = _metadata_section(metadata, "sender")
    receiver_meta = _metadata_section(metadata, "receiver")
    origin_meta = _metadata_section(metadata, "origin")
    destination_meta = _metadata_section(metadata, "destination")
    cargo_meta = _metadata_section(metadata, "cargo")
    vehicle_meta = _metadata_section(metadata, "vehicle")
    financial_meta = _metadata_section(metadata, "financial")
    shipping_meta = _metadata_section(metadata, "shipping_options")

    origin_text = str(_first_value(payload.get("origin")) or "").strip()
    destination_text = str(_first_value(payload.get("destination")) or "").strip()
    origin_province, origin_city, origin_address = _location_parts(origin_text, origin_meta, metadata)
    destination_province, destination_city, destination_address = _location_parts(
        destination_text, destination_meta, metadata
    )
    cargo_type = _first_value(payload.get("cargo_type"), cargo_meta.get("type"))
    cargo_weight = _first_value(payload.get("cargo_weight"), cargo_meta.get("weight"))
    vehicle_type = _first_value(payload.get("vehicle_type"), vehicle_meta.get("type")) or ""
    plate_number = _first_value(payload.get("plate_number"), vehicle_meta.get("plate")) or ""
    driver_code = str(
        _first_value(payload.get("driver_national_code"), vehicle_meta.get("driver_national_code")) or ""
    ).strip()

    default_sender_name = _first_value(sender_meta.get("name"), metadata.get("company_name"))
    default_receiver_name = _first_value(receiver_meta.get("name"), metadata.get("customer_name"))

    return {
        "route_source": "user_text",
        "location_mode": "user_text",
        "sender": {
            "name": default_sender_name,
            "phone": _first_value(payload.get("sender_phone"), sender_meta.get("phone"), metadata.get("sender_phone")),
            "address": _first_value(sender_meta.get("address"), metadata.get("sender_address")),
            "national_code": _first_value(sender_meta.get("national_code"), metadata.get("sender_national_code")),
            "entity_type": _first_value(sender_meta.get("entity_type"), sender_meta.get("type")) or "individual",
        },
        "receiver": {
            "name": default_receiver_name,
            "phone": _first_value(
                payload.get("receiver_phone"), receiver_meta.get("phone"), metadata.get("receiver_phone")
            ),
            "address": _first_value(receiver_meta.get("address"), metadata.get("receiver_address")),
            "national_code": _first_value(receiver_meta.get("national_code"), metadata.get("receiver_national_code")),
            "entity_type": _first_value(receiver_meta.get("entity_type"), receiver_meta.get("type")) or "individual",
        },
        "origin": {
            "province": origin_province or str(_first_value(metadata.get("origin_province")) or ""),
            "city": origin_city,
            "district": _first_value(origin_meta.get("district")),
            "address": str(_first_value(origin_address, metadata.get("origin_address")) or ""),
            "coordinates": None,
            "route_source": "user_text",
            "location_mode": "user_text",
        },
        "destination": {
            "province": destination_province or str(_first_value(metadata.get("destination_province")) or ""),
            "city": destination_city,
            "district": _first_value(destination_meta.get("district")),
            "address": str(_first_value(destination_address, metadata.get("destination_address")) or ""),
            "coordinates": None,
            "route_source": "user_text",
            "location_mode": "user_text",
        },
        "cargo": {
            "type": str(cargo_type or ""),
            "weight": cargo_weight,
            "count": _first_value(cargo_meta.get("count"), metadata.get("cargo_count")) or "1",
            "description": _first_value(payload.get("cargo_description"), cargo_meta.get("description")),
            "packaging": _first_value(payload.get("cargo_packaging"), cargo_meta.get("packaging")),
            "value": _first_value(
                payload.get("cargo_value"),
                cargo_meta.get("value"),
                financial_meta.get("cargo_value"),
                metadata.get("cargo_value"),
            ),
        },
        "vehicle": {
            "driver_national_code": driver_code or None,
            "driver_phone": _first_value(
                payload.get("driver_phone"), vehicle_meta.get("driver_phone"), metadata.get("driver_phone")
            ),
            "plate": plate_number or None,
            "type": vehicle_type or None,
        },
        "financial": {
            "cost": _first_value(financial_meta.get("cost"), metadata.get("financial_cost")),
            "payment_method": _first_value(
                financial_meta.get("payment_method"),
                metadata.get("payment_method"),
                metadata.get("financial_payment_method"),
            ),
        },
        "shipping_options": {
            "two_way": bool(
                _first_value(shipping_meta.get("two_way"), metadata.get("two_way"), metadata.get("shipping_two_way"))
                or False
            ),
            "time_limit": _first_value(
                shipping_meta.get("time_limit"), metadata.get("time_limit"), metadata.get("shipping_time_limit")
            ),
            "end_shipping": _first_value(
                shipping_meta.get("end_shipping"), metadata.get("end_shipping"), metadata.get("shipping_end_shipping")
            ),
            "otp": _first_value(shipping_meta.get("otp"), metadata.get("otp"), metadata.get("shipping_otp")),
        },
    }


__all__ = [
    "build_enhanced_waybill_payload",
    "validate_enhanced_waybill_payload",
    "validate_live_waybill_payload",
    "compute_canonical_route_key",
]
