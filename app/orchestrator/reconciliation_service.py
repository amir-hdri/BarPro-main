"""
Reconciliation Service for reconciling orphan and ambiguous waybill jobs.
"""

import json
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.browser import BrowserManager
from app.core.error_taxonomy import ErrorCategory
from app.models_multitenant import Driver, WaybillJob
from app.monitoring.metrics import track_reconciliation_outcome
from app.orchestrator.alert_manager import admin_alert_service
from app.orchestrator.state_machine import JobStateMachine, JobStatus
from app.orchestrator.utcms_reconciliation_scraper import ScraperOutcome, reconciliation_scraper
from app.services.rpa_runtime_service import rpa_runtime

logger = logging.getLogger(__name__)

# Eventual consistency retry delays in seconds: 15s, 45s, 2m, 5m
RECONCILIATION_SCHEDULE = [15, 45, 120, 300]


class ReconciliationService:
    """Service to match waybill job states with UTCMS portal reality."""

    async def reconcile_job(
        self,
        session: AsyncSession,
        job_id: int,
        browser_manager: BrowserManager | None = None,
    ) -> WaybillJob | None:
        """
        Reconcile a single WaybillJob with UTCMS.
        Transitions status from unknown -> reconciling -> success/needs_review.
        """
        stmt = select(WaybillJob).where(WaybillJob.id == job_id).with_for_update(skip_locked=True)
        job = (await session.execute(stmt)).scalar_one_or_none()

        if not job:
            logger.warning("Job #%s not found for reconciliation", job_id)
            return None

        # Only reconcile jobs in unknown or reconciling status
        if job.status not in (JobStatus.UNKNOWN, JobStatus.RECONCILING):
            logger.info("Job #%s status is '%s', skipping reconciliation", job_id, job.status)
            return job

        # Move to RECONCILING if currently UNKNOWN
        if job.status == JobStatus.UNKNOWN:
            try:
                JobStateMachine.transition(session, job, JobStatus.RECONCILING)
                await session.commit()
                await session.refresh(job)
            except Exception as e:
                logger.error("Failed to transition job #%s to reconciling: %s", job_id, e)
                await session.rollback()
                return job

        outcome = ScraperOutcome.AMBIGUOUS
        res_json = job.result_json
        if isinstance(res_json, str):
            try:
                res_json = json.loads(res_json)
            except Exception:
                res_json = {}
        else:
            res_json = res_json or {}
        tracking_code = res_json.get("tracking_code")

        utcms_username = None
        driver_obj = None
        if job.driver_id:
            driver_stmt = select(Driver).where(Driver.id == job.driver_id)
            driver_obj = (await session.execute(driver_stmt)).scalar_one_or_none()
            if driver_obj:
                utcms_username = driver_obj.utcms_username

        # Extract reconciliation identity
        from app.core.submission_identity import extract_reconciliation_identity

        identity = extract_reconciliation_identity(job.payload_json, driver=driver_obj)
        identity.submission_fingerprint = job.submission_fingerprint
        reconciliation_fields = identity.to_dict()

        # Execute Playwright scraping if browser_manager provided
        from app.automation.worker_proxy import get_playwright_proxy
        from app.services.session_vault import session_vault

        auth_state_path = None
        if utcms_username and job.client_id and job.driver_id:
            auth_state_path = session_vault.auth_state_path_for_driver(
                client_id=job.client_id,
                driver_id=job.driver_id,
                username=utcms_username,
                fallback=utcms_username,
            )

        proxy_dict = get_playwright_proxy()

        bm = browser_manager or BrowserManager()
        session_id = None
        try:
            session_id, context = await bm.create_context(auth_state_path=auth_state_path, proxy_dict=proxy_dict)
            page = await bm.new_page(context)
            res = await reconciliation_scraper.query_waybill_status(
                page=page,
                tracking_code=tracking_code,
                job_id=job.id,
                reconciliation_fields=reconciliation_fields,
            )

            # Auto-authenticate if query was ambiguous / unauthenticated
            if res.outcome == ScraperOutcome.AMBIGUOUS and driver_obj:
                enc_pass = driver_obj.utcms_password_encrypted or getattr(driver_obj, "encrypted_password", None)
                if enc_pass:
                    try:
                        from app.auth_multitenant import decrypt_driver_password
                        from app.automation.auth import UTCMSAuthenticator

                        raw_password = decrypt_driver_password(enc_pass)
                        authenticator = UTCMSAuthenticator(page=page, context=context)
                        logged_in = await authenticator.login(
                            username=driver_obj.utcms_username,
                            password=raw_password,
                        )
                        if logged_in:
                            logger.info(
                                "Reconciliation auto-login successful for driver %s",
                                driver_obj.utcms_username,
                            )
                            if job.client_id and job.driver_id:
                                try:
                                    await session_vault.save_driver_session(
                                        client_id=job.client_id,
                                        driver_id=job.driver_id,
                                        username=driver_obj.utcms_username,
                                        context=context,
                                    )
                                except Exception as sv_exc:
                                    logger.warning("Failed saving refreshed session in reconciliation: %s", sv_exc)

                            # Retry query with authenticated session
                            res = await reconciliation_scraper.query_waybill_status(
                                page=page,
                                tracking_code=tracking_code,
                                job_id=job.id,
                                reconciliation_fields=reconciliation_fields,
                            )
                    except Exception as auth_exc:
                        logger.warning("Reconciliation auto-login failed: %s", auth_exc)

            outcome = res.outcome
            details = res.details
        except Exception as exc:
            logger.error("Failed browser execution during reconciliation of job #%s: %s", job_id, exc)
            outcome = ScraperOutcome.AMBIGUOUS
            details = {"error": str(exc)}
        finally:
            if session_id:
                try:
                    success_outcome = outcome in (ScraperOutcome.REGISTERED, ScraperOutcome.NOT_FOUND)
                    await bm.close_context(
                        session_id=session_id,
                        success=success_outcome,
                        error="" if success_outcome else str(details.get("error", "Ambiguous reconciliation outcome")),
                    )
                except Exception as close_exc:
                    logger.warning("Failed closing context in reconciliation of job #%s: %s", job_id, close_exc)

        track_reconciliation_outcome(outcome.value)
        confirmed_success = False

        # Handle Reconciliation Results via JobStateMachine
        try:
            # Metadata tracking for eventual consistency retries
            payload_meta = job.payload_json
            if isinstance(payload_meta, str):
                try:
                    payload_meta = json.loads(payload_meta)
                except Exception:
                    payload_meta = {}
            else:
                payload_meta = dict(payload_meta or {})

            recon_attempts = int(payload_meta.get("reconciliation_attempts", 0)) + 1
            payload_meta["reconciliation_attempts"] = recon_attempts

            if outcome == ScraperOutcome.REGISTERED:
                found_code = (
                    (res.tracking_code if hasattr(res, "tracking_code") else None)
                    or details.get("tracking_code")
                    or tracking_code
                )
                if not found_code:
                    # Without a verifiable tracking code, success is unreliable — downgrade to needs_review
                    JobStateMachine.transition(
                        session,
                        job,
                        JobStatus.NEEDS_REVIEW,
                        error_category=ErrorCategory.SUBMISSION_UNCONFIRMED.value,
                        last_error="Reconciliation scraper indicated REGISTERED but no tracking code found; requires manual review",
                    )
                    logger.warning("Job #%s reconciled to NEEDS_REVIEW (REGISTERED without tracking code)", job.id)
                else:
                    res_json = job.result_json
                    if isinstance(res_json, str):
                        try:
                            res_json = json.loads(res_json)
                        except Exception:
                            res_json = {}
                    else:
                        res_json = dict(res_json or {})
                    res_json["tracking_code"] = found_code
                    res_json["confirmation_status"] = "confirmed_by_history"
                    if isinstance(job.result_json, str):
                        result_json_val = json.dumps(res_json, ensure_ascii=False)
                    else:
                        result_json_val = res_json

                    # Three witnesses confirmed: RPA code + DB persistence + UTCMS History record
                    job.reconciled_at = datetime.now(UTC).replace(tzinfo=None)
                    job.mutation_status = "confirmed"
                    if res.document_id:
                        job.document_id = res.document_id

                    JobStateMachine.transition(
                        session,
                        job,
                        JobStatus.SUCCESS,
                        result_json=result_json_val,
                        finished_at=datetime.now(UTC).replace(tzinfo=None),
                        next_retry_at=None,
                        submit_after=None,
                        last_error=None,
                        error_category=None,
                        retryable=False,
                    )
                    confirmed_success = True
                    logger.info("Job #%s reconciled to SUCCESS with tracking code %s", job.id, found_code)

            elif outcome == ScraperOutcome.NOT_FOUND:
                # Eventual Consistency: Indexing delay. Try up to 4 times (15s, 45s, 2m, 5m).
                if recon_attempts <= len(RECONCILIATION_SCHEDULE):
                    delay = RECONCILIATION_SCHEDULE[recon_attempts - 1]
                    next_retry = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=delay)
                    job.next_retry_at = next_retry
                    if isinstance(job.payload_json, str):
                        job.payload_json = json.dumps(payload_meta, ensure_ascii=False)
                    else:
                        job.payload_json = payload_meta
                    logger.info(
                        "Job #%s not yet visible in UTCMS History (attempt %s/%s). Retrying in %ss",
                        job.id,
                        recon_attempts,
                        len(RECONCILIATION_SCHEDULE),
                        delay,
                    )
                else:
                    # Reconciliation window expired without confirmation -> Move to NEEDS_REVIEW (NEVER auto-resubmit!)
                    JobStateMachine.transition(
                        session,
                        job,
                        JobStatus.NEEDS_REVIEW,
                        error_category=ErrorCategory.SUBMISSION_UNCONFIRMED.value,
                        last_error="Waybill unconfirmed in UTCMS History after full eventual consistency window (5m); requires manual review",
                        finished_at=datetime.now(UTC).replace(tzinfo=None),
                    )
                    logger.warning(
                        "Job #%s reconciled to NEEDS_REVIEW after %s failed attempts. Resubmission blocked.",
                        job.id,
                        recon_attempts,
                    )

            else:  # AMBIGUOUS
                JobStateMachine.transition(
                    session,
                    job,
                    JobStatus.NEEDS_REVIEW,
                    error_category=ErrorCategory.SUBMISSION_UNCONFIRMED.value,
                    last_error="Reconciliation result ambiguous; marked for manual review",
                )
                consecutive_unknowns = payload_meta.get("consecutive_unknowns", 0) + 1
                payload_meta["consecutive_unknowns"] = consecutive_unknowns
                if isinstance(job.payload_json, str):
                    job.payload_json = json.dumps(payload_meta, ensure_ascii=False)
                else:
                    job.payload_json = payload_meta

                # Check if high severity alert should be raised (>= 3 attempts)
                await admin_alert_service.check_repeated_unknown_submission(
                    session=session,
                    job_id=job.id,
                    consecutive_count=consecutive_unknowns,
                    tenant_id=job.client_id,
                )
                logger.warning("Job #%s reconciled to NEEDS_REVIEW (Ambiguous count: %s)", job.id, consecutive_unknowns)

            await session.commit()
            await session.refresh(job)
            if confirmed_success and job.driver_id is not None:
                try:
                    await rpa_runtime.increment_success(job.client_id, job.driver_id)
                except Exception:
                    logger.warning("confirmed_success_counter_increment_failed", exc_info=True)

        except Exception as exc:
            await session.rollback()
            logger.error("Failed to commit reconciliation state change for job #%s: %s", job_id, exc)

        return job

    async def reconcile_orphaned_jobs(
        self,
        session: AsyncSession,
        browser_manager: BrowserManager | None = None,
    ) -> dict[str, int]:
        """Scan and reconcile all UNKNOWN / RECONCILING jobs whose next_retry_at is due."""
        now_utc = datetime.now(UTC).replace(tzinfo=None)
        stmt = (
            select(WaybillJob.id)
            .where(
                WaybillJob.status.in_([JobStatus.UNKNOWN, JobStatus.RECONCILING]),
                (WaybillJob.next_retry_at == None) | (WaybillJob.next_retry_at <= now_utc),  # noqa: E711
            )
            .with_for_update(skip_locked=True)
        )
        job_ids = (await session.execute(stmt)).scalars().all()

        results = {"total": len(job_ids), "success": 0, "failed": 0, "needs_review": 0, "errors": 0}

        for jid in job_ids:
            try:
                updated_job = await self.reconcile_job(session=session, job_id=jid, browser_manager=browser_manager)
                if updated_job:
                    if updated_job.status == JobStatus.SUCCESS:
                        results["success"] += 1
                    elif updated_job.status == JobStatus.FAILED:
                        results["failed"] += 1
                    elif updated_job.status == JobStatus.NEEDS_REVIEW:
                        results["needs_review"] += 1
            except Exception as exc:
                logger.error("Error during batch reconciliation of job #%s: %s", jid, exc)
                results["errors"] += 1

        return results


reconciliation_service = ReconciliationService()
