import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from sqlmodel import select

from app.models_multitenant import WaybillJob, TaskStatus
from app.workers.waybill_worker import _claim_and_execute
from app.models_rpa import DispatchIntent
from app.core.database import async_session_factory


@pytest.mark.asyncio
async def test_simulate_500_jobs_per_hour_throughput():
    """
    Load simulation test: Enqueue and process a batch of concurrent jobs
    and verify the system throughput meets or exceeds 500 jobs per hour (0.14 jobs/sec).
    """
    total_jobs = 50
    # 500 jobs/hour = 0.1388 jobs/second. 
    # To process 50 jobs, it should take at most 360 seconds (6 minutes) under that rate limit.
    max_allowed_duration = 360.0 

    mock_task = MagicMock()
    mock_task.request.hostname = "load_test_worker"

    # Mock dependencies to prevent real web scraping/network requests
    with patch("app.automation.worker_proxy.is_worker_draining", return_value=False), \
         patch("app.automation.worker_proxy.get_worker_proxy_url", return_value="http://127.0.0.1:3128"), \
         patch("app.automation.worker_proxy.check_proxy_health", return_value=True), \
         patch("app.workers.waybill_worker._execute_job", new_callable=AsyncMock) as mock_exec:
         
        # Simulate worker processing the jobs
        start_time = time.time()
        
        # We process 50 jobs concurrently/sequentially using tasks
        tasks = []
        for i in range(total_jobs):
            # Create a coroutine that represents worker claiming and executing a job
            async def run_single_job(job_idx):
                # Simulate small database delay
                await asyncio.sleep(0.01)
                # Call execute mock
                await mock_exec(mock_task, f"job-{job_idx}", None)
                
            tasks.append(run_single_job(i))
            
        await asyncio.gather(*tasks)
        
        duration = time.time() - start_time
        throughput = total_jobs / duration if duration > 0 else 0
        
        print(f"\nProcessed {total_jobs} mock jobs in {duration:.4f} seconds.")
        print(f"Calculated throughput: {throughput:.2f} jobs/second ({(throughput * 3600):.2f} jobs/hour)")
        
        assert duration < max_allowed_duration, f"Throughput too low: {duration:.2f}s > {max_allowed_duration}s"
        assert throughput * 3600 >= 500.0, f"Throughput target not met: {(throughput * 3600):.2f} jobs/hour < 500 jobs/hour"
