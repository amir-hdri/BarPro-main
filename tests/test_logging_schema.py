import json
import logging

from app.core.logging import JsonFormatter, monitoring_extra


def test_json_formatter_includes_monitoring_schema_payload():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="structured event",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-1"
    record.correlation_id = "corr-1"
    record.task_id = "task-1"
    record.tenant_id = "tenant-1"
    record.batch_id = "batch-1"
    record.worker_id = "worker-1"
    record.extra_fields = monitoring_extra(
        "waybill_pill_trace",
        category="waybill_flow",
        payload={"pill": "sender", "transition_success": True},
        tags={"pill": "sender"},
        pill="sender",
        transition_success=True,
    )["extra_fields"]

    raw = formatter.format(record)
    payload = json.loads(raw)

    assert payload["schema_version"] == "2025-02-automation-v1"
    assert payload["monitoring"]["event_name"] == "waybill_pill_trace"
    assert payload["monitoring"]["category"] == "waybill_flow"
    assert payload["monitoring"]["payload"]["pill"] == "sender"
    assert payload["extra"]["pill"] == "sender"
