"""Regression test for the missing-driver guard in RPAHttpSubmitService._process_job.

session.get(Driver, job.driver_id) may return None (driver deleted between job
creation and submit). The service must raise a clean ValueError instead of
crashing later with AttributeError inside _mark_daily_limit.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.rpa_submit_service import RPAHttpSubmitService


def _make_session(*, driver):
    session = AsyncMock()
    job = MagicMock()
    job.job_id = "job_123"
    job.client_id = 7
    job.driver_id = 42
    job.result_json = None
    exec_result = MagicMock()
    exec_result.first.return_value = job
    session.exec.return_value = exec_result
    session.get.return_value = driver
    return session


@pytest.mark.asyncio
async def test_process_job_missing_driver_raises_value_error():
    session = _make_session(driver=None)
    service = RPAHttpSubmitService()

    with (
        patch("app.services.rpa_submit_service.async_session_factory", return_value=session),
        pytest.raises(ValueError, match="driver 42 not found for job job_123"),
    ):
        await service._process_job(client_id=7, job_id="job_123")
