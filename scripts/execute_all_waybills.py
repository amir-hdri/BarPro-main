"""Reset and trigger end-to-end execution of all pending waybill jobs via the orchestrator pipeline."""
import asyncio
from datetime import datetime, timezone
from sqlalchemy import text
from sqlmodel import select
from app.core.database import async_session_factory
from app.models_multitenant import WaybillJob, Driver, DriverPlate, TaskStatus
from app.models_rpa import DriverRuntimeState, DispatchIntent
from app.orchestrator.scheduler_service import scheduler_service
from app.orchestrator.dispatcher_service import dispatcher_service

async def main():
    async with async_session_factory() as session:
        print("=== 1. Resetting Driver Slots & Intent Queue ===")
        # Release any stuck active execution slots
        await session.exec(text("UPDATE driver_runtime_states SET active_execution_id = NULL;"))
        # Clear old dispatch intents
        await session.exec(text("DELETE FROM dispatch_intents;"))
        # Set all remaining waybill jobs to pending
        await session.exec(text("UPDATE waybill_jobs SET status = 'pending', error_category = NULL, last_error = NULL, terminal_reason = NULL, retryable = true, next_retry_at = NULL, submit_after = NULL, attempt_count = 0, started_at = NULL, finished_at = NULL, celery_task_id = NULL, worker_id = NULL;"))
        await session.commit()
        print("✅ Slots released and jobs reset to PENDING.")

    # 2. Run Orchestrator Scheduler
    print("\n=== 2. Running Orchestrator Scheduler ===")
    scheduled_count = await scheduler_service.run()
    print(f"✅ Scheduler created {scheduled_count} dispatch intents.")

    # 3. Run Orchestrator Dispatcher
    print("\n=== 3. Running Orchestrator Dispatcher ===")
    dispatched_count = await dispatcher_service.run()
    print(f"✅ Dispatcher sent {dispatched_count} intents to worker queues (barpro.waybill.execute).")

    # 4. Check Initial Status
    async with async_session_factory() as session:
        jobs = (await session.exec(select(WaybillJob).order_by(WaybillJob.id))).all()
        print(f"\n=== 4. Jobs Status After Dispatch ({len(jobs)} total) ===")
        for j in jobs:
            print(f"Job {j.id} (Driver ID: {j.driver_id}) -> Status: {j.status}, Celery Task: {j.celery_task_id}")

if __name__ == "__main__":
    asyncio.run(main())
