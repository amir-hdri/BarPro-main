"""
Test suite to verify Pydantic schema resilience for PostgreSQL JSONB columns.

After the field_validator fix:
- dict inputs pass through as-is
- JSON string inputs are parsed into dicts/lists by _coerce_json_field
- None/empty strings → None
- Plain non-JSON strings → preserved as-is (graceful fallback)
- ORM mapping: FuelInquiryResponse.quota_data reads from quota_data_json via validation_alias
"""

from datetime import datetime

from app.schemas.multitenant import (
    ClientResponse,
    DriverResponse,
    FuelInquiryResponse,
    TaskLogEntry,
    WaybillJobResponse,
    _coerce_json_field,
)
from app.schemas.panel import WaybillResponse

# ==================== Helper function tests ====================


def test_coerce_json_field_helper():
    """Verify generic JSON coercion helper converts correctly."""
    assert _coerce_json_field(None) is None
    assert _coerce_json_field("") is None
    assert _coerce_json_field("   ") is None
    assert _coerce_json_field({"key": "val"}) == {"key": "val"}
    assert _coerce_json_field([1, 2, 3]) == [1, 2, 3]
    assert _coerce_json_field('{"a": 1}') == {"a": 1}
    assert _coerce_json_field('[{"b": 2}]') == [{"b": 2}]
    # Plain text that is not valid JSON is passed through
    assert _coerce_json_field("plain text") == "plain text"


# ==================== WaybillJobResponse ====================


def test_waybill_job_response_dict_payload():
    """Dict inputs are passed through unchanged."""
    base_data = _waybill_job_base()
    job = WaybillJobResponse(**base_data, payload_json={"national_code": "1234567890"}, result_json={"tracking": "OK"})
    assert job.payload_json == {"national_code": "1234567890"}
    assert job.result_json == {"tracking": "OK"}


def test_waybill_job_response_json_string_payload_parsed():
    """JSON string inputs from DB must be parsed to dicts by the validator."""
    base_data = _waybill_job_base()
    job = WaybillJobResponse(
        **base_data,
        payload_json='{"national_code": "1234567890"}',
        result_json='{"status": "ok"}',
    )
    # After fix: validator parses JSON strings → dicts
    assert job.payload_json == {"national_code": "1234567890"}
    assert job.result_json == {"status": "ok"}


def test_waybill_job_response_none_payload():
    """None inputs remain None."""
    base_data = _waybill_job_base()
    job = WaybillJobResponse(**base_data, payload_json=None, result_json=None)
    assert job.payload_json is None
    assert job.result_json is None


def test_waybill_job_response_multiroute_fields_from_orm():
    """Migration-038 columns must survive ORM → response serialization.

    Regression: the frontend batches progress dashboard and history filters
    read batch_id / route_template_id / sequence_index / distance_km /
    duration_min / submission_fingerprint; the Pydantic schema used to strip
    them silently (always undefined client-side).
    """
    from app.models_multitenant import WaybillJob

    orm_job = WaybillJob(
        id=501,
        job_id="job-mr-1",
        idempotency_key="idem-mr-1",
        client_id=1,
        status="pending",
        payload_json={},
        batch_id=77,
        route_template_id=12,
        sequence_index=3,
        distance_km=412.5,
        duration_min=330.0,
        submission_fingerprint="fp-abc123",
    )
    resp = WaybillJobResponse.model_validate(orm_job)
    assert resp.batch_id == 77
    assert resp.route_template_id == 12
    assert resp.sequence_index == 3
    assert resp.distance_km == 412.5
    assert resp.duration_min == 330.0
    assert resp.submission_fingerprint == "fp-abc123"

    # Defaults stay optional for legacy jobs without batch linkage
    legacy = WaybillJobResponse(**_waybill_job_base())
    assert legacy.batch_id is None
    assert legacy.submission_fingerprint is None


# ==================== ClientResponse ====================


def test_client_response_dict_metadata():
    """Dict metadata_json passes through."""
    c = ClientResponse(**_client_data(metadata_json={"tier": "gold"}))
    assert c.metadata_json == {"tier": "gold"}


def test_client_response_json_string_metadata_parsed():
    """JSON string metadata_json from DB must be parsed."""
    c = ClientResponse(**_client_data(metadata_json='{"tier": "gold"}'))
    assert c.metadata_json == {"tier": "gold"}


def test_client_response_none_metadata():
    """None metadata_json stays None."""
    c = ClientResponse(**_client_data(metadata_json=None))
    assert c.metadata_json is None


# ==================== DriverResponse ====================


def test_driver_response_dict_fields():
    """Dict JSONB fields are passed through unchanged."""
    d = DriverResponse(**_driver_data(default_payload_json={"vehicle_type": "truck"}, metadata_json={"notes": "VIP"}))
    assert d.default_payload_json == {"vehicle_type": "truck"}
    assert d.metadata_json == {"notes": "VIP"}


