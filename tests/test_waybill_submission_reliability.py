from unittest.mock import AsyncMock, patch

import pytest

from app.rpa.contracts import SessionBundle, SubmitOutcome
from app.services.rpa_submit_service import SubmitAdapter


class _Response:
    status_code = 200
    text = '{"success": true, "data": {"trackingCode": "UTC-12345"}}'

    @staticmethod
    def json():
        return {"success": True, "data": {"trackingCode": "UTC-12345"}}


class _AsyncClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    post = AsyncMock(return_value=_Response())


@pytest.mark.asyncio
async def test_http_submit_adapter_preserves_tracking_code(monkeypatch):
    monkeypatch.setattr("app.services.rpa_submit_service.utcms_config.RPA_SUBMIT_ENDPOINT", "https://example.test")
    with patch("app.services.rpa_submit_service.httpx.AsyncClient", return_value=_AsyncClient()):
        result = await SubmitAdapter().execute({}, SessionBundle(user_agent="test"))

    assert result.classification.outcome == SubmitOutcome.SUCCESS
    assert result.raw_payload["tracking_code"] == "UTC-12345"


@pytest.mark.asyncio
async def test_http_submit_adapter_does_not_invent_tracking_code(monkeypatch):
    response = _Response()
    response.text = '{"success": true}'
    response.json = lambda: {"success": True}
    client = _AsyncClient()
    client.post = AsyncMock(return_value=response)

    monkeypatch.setattr("app.services.rpa_submit_service.utcms_config.RPA_SUBMIT_ENDPOINT", "https://example.test")
    with patch("app.services.rpa_submit_service.httpx.AsyncClient", return_value=client):
        result = await SubmitAdapter().execute({}, SessionBundle(user_agent="test"))

    assert result.classification.outcome == SubmitOutcome.SUCCESS
    assert "tracking_code" not in result.raw_payload
