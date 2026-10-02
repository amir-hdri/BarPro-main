"""Read-only waybill API workflow using the supported resilience interfaces.

Run ``python -m examples.enterprise_waybill_example`` for an offline demo.
The demo uses httpx.MockTransport and performs no UTCMS or BarPro mutation.
For an application integration, supply an AsyncClient with the tenant's existing
httpOnly authentication cookie. Job status is reported as returned by BarPro;
this example does not claim or independently verify final UTCMS registration.
"""

import asyncio
import json
from typing import Any
from urllib.parse import quote

import httpx

from app.core.exceptions import ErrorCode, UTCMSException
from app.core.resilience import WorkflowState, resilient_step


@resilient_step(max_retries=2, error_code=ErrorCode.NET_TIMEOUT.value)
async def fetch_waybill_status(client: httpx.AsyncClient, job_id: str) -> dict[str, Any]:
    """Read one job; retry only transient failures of this read-only request."""
    if not job_id.strip():
        raise ValueError("job_id must be non-empty")

    try:
        response = await client.get(f"/api/v1/waybill-jobs/{quote(job_id, safe='')}", timeout=15.0)
    except httpx.TimeoutException as exc:
        raise UTCMSException(
            "Waybill status request timed out",
            error_code=ErrorCode.NET_TIMEOUT,
            status_code=503,
            retryable=True,
        ) from exc

    if response.status_code == 401:
        raise UTCMSException(
            "An authenticated BarPro session is required",
            error_code=ErrorCode.AUTH_SESSION_EXPIRED,
            status_code=401,
        )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Expected a waybill job object")
    return payload


async def inspect_waybill_workflow(client: httpx.AsyncClient, job_id: str) -> dict[str, Any]:
    """Track the status lookup without submitting, retrying, or changing a job."""
    workflow = WorkflowState(workflow_id="waybill-status-example", workflow_name="Read waybill status")
    workflow.start()
    step = workflow.add_step("fetch_status")
    workflow.current_step = step.step_name
    step.start()

    try:
        job = await fetch_waybill_status(client, job_id)
    except Exception as exc:
        code = getattr(exc, "error_code", ErrorCode.INTERNAL_ERROR)
        message = "Waybill status lookup failed"
        step.fail(error_code=str(code), error_message=message)
        workflow.fail(error_code=str(code), error_message=message)
        return {"lookup_succeeded": False, "workflow": workflow.to_dict()}

    step.complete()
    workflow.complete()
    return {"lookup_succeeded": True, "job": job, "workflow": workflow.to_dict()}


async def main() -> None:
    """Exercise the example with a local response and no network connection."""

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"job_id": "example-job", "status": "unknown"}, request=request)

    async with httpx.AsyncClient(base_url="https://barpro.example", transport=httpx.MockTransport(respond)) as client:
        result = await inspect_waybill_workflow(client, "example-job")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
