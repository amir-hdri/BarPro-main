import pytest
from pydantic import ValidationError
from unittest.mock import patch

from app.schemas.enterprise_reporting import (
    TelemetryEventSchema,
    WorkflowStepSchema,
    WorkflowStateSchema,
    EvidenceSchema,
    ClientReportSummarySchema,
    ClientReportSchema,
    WorkerHealthSchema,
    BrowserResourceSchema,
    SystemHealthSchema,
    AuditLogEntrySchema,
    create_telemetry_event,
    create_workflow_state,
    create_client_report,
)

# --- TelemetryEventSchema Tests ---

def test_telemetry_event_schema_valid():
    data = {
        "event_id": "uuid-123",
        "event_type": "login_attempt",
        "timestamp": "2023-10-27T10:00:00",
        "status": "success",
        "metadata": {"key": "value"}
    }
    event = TelemetryEventSchema(**data)
    assert event.event_id == "uuid-123"
    assert event.status == "success"

def test_telemetry_event_schema_invalid_timestamp():
    data = {
        "event_id": "uuid-123",
        "event_type": "login_attempt",
        "timestamp": "invalid-timestamp",
        "status": "success"
    }
    with pytest.raises(ValidationError) as excinfo:
        TelemetryEventSchema(**data)
    assert "Timestamp must be valid ISO 8601 format" in str(excinfo.value)

def test_telemetry_event_schema_invalid_status():
    data = {
        "event_id": "uuid-123",
        "event_type": "login_attempt",
        "timestamp": "2023-10-27T10:00:00",
        "status": "invalid-status"
    }
    with pytest.raises(ValidationError) as excinfo:
        TelemetryEventSchema(**data)
    assert "Status must be one of" in str(excinfo.value)

# --- WorkflowStepSchema Tests ---

def test_workflow_step_schema_valid():
    data = {
        "step_name": "Step 1",
        "step_id": "id-1",
        "status": "completed"
    }
    step = WorkflowStepSchema(**data)
    assert step.status == "completed"

def test_workflow_step_schema_invalid_status():
    with pytest.raises(ValidationError):
        WorkflowStepSchema(step_name="Step 1", step_id="id-1", status="invalid")

# --- WorkflowStateSchema Tests ---

def test_workflow_state_schema_valid():
    data = {
        "workflow_id": "wf-1",
        "workflow_name": "My Workflow",
        "status": "in_progress"
    }
    state = WorkflowStateSchema(**data)
    assert state.status == "in_progress"

def test_workflow_state_schema_invalid_status():
    with pytest.raises(ValidationError):
        WorkflowStateSchema(workflow_id="wf-1", workflow_name="My Workflow", status="invalid")

# --- EvidenceSchema Tests ---

def test_evidence_schema_valid():
    data = {
        "evidence_id": "ev-1",
        "evidence_type": "screenshot",
        "timestamp": "2023-10-27T10:00:00",
        "workflow_id": "wf-1",
        "step_name": "Step 1"
    }
    evidence = EvidenceSchema(**data)
    assert evidence.evidence_type == "screenshot"

def test_evidence_schema_invalid_type():
    with pytest.raises(ValidationError):
        EvidenceSchema(
            evidence_id="ev-1", evidence_type="invalid",
            timestamp="2023-10-27T10:00:00", workflow_id="wf-1", step_name="Step 1"
        )

# --- ClientReportSummarySchema Tests ---

def test_client_report_summary_schema_valid():
    data = {
        "message": "All good",
        "severity": "info",
        "total_steps": 5,
        "completed_steps": 5,
        "failed_steps": 0,
        "total_duration_ms": 100.5,
        "avg_step_duration_ms": 20.1
    }
    summary = ClientReportSummarySchema(**data)
    assert summary.severity == "info"

def test_client_report_summary_schema_invalid_severity():
    with pytest.raises(ValidationError):
        ClientReportSummarySchema(
            message="m", severity="bad", total_steps=1,
            completed_steps=1, failed_steps=0,
            total_duration_ms=1.0, avg_step_duration_ms=1.0
        )

# --- ClientReportSchema Tests ---

def test_client_report_schema_valid():
    summary_data = {
        "message": "All good",
        "severity": "info",
        "total_steps": 1,
        "completed_steps": 1,
        "failed_steps": 0,
        "total_duration_ms": 10.0,
        "avg_step_duration_ms": 10.0
    }
    data = {
        "report_id": "rep-1",
        "generated_at": "2023-10-27T10:00:00",
        "overall_status": "success",
        "summary": summary_data
    }
    report = ClientReportSchema(**data)
    assert report.overall_status == "success"

def test_client_report_schema_invalid_status():
    with pytest.raises(ValidationError):
        ClientReportSchema(
            report_id="rep-1", generated_at="2023-10-27T10:00:00", overall_status="invalid",
            summary={"message": "m", "severity": "info", "total_steps": 1, "completed_steps": 1, "failed_steps": 0, "total_duration_ms": 1.0, "avg_step_duration_ms": 1.0}
        )

# --- WorkerHealthSchema Tests ---

def test_worker_health_schema_valid():
    data = {
        "worker_id": "w-1",
        "status": "active"
    }
    health = WorkerHealthSchema(**data)
    assert health.status == "active"

