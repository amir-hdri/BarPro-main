"""Unit tests for auto_start_shipping and get_due_start_shipping_jobs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.automation.gps_shipping_manager import (
    ShippingState,
    auto_start_shipping,
    get_due_start_shipping_jobs,
)


@pytest.mark.asyncio
async def test_auto_start_shipping_disabled_live_submit():
    with patch("app.core.config.utcms_config.ALLOW_LIVE_SUBMIT", False):
        res = await auto_start_shipping("job-1")
        assert res["status"] == "skipped"
        assert res["reason"] == "live_submit_disabled"


@pytest.mark.asyncio
async def test_auto_start_shipping_no_state():
    with (
        patch("app.core.config.utcms_config.ALLOW_LIVE_SUBMIT", True),
        patch("app.automation.gps_shipping_manager.load_shipping_state", AsyncMock(return_value=None)),
    ):
        res = await auto_start_shipping("job-not-found")
        assert res["status"] == "skipped"
        assert res["reason"] == "no_shipping_state"


@pytest.mark.asyncio
async def test_auto_start_shipping_already_started():
    state = ShippingState(job_id="job-already", doc_no="123", doc_id="456", status="in_transit")
    with (
        patch("app.core.config.utcms_config.ALLOW_LIVE_SUBMIT", True),
        patch("app.automation.gps_shipping_manager.load_shipping_state", AsyncMock(return_value=state)),
    ):
        res = await auto_start_shipping("job-already")
        assert res["status"] == "already_started"
        assert res["shipping_status"] == "in_transit"


@pytest.mark.asyncio
async def test_auto_start_shipping_waiting_cooldown():
    future_time = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
    state = ShippingState(
        job_id="job-wait",
        doc_no="123",
        doc_id="456",
        status="rate_limited",
        backoff_until=future_time,
    )
    with (
        patch("app.core.config.utcms_config.ALLOW_LIVE_SUBMIT", True),
        patch("app.automation.gps_shipping_manager.load_shipping_state", AsyncMock(return_value=state)),
    ):
        res = await auto_start_shipping("job-wait")
        assert res["status"] == "waiting_cooldown"
        assert res["backoff_until"] == future_time


@pytest.mark.asyncio
async def test_auto_start_shipping_success():
    state = ShippingState(
        job_id="job-ok",
        doc_no="1363223066",
        doc_id="998877",
        status="unknown",
        origin_lat=35.6892,
        origin_lng=51.3890,
        dest_lat=35.7000,
        dest_lng=51.4000,
        distance_km=15.0,
    )

    mock_driver = AsyncMock()
    mock_driver.id = 4
    mock_driver.client_id = "test-tenant"
    mock_driver.driver_national_code = "5720138129"
    mock_driver.utcms_password_encrypted = "encrypted_secret"

    mock_job = AsyncMock()
    mock_job.job_id = "job-ok"
    mock_job.driver_id = 4
    mock_job.client_id = "test-tenant"

    mock_client = AsyncMock()
    mock_client.register_start_of_shipping.return_value = {
        "resultCode": 0,
        "resultMessage": "عملیات با موفقیت انجام شد",
    }

    from unittest.mock import MagicMock

    mock_session = AsyncMock()
    mock_exec = MagicMock()
    mock_exec.first.return_value = mock_job
    mock_session.exec = AsyncMock(return_value=mock_exec)
    mock_session.get = AsyncMock(return_value=mock_driver)

    class SessionContext:
        async def __aenter__(self):
            return mock_session

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with (
        patch("app.core.config.utcms_config.ALLOW_LIVE_SUBMIT", True),
        patch("app.automation.gps_shipping_manager.load_shipping_state", AsyncMock(return_value=state)),
        patch("app.core.database.async_session_factory", return_value=SessionContext()),
        patch("app.auth_multitenant.decrypt_driver_password", return_value="plain_pass"),
        patch("app.automation.worker_proxy.get_worker_proxy_url", return_value="http://127.0.0.1:3128"),
        patch("app.automation.gps_shipping_manager.get_or_login_client", AsyncMock(return_value=mock_client)),
        patch("app.automation.gps_shipping_manager.save_shipping_state", AsyncMock()) as mock_save,
    ):
        res = await auto_start_shipping("job-ok")
        assert res["status"] == "started"
        assert state.status == "in_transit"
        assert len(state.gps_list) == 1
        assert state.gps_list[0]["Type"] == 2
        assert state.gps_list[0]["Latitude"] == 35.6892
        assert mock_save.call_count == 1


@pytest.mark.asyncio
async def test_get_due_start_shipping_jobs_filters_cooldown():
    now = datetime(2026, 10, 17, 12, 0, 0, tzinfo=UTC)
    state_ready = {
        "job_id": "job-ready",
        "doc_id": "111",
        "doc_no": "111",
        "status": "ready",
        "origin_lat": 35.0,
        "origin_lng": 51.0,
        "backoff_until": "",
    }
    state_cooling = {
        "job_id": "job-cooling",
        "doc_id": "222",
        "doc_no": "222",
        "status": "unknown",
        "origin_lat": 35.0,
        "origin_lng": 51.0,
        "backoff_until": (now + timedelta(minutes=15)).isoformat(),
    }
    state_expired = {
        "job_id": "job-expired",
        "doc_id": "333",
        "doc_no": "333",
        "status": "rate_limited",
        "origin_lat": 35.0,
        "origin_lng": 51.0,
        "backoff_until": (now - timedelta(minutes=5)).isoformat(),
    }

    mock_redis = AsyncMock()
    # Mock redis scan returning keys
    mock_redis.scan.side_effect = [
        (0, ["utcms:shipping:job:job-ready", "utcms:shipping:job:job-cooling", "utcms:shipping:job:job-expired"])
    ]
    import json

    mock_redis.get.side_effect = [
        json.dumps(state_ready),
        json.dumps(state_cooling),
        json.dumps(state_expired),
    ]

    with (
        patch("app.automation.gps_shipping_manager._get_redis", AsyncMock(return_value=mock_redis)),
        patch("app.core.database.async_session_factory", side_effect=Exception("DB skipped")),
    ):
        due = await get_due_start_shipping_jobs(now_dt=now)
        job_ids = [s.job_id for s in due]
        assert "job-ready" in job_ids
        assert "job-expired" in job_ids
        assert "job-cooling" not in job_ids
