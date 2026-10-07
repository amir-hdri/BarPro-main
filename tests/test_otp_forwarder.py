import json as _json

import pytest
from fastapi import Request as _Request
from fastapi.exceptions import HTTPException as _HTTPException

from app.api.routes.otp_forwarder import clean_phone_number, extract_otp_code, normalize_to_english_digits


def test_normalize_digits():
    assert normalize_to_english_digits("۱۲۳۴۵۶۷۸۹۰") == "1234567890"
    assert normalize_to_english_digits("١٢٣٤٥٦٧٨٩٠") == "1234567890"
    assert normalize_to_english_digits("123abc456") == "123abc456"


def test_extract_otp_code_persian_messages():
    # Real UTCMS / Iranian gateway SMS messages
    msg1 = "کد تایید صدور بارنامه شما: ۵۴۳۲۱"
    assert extract_otp_code(msg1) == "54321"

    msg2 = "سامانه بارنامه شهرداری\nکد تایید: 123456\nانقضا: ۲ دقیقه"
    assert extract_otp_code(msg2) == "123456"

    msg3 = "کد ورود شما: 98765"
    assert extract_otp_code(msg3) == "98765"

    msg4 = "رمز یکبار مصرف: ۴۳۲۱۵"
    assert extract_otp_code(msg4) == "43215"

    msg5 = "کد فعالسازی 876543 برای بارنامه شهرداری"
    assert extract_otp_code(msg5) == "876543"

    msg6 = "کد: 65432"
    assert extract_otp_code(msg6) == "65432"

    # Message with year and date
    msg7 = "در تاریخ 1404/06/30 کد تایید شما 33221 می باشد"
    assert extract_otp_code(msg7) == "33221"

    # Expanded Iranian / UTCMS keyword variations
    msg8 = "کد صدور بارنامه: 77889"
    assert extract_otp_code(msg8) == "77889"

    msg9 = "کد یکبار مصرف جهت صدور بارنامه: 99112"
    assert extract_otp_code(msg9) == "99112"

    msg10 = "کد امنیتی ورود: 33445"
    assert extract_otp_code(msg10) == "33445"

    msg11 = "رمز تایید صدور: 66554"
    assert extract_otp_code(msg11) == "66554"


def test_clean_phone_number():
    assert clean_phone_number("09123612956") == "09123612956"
    assert clean_phone_number("+989123612956") == "09123612956"
    assert clean_phone_number("۹۸۹۱۲۳۶۱۲۹۵۶") == "09123612956"
    assert clean_phone_number("20007777") == "20007777"


@pytest.mark.asyncio
async def test_submit_manual_otp_delegates_to_authorized_service():
    from types import SimpleNamespace
    from unittest.mock import ANY, AsyncMock, patch

    from app.api.routes.otp_forwarder import ManualOtpRequest, submit_manual_otp

    context = {"role": "master_admin"}
    service = AsyncMock(return_value=SimpleNamespace(status="unknown"))
    with patch("app.services.waybill_job_service.WaybillJobService.submit_otp", service):
        req = ManualOtpRequest(code="۵۴۳۲۱", phone="09121234567", job_id="job-test-123")
        res = await submit_manual_otp(req, user_context=context)

    assert res["status"] == "accepted"
    assert res["job_status"] == "unknown"
    assert "code" not in res  # codes must not be echoed back in API responses
    assert res["job_id"] == "job-test-123"
    service.assert_awaited_once_with(user_context=context, job_id="job-test-123", session=ANY, otp_code="54321")


# ── Webhook authentication (C2 fix) ────────────────────────────────────────────


