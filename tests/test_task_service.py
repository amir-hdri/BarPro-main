from app.services.task_service import WaybillTaskService


def test_build_idempotency_key_blank_value_falls_back_to_auto_hash():
    payload = {"sender": {"name": "x"}, "receiver": {"name": "y"}}
    key = WaybillTaskService.build_idempotency_key(payload, "   ")
    assert key.startswith("auto-")


def test_build_idempotency_key_long_value_is_hashed():
    payload = {"sender": {"name": "x"}}
    provided = "a" * 400
    key = WaybillTaskService.build_idempotency_key(payload, provided)
    assert key.startswith("user-")
    assert len(key) == len("user-") + 64


def test_build_task_payload_defaults_can_hold_correlation_context():
    payload = {"sender": {"name": "x"}, "receiver": {"name": "y"}}
    payload.setdefault("correlation_id", "corr-123")
    payload.setdefault("batch_id", "batch-123")

    assert payload["correlation_id"] == "corr-123"
    assert payload["batch_id"] == "batch-123"
