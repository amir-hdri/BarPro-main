import asyncio
from sqlalchemy import text
from sqlmodel import select
from app.core.database import async_session_factory
from app.models_multitenant import WaybillJob, TaskStatus
from datetime import datetime, timezone

async def retry_job_109():
    async with async_session_factory() as session:
        job = (await session.exec(select(WaybillJob).where(WaybillJob.id == 109))).first()
        if not job:
            print("Job 109 not found!")
            return
        
        job.status = TaskStatus.WAITING_SUBMISSION_WINDOW.value
        job.mutation_status = "unattempted"
        job.celery_task_id = None
        job.last_error = None
        job.error_category = None
        job.result_json = None
        job.mutation_at = None
        job.submit_after = datetime.now(timezone.utc).replace(tzinfo=None)
        job.next_retry_at = datetime.now(timezone.utc).replace(tzinfo=None)
        
        await session.commit()
        print(f"✅ Job 109 status updated to {job.status}.")

    try:
        from app.services.rpa_dispatch_service import rpa_dispatch_service
        print("\n--- Triggering RPA Dispatch ---")
        dispatched = await rpa_dispatch_service.dispatch_phase1_due_jobs()
        print(f"Dispatched {len(dispatched)} decisions to Celery queues.")
        for d in dispatched:
            print(" ->", d)
    except Exception as e:
        print(f"Dispatch error: {e}")

if __name__ == "__main__":
    asyncio.run(retry_job_109())
