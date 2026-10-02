from unittest.mock import AsyncMock, patch

import pytest

from app.monitoring.event_bridge import MonitoringEventBridge


async def test_active_selector_audit_logs_summary_and_reaches_timeline() -> None:
    """The enhanced waybill manager still emits this event in its finalizer."""
    bridge = MonitoringEventBridge()
    payload = {"items": [{"status": "filled"}, {"status": "failed"}, {"status": "unsupported"}]}

    with (
        patch("app.monitoring.event_bridge.event_hub.publish", new_callable=AsyncMock) as publish,
        patch("app.monitoring.event_bridge.logger.info") as log,
    ):
        await bridge.emit("waybill_selector_inventory_audit", payload, task_id="job-1", tags={"item_count": "3"})

    log.assert_called_once_with(
        "selector_audit_summary", extra={"extra_fields": {"total_fields": 3, "filled": 1, "failed": 2}}
    )
    publish.assert_awaited_once_with(
        {
            "event_type": "waybill_selector_inventory_audit",
            "payload": payload,
            "task_id": "job-1",
            "correlation_id": None,
            "tags": {"item_count": "3"},
        }
    )


@pytest.mark.asyncio
async def test_publish_to_timeline_failure():
    """Test that event publishing failures are logged appropriately."""
    bridge = MonitoringEventBridge()

    with (
        patch("app.monitoring.event_bridge.event_hub.publish", new_callable=AsyncMock) as mock_publish,
        patch("app.monitoring.event_bridge.logger.warning") as mock_logger_warning,
    ):
        mock_publish.side_effect = Exception("Test error")

        await bridge._publish_to_timeline(
            event_type="test_event",
            payload={"test": "data"},
            task_id="task-123",
            correlation_id="corr-123",
            tags={"tag1": "value1"},
        )

        mock_logger_warning.assert_called_once()
        args, kwargs = mock_logger_warning.call_args
        assert args[0] == "timeline_publish_failed"
        assert kwargs["extra"]["extra_fields"]["error"] == "Test error"
        assert kwargs["extra"]["extra_fields"]["event_type"] == "test_event"
