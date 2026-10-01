from app.services.task_service import WaybillTaskService


def test_build_idempotency_key_blank_value_falls_back_to_auto_hash():
    payload = {"sender": {"name": "x"}, "receiver": {"name": "y"}}
    key = WaybillTaskService.build_idempotency_key(payload, "   ", client_id=7)
    # Tenant-scoped: blank supplied value falls back to a deterministic
    # tenant-scoped auto key (no global "auto-" semantics anymore).
    assert key == WaybillTaskService.build_idempotency_key(payload, "   ", client_id=7)
    other_tenant = WaybillTaskService.build_idempotency_key(payload, "   ", client_id=8)
    assert key != other_tenant


def test_build_idempotency_key_long_value_is_hashed():
    payload = {"sender": {"name": "x"}}
    provided = "a" * 400
    key = WaybillTaskService.build_idempotency_key(payload, provided, client_id=7)
    # Long supplied keys are hashed and tenant-scoped.
    assert "7" in key
    assert "a" * 400 not in key
    other_tenant = WaybillTaskService.build_idempotency_key(payload, provided, client_id=8)
    assert key != other_tenant


def test_build_idempotency_key_supplied_value_is_tenant_scoped():
    payload = {"sender": {"name": "x"}}
    key_a = WaybillTaskService.build_idempotency_key(payload, "dup-key", client_id=7)
    key_b = WaybillTaskService.build_idempotency_key(payload, "dup-key", client_id=8)
    assert key_a != key_b  # no cross-tenant collision (audit A1)


def test_build_task_payload_defaults_can_hold_correlation_context():
    payload = {"sender": {"name": "x"}, "receiver": {"name": "y"}}
    payload.setdefault("correlation_id", "corr-123")
    payload.setdefault("batch_id", "batch-123")

    assert payload["correlation_id"] == "corr-123"
    assert payload["batch_id"] == "batch-123"
