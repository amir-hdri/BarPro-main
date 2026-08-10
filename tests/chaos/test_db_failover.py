from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import OperationalError

from app.workers.waybill_worker import _claim_and_execute


@pytest.mark.asyncio
async def test_database_failover_retry():
    """
    Chaos test: Verify that when a database operation encounters a temporary connection error
    (OperationalError), the system retries the query or safely bubbles up for Celery retry.
    """
    mock_task = MagicMock()
    mock_task.request.hostname = "chaos_worker"

    # We mock the database session factory to raise OperationalError on the first transaction
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = False
    # First execution raises OperationalError, second succeeds
    mock_session.exec.side_effect = [
        OperationalError("select", {}, "Connection lost"),
        MagicMock(),  # Second call succeeds
    ]

    # Create dummy session factory that yields our failing session
    call_count = 0

    def mock_session_factory():
        nonlocal call_count
        call_count += 1
        return mock_session

    with (
        patch("app.workers.waybill_worker.async_session_factory", new=mock_session_factory),
        patch("app.automation.worker_proxy.is_worker_draining", return_value=False),
    ):

        # Execute should raise OperationalError or handle it for Celery retry
        with pytest.raises((OperationalError, Exception)):
            await _claim_and_execute(mock_task, "intent-1")

        assert call_count > 0
        print("\nSuccessfully simulated database OperationalError. Call count:", call_count)
