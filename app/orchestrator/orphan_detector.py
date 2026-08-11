import logging
import uuid
from datetime import UTC, datetime

from sqlmodel import select

from app.core.database import async_session_factory
from app.models_multitenant import TaskStatus, WaybillJob
from app.models_rpa import DispatchIntent, Execution
from app.orchestrator.driver_slot import release_driver_execution_slot
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

                    if not job:
                        orphaned_count += 1
                        continue

                    # Clear active execution slot. The execution was already
                    # moved to a terminal "orphaned" status above, so it is
                    # no longer live and the slot may be released safely.
                    if job.driver_id:
                        await release_driver_execution_slot(
                            session,
                            driver_id=job.driver_id,
                            expected_intent_id=exec_row.intent_id,
                        )

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
                                TaskStatus.QUEUED.value,
                            },
                        )
                        # Job is now unambiguously stuck in UNKNOWN. Only then a
                        # reconciliation intent makes sense: the dispatcher can
                        # claim it (unknown is claimable) and the reconcile
                        # worker will drive unknown -> reconciling -> outcome.
                        intent_id = str(uuid.uuid4())
                        intent = DispatchIntent(
                            intent_id=intent_id,
                            client_id=job.client_id,
                            job_id=job.job_id,
                            attempt_no=exec_row.attempt_no,
                            operation="reconciliation",
                            fencing_token=exec_row.fencing_token,
                            status="pending",
                        )
                        session.add(intent)
                        orphaned_count += 1
                    except StateTransitionError as transition_err:
                        # The job was already moved out of the runnable set by
                        # some other path (waiting_retry / needs_review /
                        # cancelled / dead_letter / ...). Do NOT create a
                        # reconciliation intent here: it would reference a job
                        # the state machine cannot claim, and the dispatcher
                        # would fail on it forever. The job's real owner is
                        # whoever moved it (the scheduler re-dispatches
                        # waiting_retry/otp_backoff/pending when they become
                        # due; review/manual flow owns the rest).
                        logger.warning(
                            "orphan_intent_skipped",
                            extra={
                                "extra_fields": {
                                    "job_id": job.job_id,
                                    "current_status": job.status,
                                    "execution_id": exec_row.id,
                                    "error": str(transition_err),
                                }
                            },
                        )

                await session.commit()
                if orphaned_count > 0:
                    logger.warning(f"OrphanDetector marked {orphaned_count} executions as orphaned.")
                return orphaned_count

            except Exception as e:
                logger.error(f"Orphan detector failed: {e}", exc_info=True)
                await session.rollback()
                raise


orphan_detector = OrphanDetector()