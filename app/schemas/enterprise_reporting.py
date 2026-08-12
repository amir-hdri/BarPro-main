"""
Enterprise JSON Schema Definitions for Logging, Reporting & Client Dashboard
=============================================================================
Defines strict schemas for all telemetry, logging, and client-facing reports.
Ensures data consistency across the entire automation platform.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

# ============================================================================
# SCHEMA: TELEMETRY EVENT
# ============================================================================


class TelemetryEventSchema(BaseModel):
    """Schema for individual telemetry events."""

    event_id: str = Field(..., description="Unique event identifier (UUID)")
    event_type: str = Field(..., description="Type of event (e.g., 'login_attempt', 'waybill_submit')")
    timestamp: str = Field(..., description="ISO 8601 timestamp of event")

    # Context identifiers
    workflow_id: str | None = Field(None, description="Workflow execution ID")
    session_id: str | None = Field(None, description="Browser session ID")
    driver_id: str | None = Field(None, description="Driver/worker identifier")
    waybill_id: str | None = Field(None, description="Waybill document ID")

    # Execution context
    step_name: str | None = Field(None, description="Current workflow step name")
    duration_ms: float | None = Field(None, description="Operation duration in milliseconds", ge=0)

    # Result
    status: str = Field(..., description="Event status: success, failure, timeout, skipped, in_progress")
    error_code: str | None = Field(None, description="Structured error code if failed")
    error_message: str | None = Field(None, description="Technical error message")

    # Additional context
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional event-specific data")

    @field_validator("timestamp")
    def validate_timestamp_format(cls, v):
        """Ensure timestamp is valid ISO 8601."""
        try:
            datetime.fromisoformat(v)
        except ValueError:
            raise ValueError("Timestamp must be valid ISO 8601 format") from None
        return v

    @field_validator("status")
    def validate_status(cls, v):
        """Ensure status is valid value."""
        valid_statuses = {"success", "failure", "timeout", "skipped", "in_progress", "retrying"}
        if v not in valid_statuses:
            raise ValueError(f"Status must be one of {valid_statuses}")
        return v


# ============================================================================
# SCHEMA: WORKFLOW STEP STATE
# ============================================================================


class WorkflowStepSchema(BaseModel):
    """Schema for workflow step state tracking."""

    step_name: str = Field(..., description="Human-readable step name")
    step_id: str = Field(..., description="Unique step identifier")
    status: str = Field(..., description="Step status: pending, in_progress, completed, failed, skipped, retrying")

    # Timing
    started_at: str | None = Field(None, description="ISO 8601 start timestamp")
    completed_at: str | None = Field(None, description="ISO 8601 completion timestamp")
    duration_ms: float | None = Field(None, description="Step duration in milliseconds", ge=0)

    # Retry tracking
    attempts: int = Field(default=1, description="Number of attempts made", ge=1)
    max_attempts: int = Field(default=3, description="Maximum allowed attempts", ge=1)

    # Error tracking
    error_code: str | None = Field(None, description="Error code if failed")
    error_message: str | None = Field(None, description="Error message if failed")
    error_category: str | None = Field(None, description="Categorized error type")

    # Additional context
    metadata: dict[str, Any] = Field(default_factory=dict, description="Step-specific metadata")

    @field_validator("status")
    def validate_status(cls, v):
        valid = {"pending", "in_progress", "completed", "failed", "skipped", "retrying"}
        if v not in valid:
            raise ValueError(f"Status must be one of {valid}")
        return v


# ============================================================================
# SCHEMA: WORKFLOW STATE
# ============================================================================


class WorkflowStateSchema(BaseModel):
    """Schema for complete workflow execution state."""

    workflow_id: str = Field(..., description="Unique workflow execution ID")
    workflow_name: str = Field(..., description="Human-readable workflow name")
    status: str = Field(..., description="Overall workflow status")

    # Timing
    started_at: str | None = Field(None, description="ISO 8601 start timestamp")
    completed_at: str | None = Field(None, description="ISO 8601 completion timestamp")
    duration_ms: float | None = Field(None, description="Total workflow duration", ge=0)

    # Execution tracking
    current_step: str | None = Field(None, description="Currently executing step name")
    steps: list[WorkflowStepSchema] = Field(default_factory=list, description="All workflow steps")

    # Error tracking
    error_code: str | None = Field(None, description="Final error code if workflow failed")
    error_message: str | None = Field(None, description="Final error message if failed")

    # Additional context
    metadata: dict[str, Any] = Field(default_factory=dict, description="Workflow-level metadata")

    @field_validator("status")
    def validate_status(cls, v):
        valid = {"pending", "in_progress", "completed", "failed", "skipped"}
        if v not in valid:
            raise ValueError(f"Status must be one of {valid}")
        return v


# ============================================================================
# SCHEMA: EVIDENCE
# ============================================================================


class EvidenceSchema(BaseModel):
    """Schema for failure evidence artifacts."""

    evidence_id: str = Field(..., description="Unique evidence identifier")
    evidence_type: str = Field(
        ..., description="Type: screenshot, html_dump, network_log, console_log, performance_metrics, state_snapshot"
    )
    timestamp: str = Field(..., description="ISO 8601 capture timestamp")
    workflow_id: str = Field(..., description="Associated workflow ID")
    step_name: str = Field(..., description="Step where evidence was captured")

    # File information
    file_path: str | None = Field(None, description="Path to evidence file")
    file_size_bytes: int | None = Field(None, description="File size in bytes", ge=0)

    # Context
    metadata: dict[str, Any] = Field(default_factory=dict, description="Evidence metadata")
    error: str | None = Field(None, description="Error during evidence capture")

    @field_validator("evidence_type")
    def validate_evidence_type(cls, v):
        valid = {"screenshot", "html_dump", "network_log", "console_log", "performance_metrics", "state_snapshot"}
        if v not in valid:
            raise ValueError(f"Evidence type must be one of {valid}")
        return v


# ============================================================================
# SCHEMA: CLIENT-FACING REPORT
# ============================================================================


class ClientReportSummarySchema(BaseModel):
    """Summary section of client-facing report."""

    message: str = Field(..., description="User-friendly status message")
    severity: str = Field(..., description="Severity level: info, warning, error, critical, unknown")
    total_steps: int = Field(..., description="Total number of workflow steps", ge=0)
    completed_steps: int = Field(..., description="Number of completed steps", ge=0)
    failed_steps: int = Field(..., description="Number of failed steps", ge=0)
    total_duration_ms: float = Field(..., description="Total execution time", ge=0)
    avg_step_duration_ms: float = Field(..., description="Average step duration", ge=0)

    @field_validator("severity")
    def validate_severity(cls, v):
        valid = {"info", "warning", "error", "critical", "unknown"}
        if v not in valid:
            raise ValueError(f"Severity must be one of {valid}")
        return v


class ClientStepReportSchema(BaseModel):
    """Step detail in client report."""

    step_name: str = Field(..., description="Step name")
    status: str = Field(..., description="Step status")
    duration_ms: float | None = Field(None, description="Step duration", ge=0)
    attempts: int = Field(default=1, description="Number of attempts", ge=1)
    error_code: str | None = Field(None, description="Error code if failed")
    error_message: str | None = Field(None, description="User-friendly error message")
    severity: str | None = Field(None, description="Error severity")


class ClientErrorDetailsSchema(BaseModel):
    """Error details section in client report."""

    error_code: str | None = Field(None, description="Technical error code")
    technical_message: str = Field(default="", description="Technical error message")
    user_friendly_message: str = Field(..., description="User-friendly explanation")
    severity: str = Field(..., description="Error severity")
    recommended_action: str = Field(..., description="Suggested action for user")


class ClientReportSchema(BaseModel):
    """Complete client-facing report schema."""

    report_id: str = Field(..., description="Report identifier (matches workflow_id)")
    generated_at: str = Field(..., description="ISO 8601 report generation timestamp")
    overall_status: str = Field(..., description="Overall status: success, failed, partial")

    # Summary
    summary: ClientReportSummarySchema = Field(..., description="Report summary")

    # Step details
    steps: list[ClientStepReportSchema] = Field(default_factory=list, description="Step-by-step breakdown")

    # Error information
    error_details: ClientErrorDetailsSchema | None = Field(None, description="Error details if failed")

    # Evidence
    evidence_count: int = Field(default=0, description="Number of evidence artifacts", ge=0)
    evidence: list[EvidenceSchema] = Field(default_factory=list, description="Collected evidence")

    # Telemetry summary
    telemetry_summary: dict[str, Any] | None = Field(None, description="Telemetry statistics")

    @field_validator("overall_status")
    def validate_overall_status(cls, v):
        valid = {"success", "failed", "partial"}
        if v not in valid:
            raise ValueError(f"Overall status must be one of {valid}")
        return v


# ============================================================================
# SCHEMA: DASHBOARD METRICS
# ============================================================================


class DashboardMetricsSchema(BaseModel):
    """Schema for client dashboard metrics."""

    # Overall statistics
    total_requests: int = Field(..., description="Total requests processed", ge=0)
    successful_waybills: int = Field(..., description="Total successful waybills", ge=0)
    failed_attempts: int = Field(..., description="Total failed attempts", ge=0)
    success_rate_percent: float = Field(..., description="Success rate percentage", ge=0, le=100)

    # Performance metrics
    performance: dict[str, float] = Field(
        default_factory=dict, description="Performance statistics (avg, p95, p99 latency)"
    )

    # Trends
    hourly_trend: list[dict[str, Any]] = Field(default_factory=list, description="Hourly performance trend")
    daily_trend: list[dict[str, Any]] = Field(default_factory=list, description="Daily performance trend")

    # Error analysis
    recent_errors: list[dict[str, Any]] = Field(default_factory=list, description="Recent error details")
    error_categories: dict[str, int] = Field(default_factory=dict, description="Errors by category")

    # Map usage
    map_usage_distribution: dict[str, int] = Field(default_factory=dict, description="Map provider usage")

    # Current status
    current_mode_counters: dict[str, dict[str, int]] = Field(
        default_factory=dict, description="Current operation counters"
    )


# ============================================================================
# SCHEMA: WORKER HEALTH
# ============================================================================


class WorkerHealthSchema(BaseModel):
    """Schema for worker/bot health status."""

    worker_id: str = Field(..., description="Worker identifier")
    status: str = Field(..., description="Worker status: active, idle, error, paused")
    current_workflow: str | None = Field(None, description="Currently executing workflow")
    current_step: str | None = Field(None, description="Current workflow step")

    # Performance
    workflows_completed: int = Field(default=0, description="Total workflows completed", ge=0)
    workflows_failed: int = Field(default=0, description="Total workflows failed", ge=0)
    avg_duration_ms: float = Field(default=0, description="Average workflow duration", ge=0)

    # Resource usage
    memory_mb: float | None = Field(None, description="Current memory usage in MB")
    cpu_percent: float | None = Field(None, description="Current CPU usage percentage")

    # Last activity
    last_activity_at: str | None = Field(None, description="ISO 8601 last activity timestamp")
    last_error: str | None = Field(None, description="Last error encountered")

    @field_validator("status")
    def validate_status(cls, v):
        valid = {"active", "idle", "error", "paused", "stopped"}
        if v not in valid:
            raise ValueError(f"Status must be one of {valid}")
        return v


# ============================================================================
# SCHEMA: BROWSER RESOURCE STATUS
# ============================================================================


class BrowserResourceSchema(BaseModel):
    """Schema for browser resource tracking."""

    resource_id: str = Field(..., description="Browser context identifier")
    age_seconds: float = Field(..., description="Time since creation", ge=0)
    idle_seconds: float = Field(..., description="Time since last access", ge=0)
    pages_open: int = Field(..., description="Number of open pages", ge=0)
    status: str = Field(..., description="Resource status: active, idle, stale")

    @field_validator("status")
    def validate_status(cls, v):
        valid = {"active", "idle", "stale"}
        if v not in valid:
            raise ValueError(f"Status must be one of {valid}")
        return v


class BrowserPoolStatsSchema(BaseModel):
    """Schema for browser pool statistics."""

    total_contexts: int = Field(..., description="Total browser contexts", ge=0)
    active_contexts: int = Field(..., description="Currently active contexts", ge=0)
    idle_contexts: int = Field(..., description="Idle contexts available", ge=0)
    pooled_sessions: int = Field(..., description="Pooled session count", ge=0)

    resources: list[BrowserResourceSchema] = Field(default_factory=list, description="Individual resource details")

    # Performance
    avg_creation_time_ms: float = Field(default=0, description="Average context creation time", ge=0)
    total_reuses: int = Field(default=0, description="Total context reuse count", ge=0)

    # Health
    healthy: bool = Field(default=True, description="Pool health status")
    last_cleanup_at: str | None = Field(None, description="Last cleanup timestamp")


# ============================================================================
# SCHEMA: SYSTEM HEALTH
# ============================================================================


class SystemHealthSchema(BaseModel):
    """Complete system health status."""

    timestamp: str = Field(..., description="ISO 8601 health check timestamp")

    # Component health
    api_server: bool = Field(..., description="API server health")
    database: bool = Field(..., description="Database connectivity")
    browser_pool: bool = Field(..., description="Browser pool health")
    captcha_solver: bool = Field(..., description="CAPTCHA solver availability")
    queue_system: bool = Field(..., description="Queue system status")

    # Resource usage
    memory_usage_mb: float | None = Field(None, description="Total memory usage")
    cpu_usage_percent: float | None = Field(None, description="CPU usage percentage")
    disk_usage_percent: float | None = Field(None, description="Disk usage percentage")

    # Active operations
    active_workflows: int = Field(default=0, description="Currently running workflows", ge=0)
    queued_tasks: int = Field(default=0, description="Tasks in queue", ge=0)
    active_browser_contexts: int = Field(default=0, description="Active browser contexts", ge=0)

    # Performance
    requests_per_minute: float = Field(default=0, description="Current request rate", ge=0)
    avg_response_time_ms: float = Field(default=0, description="Average response time", ge=0)
    success_rate_percent: float = Field(default=0, description="Current success rate", ge=0, le=100)

    # Errors
    recent_errors: list[dict[str, Any]] = Field(default_factory=list, description="Recent system errors")

    # Overall status
    overall_status: str = Field(..., description="System status: healthy, degraded, critical")

    @field_validator("overall_status")
    def validate_overall_status(cls, v):
        valid = {"healthy", "degraded", "critical"}
        if v not in valid:
            raise ValueError(f"Overall status must be one of {valid}")
        return v


# ============================================================================
# SCHEMA: AUDIT LOG ENTRY
# ============================================================================


class AuditLogEntrySchema(BaseModel):
    """Schema for audit log entries."""

    timestamp: str = Field(..., description="ISO 8601 event timestamp")
    level: str = Field(..., description="Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL")
    logger: str = Field(..., description="Logger name")
    message: str = Field(..., description="Log message")
    request_id: str | None = Field(None, description="Request identifier")

    # Structured data
    extra: dict[str, Any] | None = Field(None, description="Additional structured data")

    # User context
    user_id: str | None = Field(None, description="User who triggered the action")
    tenant_id: str | None = Field(None, description="Tenant identifier")
    ip_address: str | None = Field(None, description="Client IP address")

    # Action tracking
    action: str | None = Field(None, description="Action performed")
    resource_type: str | None = Field(None, description="Type of resource affected")
    resource_id: str | None = Field(None, description="Identifier of resource affected")

    @field_validator("level")
    def validate_level(cls, v):
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v not in valid:
            raise ValueError(f"Level must be one of {valid}")
        return v


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def create_telemetry_event(
    event_type: str,
    workflow_id: str | None = None,
    session_id: str | None = None,
    driver_id: str | None = None,
    waybill_id: str | None = None,
    step_name: str | None = None,
    duration_ms: float | None = None,
    status: str = "success",
    error_code: str | None = None,
    error_message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Helper to create a validated telemetry event dict."""
    import uuid

    event: dict[str, Any] = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "timestamp": datetime.now(UTC).replace(tzinfo=None).isoformat(),
        "workflow_id": workflow_id,
        "session_id": session_id,
        "driver_id": driver_id,
        "waybill_id": waybill_id,
        "step_name": step_name,
        "duration_ms": duration_ms,
        "status": status,
        "error_code": error_code,
        "error_message": error_message,
        "metadata": metadata or {},
    }

    # Validate against schema
    TelemetryEventSchema(**event)
    return event


def create_workflow_state(
    workflow_id: str,
    workflow_name: str,
    status: str = "pending",
    steps: list[dict[str, Any]] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Helper to create a validated workflow state dict."""
    state: dict[str, Any] = {
        "workflow_id": workflow_id,
        "workflow_name": workflow_name,
        "status": status,
        "started_at": datetime.now(UTC).replace(tzinfo=None).isoformat() if status != "pending" else None,
        "completed_at": None,
        "duration_ms": None,
        "current_step": None,
        "steps": steps or [],
        "error_code": error_code,
        "error_message": error_message,
        "metadata": metadata or {},
    }

    # Validate against schema
    WorkflowStateSchema(**state)
    return state


def create_client_report(
    workflow_state: dict[str, Any],
    telemetry_events: list[dict[str, Any]] | None = None,
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Helper to create a validated client report."""
    from app.core.telemetry import ClientReportGenerator

    report = ClientReportGenerator.generate_client_report(
        workflow_state=workflow_state,
        telemetry_events=telemetry_events,
        evidence=evidence,
    )

    # Validate against schema
    ClientReportSchema(**report)
    return report
