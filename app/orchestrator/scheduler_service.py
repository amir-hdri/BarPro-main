import logging
import uuid
from datetime import datetime, UTC
from sqlmodel import select
from app.core.database import async_session_factory
from app.models_multitenant import WaybillJob, TaskStatus
from app.models_rpa import DispatchIntent, DriverRuntimeState
from app.orchestrator.state_machine import JobStateMachine

logger = logging.getLogger(__name__)


class SchedulerService:
    async def run(self) -> int:
        """
        Scan for pending, waiting_retry, and otp_backoff jobs that are ready to run,
        and whose driver does not have an active execution slot.
        Mark them as queued, lock their driver's slot, and insert corresponding dispatch intents.
        Returns the number of scheduled jobs.
        """
        async with async_session_factory() as session:
            try:
                # Query due jobs with skip_locked, joining with DriverRuntimeState to verify slot is free
                now = datetime.now(UTC).replace(tzinfo=None)
                statement = (
                    select(WaybillJob)
                    .join(DriverRuntimeState, WaybillJob.driver_id == DriverRuntimeState.driver_id)
                    .where(DriverRuntimeState.active_execution_id == None)
                    .where(
                        WaybillJob.status.in_([
                            TaskStatus.PENDING.value,
                            TaskStatus.WAITING_RETRY.value,
                            TaskStatus.OTP_BACKOFF.value
                        ])
                    )
                    .where(
                        (WaybillJob.next_retry_at == None) | (WaybillJob.next_retry_at <= now)
                    )
                    .order_by(WaybillJob.priority.desc(), WaybillJob.created_at.sa_column.asc() if hasattr(WaybillJob.created_at, "sa_column") else WaybillJob.created_at.asc())
                    .with_for_update(skip_locked=True)
                )
                
                result = await session.exec(statement)
                due_jobs = result.all()
                
                if not due_jobs:
                    return 0

                scheduled_count = 0
                scheduled_driver_ids = set()
                for job in due_jobs:
                    if job.driver_id in scheduled_driver_ids:
                        continue
                    
                    # Create dispatch intent
                    intent_id = str(uuid.uuid4())
                    attempt_no = job.attempt_count + 1
                    
                    intent = DispatchIntent(
                        intent_id=intent_id,
                        client_id=job.client_id,
                        job_id=job.job_id,
                        attempt_no=attempt_no,
                        operation="submit",
                        fencing_token=attempt_no,
                        status="pending"
                    )
                    session.add(intent)
                    
                    # Set the active execution slot on the driver runtime state
                    driver_state_stmt = select(DriverRuntimeState).where(DriverRuntimeState.driver_id == job.driver_id).with_for_update()
                    driver_state_res = await session.exec(driver_state_stmt)
                    driver_state = driver_state_res.first()
                    if driver_state:
                        driver_state.active_execution_id = intent_id
                        session.add(driver_state)
                    
                    # Transition job to queued status
                    JobStateMachine.transition(session, job, TaskStatus.QUEUED.value)
                    scheduled_driver_ids.add(job.driver_id)
                    scheduled_count += 1
                    
                await session.commit()
                if scheduled_count > 0:
                    logger.info(f"Scheduled {scheduled_count} jobs as pending dispatch intents.")
                return scheduled_count
                
            except Exception as e:
                logger.error(f"Scheduler run failed: {e}", exc_info=True)
                await session.rollback()
                raise


scheduler_service = SchedulerService()