def test_driver_response_json_string_parsed():
    """JSON strings for JSONB driver fields must be parsed by the validator."""
    d = DriverResponse(
        **_driver_data(
            default_payload_json='{"vehicle_type": "truck"}',
            metadata_json='{"notes": "VIP"}',
        )
    )
    # After fix: strings are parsed to dicts
    assert d.default_payload_json == {"vehicle_type": "truck"}
    assert d.metadata_json == {"notes": "VIP"}


# ==================== TaskLogEntry ====================


def test_task_log_entry_dict():
    """Dict details_json passes through."""
    entry = TaskLogEntry(**_log_data(details_json={"captcha_retries": 1}))
    assert entry.details_json == {"captcha_retries": 1}


def test_task_log_entry_json_string_parsed():
    """JSON string details_json from DB must be parsed."""
    entry = TaskLogEntry(**_log_data(details_json='{"captcha_retries": 2}'))
    assert entry.details_json == {"captcha_retries": 2}


def test_task_log_entry_list():
    """List details_json passes through."""
    entry = TaskLogEntry(**_log_data(details_json=[{"step": "login"}]))
    assert entry.details_json == [{"step": "login"}]


# ==================== FuelInquiryResponse ====================


def test_fuel_inquiry_response_dict_via_alias():
    """
    quota_data reads from quota_data_json via validation_alias.
    ORM simulation: pass quota_data_json (the actual column name) as a kwarg.
    """
    fi = FuelInquiryResponse(**_fuel_data(quota_data_json={"liters": 500}))
    assert fi.quota_data == {"liters": 500}


def test_fuel_inquiry_response_json_string_parsed():
    """JSON string from ORM is parsed by validator."""
    fi = FuelInquiryResponse(**_fuel_data(quota_data_json='{"liters": 500}'))
    assert fi.quota_data == {"liters": 500}


def test_fuel_inquiry_response_none():
    """None quota_data_json stays None."""
    fi = FuelInquiryResponse(**_fuel_data(quota_data_json=None))
    assert fi.quota_data is None


# ==================== Panel WaybillResponse ====================


def test_waybill_panel_response_dict():
    """Dict JSONB fields pass through in Panel schema."""
    w = WaybillResponse(**_panel_data(payload_json={"origin": "Tehran"}, result_json={"waybill_no": "998877"}))
    assert w.payload_json == {"origin": "Tehran"}
    assert w.result_json == {"waybill_no": "998877"}


def test_waybill_panel_response_json_string_parsed():
    """JSON strings in Panel schema must be parsed by the validator."""
    w = WaybillResponse(
        **_panel_data(
            payload_json='{"origin": "Tehran"}',
            result_json='{"waybill_no": "998877"}',
        )
    )
    assert w.payload_json == {"origin": "Tehran"}
    assert w.result_json == {"waybill_no": "998877"}


def test_waybill_panel_response_none():
    """None JSONB fields stay None in Panel schema."""
    w = WaybillResponse(**_panel_data(payload_json=None, result_json=None))
    assert w.payload_json is None
    assert w.result_json is None


# ==================== Private helpers ====================


def _waybill_job_base() -> dict:
    return {
        "id": 1,
        "job_id": "test-job-uuid",
        "client_id": 1,
        "driver_id": 10,
        "status": "pending",
        "source": "web",
        "correlation_id": None,
        "business_date": "1403/05/10",
        "priority": 5,
        "last_error": None,
        "error_category": None,
        "next_retry_at": None,
        "submit_after": None,
        "terminal_reason": None,
        "attempt_count": 0,
        "max_retries": 3,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
        "started_at": None,
        "finished_at": None,
    }


def _client_data(**overrides) -> dict:
    base = {
        "id": 1,
        "client_code": "CLI-01",
        "name": "Test Client",
        "email": "test@example.com",
        "phone": "09123456789",
        "status": "active",
        "access_level": "standard",
        "max_drivers": 10,
        "max_plates": 20,
        "max_concurrent_tasks": 3,
        "max_daily_tasks": 100,
        "created_at": datetime.now(),
        "last_login_at": None,
    }
    base.update(overrides)
    return base


def _driver_data(**overrides) -> dict:
    base = {
        "id": 5,
        "client_id": 1,
        "driver_national_code": "0012345678",
        "full_name": "Ali Alavi",
        "phone": "09120000000",
        "license_number": "123456",
        "utcms_username": "driver_user",
        "status": "active",
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }
    base.update(overrides)
    return base


def _log_data(**overrides) -> dict:
    base = {
        "id": 100,
        "job_id": "job-123",
        "step": "login",
        "status": "success",
        "message": "Captcha solved",
        "created_at": datetime.now(),
    }
    base.update(overrides)
    return base


def _fuel_data(**overrides) -> dict:
    base = {
        "id": 10,
        "client_id": 1,
        "driver_id": 5,
        "status": "completed",
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }
    base.update(overrides)
    return base


def _panel_data(**overrides) -> dict:
    base = {
        "id": 20,
        "job_id": "job-panel-1",
        "client_id": 1,
        "driver_id": 5,
        "status": "success",
        "scheduled_by": "auto",
        "created_at": datetime.now(),
    }
    base.update(overrides)
    return base
