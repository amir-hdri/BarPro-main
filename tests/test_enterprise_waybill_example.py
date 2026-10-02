from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.exceptions import UTCMSException
from examples.enterprise_waybill_example import fetch_waybill_status, inspect_waybill_workflow


async def test_example_reads_one_job_without_promoting_unknown_status() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"job_id": "job-1", "status": "unknown"})

    async with httpx.AsyncClient(base_url="https://barpro.example", transport=httpx.MockTransport(respond)) as client:
        result = await inspect_waybill_workflow(client, "job-1")

    assert [(request.method, request.url.path) for request in requests] == [("GET", "/api/v1/waybill-jobs/job-1")]
    assert result["lookup_succeeded"] is True
    assert result["job"]["status"] == "unknown"
    assert result["workflow"]["status"] == "completed"


async def test_example_authentication_error_is_serializable_and_not_retried() -> None:
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401)

    async with httpx.AsyncClient(base_url="https://barpro.example", transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(UTCMSException) as caught:
            await fetch_waybill_status(client, "job-1")

    assert calls == 1
    assert caught.value.status_code == 401
    assert caught.value.to_dict() == {
        "error": "AUTH_SESSION_EXPIRED",
        "message": "An authenticated BarPro session is required",
        "retryable": False,
    }


async def test_example_timeout_retries_only_the_status_read() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise httpx.ReadTimeout("simulated read timeout", request=request)

    async with httpx.AsyncClient(base_url="https://barpro.example", transport=httpx.MockTransport(respond)) as client:
        with patch("app.core.resilience.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(UTCMSException) as caught:
                await fetch_waybill_status(client, "job-1")

    assert len(requests) == 3
    assert all(request.method == "GET" for request in requests)
    assert caught.value.to_dict()["error"] == "NET_TIMEOUT"
    assert caught.value.retryable is True


async def test_example_records_a_failed_lookup_without_a_job_result() -> None:
    async with httpx.AsyncClient(
        base_url="https://barpro.example", transport=httpx.MockTransport(lambda request: httpx.Response(401))
    ) as client:
        result = await inspect_waybill_workflow(client, "job-1")

    assert result["lookup_succeeded"] is False
    assert "job" not in result
    assert result["workflow"]["status"] == "failed"
    assert result["workflow"]["error_code"] == "AUTH_SESSION_EXPIRED"
