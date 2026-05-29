from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.models_multitenant import TaskStatus, WaybillJob
from app.models_rpa import DriverRuntimeState, DriverRuntimeStateValue
from app.services.rpa_run_isolation import prepare_live_run_isolation
from app.services.rpa_runtime_service import rpa_runtime


@pytest.mark.asyncio
async def test_prepare_live_run_isolation_clears_locks_and_job_state():
    client_id = 101
    driver_id = 202
    now = datetime.now(UTC).replace(tzinfo=None)
    job = WaybillJob(
        job_id="job-live-1",
        idempotency_key="idem-live-1",
        client_id=client_id,
        driver_id=driver_id,
        payload_json="{}",
        status=TaskStatus.WAITING_AUTH.value,
        celery_task_id="celery-123",
        worker_id="worker-a",
        started_at=now,
        finished_at=now,
        submit_after=now + timedelta(minutes=5),
        next_retry_at=now + timedelta(minutes=15),
    )
    runtime_state = DriverRuntimeState(
        client_id=client_id,
        driver_id=driver_id,
        state=DriverRuntimeStateValue.SUBMITTING.value,
        next_retry_at=now + timedelta(minutes=15),
    )

    with patch.object(rpa_runtime, "_get_redis", new=AsyncMock(return_value=None)):
        rpa_runtime._memory.clear()
        await rpa_runtime.acquire_lock(rpa_runtime.auth_lock_key(client_id, driver_id), 30)
        await rpa_runtime.acquire_lock(rpa_runtime.submit_lock_key(client_id, driver_id), 30)

        result = await prepare_live_run_isolation(
            client_id=client_id,
            driver_id=driver_id,
            job=job,
            runtime_state=runtime_state,
        )

        assert job.status == TaskStatus.PENDING.value
        assert job.celery_task_id is None
        assert job.worker_id is None
        assert job.started_at is None
        assert job.finished_at is None
        assert job.next_retry_at is None
        assert runtime_state.state == DriverRuntimeStateValue.READY.value
        assert runtime_state.next_retry_at is None
        assert result["job_status"] == TaskStatus.PENDING.value
        assert await rpa_runtime._get_value(rpa_runtime.auth_lock_key(client_id, driver_id)) is None
        assert await rpa_runtime._get_value(rpa_runtime.submit_lock_key(client_id, driver_id)) is None
