"""Bridge between monitoring events and metrics/timeline APIs.

This module connects structured monitoring events (like waybill_pill_trace,
waybill_selector_inventory_audit) to:
1. Prometheus metrics for aggregation
2. Real-time event hub for UI display
"""
import logging
from typing import Any, Dict, Optional

from app.monitoring.metrics import (
    WAYBILL_FAILURES,
    WAYBILL_REQUESTS,
    WAYBILL_SUCCESSES,
)
from app.realtime.events import event_hub

logger = logging.getLogger(__name__)


class MonitoringEventBridge:
    """Bridge monitoring events to metrics and real-time streams."""

    def __init__(self):
        self._event_handlers = {
            "waybill_pill_trace": self._handle_pill_trace,
            "waybill_selector_inventory_audit": self._handle_selector_audit,
            "waybill_create_started": self._handle_waybill_started,
            "waybill_create_success": self._handle_waybill_success,
            "waybill_create_failed": self._handle_waybill_failed,
        }

    async def emit(
        self,
        event_type: str,
        payload: Dict[str, Any],
        *,
        task_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> None:
        """Emit a monitoring event to metrics and timeline."""
        handler = self._event_handlers.get(event_type)
        if handler:
            handler(payload, tags or {})

        await self._publish_to_timeline(
            event_type=event_type,
            payload=payload,
            task_id=task_id,
            correlation_id=correlation_id,
            tags=tags,
        )

    def _handle_pill_trace(self, payload: Dict[str, Any], tags: Dict[str, str]) -> None:
        """Handle waybill pill transition events."""
        pill = payload.get("pill", "unknown")
        transition_success = payload.get("transition_success", False)
        
        logger.info(
            "pill_transition",
            extra={
                "extra_fields": {
                    "pill": pill,
                    "target_pill": payload.get("target_pill"),
                    "success": transition_success,
                    "button_text": payload.get("button_text"),
                }
            },
        )

    def _handle_selector_audit(self, payload: Dict[str, Any], tags: Dict[str, str]) -> None:
        """Handle selector inventory audit events."""
        items = payload.get("items", [])
        
        filled_count = sum(1 for item in items if item.get("status") == "filled")
        failed_count = sum(1 for item in items if item.get("status") in ("unsupported", "failed"))
        
        logger.info(
            "selector_audit_summary",
            extra={
                "extra_fields": {
                    "total_fields": len(items),
                    "filled": filled_count,
                    "failed": failed_count,
                }
            },
        )

    def _handle_waybill_started(self, payload: Dict[str, Any], tags: Dict[str, str]) -> None:
        """Handle waybill creation start."""
        mode = tags.get("mode", "unknown")
        WAYBILL_REQUESTS.labels(mode=mode).inc()

    def _handle_waybill_success(self, payload: Dict[str, Any], tags: Dict[str, str]) -> None:
        """Handle waybill creation success."""
        mode = tags.get("mode", "unknown")
        WAYBILL_SUCCESSES.labels(mode=mode).inc()

    def _handle_waybill_failed(self, payload: Dict[str, Any], tags: Dict[str, str]) -> None:
        """Handle waybill creation failure."""
        mode = tags.get("mode", "unknown")
        category = tags.get("error_category", "unknown")
        WAYBILL_FAILURES.labels(mode=mode, category=category).inc()

    async def _publish_to_timeline(
        self,
        event_type: str,
        payload: Dict[str, Any],
        task_id: Optional[str],
        correlation_id: Optional[str],
        tags: Optional[Dict[str, str]],
    ) -> None:
        """Publish event to real-time timeline."""
        try:
            event = {
                "event_type": event_type,
                "payload": payload,
                "task_id": task_id,
                "correlation_id": correlation_id,
                "tags": tags or {},
            }
            await event_hub.publish(event)
        except Exception as exc:
            logger.warning(
                "timeline_publish_failed",
                extra={"extra_fields": {"error": str(exc), "event_type": event_type}},
            )


monitoring_bridge = MonitoringEventBridge()
