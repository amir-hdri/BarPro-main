"""Central driver execution-slot lifecycle helpers.

A driver can only run one waybill pipeline at a time. Serialization is done
through ``DriverRuntimeState.active_execution_id``: when the scheduler queues a
job it sets this column to the ``DispatchIntent.intent_id``, and it must be
cleared *exactly once* when the pipeline for that intent concludes — either on
success/failure, or on an infrastructure failure that happens *before* an
``Execution`` row is created.

The critical invariant this module guards:

    A job in a retryable state (``waiting_retry``, ``unknown``, ...) must never
    be left holding a driver slot. The scheduler only picks up jobs whose
    driver slot is empty (``active_execution_id IS NULL``); if a pre-execution
    failure path forgets to clear the slot the job is stuck forever.

Every pre-execution failure path must release the slot through
:func:`release_driver_execution_slot` so the invariant holds and the scheduler
can re-dispatch the job:

* worker draining
* proxy unavailable / unhealthy
* celery unavailable during dispatch
* failed claim before an Execution is created
* cancel (soft-cancel) path
* stale-claimed recovery (claim reaper)
* orphaned-execution recovery
"""

import logging
from datetime import UTC, datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models_rpa import DriverRuntimeState, DriverRuntimeStateValue, Execution

logger = logging.getLogger(__name__)

# Execution statuses that count as "live" for slot purposes. A live execution
# means a worker genuinely owns the pipeline, so the slot must not be freed.
_LIVE_EXECUTION_STATUSES = ("pending", "running")


async def _has_live_execution(session: AsyncSession, intent_id: str | None) -> bool:
    """Return True if ``intent_id`` currently has a pending/running Execution."""
    if not intent_id:
        return False
    stmt = (
        select(Execution.id)
        .where(
            Execution.intent_id == intent_id,
            Execution.status.in_(_LIVE_EXECUTION_STATUSES),
        )
        .limit(1)
    )
    result = await session.exec(stmt)
    return result.first() is not None


async def release_driver_execution_slot(
    session: AsyncSession,
    *,
    driver_id: int,
    expected_intent_id: str | None = None,
) -> bool:
    """Release a driver's active execution slot, safely and idempotently.

    Rules enforced:

    * The ``DriverRuntimeState`` row is locked with ``FOR UPDATE`` before any
      read-modify-write, so two concurrent releasers never double-release.
    * If ``expected_intent_id`` is given, the slot is only cleared when its
      current value equals ``expected_intent_id`` (ownership guard). A caller
      that cannot pin the exact intent (e.g. soft-cancel) passes ``None``.
    * The slot is **never** cleared while the slot's intent has a live
      (pending/running) ``Execution`` — a worker may genuinely own it.
    * The operation is idempotent: releasing an already-empty slot is a no-op.

    Returns ``True`` if the slot is clear after the call (released now, or was
    already empty / no runtime-state row), ``False`` if the slot was left
    intact (intent mismatch or a live execution is present).
    """
    stmt = select(DriverRuntimeState).where(DriverRuntimeState.driver_id == driver_id).with_for_update()
    result = await session.exec(stmt)
    state = result.first()

    if state is None:
        # No runtime-state row — there is nothing to hold the slot.
        logger.info(
            "driver_slot_release_no_runtime_state",
            extra={"extra_fields": {"driver_id": driver_id}},
        )
        return True

    slot_intent_id = state.active_execution_id

    if not slot_intent_id:
        if state.auth_lock_owner or state.state != DriverRuntimeStateValue.READY.value:
            state.auth_lock_owner = None
            state.auth_lock_acquired_at = None
            state.state = DriverRuntimeStateValue.READY.value
            state.updated_at = datetime.now(UTC).replace(tzinfo=None)
            session.add(state)
        # Idempotent: already released. This is checked before the ownership
        # guard so that releasing an already-empty slot always succeeds.
        logger.info(
            "driver_slot_release_already_clear",
            extra={"extra_fields": {"driver_id": driver_id}},
        )
        return True

    if expected_intent_id is not None and slot_intent_id != expected_intent_id:
        # Ownership guard: the slot belongs to a different intent — leave it
        # alone. This prevents one job's failure from freeing another job's slot.
        logger.info(
            "driver_slot_release_mismatch",
            extra={
                "extra_fields": {
                    "driver_id": driver_id,
                    "slot_intent_id": slot_intent_id,
                    "expected_intent_id": expected_intent_id,
                }
            },
        )
        return False

    # Never release a slot whose intent still has a live Execution.
    if await _has_live_execution(session, slot_intent_id):
        logger.info(
            "driver_slot_release_skipped_live_execution",
            extra={
                "extra_fields": {
                    "driver_id": driver_id,
                    "intent_id": slot_intent_id,
                }
            },
        )
        return False

    state.active_execution_id = None
    state.auth_lock_owner = None
    state.auth_lock_acquired_at = None
    state.state = DriverRuntimeStateValue.READY.value
    state.updated_at = datetime.now(UTC).replace(tzinfo=None)
    session.add(state)
    logger.info(
        "driver_slot_released",
        extra={
            "extra_fields": {
                "driver_id": driver_id,
                "intent_id": slot_intent_id,
                "released_by_expected_intent": expected_intent_id is not None,
            }
        },
    )
    return True
