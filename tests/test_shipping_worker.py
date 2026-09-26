"""Unit tests for the shipping worker Celery task and beat schedule."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

from app.automation.gps_shipping_manager import ShippingState
from app.core.config import utcms_config
from app.workers.celery_app import celery_app
from app.workers.shipping_worker import auto_complete_due_trips


def test_shipping_worker_task_registration():
    """Verify that the task is properly registered in Celery with expected attributes."""
    assert celery_app is not None
    assert "shipping.auto_complete_due_trips" in celery_app.tasks

    task = celery_app.tasks["shipping.auto_complete_due_trips"]
    assert task.name == "shipping.auto_complete_due_trips"
    assert task.max_retries == 2
    assert task.default_retry_delay == 30
    assert "app.workers.shipping_worker" in celery_app.conf.include


def test_shipping_worker_beat_schedule_entry():
    """Verify that the periodic beat schedule for due trips auto-complete is properly configured."""
    assert celery_app is not None
    beat_schedule = celery_app.conf.beat_schedule
    assert "shipping-auto-complete-due" in beat_schedule

    entry = beat_schedule["shipping-auto-complete-due"]
    assert entry["task"] == "shipping.auto_complete_due_trips"
    # Verify crontab schedule is every 2 minutes
    assert entry["schedule"].minute == set(range(0, 60, 2))
    assert entry["options"]["queue"] == utcms_config.CELERY_WAYBILL_TASKS_QUEUE
    assert entry["options"]["expires"] == 110


def test_auto_complete_due_trips_no_jobs(caplog):
    """Verify task execution when no due jobs are found."""
    with (
        patch("app.workers.shipping_worker.get_due_in_transit_jobs", new_callable=AsyncMock) as mock_get_due,
        patch("app.workers.shipping_worker.auto_complete_shipping", new_callable=AsyncMock) as mock_auto_complete,
        caplog.at_level(logging.INFO),
    ):
        mock_get_due.return_value = []

        result = auto_complete_due_trips()

        assert mock_get_due.call_count == 1
        assert mock_auto_complete.call_count == 0
        assert result["scanned_count"] == 0
        assert result["completed_count"] == 0
        assert result["skipped_count"] == 0
        assert result["failed_count"] == 0
        assert result["completed"] == []
        assert "shipping_due_trips_scan_started" in caplog.text
        assert "shipping_due_trips_scan_completed" in caplog.text


def test_auto_complete_due_trips_successful_completion(caplog):
    """Verify task execution when due jobs exist and succeed."""
    state1 = ShippingState(
        job_id="job-101",
        doc_no="226001",
        doc_id="doc-101",
        status="in_transit",
        origin_address="Tehran",
        dest_address="Isfahan",
        distance_km=440.0,
        estimated_end_at="2026-09-26T12:00:00Z",
    )
    state2 = ShippingState(
        job_id="job-102",
        doc_no="226002",
        doc_id="doc-102",
        status="in_transit",
        origin_address="Tabriz",
        dest_address="Shiraz",
        distance_km=1100.0,
        estimated_end_at="2026-09-26T12:30:00Z",
    )

    with (
        patch("app.workers.shipping_worker.get_due_in_transit_jobs", new_callable=AsyncMock) as mock_get_due,
        patch("app.workers.shipping_worker.auto_complete_shipping", new_callable=AsyncMock) as mock_auto_complete,
        caplog.at_level(logging.INFO),
    ):
        mock_get_due.return_value = [state1, state2]
        mock_auto_complete.return_value = {
            "status": "delivered",
            "result": {"resultCode": 0, "resultMessage": "Success"},
        }

        result = auto_complete_due_trips()

        assert mock_get_due.call_count == 1
        assert mock_auto_complete.call_count == 2
        mock_auto_complete.assert_any_call("job-101")
        mock_auto_complete.assert_any_call("job-102")

        assert result["scanned_count"] == 2
        assert result["completed_count"] == 2
        assert result["skipped_count"] == 0
        assert result["failed_count"] == 0
        assert len(result["completed"]) == 2
        assert result["completed"][0]["job_id"] == "job-101"
        assert result["completed"][1]["job_id"] == "job-102"

        # Structured logs checks
        assert "shipping_due_trip_scanned" in caplog.text
        assert "shipping_due_trip_completed" in caplog.text


def test_auto_complete_due_trips_skipped_status(caplog):
    """Verify task execution when shipping auto-complete returns non-delivered (skipped)."""
    state = ShippingState(
        job_id="job-waiting",
        doc_no="226003",
        status="in_transit",
        origin_address="Mashhad",
        dest_address="Qom",
    )

    with (
        patch("app.workers.shipping_worker.get_due_in_transit_jobs", new_callable=AsyncMock) as mock_get_due,
        patch("app.workers.shipping_worker.auto_complete_shipping", new_callable=AsyncMock) as mock_auto_complete,
        caplog.at_level(logging.INFO),
    ):
        mock_get_due.return_value = [state]
        mock_auto_complete.return_value = {
            "status": "waiting_eta",
            "remaining_seconds": 180,
        }

        result = auto_complete_due_trips()

        assert result["scanned_count"] == 1
        assert result["completed_count"] == 0
        assert result["skipped_count"] == 1
        assert result["failed_count"] == 0
        assert result["skipped"][0]["job_id"] == "job-waiting"
        assert result["skipped"][0]["status"] == "waiting_eta"
        assert "shipping_due_trip_skipped" in caplog.text


def test_auto_complete_due_trips_partial_failure(caplog):
    """Verify that a failure on one job does not abort processing of subsequent jobs."""
    state_fail = ShippingState(job_id="job-fail", doc_no="226004", status="in_transit")
    state_ok = ShippingState(job_id="job-ok", doc_no="226005", status="in_transit")

    async def _mock_shipping(job_id: str):
        if job_id == "job-fail":
            raise RuntimeError("UTCMS API Error 500")
        return {"status": "delivered", "result": {"resultCode": 0}}

    with (
        patch("app.workers.shipping_worker.get_due_in_transit_jobs", new_callable=AsyncMock) as mock_get_due,
        patch("app.workers.shipping_worker.auto_complete_shipping", side_effect=_mock_shipping),
        caplog.at_level(logging.INFO),
    ):
        mock_get_due.return_value = [state_fail, state_ok]

        result = auto_complete_due_trips()

        assert result["scanned_count"] == 2
        assert result["completed_count"] == 1
        assert result["failed_count"] == 1
        assert result["failed"][0]["job_id"] == "job-fail"
        assert "UTCMS API Error 500" in result["failed"][0]["error"]
        assert result["completed"][0]["job_id"] == "job-ok"
        assert "shipping_due_trip_failed" in caplog.text
        assert "shipping_due_trip_completed" in caplog.text


def test_auto_complete_due_trips_retry_on_top_level_exception():
    """Verify that if get_due_in_transit_jobs raises an unexpected error, Celery retry is invoked."""
    with (
        patch.object(auto_complete_due_trips, "retry", side_effect=RuntimeError("Retry triggered")) as mock_retry,
        patch("app.workers.shipping_worker.get_due_in_transit_jobs", new_callable=AsyncMock) as mock_get_due,
    ):
        mock_get_due.side_effect = ConnectionError("Redis unavailable")

        with pytest.raises(RuntimeError, match="Retry triggered"):
            auto_complete_due_trips()

        mock_retry.assert_called_once()
