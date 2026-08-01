from __future__ import annotations

import time
from collections import Counter as CollectionsCounter
from collections import deque
from threading import Lock
from typing import Any

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
except Exception:
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4"

    class _NoopMetric:
        def __init__(self, *args: Any, **kwargs: Any):
            return None

        def labels(self, *args: Any, **kwargs: Any):
            return self

        def inc(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def observe(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def set(self, *_args: Any, **_kwargs: Any) -> None:
            return None

    Counter = Gauge = Histogram = _NoopMetric  # type: ignore

    def generate_latest() -> bytes:  # type: ignore
        return b""


WAYBILL_REQUESTS = Counter(
    "waybill_requests_total",
    "Total incoming waybill create requests",
    ["mode"],
)
WAYBILL_SUCCESSES = Counter(
    "waybill_success_total",
    "Total successful waybill operations",
    ["mode"],
)
WAYBILL_FAILURES = Counter(
    "waybill_failure_total",
    "Total failed waybill operations",
    ["mode", "category"],
)
WAYBILL_TASK_STATUS = Counter(
    "waybill_task_status_total",
    "Task state transitions",
    ["status"],
)
WAYBILL_TASK_LATENCY = Histogram(
    "waybill_task_latency_seconds",
    "Total task execution latency",
    buckets=(0.2, 0.5, 1, 2, 5, 10, 20, 40, 60, 120, 240),
)
WAYBILL_QUEUE_DEPTH = Gauge(
    "waybill_queue_depth",
    "Current number of queued/retrying tasks",
)
ITMB_CIRCUIT_STATE = Gauge(
    "itmb_circuit_breaker_state",
    "Circuit breaker state: 0 closed, 1 half-open, 2 open",
)
RECONCILIATION_BACKLOG = Gauge(
    "reconciliation_backlog",
    "Current number of jobs needing reconciliation",
)
DB_POOL_UTILIZATION = Gauge(
    "db_pool_utilization",
    "FastAPI DB connection pool utilization percentage",
)
ACTIVE_WORKER_COUNT = Gauge(
    "active_worker_count",
    "Number of active RPA workers",
)
WORKER_LIVENESS = Gauge(
    "worker_liveness",
    "Liveness status per worker (1=alive, 0=dead)",
    ["worker_id"],
)
HEALTHY_PROXY_COUNT = Gauge(
    "healthy_proxy_count",
    "Number of healthy worker proxies",
)
CAPTCHA_ATTEMPTS = Counter(
    "captcha_attempts_total",
    "Captcha solve attempts by strategy",
    ["strategy"],
)
CAPTCHA_SUCCESSES = Counter(
    "captcha_success_total",
    "Captcha solved successfully by strategy",
    ["strategy"],
)
CAPTCHA_FAILURES = Counter(
    "captcha_failure_total",
    "Captcha solve failures by reason",
    ["reason"],
)
CAPTCHA_SUBMIT_RETRIES = Counter(
    "captcha_submit_retries_total",
    "Number of login submit retries due to captcha issues",
)
CAPTCHA_PHASE_ATTEMPTS = Counter(
    "captcha_phase_attempts_total",
    "Captcha solve attempts grouped by phase and strategy",
    ["phase", "strategy"],
)
CAPTCHA_PHASE_SUCCESSES = Counter(
    "captcha_phase_success_total",
    "Captcha solve successes grouped by phase and strategy",
    ["phase", "strategy"],
)
CAPTCHA_PHASE_FAILURES = Counter(
    "captcha_phase_failure_total",
    "Captcha solve failures grouped by phase and reason",
    ["phase", "reason"],
)
CAPTCHA_SOLVE_LATENCY = Histogram(
    "captcha_solve_latency_seconds",
    "Latency of captcha solve operations",
    ["phase", "strategy", "outcome"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 15),
)
CAPTCHA_ADAPTIVE_FAILURE_RATE = Gauge(
    "captcha_adaptive_failure_rate",
    "Rolling failure rate used by adaptive captcha policy",
)
CAPTCHA_ADAPTIVE_TARGET_ATTEMPTS = Gauge(
    "captcha_adaptive_target_attempts",
    "Adaptive target attempts for captcha solving",
)
CAPTCHA_ADAPTIVE_TARGET_DELAY = Gauge(
    "captcha_adaptive_target_delay_seconds",
    "Adaptive target delay between captcha retries",
)

METRICS_CONTENT_TYPE = CONTENT_TYPE_LATEST
_CAPTCHA_RUNTIME_MAX_EVENTS = 240
_CAPTCHA_RUNTIME_LOCK = Lock()
_CAPTCHA_RUNTIME_EVENTS = deque(maxlen=_CAPTCHA_RUNTIME_MAX_EVENTS)
_CAPTCHA_RUNTIME_ATTEMPTS_BY_STRATEGY: CollectionsCounter[str] = CollectionsCounter()
_CAPTCHA_RUNTIME_SUCCESSES_BY_STRATEGY: CollectionsCounter[str] = CollectionsCounter()
_CAPTCHA_RUNTIME_FAILURES_BY_REASON: CollectionsCounter[str] = CollectionsCounter()
_CAPTCHA_RUNTIME_ATTEMPTS_BY_PHASE: CollectionsCounter[str] = CollectionsCounter()
_CAPTCHA_RUNTIME_SUCCESSES_BY_PHASE: CollectionsCounter[str] = CollectionsCounter()
_CAPTCHA_RUNTIME_FAILURES_BY_PHASE: CollectionsCounter[str] = CollectionsCounter()
_CAPTCHA_RUNTIME_ATTEMPTS_TOTAL = 0
_CAPTCHA_RUNTIME_SUCCESSES_TOTAL = 0
_CAPTCHA_RUNTIME_FAILURES_TOTAL = 0


def track_waybill_request(mode: str) -> None:
    WAYBILL_REQUESTS.labels(mode=(mode or "safe")).inc()


def track_waybill_success(mode: str) -> None:
    WAYBILL_SUCCESSES.labels(mode=(mode or "safe")).inc()


def track_waybill_failure(mode: str, category: str) -> None:
    WAYBILL_FAILURES.labels(mode=(mode or "safe"), category=(category or "unknown")).inc()


def track_task_status(status: str) -> None:
    WAYBILL_TASK_STATUS.labels(status=(status or "unknown")).inc()


def track_task_latency(latency_seconds: float) -> None:
    if latency_seconds < 0:
        return
    WAYBILL_TASK_LATENCY.observe(latency_seconds)


def set_queue_depth(depth: int) -> None:
    WAYBILL_QUEUE_DEPTH.set(max(0, int(depth)))


def set_circuit_breaker_state(state: str) -> None:
    state_map = {"closed": 0, "half_open": 1, "open": 2}
    ITMB_CIRCUIT_STATE.set(state_map.get((state or "").lower(), 0))


def set_reconciliation_backlog(backlog: int) -> None:
    RECONCILIATION_BACKLOG.set(max(0, int(backlog)))


def set_db_pool_utilization(utilization: float) -> None:
    DB_POOL_UTILIZATION.set(max(0.0, float(utilization)))


def set_active_worker_count(count: int) -> None:
    ACTIVE_WORKER_COUNT.set(max(0, int(count)))


def set_worker_liveness(worker_id: str, is_alive: bool) -> None:
    WORKER_LIVENESS.labels(worker_id=worker_id).set(1 if is_alive else 0)


def set_healthy_proxy_count(count: int) -> None:
    HEALTHY_PROXY_COUNT.set(max(0, int(count)))


def track_captcha_attempt(strategy: str, phase: str = "unknown", attempt: int | None = None) -> None:
    global _CAPTCHA_RUNTIME_ATTEMPTS_TOTAL
    normalized_strategy = strategy or "unknown"
    normalized_phase = phase or "unknown"
    CAPTCHA_ATTEMPTS.labels(strategy=normalized_strategy).inc()
    CAPTCHA_PHASE_ATTEMPTS.labels(phase=normalized_phase, strategy=normalized_strategy).inc()
    with _CAPTCHA_RUNTIME_LOCK:
        _CAPTCHA_RUNTIME_ATTEMPTS_TOTAL += 1
        _CAPTCHA_RUNTIME_ATTEMPTS_BY_STRATEGY[normalized_strategy] += 1
        _CAPTCHA_RUNTIME_ATTEMPTS_BY_PHASE[normalized_phase] += 1
        _CAPTCHA_RUNTIME_EVENTS.append(
            {
                "timestamp": time.time(),
                "event": "attempt",
                "strategy": normalized_strategy,
                "phase": normalized_phase,
                "attempt": attempt,
            }
        )


def track_captcha_success(
    strategy: str,
    phase: str = "unknown",
    confidence: float | None = None,
    latency_seconds: float | None = None,
    attempt: int | None = None,
) -> None:
    global _CAPTCHA_RUNTIME_SUCCESSES_TOTAL
    normalized_strategy = strategy or "unknown"
    normalized_phase = phase or "unknown"
    CAPTCHA_SUCCESSES.labels(strategy=normalized_strategy).inc()
    CAPTCHA_PHASE_SUCCESSES.labels(phase=normalized_phase, strategy=normalized_strategy).inc()
    if latency_seconds is not None and latency_seconds >= 0:
        CAPTCHA_SOLVE_LATENCY.labels(
            phase=normalized_phase,
            strategy=normalized_strategy,
            outcome="success",
        ).observe(latency_seconds)
    with _CAPTCHA_RUNTIME_LOCK:
        _CAPTCHA_RUNTIME_SUCCESSES_TOTAL += 1
        _CAPTCHA_RUNTIME_SUCCESSES_BY_STRATEGY[normalized_strategy] += 1
        _CAPTCHA_RUNTIME_SUCCESSES_BY_PHASE[normalized_phase] += 1
        _CAPTCHA_RUNTIME_EVENTS.append(
            {
                "timestamp": time.time(),
                "event": "success",
                "strategy": normalized_strategy,
                "phase": normalized_phase,
                "confidence": round(float(confidence), 4) if confidence is not None else None,
                "latency_seconds": round(float(latency_seconds), 4) if latency_seconds is not None else None,
                "attempt": attempt,
            }
        )


def track_captcha_failure(
    reason: str,
    phase: str = "unknown",
    strategy: str | None = None,
    latency_seconds: float | None = None,
    attempt: int | None = None,
) -> None:
    global _CAPTCHA_RUNTIME_FAILURES_TOTAL
    normalized_reason = reason or "unknown"
    normalized_phase = phase or "unknown"
    normalized_strategy = strategy or "unknown"
    CAPTCHA_FAILURES.labels(reason=normalized_reason).inc()
    CAPTCHA_PHASE_FAILURES.labels(phase=normalized_phase, reason=normalized_reason).inc()
    if latency_seconds is not None and latency_seconds >= 0:
        CAPTCHA_SOLVE_LATENCY.labels(
            phase=normalized_phase,
            strategy=normalized_strategy,
            outcome="failure",
        ).observe(latency_seconds)
    with _CAPTCHA_RUNTIME_LOCK:
        _CAPTCHA_RUNTIME_FAILURES_TOTAL += 1
        _CAPTCHA_RUNTIME_FAILURES_BY_REASON[normalized_reason] += 1
        _CAPTCHA_RUNTIME_FAILURES_BY_PHASE[normalized_phase] += 1
        _CAPTCHA_RUNTIME_EVENTS.append(
            {
                "timestamp": time.time(),
                "event": "failure",
                "reason": normalized_reason,
                "phase": normalized_phase,
                "strategy": normalized_strategy,
                "latency_seconds": round(float(latency_seconds), 4) if latency_seconds is not None else None,
                "attempt": attempt,
            }
        )


def track_captcha_submit_retry() -> None:
    CAPTCHA_SUBMIT_RETRIES.inc()


def set_captcha_adaptive_state(failure_rate: float, target_attempts: int, target_delay_seconds: float) -> None:
    CAPTCHA_ADAPTIVE_FAILURE_RATE.set(max(0.0, min(1.0, float(failure_rate))))
    CAPTCHA_ADAPTIVE_TARGET_ATTEMPTS.set(max(1, int(target_attempts)))
    CAPTCHA_ADAPTIVE_TARGET_DELAY.set(max(0.0, float(target_delay_seconds)))


def export_metrics() -> bytes:
    return generate_latest()


def summarize_queue_depth(snapshot: dict[str, int]) -> int:
    return int(snapshot.get("queued", 0)) + int(snapshot.get("retrying", 0))


def get_captcha_runtime_snapshot(window_size: int = 50) -> dict[str, Any]:
    normalized_window = max(5, min(200, int(window_size or 50)))

    with _CAPTCHA_RUNTIME_LOCK:
        events = list(_CAPTCHA_RUNTIME_EVENTS)
        attempts_total = int(_CAPTCHA_RUNTIME_ATTEMPTS_TOTAL)
        successes_total = int(_CAPTCHA_RUNTIME_SUCCESSES_TOTAL)
        failures_total = int(_CAPTCHA_RUNTIME_FAILURES_TOTAL)
        attempts_by_strategy = dict(_CAPTCHA_RUNTIME_ATTEMPTS_BY_STRATEGY)
        successes_by_strategy = dict(_CAPTCHA_RUNTIME_SUCCESSES_BY_STRATEGY)
        failures_by_reason = dict(_CAPTCHA_RUNTIME_FAILURES_BY_REASON)
        attempts_by_phase = dict(_CAPTCHA_RUNTIME_ATTEMPTS_BY_PHASE)
        successes_by_phase = dict(_CAPTCHA_RUNTIME_SUCCESSES_BY_PHASE)
        failures_by_phase = dict(_CAPTCHA_RUNTIME_FAILURES_BY_PHASE)

    outcome_events = [event for event in events if event.get("event") in {"success", "failure"}]
    recent_outcomes = outcome_events[-normalized_window:]
    window_failures = sum(1 for event in recent_outcomes if event.get("event") == "failure")
    sample_size = len(recent_outcomes)
    failure_rate = (window_failures / sample_size) if sample_size else 0.0
    last_failure_reason = next(
        (event.get("reason") for event in reversed(outcome_events) if event.get("event") == "failure"),
        None,
    )

    recent_history = []
    for event in outcome_events[-20:]:
        recent_history.append(
            {
                "timestamp": event.get("timestamp"),
                "status": event.get("event"),
                "strategy": event.get("strategy"),
                "reason": event.get("reason"),
                "phase": event.get("phase"),
                "confidence": event.get("confidence"),
                "latency_seconds": event.get("latency_seconds"),
                "attempt": event.get("attempt"),
            }
        )

    return {
        "totals": {
            "attempts": attempts_total,
            "successes": successes_total,
            "failures": failures_total,
            "success_rate": round((successes_total / attempts_total), 4) if attempts_total else 0.0,
            "failure_rate": round((failures_total / attempts_total), 4) if attempts_total else 0.0,
        },
        "window": {
            "size": normalized_window,
            "sample_size": sample_size,
            "failures": window_failures,
            "failure_rate": round(failure_rate, 4),
        },
        "attempts_by_strategy": attempts_by_strategy,
        "successes_by_strategy": successes_by_strategy,
        "failures_by_reason": failures_by_reason,
        "attempts_by_phase": attempts_by_phase,
        "successes_by_phase": successes_by_phase,
        "failures_by_phase": failures_by_phase,
        "last_failure_reason": last_failure_reason,
        "recent_history": recent_history,
        "timestamp": time.time(),
    }


def reset_captcha_runtime_snapshot() -> None:
    global _CAPTCHA_RUNTIME_ATTEMPTS_TOTAL, _CAPTCHA_RUNTIME_SUCCESSES_TOTAL, _CAPTCHA_RUNTIME_FAILURES_TOTAL
    with _CAPTCHA_RUNTIME_LOCK:
        _CAPTCHA_RUNTIME_EVENTS.clear()
        _CAPTCHA_RUNTIME_ATTEMPTS_BY_STRATEGY.clear()
        _CAPTCHA_RUNTIME_SUCCESSES_BY_STRATEGY.clear()
        _CAPTCHA_RUNTIME_FAILURES_BY_REASON.clear()
        _CAPTCHA_RUNTIME_ATTEMPTS_BY_PHASE.clear()
        _CAPTCHA_RUNTIME_SUCCESSES_BY_PHASE.clear()
        _CAPTCHA_RUNTIME_FAILURES_BY_PHASE.clear()
        _CAPTCHA_RUNTIME_ATTEMPTS_TOTAL = 0
        _CAPTCHA_RUNTIME_SUCCESSES_TOTAL = 0
        _CAPTCHA_RUNTIME_FAILURES_TOTAL = 0
