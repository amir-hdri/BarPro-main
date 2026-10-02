"""Offline import of the separately hosted benchmark bot's saved model.

This is not the UTCMS mobile DTO and is not a transport. Only the documented
business model is converted; account credentials, statuses and scheduling
instructions from the surrounding record never enter a BarPro draft.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from app.automation.multitenant_payload_adapter import validate_live_waybill_payload

BASE_MODEL_KEYS = (
    "sender_national_code",
    "sender_firstname",
    "sender_lastname",
    "sender_mobile",
    "receiver_national_code",
    "receiver_firstname",
    "receiver_lastname",
    "receiver_mobile",
    "source_address",
    "source_lat",
    "source_lng",
    "source_city",
    "dest_address",
    "dest_lat",
    "dest_lng",
    "dest_city",
    "load",
    "box",
    "load_count",
    "load_weight",
    "load_price",
    "cost",
    "driver_national_code",
    "plack_region",
    "plack_2",
    "plack_char",
    "plack_3",
)
SENT_COORDINATE_KEYS = ("sent_source_lat", "sent_source_lng", "sent_dest_lat", "sent_dest_lng")
MODEL_KEYS = BASE_MODEL_KEYS + SENT_COORDINATE_KEYS
RANDOMIZER_FIELDS = (
    "sender_firstname",
    "sender_lastname",
    "sender_mobile",
    "receiver_firstname",
    "receiver_lastname",
    "receiver_mobile",
    "rent",
    "latlng",
    "value",
)


@dataclass(frozen=True)
class BenchmarkImportDraft:
    """A reviewable draft, never a submitted job or verified GPS observation."""

    payload: dict[str, Any] = field(repr=False)
    sent_coordinate_reference: dict[str, str] = field(repr=False)
    validation_errors: tuple[str, ...]
    requires_review: bool = field(default=True, init=False)


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate key in benchmark model")
        result[key] = value
    return result


def read_benchmark_model(source: Mapping[str, Any] | str) -> dict[str, str]:
    """Read the 27-key baseline or its complete four-coordinate enrichment.

    ``source`` may be the model itself or a saved record with a JSON-string
    ``model``. The dead form input ``load_description`` is intentionally
    ignored. Unknown fields, partial enrichment and non-string model values
    fail closed so schema drift cannot silently produce an import.
    """
    raw = source.get("model") if isinstance(source, Mapping) and "model" in source else source
    if isinstance(raw, str):
        try:
            raw = json.loads(raw, object_pairs_hook=_unique_json_object)
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON in benchmark model") from None
    if not isinstance(raw, Mapping):
        raise ValueError("Benchmark model must be an object")
    model = {key: value for key, value in raw.items() if key != "load_description"}
    keys = set(model)
    if not set(BASE_MODEL_KEYS).issubset(keys) or keys - set(MODEL_KEYS):
        raise ValueError("Benchmark model keys do not match the documented contract")
    sent_keys = keys.intersection(SENT_COORDINATE_KEYS)
    if sent_keys and sent_keys != set(SENT_COORDINATE_KEYS):
        raise ValueError("Benchmark sent coordinates must contain all four fields")
    if any(not isinstance(value, str) for value in model.values()):
        raise ValueError("Benchmark model values must be strings")
    return dict(model)


def _digits(value: str) -> str:
    return value.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")).strip()


def _mobile(value: str) -> str:
    # The benchmark accepts both forms. BarPro retains its canonical 09 form;
    # invalid text is left invalid instead of deleting arbitrary characters.
    value = _digits(value)
    return f"0{value}" if re.fullmatch(r"9[0-9]{9}", value) else value


def _positive_number(value: str, label: str) -> Decimal:
    try:
        number = Decimal(_digits(value).replace(",", "").replace("٬", ""))
    except InvalidOperation:
        raise ValueError(f"Invalid benchmark {label}") from None
    if not number.is_finite() or number <= 0:
        raise ValueError(f"Invalid benchmark {label}")
    return number


def _coordinates(model: Mapping[str, str], prefix: str) -> dict[str, float]:
    try:
        lat = float(_digits(model[f"{prefix}_lat"]))
        lng = float(_digits(model[f"{prefix}_lng"]))
    except ValueError:
        raise ValueError(f"Invalid benchmark {prefix} coordinates") from None
    if not (math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValueError(f"Invalid benchmark {prefix} coordinates")
    return {"lat": lat, "lng": lng}


def build_benchmark_import_draft(
    source: Mapping[str, Any] | str,
    *,
    origin_province: str,
    destination_province: str,
    weight_unit: Literal["ton", "kg"],
) -> BenchmarkImportDraft:
    """Convert explicit benchmark business values to a BarPro review draft.

    The source model has no provinces and its form does not label the weight
    unit. Both must be supplied explicitly. The caller must still select and
    authorize a BarPro driver, run normal submission validation and enrich any
    fields required by the chosen transport (e.g. mobile postal codes/IDs).
    No driver account, job state, retry, OTP or shipment action is imported.
    """
    if not origin_province.strip() or not destination_province.strip():
        raise ValueError("Both provinces must be supplied explicitly for benchmark import")
    if weight_unit not in {"ton", "kg"}:
        raise ValueError("Benchmark weight unit must be explicitly ton or kg")
    model = read_benchmark_model(source)
    weight = _positive_number(model["load_weight"], "weight")
    if weight_unit == "kg":
        weight /= Decimal(1000)
    count = _positive_number(model["load_count"], "count")
    if count != count.to_integral_value():
        raise ValueError("Benchmark load count must be an integer")

    def party(prefix: str) -> dict[str, str]:
        first = model[f"{prefix}_firstname"].strip()
        last = model[f"{prefix}_lastname"].strip()
        return {
            "first_name": first,
            "last_name": last,
            "name": f"{first} {last}".strip(),
            "national_code": _digits(model[f"{prefix}_national_code"]),
            "phone": _mobile(model[f"{prefix}_mobile"]),
            "entity_type": "individual",
        }

    payload: dict[str, Any] = {
        "sender": party("sender"),
        "receiver": party("receiver"),
        "origin": {
            "province": origin_province.strip(),
            "city": model["source_city"].strip(),
            "address": model["source_address"].strip(),
            "coordinates": _coordinates(model, "source"),
        },
        "destination": {
            "province": destination_province.strip(),
            "city": model["dest_city"].strip(),
            "address": model["dest_address"].strip(),
            "coordinates": _coordinates(model, "dest"),
        },
        "cargo": {
            "type": model["load"].strip(),
            "packaging": model["box"].strip(),
            "weight": format(weight, "f"),
            "count": format(count, "f"),
            "value": format(_positive_number(model["load_price"], "cargo value"), "f"),
        },
        "financial": {"cost": format(_positive_number(model["cost"], "fare"), "f")},
        "vehicle": {
            "driver_national_code": _digits(model["driver_national_code"]),
            "plate": (
                f"{_digits(model['plack_2'])}{model['plack_char'].strip()}"
                f"{_digits(model['plack_3'])}ایران{_digits(model['plack_region'])}"
            ),
        },
    }
    return BenchmarkImportDraft(
        payload=payload,
        sent_coordinate_reference={key: model[key] for key in SENT_COORDINATE_KEYS if key in model},
        validation_errors=tuple(validate_live_waybill_payload(payload)),
    )
