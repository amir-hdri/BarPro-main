from unittest.mock import AsyncMock, patch

import pytest

from app.monitoring.event_bridge import MonitoringEventBridge


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
