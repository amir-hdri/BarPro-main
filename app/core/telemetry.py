"""
Enterprise-Grade Telemetry, Structured Logging & Evidence Collection System
===========================================================================
Provides comprehensive observability with JSON structured logging,
automatic evidence collection on failure, and client-facing reporting.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from playwright.async_api import Page

logger = logging.getLogger(__name__)

# ============================================================================
# EVIDENCE COLLECTOR
# ============================================================================


class EvidenceType(StrEnum):
    """Types of evidence that can be collected."""

    SCREENSHOT = "screenshot"
    HTML_DUMP = "html_dump"
    NETWORK_LOG = "network_log"
    CONSOLE_LOG = "console_log"
    PERFORMANCE_METRICS = "performance_metrics"
    STATE_SNAPSHOT = "state_snapshot"


@dataclass
class Evidence:
    """Represents a single piece of collected evidence."""

    evidence_id: str
    evidence_type: EvidenceType
    timestamp: str
    workflow_id: str
    step_name: str
    file_path: str | None = None
    file_size_bytes: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "evidence_type": self.evidence_type.value,
            "timestamp": self.timestamp,
            "workflow_id": self.workflow_id,
            "step_name": self.step_name,
            "file_path": self.file_path,
            "file_size_bytes": self.file_size_bytes,
            "metadata": self.metadata,
            "error": self.error,
        }


class EvidenceCollector:
    """
    Automatically captures evidence on failure for debugging.
    Stores screenshots, HTML dumps, and metadata in organized structure.
    """

    def __init__(
        self,
        base_dir: str = "evidence",
        max_evidence_per_workflow: int = 10,
        retention_days: int = 7,
        auto_cleanup: bool = True,
    ):
        self.base_dir = Path(base_dir)
        self.max_evidence_per_workflow = max_evidence_per_workflow
        self.retention_days = retention_days
        self.auto_cleanup = auto_cleanup
        self._evidence_log: list[Evidence] = []
        self._workflow_counts: dict[str, int] = {}

        # Create base directory
        self.base_dir.mkdir(parents=True, exist_ok=True)
        (self.base_dir / "screenshots").mkdir(exist_ok=True)
        (self.base_dir / "html_dumps").mkdir(exist_ok=True)
        (self.base_dir / "metadata").mkdir(exist_ok=True)

    async def capture_failure_evidence(
        self,
        page: Page,
        workflow_id: str,
        step_name: str,
        error_code: str,
        error_message: str,
    ) -> list[Evidence]:
        """
        Capture comprehensive evidence when a step fails.

        Args:
            page: Playwright page instance
            workflow_id: Current workflow identifier
            step_name: Name of the failed step
            error_code: Structured error code
            error_message: Human-readable error message

        Returns:
            List of captured evidence objects
        """
        evidence_list = []
        timestamp = datetime.now(UTC).replace(tzinfo=None).strftime("%Y%m%d_%H%M%S")

        # Check evidence limit
        current_count = self._workflow_counts.get(workflow_id, 0)
        if current_count >= self.max_evidence_per_workflow:
            logging.warning(
                "evidence_limit_reached",
                extra={
                    "extra_fields": {
                        "workflow_id": workflow_id,
                        "count": current_count,
                        "max": self.max_evidence_per_workflow,
                    }
                },
            )
            return evidence_list

        # 1. Capture full-page screenshot
        screenshot_evidence = await self._capture_screenshot(page, workflow_id, step_name, timestamp, error_code)
        if screenshot_evidence:
            evidence_list.append(screenshot_evidence)

        # 2. Capture HTML DOM dump
        html_evidence = await self._capture_html_dump(page, workflow_id, step_name, timestamp, error_code)
        if html_evidence:
            evidence_list.append(html_evidence)

        # 3. Capture console logs
        console_evidence = await self._capture_console_logs(page, workflow_id, step_name, timestamp, error_code)
        if console_evidence:
            evidence_list.append(console_evidence)

        # 4. Capture page metadata
        metadata_evidence = await self._capture_metadata(
            page, workflow_id, step_name, timestamp, error_code, error_message
        )
        if metadata_evidence:
            evidence_list.append(metadata_evidence)

        # Update workflow count
        self._workflow_counts[workflow_id] = current_count + len(evidence_list)

        # Log evidence collection
        if evidence_list:
            logging.info(
                "evidence_collected",
                extra={
                    "extra_fields": {
                        "workflow_id": workflow_id,
                        "step_name": step_name,
                        "evidence_count": len(evidence_list),
                        "error_code": error_code,
                    }
                },
            )

        self._evidence_log.extend(evidence_list)
        return evidence_list

    async def _capture_screenshot(
        self,
        page: Page,
        workflow_id: str,
        step_name: str,
        timestamp: str,
        error_code: str,
    ) -> Evidence | None:
        """Capture full-page screenshot."""
        try:
            filename = f"{workflow_id}_{step_name}_{timestamp}.png"
            file_path = self.base_dir / "screenshots" / filename

            await page.screenshot(
                path=str(file_path),
                full_page=True,
                type="png",
            )

            file_size = file_path.stat().st_size if file_path.exists() else None

            return Evidence(
                evidence_id=f"screenshot_{workflow_id}_{timestamp}",
                evidence_type=EvidenceType.SCREENSHOT,
                timestamp=timestamp,
                workflow_id=workflow_id,
                step_name=step_name,
                file_path=str(file_path),
                file_size_bytes=file_size,
                metadata={
                    "url": await page.url(),
                    "title": await page.title(),
                    "error_code": error_code,
                },
            )

        except Exception as e:
            logging.warning("screenshot_capture_failed", extra={"extra_fields": {"error": str(e)}})
            return None

    async def _capture_html_dump(
        self,
        page: Page,
        workflow_id: str,
        step_name: str,
        timestamp: str,
        error_code: str,
    ) -> Evidence | None:
        """Capture full HTML DOM."""
        try:
            filename = f"{workflow_id}_{step_name}_{timestamp}.html"
            file_path = self.base_dir / "html_dumps" / filename

            html_content = await page.content()

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            file_size = file_path.stat().st_size if file_path.exists() else None

            return Evidence(
                evidence_id=f"html_{workflow_id}_{timestamp}",
                evidence_type=EvidenceType.HTML_DUMP,
                timestamp=timestamp,
                workflow_id=workflow_id,
                step_name=step_name,
                file_path=str(file_path),
                file_size_bytes=file_size,
                metadata={
                    "url": await page.url(),
                    "title": await page.title(),
                    "error_code": error_code,
                    "html_length": len(html_content),
                },
            )

        except Exception as e:
            logging.warning("html_dump_capture_failed", extra={"extra_fields": {"error": str(e)}})
            return None

    async def _capture_console_logs(
        self,
        page: Page,
        workflow_id: str,
        step_name: str,
        timestamp: str,
        error_code: str,
    ) -> Evidence | None:
        """Capture console logs from page."""
        try:
            filename = f"{workflow_id}_{step_name}_{timestamp}_console.json"
            file_path = self.base_dir / "metadata" / filename

            # Evaluate to get recent console errors
            console_logs = await page.evaluate(
                """
                () => {
                    // This captures any stored console messages
                    // In production, you'd set up a listener earlier
                    return {
                        timestamp: new Date().toISOString(),
                        url: window.location.href,
                        note: "Console capture requires prior listener setup"
                    };
                }
            """
            )

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(console_logs, f, indent=2, ensure_ascii=False)

            return Evidence(
                evidence_id=f"console_{workflow_id}_{timestamp}",
                evidence_type=EvidenceType.CONSOLE_LOG,
                timestamp=timestamp,
                workflow_id=workflow_id,
                step_name=step_name,
                file_path=str(file_path),
                metadata={
                    "error_code": error_code,
                },
            )

        except Exception:
            return None

    async def _capture_metadata(
        self,
        page: Page,
        workflow_id: str,
        step_name: str,
        timestamp: str,
        error_code: str,
        error_message: str,
    ) -> Evidence | None:
        """Capture page metadata as evidence."""
        try:
            filename = f"{workflow_id}_{step_name}_{timestamp}_meta.json"
            file_path = self.base_dir / "metadata" / filename

            metadata = {
                "url": await page.url(),
                "title": await page.title(),
                "timestamp": timestamp,
                "workflow_id": workflow_id,
                "step_name": step_name,
                "error_code": error_code,
                "error_message": error_message,
                "user_agent": await page.evaluate("navigator.userAgent"),
                "viewport": await page.evaluate(
                    """
                    () => ({
                        width: window.innerWidth,
                        height: window.innerHeight,
                        devicePixelRatio: window.devicePixelRatio
                    })
                """
                ),
                "cookies_count": len(await page.context.cookies()),
                "local_storage_size": await page.evaluate(
                    """
                    () => {
                        let total = 0;
                        for (let key in localStorage) {
                            if (localStorage.hasOwnProperty(key)) {
                                total += localStorage[key].length + key.length;
                            }
                        }
                        return total;
                    }
                """
                ),
            }

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            file_size = file_path.stat().st_size if file_path.exists() else None

            return Evidence(
                evidence_id=f"metadata_{workflow_id}_{timestamp}",
                evidence_type=EvidenceType.STATE_SNAPSHOT,
                timestamp=timestamp,
                workflow_id=workflow_id,
                step_name=step_name,
                file_path=str(file_path),
                file_size_bytes=file_size,
                metadata=metadata,
            )

        except Exception:
            return None

    def cleanup_old_evidence(self) -> int:
        """Remove evidence older than retention period."""
        if not self.auto_cleanup:
            return 0

        cleaned = 0
        cutoff_time = time.time() - (self.retention_days * 86400)

        for subdir in ["screenshots", "html_dumps", "metadata"]:
            dir_path = self.base_dir / subdir
            if not dir_path.exists():
                continue

            for file_path in dir_path.iterdir():
                if file_path.stat().st_mtime < cutoff_time:
                    try:
                        file_path.unlink()
                        cleaned += 1
                    except Exception:
                        logger.warning("evidence_cleanup_file_unlink_failed", exc_info=True)

        return cleaned

    def get_evidence_for_workflow(self, workflow_id: str) -> list[dict[str, Any]]:
        """Get all evidence for a specific workflow."""
        return [e.to_dict() for e in self._evidence_log if e.workflow_id == workflow_id]

    def get_storage_usage(self) -> dict[str, Any]:
        """Get evidence storage usage statistics."""
        total_size = 0
        file_count = 0

        for subdir in ["screenshots", "html_dumps", "metadata"]:
            dir_path = self.base_dir / subdir
            if dir_path.exists():
                for file_path in dir_path.iterdir():
                    total_size += file_path.stat().st_size
                    file_count += 1

        return {
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "file_count": file_count,
            "base_dir": str(self.base_dir),
            "workflows_tracked": len(self._workflow_counts),
        }


# ============================================================================
# ADVANCED STRUCTURED LOGGER
# ============================================================================


class TelemetryLevel(StrEnum):
    """Telemetry detail levels."""

    MINIMAL = "minimal"
    STANDARD = "standard"
    DETAILED = "detailed"
    DEBUG = "debug"


@dataclass
class TelemetryEvent:
    """Represents a single telemetry event."""

    event_id: str
    event_type: str
    timestamp: str
    workflow_id: str | None = None
    session_id: str | None = None
    driver_id: str | None = None
    waybill_id: str | None = None
    step_name: str | None = None
    duration_ms: float | None = None
    status: str = "success"
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "workflow_id": self.workflow_id,
            "session_id": self.session_id,
            "driver_id": self.driver_id,
            "waybill_id": self.waybill_id,
            "step_name": self.step_name,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }


class TelemetryCollector:
    """
    Collects and manages comprehensive telemetry data.
    Provides structured logging and client-facing reports.
    """

    def __init__(
        self,
        telemetry_level: TelemetryLevel = TelemetryLevel.DETAILED,
        max_events_buffer: int = 10000,
        flush_interval_seconds: float = 60.0,
    ):
        self.telemetry_level = telemetry_level
        self.max_events_buffer = max_events_buffer
        self.flush_interval_seconds = flush_interval_seconds
        self._events: list[TelemetryEvent] = []
        self._workflow_sessions: dict[str, list[TelemetryEvent]] = {}
        self._lock = asyncio.Lock()
        self._last_flush = time.time()

    async def record_event(
        self,
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
    ) -> TelemetryEvent:
        """
        Record a telemetry event.

        Args:
            event_type: Type of event (e.g., 'login_attempt', 'waybill_submit')
            workflow_id: Workflow identifier
            session_id: Browser session identifier
            driver_id: Driver/worker identifier
            waybill_id: Waybill identifier
            step_name: Current workflow step
            duration_ms: Operation duration in milliseconds
            status: Event status ('success', 'failure', 'timeout', etc.)
            error_code: Structured error code if failed
            error_message: Human-readable error message
            metadata: Additional context data

        Returns:
            Created telemetry event
        """
        import uuid

        event = TelemetryEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            timestamp=datetime.now(UTC).replace(tzinfo=None).isoformat(),
            workflow_id=workflow_id,
            session_id=session_id,
            driver_id=driver_id,
            waybill_id=waybill_id,
            step_name=step_name,
            duration_ms=duration_ms,
            status=status,
            error_code=error_code,
            error_message=error_message,
            metadata=metadata or {},
        )

        async with self._lock:
            self._events.append(event)

            # Index by workflow
            if workflow_id:
                if workflow_id not in self._workflow_sessions:
                    self._workflow_sessions[workflow_id] = []
                self._workflow_sessions[workflow_id].append(event)

            # Auto-flush if buffer is full
            if len(self._events) >= self.max_events_buffer:
                await self._flush_old_events()

        # Log event at appropriate level
        if status == "failure" and error_code:
            logging.error(
                "telemetry_failure",
                extra={
                    "extra_fields": {
                        "event_type": event_type,
                        "workflow_id": workflow_id,
                        "error_code": error_code,
                        "error_message": error_message,
                    }
                },
            )
        elif self.telemetry_level == TelemetryLevel.DEBUG:
            logging.debug(
                "telemetry_event",
                extra={
                    "extra_fields": {
                        "event_type": event_type,
                        "status": status,
                        "duration_ms": duration_ms,
                    }
                },
            )

        return event

    async def record_step_start(
        self,
        workflow_id: str,
        step_name: str,
        session_id: str | None = None,
        driver_id: str | None = None,
    ) -> TelemetryEvent:
        """Record the start of a workflow step."""
        return await self.record_event(
            event_type="step_start",
            workflow_id=workflow_id,
            session_id=session_id,
            driver_id=driver_id,
            step_name=step_name,
            status="in_progress",
            metadata={"action": "step_started"},
        )

    async def record_step_complete(
        self,
        workflow_id: str,
        step_name: str,
        duration_ms: float,
        session_id: str | None = None,
        driver_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TelemetryEvent:
        """Record successful completion of a workflow step."""
        return await self.record_event(
            event_type="step_complete",
            workflow_id=workflow_id,
            session_id=session_id,
            driver_id=driver_id,
            step_name=step_name,
            duration_ms=duration_ms,
            status="success",
            metadata=metadata or {},
        )

    async def record_step_failure(
        self,
        workflow_id: str,
        step_name: str,
        error_code: str,
        error_message: str,
        duration_ms: float | None = None,
        session_id: str | None = None,
        driver_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TelemetryEvent:
        """Record failure of a workflow step."""
        return await self.record_event(
            event_type="step_failure",
            workflow_id=workflow_id,
            session_id=session_id,
            driver_id=driver_id,
            step_name=step_name,
            duration_ms=duration_ms,
            status="failure",
            error_code=error_code,
            error_message=error_message,
            metadata=metadata or {},
        )

    async def get_workflow_telemetry(self, workflow_id: str) -> list[dict[str, Any]]:
        """Get all telemetry events for a workflow."""
        async with self._lock:
            events = self._workflow_sessions.get(workflow_id, [])
            return [e.to_dict() for e in events]

    async def get_performance_summary(self) -> dict[str, Any]:
        """Get performance summary from recent telemetry."""
        async with self._lock:
            recent_events = self._events[-1000:]

        successful = [e for e in recent_events if e.status == "success" and e.duration_ms]
        failed = [e for e in recent_events if e.status == "failure"]

        durations = [e.duration_ms for e in successful if e.duration_ms]

        return {
            "total_events": len(recent_events),
            "successful_events": len(successful),
            "failed_events": len(failed),
            "success_rate": round(len(successful) / max(1, len(recent_events)) * 100, 2),
            "avg_duration_ms": round(sum(durations) / len(durations), 2) if durations else 0,
            "min_duration_ms": round(min(durations), 2) if durations else 0,
            "max_duration_ms": round(max(durations), 2) if durations else 0,
            "events_by_type": self._count_by_type(recent_events),
            "errors_by_code": self._count_by_error_code(failed),
        }

    async def flush(self) -> int:
        """Flush all buffered events (for persistence or export)."""
        async with self._lock:
            count = len(self._events)
            self._events.clear()
            self._workflow_sessions.clear()
            self._last_flush = time.time()
            return count

    async def _flush_old_events(self) -> None:
        """Remove oldest events if buffer is full."""
        # Keep only the most recent events
        if len(self._events) > self.max_events_buffer:
            self._events = self._events[-self.max_events_buffer :]

    @staticmethod
    def _count_by_type(events: list[TelemetryEvent]) -> dict[str, int]:
        counts = {}
        for event in events:
            counts[event.event_type] = counts.get(event.event_type, 0) + 1
        return counts

    @staticmethod
    def _count_by_error_code(events: list[TelemetryEvent]) -> dict[str, int]:
        counts = {}
        for event in events:
            if event.error_code:
                counts[event.error_code] = counts.get(event.error_code, 0) + 1
        return counts


# ============================================================================
# CLIENT-FACING REPORT GENERATOR
# ============================================================================


class ClientReportGenerator:
    """
    Generates client-facing reports with user-friendly language
    and detailed technical information for debugging.
    """

    # User-friendly error messages
    FRIENDLY_ERROR_MESSAGES = {
        "AUTH_INVALID_CREDENTIALS": "Invalid username or password. Please check your credentials.",
        "AUTH_SESSION_EXPIRED": "Your session has expired. Please log in again.",
        "AUTH_CAPTCHA_FAILED": "CAPTCHA verification failed. Please try again.",
        "CAPTCHA_MAX_RETRY": "CAPTCHA verification failed too many times. Please wait and try again later.",
        "NET_TIMEOUT": "The portal is not responding. This may be due to network issues or portal maintenance.",
        "NET_CONNECTION_REFUSED": "Unable to connect to the portal. The service may be temporarily unavailable.",
        "BR_NAVIGATION_TIMEOUT": "The portal is taking too long to load. Please try again later.",
        "ELEMENT_NOT_FOUND": "The portal interface has changed. Please contact support.",
        "WAYBILL_FORM_CHANGED": "The waybill form structure has changed. Please contact support.",
        "WAYBILL_SUBMISSION_FAILED": "Waybill submission failed. Please review your data and try again.",
        "MAP_LOADING_TIMEOUT": "Map service is not responding. Please try again later.",
        "MAP_INTERACTION_FAILED": "Unable to interact with map. Please try manual selection.",
        "PORTAL_DOWN": "The UTCMS portal is currently unavailable. Please try again later.",
        "PORTAL_MAINTENANCE": "The portal is under maintenance. Please try again later.",
        "RATE_LIMITED": "Too many requests. Please wait before trying again.",
        "PERMISSION_DENIED": "Your account does not have permission for this action.",
    }

    # Severity levels for client display
    ERROR_SEVERITY = {
        "AUTH_INVALID_CREDENTIALS": "warning",
        "AUTH_SESSION_EXPIRED": "info",
        "AUTH_CAPTCHA_FAILED": "warning",
        "CAPTCHA_MAX_RETRY": "error",
        "NET_TIMEOUT": "warning",
        "NET_CONNECTION_REFUSED": "error",
        "BR_NAVIGATION_TIMEOUT": "warning",
        "ELEMENT_NOT_FOUND": "critical",
        "WAYBILL_FORM_CHANGED": "critical",
        "WAYBILL_SUBMISSION_FAILED": "error",
        "MAP_LOADING_TIMEOUT": "warning",
        "MAP_INTERACTION_FAILED": "error",
        "PORTAL_DOWN": "critical",
        "PORTAL_MAINTENANCE": "info",
        "RATE_LIMITED": "warning",
        "PERMISSION_DENIED": "error",
    }

    @classmethod
    def generate_client_report(
        cls,
        workflow_state: dict[str, Any],
        telemetry_events: list[dict[str, Any]] | None = None,
        evidence: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Generate a comprehensive client-facing report.

        Args:
            workflow_state: Workflow execution state
            telemetry_events: Optional telemetry data
            evidence: Optional evidence collected

        Returns:
            Client-friendly report dictionary
        """
        # Determine overall status
        status = workflow_state.get("status", "unknown")
        is_success = status == "completed"

        # Get error information
        error_code = workflow_state.get("error_code")
        error_message = workflow_state.get("error_message", "")

        # Generate user-friendly message
        friendly_message = cls._get_friendly_message(error_code, error_message, is_success)
        severity = cls.ERROR_SEVERITY.get(error_code, "unknown") if error_code else "info"

        # Build step-by-step breakdown
        steps = []
        for step in workflow_state.get("steps", []):
            step_status = step.get("status", "unknown")
            step_error = step.get("error_code")

            steps.append(
                {
                    "step_name": step.get("step_name", "Unknown Step"),
                    "status": step_status,
                    "duration_ms": step.get("duration_ms"),
                    "attempts": step.get("attempts", 1),
                    "error_code": step_error,
                    "error_message": (
                        cls._get_friendly_message(step_error, step.get("error_message"), step_status == "completed")
                        if step_error
                        else None
                    ),
                    "severity": cls.ERROR_SEVERITY.get(step_error, "unknown") if step_error else None,
                }
            )

        # Calculate performance metrics
        completed_steps = [s for s in steps if s["status"] == "completed"]
        total_duration = sum(s["duration_ms"] or 0 for s in completed_steps)
        avg_duration = total_duration / len(completed_steps) if completed_steps else 0

        # Build report
        report = {
            "report_id": workflow_state.get("workflow_id", "unknown"),
            "generated_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
            "overall_status": "success" if is_success else "failed",
            "summary": {
                "message": friendly_message,
                "severity": severity,
                "total_steps": len(steps),
                "completed_steps": len(completed_steps),
                "failed_steps": len([s for s in steps if s["status"] == "failed"]),
                "total_duration_ms": round(total_duration, 2),
                "avg_step_duration_ms": round(avg_duration, 2),
            },
            "steps": steps,
            "error_details": (
                {
                    "error_code": error_code,
                    "technical_message": error_message,
                    "user_friendly_message": friendly_message,
                    "severity": severity,
                    "recommended_action": cls._get_recommended_action(error_code),
                }
                if error_code
                else None
            ),
            "evidence_count": len(evidence) if evidence else 0,
            "evidence": evidence or [],
        }

        # Add telemetry summary if available
        if telemetry_events:
            report["telemetry_summary"] = {
                "total_events": len(telemetry_events),
                "events_by_type": cls._count_events_by_type(telemetry_events),
            }

        return report

    @classmethod
    def _get_friendly_message(
        cls,
        error_code: str | None,
        technical_message: str = "",
        is_success: bool = True,
    ) -> str:
        """Get user-friendly error message."""
        if is_success:
            return "Operation completed successfully."

        if error_code and error_code in cls.FRIENDLY_ERROR_MESSAGES:
            return cls.FRIENDLY_ERROR_MESSAGES[error_code]

        return f"An error occurred: {technical_message or 'Unknown error'}"

    @classmethod
    def _get_recommended_action(cls, error_code: str | None) -> str:
        """Get recommended action for error."""
        actions = {
            "AUTH_INVALID_CREDENTIALS": "Verify your username and password are correct.",
            "AUTH_SESSION_EXPIRED": "Log in again to start a new session.",
            "AUTH_CAPTCHA_FAILED": "Try again and ensure CAPTCHA is entered correctly.",
            "CAPTCHA_MAX_RETRY": "Wait 5-10 minutes before attempting again.",
            "NET_TIMEOUT": "Check your internet connection and try again.",
            "NET_CONNECTION_REFUSED": "The portal may be down. Try again in a few minutes.",
            "BR_NAVIGATION_TIMEOUT": "The portal is slow. Try again later.",
            "ELEMENT_NOT_FOUND": "Contact support - the portal interface may have changed.",
            "WAYBILL_FORM_CHANGED": "Contact support - the waybill form has been updated.",
            "WAYBILL_SUBMISSION_FAILED": "Review your data and try again.",
            "MAP_LOADING_TIMEOUT": "Try again or select location manually.",
            "MAP_INTERACTION_FAILED": "Try again or use dropdown selection.",
            "PORTAL_DOWN": "The portal is unavailable. Try again later.",
            "PORTAL_MAINTENANCE": "Wait for maintenance to complete.",
            "RATE_LIMITED": "Wait before making more requests.",
            "PERMISSION_DENIED": "Contact your administrator for access.",
        }
        return actions.get(error_code, "Contact support if the issue persists.")

    @staticmethod
    def _count_events_by_type(events: list[dict[str, Any]]) -> dict[str, int]:
        counts = {}
        for event in events:
            event_type = event.get("event_type", "unknown")
            counts[event_type] = counts.get(event_type, 0) + 1
        return counts


# ============================================================================
# GLOBAL INSTANCES
# ============================================================================

# Default evidence collector
evidence_collector = EvidenceCollector(
    base_dir="evidence",
    max_evidence_per_workflow=10,
    retention_days=7,
    auto_cleanup=True,
)

# Default telemetry collector
telemetry_collector = TelemetryCollector(
    telemetry_level=TelemetryLevel.DETAILED,
    max_events_buffer=10000,
    flush_interval_seconds=60.0,
)

# Default report generator
report_generator = ClientReportGenerator()
