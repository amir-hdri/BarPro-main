"""Unit tests for multi-route batch expansion and route-selection logic."""

import pytest

from app.models.waybill_batch import WaybillBatch
from app.models.waybill_route_template import WaybillRouteTemplate
from app.models_multitenant import WaybillJob
from app.services.batch_service import build_job_payload, select_route_index


def _route(rid: int) -> WaybillRouteTemplate:
    return WaybillRouteTemplate(
        id=rid,
        client_id=1,
        name=f"route-{rid}",
        origin_address=f"origin-{rid}",
        origin_lat=32.0 + rid,
        origin_lng=51.0,
        dest_address=f"dest-{rid}",
        dest_lat=33.0 + rid,
        dest_lng=52.0,
        distance_km=100.0 + rid,
        duration_min=60.0 + rid,
    )


def test_round_robin_cycles_through_routes():
    indices = [select_route_index(i, 3, "round_robin") for i in range(15)]
    assert indices[:6] == [0, 1, 2, 0, 1, 2]
    assert len(indices) == 15


def test_sequential_sticks_to_last_route():
    assert select_route_index(0, 3, "sequential") == 0
    assert select_route_index(1, 3, "sequential") == 1
    assert select_route_index(2, 3, "sequential") == 2
    assert select_route_index(5, 3, "sequential") == 2


def test_random_always_in_range():
    for _ in range(100):
        assert select_route_index(10, 4, "random") in {0, 1, 2, 3}


def test_select_route_index_rejects_empty():
    with pytest.raises(ValueError):
        select_route_index(0, 0, "round_robin")


def test_build_job_payload_shape():
    route = _route(1)
    payload = build_job_payload(route)
    # origin/destination are now the WaybillMapRequest-style nested dicts the worker expects.
    assert payload["origin"]["address"] == "origin-1"
    assert payload["origin"]["province"] == ""
    assert payload["origin"]["coordinates"] is None
    assert payload["destination"]["address"] == "dest-1"
    assert payload["route_source"] == "user_text"
    assert payload["location_mode"] == "user_text"
    # No base payload → no sender/receiver/cargo injected.
    assert "sender" not in payload


def test_build_job_payload_merges_base_payload():
    route = _route(1)
    base = {
        "sender": {"name": "علی رضایی", "phone": "09120000000"},
        "receiver": {"name": "محمد احمدی"},
        "cargo": {"type": "سیمان", "weight": 100},
    }
    payload = build_job_payload(route, base)
    assert payload["sender"]["name"] == "علی رضایی"
    assert payload["receiver"]["name"] == "محمد احمدی"
    assert payload["cargo"]["type"] == "سیمان"
    # Route overrides origin/destination.
    assert payload["origin"]["address"] == "origin-1"
    assert payload["destination"]["address"] == "dest-1"


def test_models_registered_and_columns_exist():
    assert WaybillRouteTemplate.__tablename__ == "waybill_route_template"
    assert WaybillBatch.__tablename__ == "waybill_batch"
    for col in ("batch_id", "route_template_id", "sequence_index", "distance_km", "duration_min"):
        assert col in WaybillJob.__table__.columns
    assert "base_payload_json" in WaybillBatch.__table__.columns
    assert "idempotency_key" in WaybillBatch.__table__.columns


def test_waybill_job_batch_fk_declared():
    # batch_id / route_template_id must declare FK (matching migration 038).
    referenced_tables = {fk.column.table.name for fk in WaybillJob.__table__.foreign_keys}
    assert "waybill_batch" in referenced_tables
    assert "waybill_route_template" in referenced_tables


def _complete_route(rid: int = 1) -> WaybillRouteTemplate:
    return WaybillRouteTemplate(
        id=rid,
        client_id=1,
        name=f"route-{rid}",
        origin_province="اصفهان",
        origin_city="اصفهان",
        origin_address="خیابان آزادی",
        origin_lat=32.65,
        origin_lng=51.66,
        dest_province="تهران",
        dest_city="تهران",
        dest_address="خیابان انقلاب",
        dest_lat=35.70,
        dest_lng=51.40,
        distance_km=100.0,
        duration_min=60.0,
    )


def _valid_base() -> dict:
    return {
        "sender": {"name": "علی رضایی", "national_code": "1234567891"},
        "receiver": {"name": "محمد احمدی"},
        "cargo": {"type": "سیمان", "packaging": "کیسه", "weight": 100, "value": 1000000},
        "vehicle": {"driver_national_code": "1234567891", "plate": "۱۲۳ع۴۵۶"},
    }


def test_route_location_validation_detects_missing():
    from app.services.batch_service import _validate_route_location

    incomplete = _route(1)  # only address, no province/city
    errs = _validate_route_location(incomplete)
    assert "استان مبدأ" in errs
    assert "شهر مبدأ" in errs
    assert "استان مقصد" in errs

    complete = _complete_route()
    assert _validate_route_location(complete) == []


def test_complete_payload_passes_worker_validation():
    from app.automation.multitenant_payload_adapter import (
        build_enhanced_waybill_payload,
        validate_enhanced_waybill_payload,
    )

    payload = build_job_payload(_complete_route(), _valid_base())
    errors = validate_enhanced_waybill_payload(build_enhanced_waybill_payload(payload))
    assert errors == []


def test_incomplete_base_payload_fails_worker_validation():
    from app.automation.multitenant_payload_adapter import (
        build_enhanced_waybill_payload,
        validate_enhanced_waybill_payload,
    )

    bad_base = {"sender": {"name": "علی"}, "cargo": {"type": "سیمان"}}  # missing many fields
    payload = build_job_payload(_complete_route(), bad_base)
    errors = validate_enhanced_waybill_payload(build_enhanced_waybill_payload(payload))
    assert errors  # non-empty → would be rejected with 422 at batch creation
