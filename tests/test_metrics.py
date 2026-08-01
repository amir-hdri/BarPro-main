"""
Unit tests for prometheus metrics export.
"""

import logging

from app.monitoring.metrics import (
    set_queue_depth,
    set_active_worker_count,
    set_worker_liveness,
    set_db_pool_utilization,
    set_reconciliation_backlog,
    set_healthy_proxy_count,
    export_metrics,
    track_waybill_request,
    track_waybill_success,
    track_waybill_failure,
    track_task_status,
    track_task_latency,
    get_captcha_runtime_snapshot,
    reset_captcha_runtime_snapshot,
    track_captcha_attempt,
    track_captcha_success,
    track_captcha_failure,
)


def test_set_queue_depth():
    """Queue depth gauge accepts positive integers without exception."""
    set_queue_depth(42)
    set_queue_depth(0)
    set_queue_depth(-5)  # clamps to 0


def test_set_active_worker_count():
    set_active_worker_count(3)
    set_active_worker_count(0)


def test_set_worker_liveness():
    set_worker_liveness("worker-1", True)
    set_worker_liveness("worker-2", False)


def test_set_db_pool_utilization():
    set_db_pool_utilization(75.5)
    set_db_pool_utilization(0.0)


def test_set_reconciliation_backlog():
    set_reconciliation_backlog(12)
    set_reconciliation_backlog(0)


def test_set_healthy_proxy_count():
    set_healthy_proxy_count(2)
    set_healthy_proxy_count(0)


def test_export_metrics_returns_bytes():
    payload = export_metrics()
    assert isinstance(payload, bytes)
    # When prometheus-client is installed, payload is non-empty.


def test_track_waybill_lifecycle():
    """Waybill counters should not raise."""
    track_waybill_request("safe")
    track_waybill_success("safe")
    track_waybill_failure("safe", "network_error")


def test_track_task_status_and_latency():
    track_task_status("CLAIMED")
    track_task_latency(12.5)
    track_task_latency(-1.0)  # ignored


def test_captcha_runtime_snapshot():
    """Captcha runtime tracking accumulates and snapshot reflects it."""
    reset_captcha_runtime_snapshot()

    for _ in range(5):
        track_captcha_attempt(strategy="cnn", phase="login")

    for _ in range(4):
        track_captcha_success(strategy="cnn", phase="login")

    track_captcha_failure(reason="timeout", phase="login", strategy="cnn")

    snapshot = get_captcha_runtime_snapshot(window_size=10)
    assert snapshot["totals"]["attempts"] == 5
    assert snapshot["totals"]["successes"] == 4
    assert snapshot["totals"]["failures"] == 1

    reset_captcha_runtime_snapshot()


async def test_metrics_endpoint_resolves_all_names():
    """Regression: the /metrics route body must not raise NameError.

    The SLO gauge block inside ``system.metrics`` uses function-local imports.
    A missing import there (historically ``async_session_factory``) was
    swallowed by the surrounding ``except Exception`` handlers, so the gauges
    silently stayed at zero while the endpoint still returned 200. This test
    asserts the names actually resolve instead of only exercising the gauge
    setters directly.
    """
    from app.api.routes import system

    captured: list[str] = []

    class _Recorder(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record.getMessage())

    handler = _Recorder(level=logging.ERROR)
    system.logger.addHandler(handler)
    try:
        response = await system.metrics()
    finally:
        system.logger.removeHandler(handler)

    assert response.status_code == 200
    name_errors = [msg for msg in captured if "not defined" in msg or "NameError" in msg]
    assert not name_errors, f"/metrics raised NameError internally: {name_errors}"