def _make_request(headers: dict | None = None, body: bytes = b"") -> _Request:
    scope = {
        "type": "http",
        "method": "POST",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return _Request(scope, receive)


def _webhook_body() -> bytes:
    return _json.dumps(
        {"content": "کد تایید صدور بارنامه: 54321", "from": "20007777", "driver_phone": "09120000001"}
    ).encode()


@pytest.mark.asyncio
async def test_webhook_rejects_missing_token(monkeypatch):
    from app.api.routes import otp_forwarder
    from app.core.config import utcms_config

    monkeypatch.setattr(utcms_config, "OTP_WEBHOOK_SECRET", "test-secret")
    request = _make_request(body=_webhook_body())
    with pytest.raises(_HTTPException) as exc_info:
        await otp_forwarder.receive_sms_forwarder_webhook(request)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_webhook_rejects_wrong_token(monkeypatch):
    from app.api.routes import otp_forwarder
    from app.core.config import utcms_config

    monkeypatch.setattr(utcms_config, "OTP_WEBHOOK_SECRET", "test-secret")
    request = _make_request(headers={"X-OTP-Webhook-Token": "wrong"}, body=_webhook_body())
    with pytest.raises(_HTTPException) as exc_info:
        await otp_forwarder.receive_sms_forwarder_webhook(request)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_webhook_fails_closed_when_secret_unconfigured(monkeypatch):
    from app.api.routes import otp_forwarder
    from app.core.config import utcms_config

    monkeypatch.setattr(utcms_config, "OTP_WEBHOOK_SECRET", "")
    request = _make_request(headers={"X-OTP-Webhook-Token": "anything"}, body=_webhook_body())
    with pytest.raises(_HTTPException) as exc_info:
        await otp_forwarder.receive_sms_forwarder_webhook(request)
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_webhook_accepts_valid_token_and_never_logs_code(monkeypatch, caplog):
    from unittest.mock import AsyncMock, patch

    from app.api.routes import otp_forwarder
    from app.core.config import utcms_config

    monkeypatch.setattr(utcms_config, "OTP_WEBHOOK_SECRET", "test-secret")
    mock_redis = AsyncMock()
    request = _make_request(headers={"X-OTP-Webhook-Token": "test-secret"}, body=_webhook_body())
    with (
        patch("app.core.redis_client.redis_manager.get", new_callable=AsyncMock, return_value=mock_redis),
        caplog.at_level("INFO", logger="app.api.routes.otp_forwarder"),
    ):
        res = await otp_forwarder.receive_sms_forwarder_webhook(request)

    assert res["status"] == "success"
    assert "code" not in res  # codes must not be echoed back in API responses
    assert mock_redis.eval.await_count == 1
    # H2: the OTP code must never appear in logs.
    assert "54321" not in caplog.text


def _dep_names(route) -> set[str]:
    """Qualified names of a route's dependencies.

    Compared by qualname (not object identity) so the check survives module
    reloads or duplicate imports that would otherwise create a second, distinct
    function object for the same dependency.
    """
    return {f"{d.call.__module__}.{d.call.__qualname__}" for d in route.dependant.dependencies}


_AUTH_DEP = "app.auth_multitenant.get_current_user_or_admin"


def test_sensitive_otp_routes_require_auth():
    """OTP routes must carry JWT auth dependencies.

    GET /latest remains admin-only for legacy diagnostic keys even though
    current intake never writes them. POST /submit-manual keeps the
    user-or-admin dependency and enforces job ownership in the handler
    (tenant-isolation GAP-2).
    """
    from app.api.routes import otp_forwarder

    expected_deps = {
        "/api/v1/otp/latest": "app.auth_multitenant.get_current_admin",
        "/api/v1/otp/submit-manual": _AUTH_DEP,
    }
    seen = set()
    for route in otp_forwarder.router.routes:
        path = getattr(route, "path", "")
        if path in expected_deps:
            seen.add(path)
            assert expected_deps[path] in _dep_names(route), f"{path} is missing auth dependency"
    assert seen == set(expected_deps)


def test_webhook_routes_use_token_auth_not_jwt():
    """The forwarder webhooks use the shared token header (dumb apps can't do JWT)."""
    from app.api.routes import otp_forwarder

    webhook_paths = {"/api/v1/otp/sms-forwarder", "/api/v1/otp/webhook"}
    seen = set()
    for route in otp_forwarder.router.routes:
        path = getattr(route, "path", "")
        if path in webhook_paths:
            seen.add(path)
            assert _AUTH_DEP not in _dep_names(route), f"{path} must not require JWT"
    assert seen == webhook_paths


def test_dep_name_check_survives_duplicate_module_import():
    """Regression: the auth-dependency check must not depend on function-object
    identity. If app.auth_multitenant is ever imported twice (e.g. under two
    different module paths by an order-dependent test polluter), the route's
    dependency is a *different object* with the same qualified name — the
    check must still recognize it."""
    import types

    # A distinct function object, masquerading as the real auth dependency
    # exactly as a duplicate module import would produce.
    fake_mod = types.ModuleType("app.auth_multitenant")
    exec(
        "async def get_current_user_or_admin():\n    return None",
        fake_mod.__dict__,
    )
    dup_fn = fake_mod.get_current_user_or_admin
    assert dup_fn.__module__ == "app.auth_multitenant"
    assert dup_fn.__qualname__ == "get_current_user_or_admin"

    from app.auth_multitenant import get_current_user_or_admin as real_fn

    assert dup_fn is not real_fn  # the polluter scenario: identity differs

    class FakeDep:
        """Mimics FastAPI's processed dependency object (exposes .call)."""

        def __init__(self, call):
            self.call = call

    class FakeRoute:
        dependant = type("D", (), {"dependencies": [FakeDep(dup_fn)]})()

    # Identity-based check would fail here; qualname-based check must pass.
    assert _AUTH_DEP in _dep_names(FakeRoute())


@pytest.mark.asyncio
async def test_webhook_ignored_sms_never_echoes_content(monkeypatch):
    """Non-OTP SMS responses must not include the message content (no preview)."""
    from unittest.mock import AsyncMock, patch

    from app.api.routes import otp_forwarder
    from app.core.config import utcms_config

    monkeypatch.setattr(utcms_config, "OTP_WEBHOOK_SECRET", "test-secret")
    body = _json.dumps({"content": "سلام، این یک پیام تبلیغاتی بدون کد است", "from": "20007777"}).encode()
    request = _make_request(headers={"X-OTP-Webhook-Token": "test-secret"}, body=body)
    mock_redis = AsyncMock()
    with patch("app.core.redis_client.redis_manager.get", new_callable=AsyncMock, return_value=mock_redis):
        res = await otp_forwarder.receive_sms_forwarder_webhook(request)

    assert res["status"] == "ignored"
    assert "preview" not in res
    assert "تبلیغاتی" not in _json.dumps(res, ensure_ascii=False)
    assert res["content_length"] == len("سلام، این یک پیام تبلیغاتی بدون کد است")
