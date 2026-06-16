"""Shared event taxonomy helpers for orchestration, workers, and timeline rendering."""

from __future__ import annotations

from typing import Any

JOB_CREATED = "job.created"
JOB_RETRY_REQUESTED = "job.retry_requested_manual"
JOB_DISPATCHED = "job.dispatched_manual"
JOB_DISPATCH_SKIPPED = "job.dispatch_skipped"
JOB_DISPATCH_FAILED = "job.dispatch_failed"
JOB_QUEUED_AUTH = "job.queued_auth"
JOB_QUEUED_SUBMIT = "job.queued_submit"
JOB_EXECUTION_STARTED = "job.execution_started"
JOB_EXECUTION_SUCCEEDED = "job.execution_succeeded"
JOB_EXECUTION_FAILED = "job.execution_failed"
JOB_RETRY_SCHEDULED = "job.retry_scheduled"
OTP_DETECTED = "otp.detected"
AUTH_SUCCEEDED = "auth.succeeded"
AUTH_FAILED = "auth.failed"
SESSION_EXPIRED = "session.expired"
SUBMIT_SUCCEEDED = "submit.succeeded"
SUBMIT_FAILED = "submit.failed"
SUBMIT_DELAYED = "submit.delayed"
DRIVER_LIMIT_REACHED = "driver.limit_reached"


def timeline_phase_for(event_type: str, source: str) -> str:
    normalized = f"{source}:{event_type}".lower()
    if "retry" in normalized:
        return "Retry"
    if "auth" in normalized or "session.expired" in normalized:
        return "Auth"
    if "queued" in normalized or "dispatch" in normalized or "scheduler" in normalized:
        return "Dispatch"
    if "otp" in normalized:
        return "OTP"
    if "failed" in normalized or "exception" in normalized:
        return "Failure"
    if "success" in normalized or "succeeded" in normalized or "complete" in normalized:
        return "Success"
    if "started" in normalized or "execution" in normalized or "submit" in normalized:
        return "Execution"
    return "Trace"


def timeline_title_for(event_type: str, source: str, payload: dict[str, Any] | None = None) -> str:
    labels = {
        JOB_CREATED: "Job created",
        JOB_RETRY_REQUESTED: "Manual retry requested",
        JOB_DISPATCHED: "Immediate dispatch",
        JOB_DISPATCH_SKIPPED: "Dispatch skipped",
        JOB_DISPATCH_FAILED: "Dispatch failed",
        JOB_QUEUED_AUTH: "Queued for authentication",
        JOB_QUEUED_SUBMIT: "Queued for submit",
        JOB_EXECUTION_STARTED: "Execution started",
        JOB_EXECUTION_SUCCEEDED: "Execution succeeded",
        JOB_EXECUTION_FAILED: "Execution failed",
        JOB_RETRY_SCHEDULED: "Retry scheduled",
        OTP_DETECTED: "OTP detected",
        AUTH_SUCCEEDED: "Authentication succeeded",
        AUTH_FAILED: "Authentication failed",
        SESSION_EXPIRED: "Session expired",
        SUBMIT_SUCCEEDED: "Submit succeeded",
        SUBMIT_FAILED: "Submit failed",
        SUBMIT_DELAYED: "Submit delayed",
        DRIVER_LIMIT_REACHED: "Driver limit reached",
    }
    if event_type in labels:
        return labels[event_type]
    if source == "task_log":
        return event_type.replace("_", " ")
    return event_type.replace(".", " -> ")
