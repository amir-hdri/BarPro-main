"""Shared helper utilities for multi-tenant service modules."""

import json
import logging

from app.models_multitenant import DriverSchedule
from app.schemas.multitenant import TaskTimelineEntry, TaskTimelineQuery

logger = logging.getLogger(__name__)


def _safe_json_payload(raw: str | dict | list | None) -> dict | None:
    """Safely parse a JSON value that may be a string (legacy TEXT) or already a dict (JSONB)."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        return {"value": raw}
    if isinstance(raw, str):
        if not raw:
            return None
        try:
            payload = json.loads(raw)
            return payload if isinstance(payload, dict) else {"value": payload}
        except Exception as exc:
            logger.debug("Failed to parse JSON payload", exc_info=True, extra={"raw": raw[:100]})
            return {"raw": raw}
    return {"value": raw}


def _deep_merge_dict(base: dict, updates: dict) -> dict:
    """Recursively merge dictionaries while letting override values win."""
    merged = dict(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _timeline_matches_query(entry: TaskTimelineEntry, query: TaskTimelineQuery) -> bool:
    if query.phase and (entry.phase or "").lower() != query.phase.lower():
        return False
    if query.event_type and entry.event_type != query.event_type:
        return False
    if query.source and entry.source != query.source:
        return False
    if query.q:
        needle = query.q.lower()
        haystack = " ".join(
            [
                entry.title,
                entry.event_type,
                entry.message or "",
                entry.status or "",
                entry.source,
                json.dumps(entry.payload or {}, ensure_ascii=False),
            ]
        ).lower()
        if needle not in haystack:
            return False
    return True


def _parse_weekdays_csv(raw: str | None) -> list[int]:
    if not raw:
        return []
    output: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if token.isdigit():
            value = int(token)
            if 0 <= value <= 6:
                output.append(value)
    return sorted(set(output))


def _build_weekdays_csv(values: list[int] | None) -> str | None:
    if not values:
        return None
    normalized = sorted({int(item) for item in values if 0 <= int(item) <= 6})
    return ",".join(str(item) for item in normalized) if normalized else None


def _parse_csv_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _build_csv_list(values: list[str] | None) -> str | None:
    if not values:
        return None
    normalized = [item.strip() for item in values if item and item.strip()]
    return ",".join(sorted(set(normalized))) if normalized else None


def _resolve_run_times(item: DriverSchedule) -> list[str]:
    run_times = _parse_csv_list(item.run_times_csv)
    if run_times:
        return run_times
    return [item.run_time]
