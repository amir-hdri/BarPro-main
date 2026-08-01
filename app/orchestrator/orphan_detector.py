import logging
import uuid
from datetime import UTC, datetime
from sqlmodel import select
from app.core.database import async_session_factory
from app.models_multitenant import WaybillJob, TaskStatus
from app.models_rpa import DispatchIntent, Execution
from app.orchestrator.state_machine import JobStateMachine, StateTransitionError

logger = logging.getLogger(__name__)


class OrphanDetector:
    async def run(self) -> int:
        """
        Scan for executions that have expired leases, mark them as orphaned,
        and schedule a reconciliation intent for the corresponding waybill job.
        Returns the number of orphaned executions detected.
        """
        async with async_session_factory() as session:
            try:
                now = datetime.now(UTC).replace(tzinfo=None)
                # Find running executions with expired leases
                statement = (
                    select(Execution)
                    .where(Execution.status == "running")
                    .where(Execution.lease_expires_at < now)
                    .with_for_update(skip_locked=True)
                )
                
                result = await session.exec(statement)
                stale_executions = result.all()
                
                if not stale_executions:
                    return 0

                orphaned_count = 0
                for exec_row in stale_executions:
                    # Update execution status to orphaned
                    exec_row.status = "orphaned"
                    exec_row.updated_at = now
                    session.add(exec_row)
                    
                    # Fetch waybill job
                    job_stmt = select(WaybillJob).where(WaybillJob.job_id == exec_row.job_id).with_for_update()
                    job_res = await session.exec(job_stmt)
                    job = job_res.first()
                    
                    if job:
                        # Clear active execution slot
                        from app.models_rpa import DriverRuntimeState
                        driver_stmt = select(DriverRuntimeState).where(DriverRuntimeState.driver_id == job.driver_id).with_for_update()
                        driver_res = await session.exec(driver_stmt)
                        driver_state = driver_res.first()
                        if driver_state:
                            driver_state.active_execution_id = None
                            session.add(driver_state)

                        # Move job status to unknown (meaning it needs reconciliation)
                        try:
                            JobStateMachine.transition(
                                session,
                                job,
                                TaskStatus.UNKNOWN.value,
                                expected_from={
                                    TaskStatus.RUNNING.value,
                                    TaskStatus.IN_PROGRESS.value,
                                    TaskStatus.CLAIMED.value,
                                    TaskStatus.QUEUED.value
                                }
                            )
                        except StateTransitionError as transition_err:
                            # Job is in an unexpected state (manual intervention or
                            # legacy data). Mark as unknown so reconciliation can take
                            # over. Logged loudly because this is never expected in
                            # steady-state operation.
                            logger.warning(
                                "orphan_unexpected_state_force_unknown",
                                extra={
                                    "extra_fields": {
                                        "job_id": job.job_id,
                                        "current_status": job.status,
                                        "error": str(transition_err),
                                    }
                                },
                            )
                            session.add(job)

                        # Create reconciliation intent
                        intent_id = str(uuid.uuid4())
                        intent = DispatchIntent(
                            intent_id=intent_id,
                            client_id=job.client_id,
                            job_id=job.job_id,
                            attempt_no=exec_row.attempt_no,
                            operation="reconciliation",
                            fencing_token=exec_row.fencing_token,
                            status="pending"
                        )
                        session.add(intent)
                        orphaned_count += 1
                        
                await session.commit()
                if orphaned_count > 0:
                    logger.warning(f"OrphanDetector marked {orphaned_count} executions as orphaned.")
                return orphaned_count
                
            except Exception as e:
                logger.error(f"Orphan detector failed: {e}", exc_info=True)
                await session.rollback()
                raise


orphan_detector = OrphanDetector()
