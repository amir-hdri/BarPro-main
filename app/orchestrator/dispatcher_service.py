import logging
from datetime import UTC, datetime

from sqlmodel import select

from app.core.database import async_session_factory
from app.models_multitenant import TaskStatus, WaybillJob
from app.models_rpa import DispatchIntent
from app.orchestrator.driver_slot import release_driver_execution_slot
from app.orchestrator.state_machine import JobStateMachine, StateTransitionError
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


class DispatcherService:
    """Dispatch pending intents to the appropriate Celery worker queue.

    A dispatch intent is a promise that its waybill job is ready to be
    executed.  The only job statuses the state machine accepts as ``claimed``
    are ``queued``/``claimed`` (submit/execute intents) and, for
    reconciliation intents, ``unknown``/``reconciling`` (the reconcile worker
    drives the ``unknown -> reconciling`` transition itself).

    Any intent whose job is in a different status is stale --- it was created
    before the job moved elsewhere (waiting_retry, needs_review, cancelled,
    ...).  Claiming those raises a StateTransitionError, and an error in one
    intent must never abort the whole batch: a single bad intent would then
    starve every later intent and loop forever.
    """

    # Statuses a job may be in for an intent to be claimable, keyed by intent
    # operation. "claimed" is included so re-claiming an already-claimed job
    # is a no-op instead of an error.
    _CLAIMABLE_JOB_STATUSES: dict[str, frozenset[str]] = {
        "submit": frozenset({TaskStatus.QUEUED.value, TaskStatus.CLAIMED.value}),
        "reconciliation": frozenset(
            {
                TaskStatus.UNKNOWN.value,
                TaskStatus.RECONCILING.value,
                TaskStatus.CLAIMED.value,
            }
        ),
    }

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
                    try:
                        dispatched_count += await self._dispatch_one(session, intent)
                    except Exception as e:
                        # A single broken intent must not abort the batch:
                        # quarantine it so the next run can serve the others.
                        logger.error(
                            f"Dispatcher failed for intent {intent.intent_id}: {e}. Quarantining intent.",
                            exc_info=True,
                        )
                        intent.status = "cancelled"
                        intent.updated_at = datetime.now(UTC).replace(tzinfo=None)
                        session.add(intent)

                await session.commit()
                if dispatched_count > 0:
                    logger.info(f"Dispatched {dispatched_count} intents to Celery.")
                return dispatched_count

            except Exception as e:
                logger.error(f"Dispatcher run failed: {e}", exc_info=True)
                await session.rollback()
                raise

    async def _dispatch_one(self, session, intent: DispatchIntent) -> int:
        # Fetch corresponding job to transition
        job_statement = select(WaybillJob).where(WaybillJob.job_id == intent.job_id).with_for_update()
        job_result = await session.exec(job_statement)
        job = job_result.first()

        if not job:
            logger.error(f"Job {intent.job_id} not found for dispatch intent {intent.intent_id}")
            intent.status = "failed"
            session.add(intent)
            return 0

        operation = intent.operation or "submit"
        claimable = self._CLAIMABLE_JOB_STATUSES.get(operation)

        if claimable is None:
            logger.error(f"Intent {intent.intent_id} has unknown operation {operation!r}, cancelling")
            self._expire_intent(session, intent, reason="unknown_operation")
            return 0

        if job.status not in claimable:
            # The job moved to a status the state machine cannot claim from
            # (waiting_retry / needs_review / cancelled / running / ...) after
            # the intent was created.  Claiming would raise, and leaving it
            # pending would loop forever — expire the intent instead.  Any
            # driver slot the scheduler pinned to this intent is released so
            # the scheduler can re-dispatch the job when it becomes due again.
            logger.info(
                f"Intent {intent.intent_id} ({operation}) belongs to job {job.job_id} in status {job.status!r}, "
                "marking intent cancelled"
            )
            self._expire_intent(session, intent, reason=f"job_status_{job.status}")
            if job.driver_id:
                await release_driver_execution_slot(
                    session, driver_id=job.driver_id, expected_intent_id=intent.intent_id
                )
            return 0

        # Claim the intent
        intent.status = "claimed"
        intent.updated_at = datetime.now(UTC).replace(tzinfo=None)
        session.add(intent)

        # Transition job for submit intents (queued/claimed -> claimed is the
        # only path the execute worker understands). Reconciliation intents
        # leave the job to the reconcile worker, which moves unknown ->
        # reconciling itself.
        if operation != "reconciliation":
            try:
                JobStateMachine.transition(session, job, TaskStatus.CLAIMED.value)
            except StateTransitionError:
                # Same status or unexpected state — the job is already claimed
                # or moved elsewhere; the intent may still be dispatched.
                raise

        # Send Celery task
        if celery_app is not None:
            if operation == "reconciliation":
                task_name = "barpro.waybill.reconcile"
                base_queue = "reconciliation_tasks"
            else:
                task_name = "barpro.waybill.execute"
                base_queue = "waybill_tasks"

            from app.core.circuit_breaker import get_routed_queue

            routed_queue = get_routed_queue(base_queue)

            celery_app.send_task(task_name, args=[intent.intent_id], queue=routed_queue, priority=job.priority or 5)
            return 1
        else:
            logger.warning("Celery app not initialized, cannot dispatch task")
            intent.status = "failed"
            session.add(intent)
            # Recover: free driver slot and revert job so scheduler can retry later.
            # No Execution was created (dispatch never reached the worker), so the
            # slot can be released safely.
            if job.driver_id:
                await release_driver_execution_slot(
                    session, driver_id=job.driver_id, expected_intent_id=intent.intent_id
                )
            JobStateMachine.transition(
                session,
                job,
                TaskStatus.WAITING_RETRY.value,
                next_retry_at=datetime.now(UTC).replace(tzinfo=None),
                last_error="Celery unavailable during dispatch",
                error_category="system_error",
            )
            return 0

    @staticmethod
    def _expire_intent(session, intent: DispatchIntent, *, reason: str) -> None:
        intent.status = "cancelled"
        intent.updated_at = datetime.now(UTC).replace(tzinfo=None)
        session.add(intent)


dispatcher_service = DispatcherService()
