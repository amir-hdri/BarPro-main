import logging
from datetime import UTC, datetime
from sqlmodel import select
from app.core.database import async_session_factory
from app.models_multitenant import WaybillJob, TaskStatus
from app.models_rpa import DispatchIntent
from app.orchestrator.state_machine import JobStateMachine
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


class DispatcherService:
    async def run(self) -> int:
        """
        Scan for pending dispatch intents, mark them as claimed, transition
        the corresponding waybill job to claimed status, and trigger the celery worker task.
        Returns the number of dispatched intents.
        """
        async with async_session_factory() as session:
            try:
                # Select pending intents with FOR UPDATE SKIP LOCKED
                statement = (
                    select(DispatchIntent)
                    .where(DispatchIntent.status == "pending")
                    .order_by(DispatchIntent.created_at.asc())
                    .with_for_update(skip_locked=True)
                )
                
                result = await session.exec(statement)
                pending_intents = result.all()
                
                if not pending_intents:
                    return 0

                dispatched_count = 0
                for intent in pending_intents:
                    # Fetch corresponding job to transition
                    job_statement = select(WaybillJob).where(WaybillJob.job_id == intent.job_id).with_for_update()
                    job_result = await session.exec(job_statement)
                    job = job_result.first()
                    
                    if not job:
                        logger.error(f"Job {intent.job_id} not found for dispatch intent {intent.intent_id}")
                        intent.status = "failed"
                        session.add(intent)
                        continue
                        
                    # Claim the intent
                    intent.status = "claimed"
                    intent.updated_at = datetime.now(UTC).replace(tzinfo=None)
                    session.add(intent)
                    
                    # Transition job to claimed
                    JobStateMachine.transition(session, job, TaskStatus.CLAIMED.value)
                    
                    # Send Celery task
                    if celery_app is not None:
                        if intent.operation == "reconciliation":
                            task_name = "barpro.waybill.reconcile"
                            base_queue = "reconciliation_tasks"
                        else:
                            task_name = "barpro.waybill.execute"
                            base_queue = "waybill_tasks"

                        from app.core.circuit_breaker import get_routed_queue
                        routed_queue = get_routed_queue(base_queue)

                        celery_app.send_task(
                            task_name,
                            args=[intent.intent_id],
                            queue=routed_queue,
                            priority=job.priority or 5
                        )
                        dispatched_count += 1
                    else:
                        logger.warning("Celery app not initialized, cannot dispatch task")
                        intent.status = "failed"
                        session.add(intent)
                        # Recover: free driver slot and revert job so scheduler can retry later
                        if job.driver_id:
                            from app.models_rpa import DriverRuntimeState
                            ds_stmt = select(DriverRuntimeState).where(DriverRuntimeState.driver_id == job.driver_id).with_for_update()
                            ds_res = await session.exec(ds_stmt)
                            ds = ds_res.first()
                            if ds:
                                ds.active_execution_id = None
                                session.add(ds)
                        JobStateMachine.transition(
                            session, job, TaskStatus.WAITING_RETRY.value,
                            next_retry_at=datetime.now(UTC).replace(tzinfo=None),
                            last_error="Celery unavailable during dispatch",
                            error_category="system_error",
                        )
                        
                await session.commit()
                if dispatched_count > 0:
                    logger.info(f"Dispatched {dispatched_count} intents to Celery.")
                return dispatched_count
                
            except Exception as e:
                logger.error(f"Dispatcher run failed: {e}", exc_info=True)
                await session.rollback()
                raise


dispatcher_service = DispatcherService()
