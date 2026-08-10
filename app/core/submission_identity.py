"""Canonical waybill submission identity extraction.

Produces the reconciliation/search fields used to verify a submission against
the UTCMS portal. Supports both nested payloads (``vehicle``, ``origin``,
``destination``, ``cargo``) and legacy flat payloads (root-level
``plate_number``, ``origin_city``, ...), and falls back to the Driver row for
the national code when the payload does not carry one.

Kept dependency-free (no FastAPI) so unit tests and the worker/reconciliation
services can import it without pulling in the web stack.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class SubmissionIdentity:
    national_code: str | None = None
    plate_number: str | None = None
    origin_city: str | None = None
    origin_address: str | None = None
    dest_city: str | None = None
    dest_address: str | None = None
    cargo_weight: Any = None
    business_date: str | None = None
    submission_fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "national_code": self.national_code,
            "plate_number": self.plate_number,
            "origin_city": self.origin_city,
            "origin_address": self.origin_address,
            "dest_city": self.dest_city,
            "dest_address": self.dest_address,
            "cargo_weight": self.cargo_weight,
            "business_date": self.business_date,
            "submission_fingerprint": self.submission_fingerprint,
        }


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first(*candidates: Any) -> Any:
    for candidate in candidates:
        if candidate is not None and candidate != "":
            return candidate
    return None


def extract_reconciliation_identity(payload: Any, driver: Any = None) -> SubmissionIdentity:
    """Extract identity/search fields from a job payload for reconciliation.

    ``payload`` may be a dict or a JSON-encoded string. ``driver`` is an
    optional ORM object exposing ``driver_national_code`` (used as a fallback
    when the payload carries no national code).
    """
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            payload = {}
    data = _as_dict(payload)

    vehicle = _as_dict(data.get("vehicle"))
    origin = _as_dict(data.get("origin"))
    destination = _as_dict(data.get("destination"))
    cargo = _as_dict(data.get("cargo"))

    plate_number = _first(
        vehicle.get("plate_number"),
        vehicle.get("driver_plate"),
        data.get("plate_number"),
        data.get("driver_plate"),
    )
    if plate_number is not None:
        plate_number = str(plate_number).strip() or None

    origin_city = _first(
        origin.get("city"),
        origin.get("city_name"),
        data.get("origin_city"),
        (str(data.get("origin")).strip() if isinstance(data.get("origin"), str) else None),
    )
    origin_address = _first(origin.get("address"), data.get("origin_address"))

    dest_city = _first(
        destination.get("city"),
        destination.get("city_name"),
        data.get("dest_city"),
        data.get("destination_city"),
        (str(data.get("destination")).strip() if isinstance(data.get("destination"), str) else None),
    )
    dest_address = _first(destination.get("address"), data.get("dest_address"), data.get("destination_address"))

    cargo_weight = _first(
        cargo.get("weight"),
        cargo.get("cargo_weight"),
        data.get("cargo_weight"),
        data.get("weight"),
    )

    national_code = _first(
        data.get("driver_national_code"),
        data.get("national_code"),
        getattr(driver, "driver_national_code", None) if driver is not None else None,
    )

    return SubmissionIdentity(
        national_code=str(national_code).strip() if national_code is not None else None,
        plate_number=plate_number,
        origin_city=str(origin_city).strip() if origin_city is not None else None,
        origin_address=str(origin_address).strip() if origin_address is not None else None,
        dest_city=str(dest_city).strip() if dest_city is not None else None,
        dest_address=str(dest_address).strip() if dest_address is not None else None,
        cargo_weight=str(cargo_weight).strip() if cargo_weight is not None else None,
        business_date=str(data.get("business_date") or "").strip() or None,
    )


def identity_fields_for_fingerprint(identity: SubmissionIdentity) -> list[str]:
    """Flatten an identity into the ordered fingerprint parts.

    Kept as a single authoring point so ``generate_submission_fingerprint``
    and any future audit hash use exactly the same field order.
    """
    return [
        identity.national_code or "",
        identity.plate_number or "",
        identity.origin_city or "",
        identity.origin_address or "",
        identity.dest_city or "",
        identity.dest_address or "",
        identity.cargo_weight or "",
        identity.business_date or "",
    ]