def test_worker_health_schema_invalid_status():
    with pytest.raises(ValidationError):
        WorkerHealthSchema(worker_id="w-1", status="invalid")

# --- BrowserResourceSchema Tests ---

def test_browser_resource_schema_valid():
    data = {
        "resource_id": "res-1",
        "age_seconds": 10.5,
        "idle_seconds": 2.0,
        "pages_open": 1,
        "status": "active"
    }
    res = BrowserResourceSchema(**data)
    assert res.status == "active"

def test_browser_resource_schema_invalid_status():
    with pytest.raises(ValidationError):
        BrowserResourceSchema(resource_id="res-1", age_seconds=1, idle_seconds=1, pages_open=1, status="invalid")

# --- SystemHealthSchema Tests ---

def test_system_health_schema_valid():
    data = {
        "timestamp": "2023-10-27T10:00:00",
        "api_server": True,
        "database": True,
        "browser_pool": True,
        "captcha_solver": True,
        "queue_system": True,
        "overall_status": "healthy"
    }
    health = SystemHealthSchema(**data)
    assert health.overall_status == "healthy"

def test_system_health_schema_invalid_status():
    with pytest.raises(ValidationError):
        SystemHealthSchema(
            timestamp="2023-10-27T10:00:00", api_server=True, database=True,
            browser_pool=True, captcha_solver=True, queue_system=True,
            overall_status="invalid"
        )

# --- AuditLogEntrySchema Tests ---

def test_audit_log_entry_schema_valid():
    data = {
        "timestamp": "2023-10-27T10:00:00",
        "level": "INFO",
        "logger": "app.test",
        "message": "Hello"
    }
    entry = AuditLogEntrySchema(**data)
    assert entry.level == "INFO"

def test_audit_log_entry_schema_invalid_level():
    with pytest.raises(ValidationError):
        AuditLogEntrySchema(timestamp="2023-10-27T10:00:00", level="INVALID", logger="l", message="m")

# --- Helper Functions Tests ---

def test_create_telemetry_event():
    event = create_telemetry_event(
        event_type="test_event",
        status="success",
        metadata={"foo": "bar"}
    )
    assert event["event_type"] == "test_event"
    assert event["status"] == "success"
    assert event["metadata"]["foo"] == "bar"
    assert "event_id" in event
    assert "timestamp" in event
    # Should be valid according to schema
    TelemetryEventSchema(**event)


def test_create_telemetry_event_full_args():
    event = create_telemetry_event(
        event_type="full_test",
        workflow_id="wf-1",
        session_id="sess-1",
        driver_id="drv-1",
        waybill_id="wb-1",
        step_name="step-1",
        duration_ms=150.5,
        status="failure",
        error_code="E001",
        error_message="Test error",
        metadata={"key": "val"}
    )
    assert event["event_type"] == "full_test"
    assert event["workflow_id"] == "wf-1"
    assert event["session_id"] == "sess-1"
    assert event["driver_id"] == "drv-1"
    assert event["waybill_id"] == "wb-1"
    assert event["step_name"] == "step-1"
    assert event["duration_ms"] == 150.5
    assert event["status"] == "failure"
    assert event["error_code"] == "E001"
    assert event["error_message"] == "Test error"
    assert event["metadata"] == {"key": "val"}
    TelemetryEventSchema(**event)

def test_create_telemetry_event_default_metadata():
    event = create_telemetry_event(
        event_type="test_event",
        status="success"
    )
    assert event["metadata"] == {}
    TelemetryEventSchema(**event)

def test_create_telemetry_event_invalid_status():
    with pytest.raises(ValidationError):
        create_telemetry_event(
            event_type="test_event",
            status="invalid_status"
        )

def test_create_telemetry_event_negative_duration():
    with pytest.raises(ValidationError):
        create_telemetry_event(
            event_type="test_event",
            duration_ms=-10.0
        )

def test_create_workflow_state():
    state = create_workflow_state(
        workflow_id="wf-123",
        workflow_name="Test Workflow",
        status="in_progress"
    )
    assert state["workflow_id"] == "wf-123"
    assert state["workflow_name"] == "Test Workflow"
    assert state["status"] == "in_progress"
    assert state["started_at"] is not None
    # Should be valid according to schema
    WorkflowStateSchema(**state)

@patch("app.core.telemetry.ClientReportGenerator.generate_client_report")
def test_create_client_report(mock_generate):
    mock_report = {
        "report_id": "wf-123",
        "generated_at": "2023-10-27T10:00:00",
        "overall_status": "success",
        "summary": {
            "message": "All good",
            "severity": "info",
            "total_steps": 1,
            "completed_steps": 1,
            "failed_steps": 0,
            "total_duration_ms": 10.0,
            "avg_step_duration_ms": 10.0
        },
        "steps": [],
        "evidence_count": 0,
        "evidence": []
    }
    mock_generate.return_value = mock_report

    workflow_state = {"workflow_id": "wf-123", "workflow_name": "Test", "status": "completed"}
    report = create_client_report(workflow_state=workflow_state)

    assert report["report_id"] == "wf-123"
    assert report["overall_status"] == "success"
    mock_generate.assert_called_once()
    # Should be valid according to schema
    ClientReportSchema(**report)
