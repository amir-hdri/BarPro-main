from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models_multitenant import Client, Driver, DriverSchedule, ScheduleFrequency
from app.services.scheduled_waybill_executor import _evaluate_single_schedule


@pytest.mark.asyncio
async def test_evaluate_single_schedule_once_deactivates():
    # Arrange
    schedule = DriverSchedule(
        id=1,
        client_id=1,
        driver_id=1,
        title="Test Once Schedule",
        frequency=ScheduleFrequency.ONCE.value,
        run_time="08:00",
        run_times_csv="08:00",
        weekdays_csv=None,
        specific_dates_csv=None,
        start_date=None,
        end_date=None,
        payload_template_json='{"sender": {"name": "Test"}}',
        is_active=True,
    )

    mock_client = Client(id=1, status="active")
    mock_driver = Driver(id=1, client_id=1, driver_national_code="1234567890", status="active")

    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    # Mock session.get side effects
    async def mock_get(model, model_id):
        if model == Client:
            return mock_client
        if model == Driver:
            return mock_driver
        return None
    mock_session.get.side_effect = mock_get

    # Mock session.exec for existing job check to return None (no duplicate)
    mock_exec_result = MagicMock()
    mock_exec_result.first.return_value = None
    mock_session.exec.return_value = mock_exec_result

    # Mock _utcnow to return a specific time so it matches the run_time "08:00"
    fixed_now = datetime(2026, 7, 7, 8, 15, tzinfo=UTC)

    with (
        patch("app.services.scheduled_waybill_executor._utcnow", return_value=fixed_now),
        patch("app.services.scheduled_waybill_executor.dispatch_scheduled_job") as mock_dispatch,
        patch("app.services.scheduled_waybill_executor._record_event", new_callable=AsyncMock),
    ):
        # Act
        result = await _evaluate_single_schedule(mock_session, schedule)

        # Assert
        assert result["jobs_created"] == 1
        assert schedule.is_active is False
        assert schedule.next_run_at is None
        assert schedule.last_run_at == fixed_now

        # Verify DB calls
        mock_session.add.assert_any_call(schedule)
        assert mock_session.commit.await_count == 2
        mock_dispatch.assert_called_once()
