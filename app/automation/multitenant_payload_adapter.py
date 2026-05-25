"""Adapters that map the compact multi-tenant job payload into the full waybill schema."""
from __future__ import annotations

from typing import Any, Dict


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


def build_enhanced_waybill_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize the multi-tenant payload for EnhancedWaybillManager.

    The multi-tenant API stores a compact payload focused on route/cargo/vehicle.
    The enhanced manager expects the richer `WaybillMapRequest`-style structure.
    This adapter fills missing sections from `metadata_json` and safe defaults so the
    self-healing manager can be integrated without breaking existing callers.
    """
    metadata = payload.get("metadata_json") if isinstance(payload.get("metadata_json"), dict) else {}
    sender_meta = _metadata_section(metadata, "sender")
    receiver_meta = _metadata_section(metadata, "receiver")
    origin_meta = _metadata_section(metadata, "origin")
    destination_meta = _metadata_section(metadata, "destination")
    cargo_meta = _metadata_section(metadata, "cargo")
    vehicle_meta = _metadata_section(metadata, "vehicle")
    financial_meta = _metadata_section(metadata, "financial")
    shipping_meta = _metadata_section(metadata, "shipping_options")

    origin_text = str(_first_value(payload.get("origin"), origin_meta.get("city")) or "").strip()
    destination_text = str(_first_value(payload.get("destination"), destination_meta.get("city")) or "").strip()
    cargo_type = _first_value(payload.get("cargo_type"), cargo_meta.get("type")) or "کالای عمومی"
    cargo_weight = _first_value(payload.get("cargo_weight"), cargo_meta.get("weight")) or "1"
    vehicle_type = _first_value(payload.get("vehicle_type"), vehicle_meta.get("type")) or ""
    plate_number = _first_value(payload.get("plate_number"), vehicle_meta.get("plate")) or ""
    driver_code = str(_first_value(payload.get("driver_national_code"), vehicle_meta.get("driver_national_code")) or "").strip()

    default_sender_name = _first_value(sender_meta.get("name"), metadata.get("company_name")) or f"فرستنده {origin_text or 'نامشخص'}"
    default_receiver_name = _first_value(receiver_meta.get("name"), metadata.get("customer_name")) or f"گیرنده {destination_text or 'نامشخص'}"

    return {
        "sender": {
            "name": default_sender_name,
            "phone": str(_first_value(sender_meta.get("phone"), metadata.get("sender_phone")) or "09120000000"),
            "address": _first_value(sender_meta.get("address"), metadata.get("sender_address")),
            "national_code": _first_value(sender_meta.get("national_code"), metadata.get("sender_national_code")),
        },
        "receiver": {
            "name": default_receiver_name,
            "phone": str(_first_value(receiver_meta.get("phone"), metadata.get("receiver_phone")) or "09120000000"),
            "address": _first_value(receiver_meta.get("address"), metadata.get("receiver_address")),
            "national_code": _first_value(receiver_meta.get("national_code"), metadata.get("receiver_national_code")),
        },
        "origin": {
            "province": str(_first_value(origin_meta.get("province"), metadata.get("origin_province"), origin_text) or "نامشخص"),
            "city": str(_first_value(origin_meta.get("city"), origin_text) or "نامشخص"),
            "district": _first_value(origin_meta.get("district")),
            "address": str(_first_value(origin_meta.get("address"), metadata.get("origin_address"), origin_text) or "نامشخص"),
            "coordinates": origin_meta.get("coordinates"),
        },
        "destination": {
            "province": str(_first_value(destination_meta.get("province"), metadata.get("destination_province"), destination_text) or "نامشخص"),
            "city": str(_first_value(destination_meta.get("city"), destination_text) or "نامشخص"),
            "district": _first_value(destination_meta.get("district")),
            "address": str(_first_value(destination_meta.get("address"), metadata.get("destination_address"), destination_text) or "نامشخص"),
            "coordinates": destination_meta.get("coordinates"),
        },
        "cargo": {
            "type": str(cargo_type),
            "weight": cargo_weight,
            "count": _first_value(cargo_meta.get("count"), metadata.get("cargo_count")) or "1",
            "description": _first_value(payload.get("cargo_description"), cargo_meta.get("description")),
            "value": _first_value(payload.get("cargo_value"), cargo_meta.get("value"), financial_meta.get("cargo_value"), metadata.get("cargo_value")),
        },
        "vehicle": {
            "driver_national_code": driver_code or None,
            "driver_phone": _first_value(payload.get("driver_phone"), vehicle_meta.get("driver_phone"), metadata.get("driver_phone")),
            "plate": plate_number or None,
            "type": vehicle_type or None,
        },
        "financial": {
            "cost": _first_value(financial_meta.get("cost"), metadata.get("financial_cost")),
            "payment_method": _first_value(financial_meta.get("payment_method"), metadata.get("payment_method"), metadata.get("financial_payment_method")),
        },
        "shipping_options": {
            "two_way": bool(_first_value(shipping_meta.get("two_way"), metadata.get("two_way"), metadata.get("shipping_two_way")) or False),
            "time_limit": _first_value(shipping_meta.get("time_limit"), metadata.get("time_limit"), metadata.get("shipping_time_limit")),
            "end_shipping": _first_value(shipping_meta.get("end_shipping"), metadata.get("end_shipping"), metadata.get("shipping_end_shipping")),
            "otp": _first_value(shipping_meta.get("otp"), metadata.get("otp"), metadata.get("shipping_otp")),
        },
    }
