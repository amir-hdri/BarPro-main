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


def _parse_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            payload = {}
    return _as_dict(payload)


def _enhanced_commercial_view(data: dict[str, Any]) -> dict[str, Any]:
    """Return the same normalized commercial view consumed by live RPA.

    Compact frontend payloads keep addresses, parties and some cargo fields in
    ``metadata_json``. Hashing the raw compact object omitted those fields and
    could collapse two different submissions onto one idempotency key. The RPA
    adapter is the canonical authoring point for that compact/nested merge, so
    identity and execution must consume the same view.
    """
    # A partially nested payload is already the most truthful source available.
    # The compact adapter deliberately treats only a complete nested form
    # (identified by sender) as nested; applying it to reconciliation fragments
    # would discard vehicle/origin fields used by workers and tests.
    if any(isinstance(data.get(key), dict) for key in ("vehicle", "origin", "destination", "cargo")):
        return data

    try:
        from app.automation.multitenant_payload_adapter import build_enhanced_waybill_payload

        normalized = build_enhanced_waybill_payload(data)
    except (TypeError, ValueError, KeyError):
        return data
    return normalized if isinstance(normalized, dict) else data


def extract_reconciliation_identity(payload: Any, driver: Any = None) -> SubmissionIdentity:
    """Extract identity/search fields from a job payload for reconciliation.

    ``payload`` may be a dict or a JSON-encoded string. ``driver`` is an
    optional ORM object exposing ``driver_national_code`` (used as a fallback
    when the payload carries no national code).
    """
    data = _parse_payload(payload)
    commercial = _enhanced_commercial_view(data)

    vehicle = _as_dict(commercial.get("vehicle"))
    origin = _as_dict(commercial.get("origin"))
    destination = _as_dict(commercial.get("destination"))
    cargo = _as_dict(commercial.get("cargo"))

    plate_number = _first(
        vehicle.get("plate_number"),
        vehicle.get("plate"),
        vehicle.get("driver_plate"),
        data.get("plate_number"),
        data.get("plate"),
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


def extract_canonical_commercial_payload(payload: Any, driver: Any = None) -> dict[str, Any]:
    """Extracts a normalized, deterministic dictionary of commercial waybill fields.

    Strips volatile metadata (correlation_id, session_id, timestamp, etc.) and
    normalizes plate, textual origin/destination, cargo, parties, and business date.
    """

    data = _parse_payload(payload)
    commercial = _enhanced_commercial_view(data)

    identity = extract_reconciliation_identity(data, driver=driver)

    origin = _as_dict(commercial.get("origin"))
    destination = _as_dict(commercial.get("destination"))
    cargo = _as_dict(commercial.get("cargo"))
    sender = _as_dict(commercial.get("sender"))
    receiver = _as_dict(commercial.get("receiver"))

    return {
        "driver_national_code": identity.national_code or "",
        "plate_number": identity.plate_number or "",
        "origin": {
            "province": str(origin.get("province") or data.get("origin_province") or "").strip(),
            "city": identity.origin_city or "",
            "district": str(origin.get("district") or "").strip(),
            "address": identity.origin_address or "",
        },
        "destination": {
            "province": str(destination.get("province") or data.get("destination_province") or "").strip(),
            "city": identity.dest_city or "",
            "district": str(destination.get("district") or "").strip(),
            "address": identity.dest_address or "",
        },
        "cargo": {
            "cargo_type": str(cargo.get("type") or cargo.get("cargo_type") or data.get("cargo_type") or "").strip(),
            "packaging": str(cargo.get("packaging") or cargo.get("box_type") or data.get("packaging") or "").strip(),
            "weight": str(identity.cargo_weight or "").strip(),
            "value": str(cargo.get("value") or cargo.get("cargo_value") or data.get("cargo_value") or "").strip(),
        },
        "sender": {
            "name": str(sender.get("name") or sender.get("full_name") or data.get("sender_name") or "").strip(),
            "national_code": str(sender.get("national_code") or data.get("sender_national_code") or "").strip(),
        },
        "receiver": {
            "name": str(receiver.get("name") or receiver.get("full_name") or data.get("receiver_name") or "").strip(),
            "national_code": str(receiver.get("national_code") or data.get("receiver_national_code") or "").strip(),
        },
        "business_date": identity.business_date or "",
    }


def compute_canonical_payload_digest(payload: Any, driver: Any = None) -> str:
    """Computes a SHA256 hex digest of the canonical commercial waybill payload."""
    import hashlib

    canonical = extract_canonical_commercial_payload(payload, driver=driver)
    serialized = json.dumps(canonical, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:32]


def compute_canonical_job_idempotency_key(
    client_id: int,
    driver_id: int | None,
    payload: dict[str, Any],
    supplied_key: str | None = None,
) -> str:
    """Computes a collision-resistant, deterministic idempotency key for waybill jobs.

    If supplied_key is provided and non-empty, scopes it by tenant (client_id).
    Otherwise, computes a deterministic hash over tenant, driver, and canonical commercial payload.
    """
    import hashlib

    candidate = str(supplied_key).strip() if supplied_key is not None else None
    if candidate:
        scoped = candidate if candidate.startswith(f"tenant:{client_id}:") else f"tenant:{client_id}:{candidate}"
        if len(scoped) <= 100:
            return scoped
        return hashlib.sha256(scoped.encode("utf-8")).hexdigest()

    canonical = extract_canonical_commercial_payload(payload)
    key_dict = {
        "client_id": client_id,
        "driver_id": driver_id,
        "commercial_payload": canonical,
    }
    serialized = json.dumps(key_dict, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
