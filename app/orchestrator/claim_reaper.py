"""
Claim Reaper: recovers jobs stuck in CLAIMED status without a corresponding
Execution or Celery task running.
"""

import logging
from datetime import UTC, datetime, timedelta
from sqlmodel import select
from app.core.database import async_session_factory
from app.models_multitenant import WaybillJob, TaskStatus
from app.models_rpa import DispatchIntent, Execution, DriverRuntimeState
from app.orchestrator.state_machine import JobStateMachine, StateTransitionError

logger = logging.getLogger(__name__)

# How long a job can stay in CLAIMED before being considered abandoned
CLAIMED_STALE_THRESHOLD = timedelta(minutes=5)


class ClaimReaper:
    async def run(self) -> int:
        """
        Scan for jobs in CLAIMED status that have been there longer than
        CLAIMED_STALE_THRESHOLD and don't have an active Execution.
        Recover them by clearing driver slot and transitioning to WAITING_RETRY.
        Returns the number of reclaimed jobs.
        """
        async with async_session_factory() as session:
            try:
                now = datetime.now(UTC).replace(tzinfo=None)
                threshold = now - CLAIMED_STALE_THRESHOLD

                # Find claimed jobs older than threshold
                statement = (
                    select(WaybillJob)
                    .where(WaybillJob.status == TaskStatus.CLAIMED.value)
                    .where(WaybillJob.updated_at < threshold)
                    .with_for_update(skip_locked=True)
                )

                result = await session.exec(statement)
                stale_claimed_jobs = result.all()

                if not stale_claimed_jobs:
                    return 0

                reclaimed_count = 0
                for job in stale_claimed_jobs:
                    # Check if there's an active Execution for this job
                    exec_stmt = select(Execution).where(
                        Execution.job_id == job.job_id,
                        Execution.status.in_(["pending", "running"])
                    )
                    exec_res = await session.exec(exec_stmt)
                    active_execution = exec_res.first()

                    if active_execution:
                        # Job has an active execution, skip
                        continue

                    # Check if there's a pending/claimed DispatchIntent for this job
                    intent_stmt = select(DispatchIntent).where(
                        DispatchIntent.job_id == job.job_id,
                        DispatchIntent.status.in_(["pending", "claimed"])
                    )
                    intent_res = await session.exec(intent_stmt)
                    active_intent = intent_res.first()

                    if active_intent:
                        # Job has a dispatch intent, skip
                        continue

                    # No execution and no intent - this is a truly orphaned claimed job
                    # Clear driver slot
                    if job.driver_id:
                        driver_stmt = select(DriverRuntimeState).where(
                            DriverRuntimeState.driver_id == job.driver_id
                        ).with_for_update()
                        driver_res = await session.exec(driver_stmt)
                        driver_state = driver_res.first()
                        if driver_state:
                            driver_state.active_execution_id = None
                            session.add(driver_state)

                    # Transition job to WAITING_RETRY so scheduler can pick it up
                    try:
                        JobStateMachine.transition(
                            session,
                            job,
                            TaskStatus.WAITING_RETRY.value,
                            expected_from={TaskStatus.CLAIMED.value},
                            next_retry_at=now,
                            last_error="Claim reaper: job was in CLAIMED without execution or intent",
                            error_category="system_error",
                        )
                    except StateTransitionError as transition_err:
                        logger.warning(
                            "claim_reaper_unexpected_state",
                            extra={
                                "extra_fields": {
                                    "job_id": job.job_id,
                                    "current_status": job.status,
                                    "error": str(transition_err),
                                }
                            },
                        )
                        continue

                    reclaimed_count += 1
                    logger.warning(
                        "claim_reaper_reclaimed_job",
                        extra={"extra_fields": {"job_id": job.job_id}},
                    )

                await session.commit()
                if reclaimed_count > 0:
                    logger.warning(f"ClaimReaper reclaimed {reclaimed_count} stale CLAIMED jobs.")
                return reclaimed_count

            except Exception as e:
                logger.error(f"Claim reaper failed: {e}", exc_info=True)
                await session.rollback()
                raise


claim_reaper = ClaimReaper()