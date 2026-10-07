"""Regression contracts for tenant-safe manual OTP and truthful setup readiness."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, Request

from app.api.routes import otp_forwarder as routes
from app.services.waybill_job_service import WaybillJobService


def request(query=b"", headers=()):
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/otp/sms-forwarder",
            "query_string": query,
            "headers": list(headers),
        }
    )


@pytest.mark.parametrize("parameter", ["token", "secret"])
def test_query_credentials_never_authenticate_webhook(monkeypatch, parameter):
    monkeypatch.setattr(routes.utcms_config, "OTP_WEBHOOK_SECRET", "synthetic-header-secret")
    with pytest.raises(HTTPException) as error:
        routes._require_webhook_auth(request(f"{parameter}=synthetic-header-secret".encode()))
    assert error.value.status_code == 401


def test_header_auth_remains_supported(monkeypatch):
    monkeypatch.setattr(routes.utcms_config, "OTP_WEBHOOK_SECRET", "synthetic-header-secret")
    routes._require_webhook_auth(request(headers=((b"x-otp-webhook-token", b"synthetic-header-secret"),)))


async def test_health_requires_configured_secret_and_storage(monkeypatch):
    redis = SimpleNamespace(ping=AsyncMock(return_value=True))
    monkeypatch.setattr(routes.redis_manager, "get", AsyncMock(return_value=redis))
    monkeypatch.setattr(routes.utcms_config, "OTP_WEBHOOK_SECRET", "")
    result = await routes.health_otp_service(request())
    assert result["status"] == "degraded"
    assert result["redis_connected"] is True
    assert result["token_configured"] is False
    assert result["intake_ready"] is False


async def test_manual_job_uses_authorized_durable_submission_service(monkeypatch):
    session = MagicMock()
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=session)
    manager.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(routes, "async_session_factory", lambda: manager)
    submit = AsyncMock(return_value=SimpleNamespace(status="unknown"))
    monkeypatch.setattr(WaybillJobService, "submit_otp", submit)
    monkeypatch.setattr(routes, "accept_forwarded_otp", AsyncMock(return_value={}))
    monkeypatch.setattr(routes.redis_manager, "get", AsyncMock(return_value=AsyncMock()))
    monkeypatch.setattr("app.services.otp_wakeup_consumer.trigger_job_completion_on_otp_received", MagicMock())
    context = {"role": "client", "user": SimpleNamespace(id=11)}
    result = await routes.submit_manual_otp(
        routes.ManualOtpRequest(job_id="own-job", phone="09120000099", code="۱۲۳۴۵"), context
    )
    submit.assert_awaited_once_with(user_context=context, job_id="own-job", session=session, otp_code="12345")
    assert result["status"] == "accepted"
    assert result["job_status"] == "unknown"
    assert "code" not in result
    routes.accept_forwarded_otp.assert_not_awaited()


async def test_manual_foreign_job_does_not_write_or_schedule(monkeypatch):
    session = MagicMock()
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=session)
    manager.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(routes, "async_session_factory", lambda: manager)
    monkeypatch.setattr(WaybillJobService, "submit_otp", AsyncMock(side_effect=HTTPException(404, "Job not found")))
    store = AsyncMock()
    monkeypatch.setattr(routes, "accept_forwarded_otp", store)
    context = {"role": "client", "user": SimpleNamespace(id=11)}
    with pytest.raises(HTTPException) as error:
        await routes.submit_manual_otp(routes.ManualOtpRequest(job_id="foreign-job", code="12345"), context)
    assert error.value.status_code == 404
    store.assert_not_awaited()


async def test_forwarder_config_scopes_driver_and_never_returns_secret(monkeypatch):
    factory = MagicMock()
    session = MagicMock()
    factory.__aenter__ = AsyncMock(return_value=session)
    factory.__aexit__ = AsyncMock(return_value=None)
    driver = SimpleNamespace(id=42, phone="09120000042", client_id=11)
    session.exec = AsyncMock(return_value=SimpleNamespace(first=lambda: driver))
    monkeypatch.setattr(routes, "async_session_factory", lambda: factory)
    monkeypatch.setattr(
        routes.redis_manager, "get", AsyncMock(return_value=SimpleNamespace(ping=AsyncMock(return_value=True)))
    )
    monkeypatch.setattr(routes.utcms_config, "OTP_WEBHOOK_SECRET", "never-return-this-secret")
    result = await routes.get_driver_forwarder_config(42, {"role": "client", "user": SimpleNamespace(id=11)})
    statement = str(session.exec.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "drivers.client_id = 11" in statement
    assert "drivers.id = 42" in statement
    assert result["webhook_path"] == "/api/v1/otp/sms-forwarder/09120000042"
    assert result["intake_ready"] is True
    assert result["forwarder_connection_verified"] is False
    assert "never-return-this-secret" not in str(result)


async def test_forwarder_config_hides_foreign_driver(monkeypatch):
    factory = MagicMock()
    session = MagicMock()
    factory.__aenter__ = AsyncMock(return_value=session)
    factory.__aexit__ = AsyncMock(return_value=None)
    session.exec = AsyncMock(return_value=SimpleNamespace(first=lambda: None))
    monkeypatch.setattr(routes, "async_session_factory", lambda: factory)
    with pytest.raises(HTTPException) as error:
        await routes.get_driver_forwarder_config(42, {"role": "client", "user": SimpleNamespace(id=11)})
    assert error.value.status_code == 404
