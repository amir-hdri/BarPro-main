import contextvars
import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

from app.core.execution_context import get_execution_context

request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
MONITORING_SCHEMA_VERSION = "2025-02-automation-v1"


def set_request_id(value: str):
    return request_id_ctx.set(value)


def reset_request_id(token) -> None:
    request_id_ctx.reset(token)


def get_request_id() -> str:
    return request_id_ctx.get()


def _sanitize_string(value: str) -> str:
    sanitized = value
    patterns = [
        (r"(?i)(authorization\s*[:=]\s*bearer\s+)[a-z0-9._\-]+", r"\1***"),
        (r"(?i)(api[_-]?key\s*[:=]\s*)[^\s,;]+", r"\1***"),
        (r"(?i)(jwt[_-]?secret\s*[:=]\s*)[^\s,;]+", r"\1***"),
        (r"(?i)(password\s*[:=]\s*)[^\s,;]+", r"\1***"),
        (r"(?i)(token\s*[:=]\s*)[^\s,;]+", r"\1***"),
    ]
    try:
        for pattern, replacement in patterns:
            sanitized = re.sub(pattern, replacement, sanitized)
    except Exception:
        # During interpreter teardown regex internals may already be unavailable.
        return value
    return sanitized


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, raw in value.items():
            lowered = str(key).lower()
            if any(secret_key in lowered for secret_key in ("password", "secret", "token", "api_key", "authorization")):
                clean[key] = "***"
            else:
                clean[key] = sanitize(raw)
        return clean
    if isinstance(value, (list, tuple, set)):
        return [sanitize(v) for v in value]
    if isinstance(value, str):
        return _sanitize_string(value)
    return value


def build_monitoring_event(
    event_name: str,
    *,
    category: str,
    payload: dict[str, Any] | None = None,
    tags: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": MONITORING_SCHEMA_VERSION,
        "event_name": str(event_name or "unknown"),
        "category": str(category or "application"),
        "payload": sanitize(payload or {}),
        "tags": sanitize(tags or {}),
    }


def monitoring_extra(
    event_name: str,
    *,
    category: str,
    payload: dict[str, Any] | None = None,
    tags: dict[str, Any] | None = None,
    **extra_fields: Any,
) -> dict[str, Any]:
    merged = dict(extra_fields)
    merged["monitoring"] = build_monitoring_event(
        event_name,
        category=category,
        payload=payload,
        tags=tags,
    )
    return {"extra_fields": merged}


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        execution_context = get_execution_context()
        record.correlation_id = execution_context.correlation_id
        record.task_id = execution_context.task_id
        record.tenant_id = execution_context.tenant_id
        record.batch_id = execution_context.batch_id
        record.worker_id = execution_context.worker_id
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "schema_version": MONITORING_SCHEMA_VERSION,
            "timestamp": datetime.now(UTC).replace(tzinfo=None).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": sanitize(record.getMessage()),
            "request_id": getattr(record, "request_id", get_request_id()),
            "correlation_id": getattr(record, "correlation_id", "-"),
            "task_id": getattr(record, "task_id", "-"),
            "tenant_id": getattr(record, "tenant_id", "-"),
            "batch_id": getattr(record, "batch_id", "-"),
            "worker_id": getattr(record, "worker_id", "-"),
        }

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        extra_fields = getattr(record, "extra_fields", None)
        if extra_fields:
            payload["extra"] = sanitize(extra_fields)
            monitoring = extra_fields.get("monitoring") if isinstance(extra_fields, dict) else None
            if monitoring:
                payload["monitoring"] = sanitize(monitoring)

        return json.dumps(payload, ensure_ascii=False)


def configure_logging(log_level: str = "INFO") -> None:
    level = getattr(logging, (log_level or "INFO").upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    formatter = JsonFormatter()
    request_filter = RequestIdFilter()

    # Reset handlers to avoid duplicate output during tests/reloads.
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(formatter)
    handler.addFilter(request_filter)
    root.addHandler(handler)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True
