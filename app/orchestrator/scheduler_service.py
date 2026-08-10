import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.core.database import async_session_factory
from app.models_multitenant import Client, ClientStatus, Driver, DriverStatus, TaskStatus, WaybillJob
from app.models_rpa import DispatchIntent, DriverRuntimeState
from app.orchestrator.state_machine import JobStateMachine

logger = logging.getLogger(__name__)

# Sentinel for cache lookups that may legitimately store None.
_MISSING_CLIENT = object()
_MISSING_DRIVER = object()

# Statuses counting toward the tenant's concurrent-task quota.
# PENDING, WAITING_RETRY, OTP_BACKOFF are pre-dispatch states;
# only jobs that have been scheduled/dispatched count as in-flight.
_IN_FLIGHT_STATUSES = [
    TaskStatus.QUEUED.value,
    TaskStatus.CLAIMED.value,
    TaskStatus.RUNNING.value,
    TaskStatus.IN_PROGRESS.value,
]

# Driver statuses that are allowed to receive new jobs.
_DISPATCHABLE_DRIVER_STATUSES = [
    DriverStatus.ACTIVE.value,
    DriverStatus.READY.value,
]


class SchedulerService:
    async def run(self) -> int:
        """
        Scan for pending, waiting_retry, and otp_backoff jobs that are ready to run,
        and whose driver does not have an active execution slot.
        Enforce tenant/driver eligibility and per-tenant concurrency/daily quotas.
        Mark them as queued, lock their driver's slot, and insert corresponding dispatch intents.
        Returns the number of scheduled jobs.
        """
        async with async_session_factory() as session:
            try:
                # Query due jobs with skip_locked. The driver-slot check (outer
                # join on DriverRuntimeState) must live in a subquery: PostgreSQL
                # rejects `FOR UPDATE` on the nullable side of an outer join.
                now = datetime.now(UTC).replace(tzinfo=None)
                slot_free_job_ids = (
                    select(WaybillJob.id)
                    .join(DriverRuntimeState, WaybillJob.driver_id == DriverRuntimeState.driver_id, isouter=True)
                    .where(
                        (DriverRuntimeState.active_execution_id == None) | (DriverRuntimeState.id == None)  # noqa: E711
                    )
                    .where(
                        WaybillJob.status.in_(
                            [TaskStatus.PENDING.value, TaskStatus.WAITING_RETRY.value, TaskStatus.OTP_BACKOFF.value]
                        )
                    )
                    .where((WaybillJob.next_retry_at == None) | (WaybillJob.next_retry_at <= now))  # noqa: E711
                    .where((WaybillJob.submit_after == None) | (WaybillJob.submit_after <= now))  # noqa: E711
                )
                statement = (
                    select(WaybillJob)
                    .where(WaybillJob.id.in_(slot_free_job_ids))
                    .order_by(WaybillJob.priority.desc(), WaybillJob.created_at.asc())
                    .with_for_update(skip_locked=True)
                )

                result = await session.exec(statement)
                due_jobs = result.all()

                if not due_jobs:
                    return 0

                # Per-tenant filters (status/quota) checked with cache
                # lookups to avoid N+1 round trips inside the loop.
                client_cache: dict[int, Client | None] = {}
                driver_cache: dict[int, Driver | None] = {}
                in_flight_counts: dict[int, int] = {}
                daily_counts: dict[int, int] = {}
                today_start = datetime.combine(now.date(), datetime.min.time())
                skipped = 0
                scheduled_count = 0
                scheduled_driver_ids = set()
                for job in due_jobs:
                    if job.driver_id in scheduled_driver_ids:
                        continue

                    # Tenant eligibility: account must be active.
                    client = client_cache.get(job.client_id, _MISSING_CLIENT)
                    if client is _MISSING_CLIENT:
                        client = await session.get(Client, job.client_id)
                        client_cache[job.client_id] = client
                    if client is None or client.status != ClientStatus.ACTIVE.value:
                        # Bad state (missing tenant, suspended, ...) — leave the
                        # job untouched; statuses never change inside the scheduler.
                        skipped += 1
                        continue

                    # Subscription window: the tenant must be within its active
                    # subscription dates (None means no bound is enforced).
                    if client.subscription_start_date and client.subscription_start_date > now:
                        skipped += 1
                        continue
                    if client.subscription_end_date and client.subscription_end_date < now:
                        skipped += 1
                        continue

                    # Driver eligibility: status active/ready.
                    driver = driver_cache.get(job.driver_id, _MISSING_DRIVER)
                    if driver is _MISSING_DRIVER:
                        driver = await session.get(Driver, job.driver_id) if job.driver_id else None
                        driver_cache[job.driver_id] = driver
                    if driver is None or driver.status not in _DISPATCHABLE_DRIVER_STATUSES:
                        skipped += 1
                        continue

                    # Tenant concurrency quota: in-flight jobs per tenant.
                    if job.client_id not in in_flight_counts:
                        in_flight_stmt = select(func.count(WaybillJob.id)).where(
                            WaybillJob.client_id == job.client_id,
                            WaybillJob.status.in_(_IN_FLIGHT_STATUSES),
                        )
                        in_flight_counts[job.client_id] = (await session.exec(in_flight_stmt)).one()
                    if in_flight_counts[job.client_id] >= client.max_concurrent_tasks:
                        skipped += 1
                        continue

                    # Tenant daily quota: jobs created today per tenant.
                    if job.client_id not in daily_counts:
                        daily_stmt = select(func.count(WaybillJob.id)).where(
                            WaybillJob.client_id == job.client_id,
                            WaybillJob.created_at >= today_start,
                        )
                        daily_counts[job.client_id] = (await session.exec(daily_stmt)).one()
                    if daily_counts[job.client_id] >= client.max_daily_tasks:
                        skipped += 1
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
                        status="pending",
                    )
                    session.add(intent)

                    # Set the active execution slot on the driver runtime state.
                    # If the runtime state does not exist yet, create it
                    # atomically: two concurrent schedulers racing for the same
                    # driver (a unique constraint on driver_id) must not both
                    # insert. Creation is wrapped in a nested transaction and
                    # retried by re-fetching on IntegrityError.
                    driver_state_stmt = (
                        select(DriverRuntimeState)
                        .where(DriverRuntimeState.driver_id == job.driver_id)
                        .with_for_update()
                    )
                    driver_state_res = await session.exec(driver_state_stmt)
                    driver_state = driver_state_res.first()
                    if driver_state:
                        driver_state.active_execution_id = intent_id
                        session.add(driver_state)
                    else:
                        try:
                            async with session.begin_nested():
                                driver_state = DriverRuntimeState(
                                    client_id=job.client_id,
                                    driver_id=job.driver_id,
                                    active_execution_id=intent_id,
                                    state="SUBMITTING",
                                )
                                session.add(driver_state)
                                await session.flush()
                        except IntegrityError:
                            # Lost the race — a concurrent scheduler created it.
                            driver_state_res2 = await session.exec(driver_state_stmt)
                            driver_state2 = driver_state_res2.first()
                            if driver_state2 is None:
                                raise
                            driver_state2.active_execution_id = intent_id
                            session.add(driver_state2)

                    # Transition job to queued status
                    JobStateMachine.transition(session, job, TaskStatus.QUEUED.value)
                    scheduled_driver_ids.add(job.driver_id)
                    in_flight_counts[job.client_id] += 1
                    daily_counts[job.client_id] += 1
                    scheduled_count += 1

                await session.commit()
                if scheduled_count > 0:
                    logger.info(
                        f"Scheduled {scheduled_count} jobs as pending dispatch intents ({skipped} skipped by policy)."
                    )
                return scheduled_count

            except Exception as e:
                logger.error(f"Scheduler run failed: {e}", exc_info=True)
                await session.rollback()
                raise


scheduler_service = SchedulerService()
