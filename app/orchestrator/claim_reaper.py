"""
Claim Reaper: recovers jobs stuck in CLAIMED status without a corresponding
Execution or Celery task running.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlmodel import select

from app.core.database import async_session_factory
from app.models_multitenant import TaskStatus, WaybillJob
from app.models_rpa import DispatchIntent, Execution
from app.orchestrator.driver_slot import release_driver_execution_slot
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
                        Execution.job_id == job.job_id, Execution.status.in_(["pending", "running"])
                    )
                    exec_res = await session.exec(exec_stmt)
                    active_execution = exec_res.first()

                    if active_execution:
                        # Job has an active execution, skip
                        continue

                    # Check if there's a pending/claimed DispatchIntent for this job
                    intent_stmt = select(DispatchIntent).where(
                        DispatchIntent.job_id == job.job_id, DispatchIntent.status.in_(["pending", "claimed"])
                    )
                    intent_res = await session.exec(intent_stmt)
                    active_intent = intent_res.first()

                    if active_intent and active_intent.status == "pending":
                        # Still waiting to be claimed by the dispatcher — skip;
                        # a dispatcher cycle should deliver it shortly.
                        continue

                    if active_intent and active_intent.status == "claimed":
                        if active_intent.updated_at >= threshold:
                            # Claimed recently — the intent may still be in
                            # transit to the worker or the worker may be about
                            # to create its Execution row. Give it time.
                            continue
                        # Stale claimed intent with no corresponding Execution:
                        # the dispatcher sent the Celery task but the worker
                        # never executed it (crash, broker loss, ...). Expire
                        # the intent and fall through to recovery so the job
                        # is re-queued instead of staying stuck forever.
                        logger.warning(
                            "claim_reaper_expiring_stale_intent",
                            extra={
                                "extra_fields": {
                                    "job_id": job.job_id,
                                    "intent_id": active_intent.intent_id,
                                    "intent_updated_at": active_intent.updated_at.isoformat(),
                                }
                            },
                        )
                        active_intent.status = "failed"
                        active_intent.updated_at = now
                        session.add(active_intent)

                    # No live execution and no deliverable intent — this is an
                    # orphaned claimed job. Clear the driver slot and let the
                    # scheduler re-dispatch it. The reaper verified above there
                    # is no live Execution, so releasing is safe. If a stale
                    # claimed intent was expired above, pin the ownership guard
                    # to that intent; otherwise release whatever slot remains.
                    if job.driver_id:
                        await release_driver_execution_slot(
                            session,
                            driver_id=job.driver_id,
                            expected_intent_id=active_intent.intent_id if active_intent else None,
                        )

                    # Transition job to WAITING_RETRY (or WAITING_SUBMISSION_WINDOW at night) so scheduler can pick it up
                    try:
                        from app.services.night_submission_policy import is_in_night_window, next_reopen_at_utc_naive

                        in_night = is_in_night_window()
                        next_retry = next_reopen_at_utc_naive() if in_night else now
                        target_status = (
                            TaskStatus.WAITING_SUBMISSION_WINDOW.value if in_night else TaskStatus.WAITING_RETRY.value
                        )

                        JobStateMachine.transition(
                            session,
                            job,
                            target_status,
                            expected_from={TaskStatus.CLAIMED.value},
                            next_retry_at=next_retry,
                            submit_after=next_retry if in_night else job.submit_after,
                            last_error="Claim reaper: job was in CLAIMED without a live execution or deliverable intent",
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

                # Also reap stale DriverRuntimeState rows where auth_lock_owner is older than threshold
                from app.models_rpa import DriverRuntimeState, DriverRuntimeStateValue

                stale_states_stmt = (
                    select(DriverRuntimeState)
                    .where(
                        (DriverRuntimeState.auth_lock_owner != None)  # noqa: E711
                        & (DriverRuntimeState.auth_lock_acquired_at < threshold)
                    )
                    .with_for_update(skip_locked=True)
                )
                stale_states = (await session.exec(stale_states_stmt)).all()
                for st in stale_states:
                    if not st.active_execution_id:
                        st.auth_lock_owner = None
                        st.auth_lock_acquired_at = None
                        st.state = DriverRuntimeStateValue.READY.value
                        st.updated_at = now
                        session.add(st)

                await session.commit()
                if reclaimed_count > 0:
                    logger.warning(f"ClaimReaper reclaimed {reclaimed_count} stale CLAIMED jobs.")
                return reclaimed_count

            except Exception as e:
                logger.error(f"Claim reaper failed: {e}", exc_info=True)
                await session.rollback()
                raise


claim_reaper = ClaimReaper()
