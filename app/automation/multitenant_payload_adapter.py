"""Adapters that map the compact multi-tenant job payload into the full waybill schema."""

from __future__ import annotations

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


def validate_enhanced_waybill_payload(payload: dict[str, Any]) -> list[str]:
    """Return missing/invalid fields that block a real UTCMS submission.

    This mirrors the live HagigiHogugi form instead of the older API schema.
    Optional contact identifiers are deliberately not required.
    """
    errors: list[str] = []
    for party_key, label in (("sender", "فرستنده"), ("receiver", "گیرنده")):
        party = payload.get(party_key)
        if not isinstance(party, dict):
            errors.append(f"مشخصات {label}")
            continue
        entity_type = str(party.get("entity_type") or party.get("type") or "individual").strip().lower()
        if entity_type in {"company", "legal", "2", "حقوقی"}:
            if not str(party.get("office_name") or party.get("name") or "").strip():
                errors.append(f"نام حقوقی {label}")
        else:
            first_name = str(party.get("first_name") or "").strip()
            last_name = str(party.get("last_name") or "").strip()
            full_name = str(party.get("name") or "").strip()
            if not (first_name and last_name) and len(full_name.split()) < 2:
                errors.append(f"نام و نام خانوادگی {label}")

    for location_key, label in (("origin", "مبدا"), ("destination", "مقصد")):
        location = payload.get(location_key)
        if not isinstance(location, dict):
            errors.append(f"مشخصات {label}")
            continue
        for field, field_label in (("province", "استان"), ("city", "شهر"), ("address", "آدرس")):
            if not str(location.get(field) or "").strip():
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
            if _clean_optional(cargo.get(field)) is None:
                errors.append(label)

    vehicle = payload.get("vehicle")
    if not isinstance(vehicle, dict):
        errors.append("مشخصات راننده و خودرو")
    else:
        if not str(vehicle.get("driver_national_code") or "").strip():
            errors.append("کد ملی راننده")
        if not str(vehicle.get("plate") or "").strip():
            errors.append("پلاک خودرو")

    return errors


def build_enhanced_waybill_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize the multi-tenant payload for EnhancedWaybillManager.

    The multi-tenant API stores either a compact payload or a full nested one.
    This adapter ensures we always return the richer `WaybillMapRequest`-style structure.
    """
    # If it's already a nested payload (from the new manual form), use it as base
    if "sender" in payload and isinstance(payload["sender"], dict):
        # Ensure it has all required sections for the manager
        base = {
            "sender": payload.get("sender", {}),
            "receiver": payload.get("receiver", {}),
            "origin": payload.get("origin", {}),
            "destination": payload.get("destination", {}),
            "cargo": payload.get("cargo", {}),
            "vehicle": payload.get("vehicle", {}),
            "financial": payload.get("financial", {}),
            "shipping_options": payload.get("shipping_options", {}),
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
        "sender": {
            "name": default_sender_name,
            "phone": _first_value(sender_meta.get("phone"), metadata.get("sender_phone")),
            "address": _first_value(sender_meta.get("address"), metadata.get("sender_address")),
            "national_code": _first_value(sender_meta.get("national_code"), metadata.get("sender_national_code")),
            "entity_type": _first_value(sender_meta.get("entity_type"), sender_meta.get("type")) or "individual",
        },
        "receiver": {
            "name": default_receiver_name,
            "phone": _first_value(receiver_meta.get("phone"), metadata.get("receiver_phone")),
            "address": _first_value(receiver_meta.get("address"), metadata.get("receiver_address")),
            "national_code": _first_value(receiver_meta.get("national_code"), metadata.get("receiver_national_code")),
            "entity_type": _first_value(receiver_meta.get("entity_type"), receiver_meta.get("type")) or "individual",
        },
        "origin": {
            "province": origin_province or str(_first_value(metadata.get("origin_province")) or ""),
            "city": origin_city,
            "district": _first_value(origin_meta.get("district")),
            "address": str(_first_value(origin_address, metadata.get("origin_address")) or ""),
            "coordinates": origin_meta.get("coordinates"),
        },
        "destination": {
            "province": destination_province or str(_first_value(metadata.get("destination_province")) or ""),
            "city": destination_city,
            "district": _first_value(destination_meta.get("district")),
            "address": str(_first_value(destination_address, metadata.get("destination_address")) or ""),
            "coordinates": destination_meta.get("coordinates"),
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


__all__ = ["build_enhanced_waybill_payload", "validate_enhanced_waybill_payload"]
