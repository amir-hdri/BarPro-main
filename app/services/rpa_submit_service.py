"""HTTP-light submit worker for Phase 1 hybrid RPA."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from playwright.async_api import BrowserContext, Page
from sqlmodel import select

from app.automation.auth import UTCMSAuthenticator
from app.automation.browser import browser_manager
from app.automation.multitenant_payload_adapter import build_enhanced_waybill_payload
from app.automation.proxy_rotator import get_proxy_rotator
from app.automation.waybill_enhanced import EnhancedWaybillManager
from app.core.config import utcms_config
from app.core.database import async_session_factory
from app.core.error_taxonomy import ErrorCategory, classify_exception
from app.core.exceptions import WaybillError
from app.models_multitenant import Driver, DriverStatus, TaskStatus, WaybillJob
from app.models_rpa import (
    AttemptResult,
    AttemptType,
    DomainEvent,
    DriverDailyCounter,
    DriverRuntimeState,
    DriverRuntimeStateValue,
    DriverSessionMetadata,
    WaybillAttempt,
)
from app.orchestrator.state_machine import JobStateMachine
from app.rpa.contracts import SessionBundle, SubmitClassification, SubmitExecutionResult, SubmitOutcome
from app.rpa.event_taxonomy import (
    DRIVER_LIMIT_REACHED,
    SESSION_EXPIRED,
    SUBMIT_DELAYED,
    SUBMIT_FAILED,
    SUBMIT_SUCCEEDED,
)
from app.services.rpa_run_isolation import prepare_live_run_isolation
from app.services.rpa_runtime_service import rpa_runtime
from app.services.utcms_submission_gate import utcms_submission_gate

logger = logging.getLogger(__name__)


def _map_error_category(outcome: SubmitOutcome, reason_code: str) -> ErrorCategory:
    """Map a SubmitOutcome + raw reason_code into a single ErrorCategory.

    Centralises the classification so individual call sites no longer scatter
    raw strings; consumers can compare the result directly to ErrorCategory
    enum members.
    """
    reason = (reason_code or "").lower()
    if outcome == SubmitOutcome.AUTH_EXPIRED or any(k in reason for k in ("login", "auth", "credential")):
        return ErrorCategory.AUTH_FAILURE
    if outcome == SubmitOutcome.VALIDATION_ERROR:
        if "driver" in reason:
            return ErrorCategory.AUTH_FAILURE
        return ErrorCategory.USER_DATA_ERROR
    if outcome == SubmitOutcome.RATE_LIMITED:
        return ErrorCategory.TARGET_SITE_TIMEOUT
    if outcome == SubmitOutcome.TRANSIENT_FAILURE:
        return ErrorCategory.TRANSIENT_INFRA_ERROR
    if outcome == SubmitOutcome.UNKNOWN_ERROR:
        if reason in {"submission_unconfirmed", "submission_unknown"}:
            return ErrorCategory.SUBMISSION_UNCONFIRMED
        return ErrorCategory.UNKNOWN_AUTOMATION_ERROR
    return ErrorCategory.UNKNOWN_AUTOMATION_ERROR


class SubmitAdapter:
    async def execute(self, payload: dict[str, Any], session_bundle: SessionBundle) -> SubmitExecutionResult:
        start = time.perf_counter()
        if not utcms_config.RPA_SUBMIT_ENDPOINT:
            raise RuntimeError("RPA_SUBMIT_ENDPOINT is not configured")

        headers = {"User-Agent": session_bundle.user_agent or "UTCMS-RPA/1.0"}
        if session_bundle.csrf_token:
            headers["X-CSRF-Token"] = session_bundle.csrf_token

        cookies = {
            cookie.get("name", ""): cookie.get("value", "") for cookie in session_bundle.cookies if cookie.get("name")
        }
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.post(
                utcms_config.RPA_SUBMIT_ENDPOINT, json=payload, headers=headers, cookies=cookies
            )
        latency_ms = int((time.perf_counter() - start) * 1000)
        raw_payload: dict[str, Any] = {"status_code": response.status_code}
        try:
            response_payload = response.json()
        except ValueError:
            response_payload = None
        if isinstance(response_payload, dict):
            raw_payload.update(response_payload)
            data = response_payload.get("data") if isinstance(response_payload.get("data"), dict) else {}
            obj = data.get("obj") if isinstance(data.get("obj"), dict) else {}
            tracking_code = (
                response_payload.get("tracking_code")
                or response_payload.get("trackingCode")
                or data.get("tracking_code")
                or data.get("trackingCode")
                or obj.get("tracking_code")
                or obj.get("trackingCode")
            )
            if tracking_code is not None:
                raw_payload["tracking_code"] = str(tracking_code).strip()
        return SubmitExecutionResult(
            classification=classify_submit_response(response.status_code, response.text),
            latency_ms=latency_ms,
            raw_payload=raw_payload,
        )


class RPAHttpSubmitService:
    def __init__(self) -> None:
        self.adapter = SubmitAdapter()

    async def process_job(self, client_id: int, job_id: str) -> SubmitExecutionResult:
        return await self._process_job(client_id, job_id)

    async def process_job_live(
        self,
        client_id: int,
        job_id: str,
        page: Page,
        context: BrowserContext,
        session_bundle: SessionBundle | None = None,
    ) -> SubmitExecutionResult:
        return await self._process_job(
            client_id,
            job_id,
            live_page=page,
            live_context=context,
            session_bundle_override=session_bundle,
        )

    async def _process_job(
        self,
        client_id: int,
        job_id: str,
        live_page: Page | None = None,
        live_context: BrowserContext | None = None,
        session_bundle_override: SessionBundle | None = None,
    ) -> SubmitExecutionResult:
        session = async_session_factory()
        lock_acquired = False
        try:
            job = (
                await session.exec(
                    select(WaybillJob).where(WaybillJob.job_id == job_id, WaybillJob.client_id == client_id)
                )
            ).first()
            if job is None:
                raise ValueError(f"job {job_id} not found")
            if job.driver_id is None:
                raise ValueError(f"job {job_id} has no driver")

            # CRITICAL: Check if job was already successfully submitted to portal
            # by checking for existing tracking_code in result_json
            if job.result_json:
                try:
                    if isinstance(job.result_json, dict):
                        result_data = job.result_json
                    elif isinstance(job.result_json, str):
                        result_data = json.loads(job.result_json)
                    else:
                        result_data = {}
                    if result_data.get("tracking_code"):
                        logger.warning(
                            "job_already_has_tracking_code_skipping_duplicate_submit",
                            extra={
                                "extra_fields": {"job_id": job_id, "tracking_code": result_data.get("tracking_code")}
                            },
                        )
                        return SubmitExecutionResult(
                            classification=SubmitClassification(
                                outcome=SubmitOutcome.DUPLICATE,
                                reason_code="already_submitted",
                                retryable=False,
                                message="Job already has tracking code - skipping duplicate submission",
                            ),
                            latency_ms=0,
                        )
                except (json.JSONDecodeError, TypeError) as exc:
                    logger.debug(
                        "rpa_submit_result_json_corrupted",
                        extra={"extra_fields": {"job_id": job.job_id, "error": str(exc)}},
                    )

            driver = await session.get(Driver, job.driver_id)
            runtime_state = await self._get_or_create_runtime_state(session, client_id, job.driver_id)
            if live_page is not None and live_context is not None:
                await prepare_live_run_isolation(
                    client_id=client_id,
                    driver_id=job.driver_id,
                    session=session,
                    job=job,
                    runtime_state=runtime_state,
                )
            counter = await rpa_runtime.counter_snapshot(client_id, job.driver_id)
            if counter.successes >= utcms_config.DRIVER_DAILY_SUCCESS_CAP:
                return await self._mark_daily_limit(session, job, driver, runtime_state, counter, success_limit=True)
            if counter.attempts >= utcms_config.DRIVER_DAILY_ATTEMPT_CAP:
                return await self._mark_daily_limit(session, job, driver, runtime_state, counter, success_limit=False)

            lock_key = rpa_runtime.submit_lock_key(client_id, job.driver_id)
            lock_acquired = False
            lock_acquired = await rpa_runtime.acquire_lock(lock_key, utcms_config.RPA_LOCK_TTL_SECONDS)
            if not lock_acquired:
                return SubmitExecutionResult(
                    classification=SubmitClassification(
                        outcome=SubmitOutcome.TRANSIENT_FAILURE,
                        reason_code="submit_already_in_progress",
                        retryable=True,
                    ),
                    latency_ms=0,
                )

            session_bundle = session_bundle_override or await rpa_runtime.get_session(client_id, job.driver_id)
            if session_bundle is None:
                return await self._mark_waiting_auth(session, job, driver, runtime_state, "missing_session")

            if isinstance(job.payload_json, dict):
                payload = job.payload_json
            elif isinstance(job.payload_json, str):
                payload = json.loads(job.payload_json)
            else:
                payload = {}
            if not await utcms_submission_gate.is_submission_allowed():
                retry_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                    seconds=utcms_config.GATE_PROBE_INTERVAL_SECONDS
                )
                JobStateMachine.transition(
                    session,
                    job,
                    TaskStatus.WAITING_SUBMISSION_WINDOW.value,
                    next_retry_at=retry_at,
                    submit_after=retry_at,
                    retryable=True,
                    celery_task_id=None,
                    last_error="UTCMS submission gate is not confirmed OTP-free",
                    error_category="otp_required",
                )
                await session.commit()
                return SubmitExecutionResult(
                    classification=SubmitClassification(
                        outcome=SubmitOutcome.TRANSIENT_FAILURE,
                        reason_code="otp_required",
                        retryable=True,
                        message="ثبت تا تایید زنده پنجره بدون OTP متوقف شد",
                    ),
                    latency_ms=0,
                )
            JobStateMachine.transition(
                session,
                job,
                TaskStatus.IN_PROGRESS.value,
                updated_at=datetime.now(UTC).replace(tzinfo=None),
            )
            driver.runtime_status = DriverStatus.READY.value
            runtime_state.state = DriverRuntimeStateValue.SUBMITTING.value
            await session.commit()

            try:
                if live_page is not None and live_context is not None:
                    result = await self._execute_browser_submit_with_page(
                        page=live_page,
                        context=live_context,
                        payload=payload,
                        prior_error="inline_auth_submit",
                        require_auth_check=False,
                        job_id=job_id,
                    )
                else:
                    try:
                        result = await self.adapter.execute(payload, session_bundle)
                    except Exception as exc:
                        logger.warning(
                            "submit_http_adapter_failed_after_possible_dispatch_no_fallback",
                            extra={
                                "extra_fields": {
                                    "job_id": job.job_id,
                                    "client_id": client_id,
                                    "driver_id": job.driver_id,
                                    "error": str(exc),
                                }
                            },
                        )
                        result = SubmitExecutionResult(
                            classification=SubmitClassification(
                                outcome=SubmitOutcome.UNKNOWN_ERROR,
                                reason_code="submission_unconfirmed",
                                retryable=False,
                                message=f"HTTP submit outcome ambiguous: {exc}",
                            ),
                            latency_ms=0,
                            raw_payload={"mutation_status": "ambiguous"},
                        )

                await rpa_runtime.increment_attempt(client_id, job.driver_id)
                classification = result.classification
                if classification.outcome == SubmitOutcome.SUCCESS:
                    raw_result = result.raw_payload if isinstance(result.raw_payload, dict) else {}
                    tracking_code = raw_result.get("tracking_code")
                    if not isinstance(tracking_code, str) or not tracking_code.strip():
                        classification = SubmitClassification(
                            outcome=SubmitOutcome.UNKNOWN_ERROR,
                            reason_code="submission_unconfirmed",
                            retryable=False,
                            http_status=classification.http_status,
                            message="Portal accepted the request without returning a tracking code",
                            response_excerpt=classification.response_excerpt,
                        )
                        result.classification = classification
                await self._record_attempt(session, job, runtime_state, classification, result.latency_ms)

                if classification.outcome == SubmitOutcome.SUCCESS:
                    res_json = {
                        "status": "success",
                        "reason": classification.reason_code,
                        "http_status": classification.http_status,
                        "latency_ms": result.latency_ms,
                    }
                    if result.raw_payload and isinstance(result.raw_payload, dict):
                        for k in ["waybill_screenshot", "tracking_code", "url", "route"]:
                            if k in result.raw_payload:
                                res_json[k] = result.raw_payload[k]
                    res_json["confirmation_status"] = "pending_history_reconciliation"
                    reconciliation_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=15)
                    job.mutation_status = "dispatched"
                    JobStateMachine.transition(
                        session,
                        job,
                        TaskStatus.UNKNOWN.value,
                        result_json=res_json,
                        finished_at=datetime.now(UTC).replace(tzinfo=None),
                        submit_after=reconciliation_at,
                        next_retry_at=reconciliation_at,
                        last_error="Tracking code received; UTCMS History reconciliation is pending",
                        error_category=ErrorCategory.SUBMISSION_UNCONFIRMED.value,
                        terminal_reason=classification.reason_code,
                        celery_task_id=None,
                        updated_at=datetime.now(UTC).replace(tzinfo=None),
                    )
                    runtime_state.state = DriverRuntimeStateValue.READY.value
                    runtime_state.next_retry_at = None
                    runtime_state.updated_at = datetime.now(UTC).replace(tzinfo=None)
                    driver.runtime_status = DriverStatus.READY.value
                    driver.last_error_code = None
                    await self._record_event(
                        session,
                        client_id,
                        job.driver_id,
                        job.job_id,
                        SUBMIT_SUCCEEDED,
                        {"reason": classification.reason_code, "confirmation_status": "pending_reconciliation"},
                    )
                elif classification.outcome == SubmitOutcome.AUTH_EXPIRED:
                    await rpa_runtime.delete_session(client_id, job.driver_id)
                    return await self._mark_waiting_auth(
                        session, job, driver, runtime_state, classification.reason_code
                    )
                elif classification.outcome in {SubmitOutcome.TRANSIENT_FAILURE, SubmitOutcome.RATE_LIMITED}:
                    job_error_category = _map_error_category(classification.outcome, classification.reason_code).value
                    next_retry_at_dt = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                        seconds=utcms_config.DRIVER_RETRY_DELAY_SECONDS
                    )
                    result_json = {
                        "status": "waiting_retry",
                        "reason": classification.reason_code,
                        "error_category": job_error_category,
                        "message": classification.message,
                        "http_status": classification.http_status,
                        "retry_at": next_retry_at_dt.isoformat() if next_retry_at_dt else None,
                    }
                    JobStateMachine.transition(
                        session,
                        job,
                        TaskStatus.WAITING_RETRY.value,
                        error_category=job_error_category,
                        last_error=classification.message or classification.reason_code,
                        next_retry_at=next_retry_at_dt,
                        submit_after=next_retry_at_dt,
                        finished_at=None,
                        celery_task_id=None,
                        updated_at=datetime.now(UTC).replace(tzinfo=None),
                        result_json=result_json,
                    )
                    job.result_json = result_json
                    runtime_state.state = DriverRuntimeStateValue.WAITING_RETRY.value
                    runtime_state.next_retry_at = job.next_retry_at
                    runtime_state.updated_at = datetime.now(UTC).replace(tzinfo=None)
                    driver.runtime_status = DriverStatus.WAITING_RETRY.value
                    driver.last_error_code = classification.reason_code
                    if classification.outcome == SubmitOutcome.RATE_LIMITED:
                        await rpa_runtime.apply_cooldown(
                            "tenant", str(client_id), utcms_config.RPA_PROXY_COOLDOWN_SECONDS
                        )
                    await self._record_event(
                        session,
                        client_id,
                        job.driver_id,
                        job.job_id,
                        SUBMIT_DELAYED,
                        {"reason": classification.reason_code, "retry_at": job.next_retry_at.isoformat()},
                    )
                else:
                    ambiguous = classification.outcome == SubmitOutcome.UNKNOWN_ERROR
                    target_status = (
                        TaskStatus.UNKNOWN.value
                        if ambiguous
                        else (
                            TaskStatus.NEEDS_REVIEW.value
                            if classification.outcome == SubmitOutcome.VALIDATION_ERROR
                            else TaskStatus.FAILED.value
                        )
                    )
                    job_error_category = _map_error_category(classification.outcome, classification.reason_code).value
                    result_json = {
                        "status": target_status,
                        "reason": classification.reason_code,
                        "error_category": job_error_category,
                        "message": classification.message,
                        "http_status": classification.http_status,
                    }
                    JobStateMachine.transition(
                        session,
                        job,
                        target_status,
                        error_category=job_error_category,
                        last_error=classification.message or classification.reason_code,
                        finished_at=datetime.now(UTC).replace(tzinfo=None),
                        submit_after=(
                            (datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=15)) if ambiguous else None
                        ),
                        next_retry_at=(
                            (datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=15)) if ambiguous else None
                        ),
                        terminal_reason=classification.reason_code,
                        celery_task_id=None,
                        updated_at=datetime.now(UTC).replace(tzinfo=None),
                        result_json=result_json,
                    )
                    job.result_json = result_json
                    if ambiguous:
                        job.mutation_status = "ambiguous"
                    runtime_state.state = DriverRuntimeStateValue.READY.value
                    runtime_state.next_retry_at = None
                    runtime_state.updated_at = datetime.now(UTC).replace(tzinfo=None)
                    driver.runtime_status = DriverStatus.READY.value
                    driver.last_error_code = classification.reason_code
                    await self._record_event(
                        session,
                        client_id,
                        job.driver_id,
                        job.job_id,
                        SUBMIT_FAILED,
                        {"reason": classification.reason_code},
                    )

                counter = await self._sync_counter_row(session, client_id, job.driver_id)
                if counter.successes >= utcms_config.DRIVER_DAILY_SUCCESS_CAP:
                    driver.runtime_status = DriverStatus.DAILY_LIMIT_REACHED.value
                    runtime_state.state = DriverRuntimeStateValue.DAILY_SUCCESS_LIMIT_REACHED.value
                elif counter.attempts >= utcms_config.DRIVER_DAILY_ATTEMPT_CAP:
                    driver.runtime_status = DriverStatus.DAILY_LIMIT_REACHED.value
                    runtime_state.state = DriverRuntimeStateValue.DAILY_ATTEMPT_LIMIT_REACHED.value

                await session.commit()
                return result
            except Exception as core_exc:
                logger.exception(
                    "submit_execution_unhandled_crash",
                    extra={
                        "extra_fields": {
                            "job_id": job.job_id,
                            "client_id": client_id,
                            "driver_id": job.driver_id,
                            "error": str(core_exc),
                        }
                    },
                )
                try:
                    # The portal may have accepted the request before the local
                    # process failed. Require reconciliation before another submit.
                    JobStateMachine.transition(
                        session,
                        job,
                        TaskStatus.NEEDS_REVIEW.value,
                        last_error=f"Unhandled crash: {str(core_exc)}",
                        error_category=ErrorCategory.SUBMISSION_UNCONFIRMED.value,
                        finished_at=datetime.now(UTC).replace(tzinfo=None),
                        celery_task_id=None,
                        updated_at=datetime.now(UTC).replace(tzinfo=None),
                    )
                    runtime_state.state = DriverRuntimeStateValue.READY.value
                    runtime_state.updated_at = datetime.now(UTC).replace(tzinfo=None)
                    driver.runtime_status = DriverStatus.READY.value
                    await session.commit()
                except Exception as db_exc:
                    logger.warning(
                        "failed_to_mark_job_as_failed_after_crash", extra={"extra_fields": {"error": str(db_exc)}}
                    )
                raise
        finally:
            if lock_acquired and "driver" in locals() and getattr(driver, "id", None):
                await rpa_runtime.release_lock(rpa_runtime.submit_lock_key(client_id, driver.id))
            await session.close()

    async def _mark_waiting_auth(
        self, session, job: WaybillJob, driver: Driver, runtime_state: DriverRuntimeState, reason: str
    ) -> SubmitExecutionResult:
        submit_after_dt = datetime.now(UTC).replace(tzinfo=None) + timedelta(
            seconds=utcms_config.DRIVER_RETRY_DELAY_SECONDS
        )
        result_json = {
            "status": "waiting_auth",
            "reason": reason,
            "error_category": ErrorCategory.AUTH_FAILURE.value,
        }
        JobStateMachine.transition(
            session,
            job,
            TaskStatus.WAITING_AUTH.value,
            error_category=ErrorCategory.AUTH_FAILURE.value,
            last_error=reason,
            submit_after=submit_after_dt,
            next_retry_at=None,
            finished_at=None,
            celery_task_id=None,
            updated_at=datetime.now(UTC).replace(tzinfo=None),
            result_json=result_json,
        )
        job.result_json = result_json
        runtime_state.state = DriverRuntimeStateValue.AUTH_REQUIRED.value
        runtime_state.next_retry_at = None
        runtime_state.updated_at = datetime.now(UTC).replace(tzinfo=None)
        driver.runtime_status = DriverStatus.AUTH_REQUIRED.value
        driver.last_error_code = reason
        await self._record_event(session, job.client_id, driver.id, job.job_id, SESSION_EXPIRED, {"reason": reason})
        await session.commit()
        return SubmitExecutionResult(
            classification=SubmitClassification(outcome=SubmitOutcome.AUTH_EXPIRED, reason_code=reason, retryable=True),
            latency_ms=0,
        )

    async def _execute_browser_submit(
        self,
        session,
        client_id: int,
        driver: Driver,
        job: WaybillJob,
        payload: dict[str, Any],
        prior_error: str,
    ) -> SubmitExecutionResult:
        metadata = (
            await session.exec(
                select(DriverSessionMetadata).where(
                    DriverSessionMetadata.client_id == client_id,
                    DriverSessionMetadata.driver_id == driver.id,
                )
            )
        ).first()
        auth_state_path = metadata.auth_state_path if metadata else None
        if not auth_state_path:
            return SubmitExecutionResult(
                classification=SubmitClassification(
                    outcome=SubmitOutcome.AUTH_EXPIRED,
                    reason_code="missing_auth_state",
                    retryable=True,
                    message="auth_state برای submit مرورگری موجود نیست",
                ),
                latency_ms=0,
            )

        start = time.perf_counter()
        internal_session_id = None
        page = None
        proxy_info = None
        try:
            await browser_manager.initialize()
            proxy_info = await get_proxy_rotator().get_next()
            proxy_dict = proxy_info.to_playwright_proxy() if proxy_info else None
            internal_session_id, context = await browser_manager.create_context(
                auth_state_path=auth_state_path, proxy_dict=proxy_dict
            )
            page = await browser_manager.new_page(context)
            res = await self._execute_browser_submit_with_page(
                page=page,
                context=context,
                payload=payload,
                prior_error=prior_error,
                require_auth_check=True,
                start_time=start,
                job_id=job.job_id,
            )
            if proxy_info:
                success = res.classification.outcome == SubmitOutcome.SUCCESS
                latency = time.perf_counter() - start
                proxy_info.record_waybill_result(success=success, latency=latency, error=res.classification.message)

            if res.classification.outcome == SubmitOutcome.SUCCESS:
                await browser_manager.record_success_for_recycle()
            else:
                from app.core.circuit_breaker import check_and_report_failure

                await check_and_report_failure(res.classification.message)

            return res
        except WaybillError as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            if proxy_info:
                proxy_info.record_waybill_result(success=False, latency=latency_ms / 1000.0, error=str(exc))
            from app.core.circuit_breaker import check_and_report_failure

            await check_and_report_failure(str(exc))
            category, retryable = classify_exception(exc)

            outcome = SubmitOutcome.UNKNOWN_ERROR
            if category == ErrorCategory.AUTH_FAILURE:
                outcome = SubmitOutcome.AUTH_EXPIRED
            elif category in {
                ErrorCategory.USER_DATA_ERROR,
                ErrorCategory.SELECTOR_CHANGED,
                ErrorCategory.BOT_DETECTED,
            }:
                outcome = SubmitOutcome.VALIDATION_ERROR
            elif category == ErrorCategory.TARGET_SITE_TIMEOUT:
                outcome = SubmitOutcome.RATE_LIMITED
            elif category in {
                ErrorCategory.TRANSIENT_INFRA_ERROR,
                ErrorCategory.CAPTCHA_EXHAUSTION,
                ErrorCategory.WORKER_RESOURCE_ERROR,
            }:
                outcome = SubmitOutcome.TRANSIENT_FAILURE

            return SubmitExecutionResult(
                classification=SubmitClassification(
                    outcome=outcome,
                    reason_code=f"browser_submit_{category.value.lower()}",
                    retryable=retryable,
                    message=str(exc),
                ),
                latency_ms=latency_ms,
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            if proxy_info:
                proxy_info.record_waybill_result(success=False, latency=latency_ms / 1000.0, error=str(exc))
            from app.core.circuit_breaker import check_and_report_failure

            await check_and_report_failure(str(exc))
            category, retryable = classify_exception(exc)

            outcome = SubmitOutcome.UNKNOWN_ERROR
            if category == ErrorCategory.AUTH_FAILURE:
                outcome = SubmitOutcome.AUTH_EXPIRED
            elif category in {
                ErrorCategory.USER_DATA_ERROR,
                ErrorCategory.SELECTOR_CHANGED,
                ErrorCategory.BOT_DETECTED,
            }:
                outcome = SubmitOutcome.VALIDATION_ERROR
            elif category == ErrorCategory.TARGET_SITE_TIMEOUT:
                outcome = SubmitOutcome.RATE_LIMITED
            elif category in {
                ErrorCategory.TRANSIENT_INFRA_ERROR,
                ErrorCategory.CAPTCHA_EXHAUSTION,
                ErrorCategory.WORKER_RESOURCE_ERROR,
            }:
                outcome = SubmitOutcome.TRANSIENT_FAILURE

            return SubmitExecutionResult(
                classification=SubmitClassification(
                    outcome=outcome,
                    reason_code=f"submit_{category.value.lower()}",
                    retryable=retryable,
                    message=f"{prior_error} | browser_fallback_error: {exc}",
                ),
                latency_ms=latency_ms,
            )
        finally:
            if page is not None:
                try:
                    await page.close()
                except Exception:
                    logger.warning("submit_page_close_failed", exc_info=True)
            if internal_session_id:
                try:
                    await browser_manager.close_context(internal_session_id)
                except Exception:
                    logger.warning("submit_context_close_failed", exc_info=True)

    async def _execute_browser_submit_with_page(
        self,
        page: Page,
        context: BrowserContext,
        payload: dict[str, Any],
        prior_error: str,
        require_auth_check: bool,
        start_time: float | None = None,
        job_id: str | None = None,
    ) -> SubmitExecutionResult:
        start = start_time or time.perf_counter()
        if require_auth_check:
            auth = UTCMSAuthenticator(page, context)
            if not await auth._is_logged_in():
                return SubmitExecutionResult(
                    classification=SubmitClassification(
                        outcome=SubmitOutcome.AUTH_EXPIRED,
                        reason_code="session_expired",
                        retryable=True,
                        message=auth.last_error or "session invalid during browser submit",
                    ),
                    latency_ms=int((time.perf_counter() - start) * 1000),
                )

        from app.automation.multitenant_payload_adapter import validate_enhanced_waybill_payload

        normalized_payload = build_enhanced_waybill_payload(payload)
        validation_errors = validate_enhanced_waybill_payload(normalized_payload)
        if validation_errors:
            return SubmitExecutionResult(
                classification=SubmitClassification(
                    outcome=SubmitOutcome.VALIDATION_ERROR,
                    reason_code="payload_validation_failed",
                    retryable=False,
                    message="اطلاعات اجباری UTCMS ناقص است: " + "، ".join(validation_errors),
                ),
                latency_ms=int((time.perf_counter() - start) * 1000),
            )

        manager = EnhancedWaybillManager(page, context)
        manager_result = await manager.create_waybill_with_map(
            normalized_payload,
            dry_run=False,
            job_id=job_id,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        if manager_result.get("success"):
            return SubmitExecutionResult(
                classification=SubmitClassification(
                    outcome=SubmitOutcome.SUCCESS,
                    reason_code="browser_submit_success",
                    retryable=False,
                    response_excerpt=json.dumps(manager_result, ensure_ascii=False)[:1000],
                ),
                latency_ms=latency_ms,
                raw_payload=manager_result,
            )
        reason = str(manager_result.get("status") or manager_result.get("message") or "browser_submit_failed")
        return SubmitExecutionResult(
            classification=SubmitClassification(
                outcome=SubmitOutcome.TRANSIENT_FAILURE,
                reason_code=reason,
                retryable=True,
                message=f"{prior_error} | browser_submit_failed",
                response_excerpt=json.dumps(manager_result, ensure_ascii=False)[:1000],
            ),
            latency_ms=latency_ms,
            raw_payload=manager_result,
        )

    async def _mark_daily_limit(
        self, session, job, driver, runtime_state, counter, success_limit: bool
    ) -> SubmitExecutionResult:
        reason = "daily_success_limit_reached" if success_limit else "daily_attempt_limit_reached"
        JobStateMachine.transition(
            session,
            job,
            TaskStatus.DAILY_LIMIT_REACHED.value,
            terminal_reason=reason,
            finished_at=datetime.now(UTC).replace(tzinfo=None),
            submit_after=None,
            next_retry_at=None,
            celery_task_id=None,
            updated_at=datetime.now(UTC).replace(tzinfo=None),
        )
        runtime_state.state = (
            DriverRuntimeStateValue.DAILY_SUCCESS_LIMIT_REACHED.value
            if success_limit
            else DriverRuntimeStateValue.DAILY_ATTEMPT_LIMIT_REACHED.value
        )
        runtime_state.next_retry_at = None
        runtime_state.updated_at = datetime.now(UTC).replace(tzinfo=None)
        driver.runtime_status = DriverStatus.DAILY_LIMIT_REACHED.value
        driver.last_error_code = reason
        await self._record_event(
            session,
            job.client_id,
            driver.id,
            job.job_id,
            DRIVER_LIMIT_REACHED,
            {"reason": reason, "attempts": counter.attempts, "successes": counter.successes},
        )
        await session.commit()
        return SubmitExecutionResult(
            classification=SubmitClassification(
                outcome=SubmitOutcome.VALIDATION_ERROR, reason_code=reason, retryable=False
            ),
            latency_ms=0,
        )

    async def _record_attempt(
        self,
        session,
        job: WaybillJob,
        runtime_state: DriverRuntimeState,
        classification: SubmitClassification,
        latency_ms: int,
    ) -> None:
        session.add(
            WaybillAttempt(
                attempt_id=f"att_{hashlib.sha256(f'{job.job_id}:{job.attempt_count + 1}:{time.time()}'.encode()).hexdigest()[:24]}",
                job_id=job.job_id,
                client_id=job.client_id,
                driver_id=job.driver_id,
                attempt_no=job.attempt_count + 1,
                attempt_type=AttemptType.SUBMIT.value,
                result=_map_attempt_result(classification.outcome),
                http_status=classification.http_status,
                reason_code=classification.reason_code,
                latency_ms=latency_ms,
                session_version=runtime_state.session_version,
                proxy_key=runtime_state.proxy_key,
                response_excerpt=(classification.response_excerpt or classification.message or "")[:1000] or None,
            )
        )
        job.attempt_count += 1

    async def _get_or_create_runtime_state(self, session, client_id: int, driver_id: int) -> DriverRuntimeState:
        state = (
            await session.exec(select(DriverRuntimeState).where(DriverRuntimeState.driver_id == driver_id))
        ).first()
        if state is None:
            state = DriverRuntimeState(client_id=client_id, driver_id=driver_id)
            session.add(state)
            await session.flush()
        return state

    async def _sync_counter_row(self, session, client_id: int, driver_id: int) -> DriverDailyCounter:
        snapshot = await rpa_runtime.counter_snapshot(client_id, driver_id)
        counter = (
            await session.exec(
                select(DriverDailyCounter).where(
                    DriverDailyCounter.client_id == client_id,
                    DriverDailyCounter.driver_id == driver_id,
                    DriverDailyCounter.business_date == snapshot.business_date,
                )
            )
        ).first()
        if counter is None:
            counter = DriverDailyCounter(client_id=client_id, driver_id=driver_id, business_date=snapshot.business_date)
            session.add(counter)
        counter.attempts = snapshot.attempts
        counter.successes = snapshot.successes
        counter.updated_at = datetime.now(UTC).replace(tzinfo=None)
        if snapshot.attempts:
            counter.last_attempt_at = datetime.now(UTC).replace(tzinfo=None)
        if snapshot.successes:
            counter.last_success_at = datetime.now(UTC).replace(tzinfo=None)
        return counter

    async def _record_event(
        self, session, client_id: int, driver_id: int, job_id: str | None, event_type: str, payload: dict
    ) -> None:
        session.add(
            DomainEvent(
                event_id=f"evt_{hashlib.sha256(f'{event_type}:{job_id}:{time.time()}'.encode()).hexdigest()[:24]}",
                event_type=event_type,
                client_id=client_id,
                driver_id=driver_id,
                job_id=job_id,
                payload_json=json.dumps(payload, ensure_ascii=False),
            )
        )


def classify_submit_response(status_code: int, body: str) -> SubmitClassification:
    lowered = (body or "").lower()
    excerpt = (body or "")[:1000]
    persian_body = body or ""

    # Parse response as JSON to check for explicit business errors
    import json

    is_json = False
    json_data = None
    try:
        json_data = json.loads(body)
        is_json = True
    except (ValueError, TypeError) as exc:
        # Expected when the response body is HTML (portal landing pages,
        # error pages, etc.). Not actionable.
        body_prefix = body[:120] if isinstance(body, str) else None
        logger.debug(
            "rpa_submit_response_body_not_json",
            extra={"extra_fields": {"error": str(exc), "body_prefix": body_prefix}},
        )

    if is_json and isinstance(json_data, dict):
        success_val = json_data.get("success")
        if success_val is None:
            success_val = json_data.get("isSuccess")
        if success_val is None:
            success_val = json_data.get("is_success")

        if success_val is False or str(success_val).lower() == "false":
            message = json_data.get("message") or json_data.get("error") or "portal_business_error"
            return SubmitClassification(
                outcome=SubmitOutcome.VALIDATION_ERROR,
                reason_code="portal_validation_error",
                retryable=False,
                http_status=status_code,
                message=str(message),
                response_excerpt=excerpt,
            )

    # Persian success indicators from UTCMS portal
    # IMPORTANT: tokens should be specific enough to avoid false positives on error pages
    # "تایید" alone is too broad (appears on error pages too); require "با موفقیت" context
    _ps_success_patterns = ("با موفقیت ثبت شد", "بارنامه ثبت شد", "کد رهگیری", "شماره بارنامه", "چاپ بارنامه")
    persian_success_match = any(p in persian_body for p in _ps_success_patterns)
    has_success_token = (
        "success" in lowered and '"success":false' not in lowered.replace(" ", "") and '"success": false' not in lowered
    )

    if status_code in {200, 201} and (has_success_token or persian_success_match):
        return SubmitClassification(
            outcome=SubmitOutcome.SUCCESS,
            reason_code="portal_success",
            retryable=False,
            http_status=status_code,
            response_excerpt=excerpt,
        )
    if status_code in {401, 403} or any(
        token in lowered for token in ("session expired", "login", "unauthorized", "دوباره وارد")
    ):
        return SubmitClassification(
            SubmitOutcome.AUTH_EXPIRED, "session_expired", True, status_code, response_excerpt=excerpt
        )
    if status_code == 409 or "duplicate" in lowered or "تکراری" in lowered:
        return SubmitClassification(
            SubmitOutcome.DUPLICATE, "duplicate_registration", False, status_code, response_excerpt=excerpt
        )
    if status_code == 429 or "rate limit" in lowered or "too many" in lowered:
        return SubmitClassification(
            SubmitOutcome.RATE_LIMITED, "rate_limited", True, status_code, response_excerpt=excerpt
        )
    if 400 <= status_code < 500:
        return SubmitClassification(
            SubmitOutcome.VALIDATION_ERROR, "validation_error", False, status_code, response_excerpt=excerpt
        )
    if status_code >= 500:
        return SubmitClassification(
            SubmitOutcome.TRANSIENT_FAILURE, "portal_server_error", True, status_code, response_excerpt=excerpt
        )
    return SubmitClassification(
        SubmitOutcome.UNKNOWN_ERROR, "unknown_response", False, status_code, response_excerpt=excerpt
    )


def build_job_idempotency_key(
    client_id: int, driver_id: int, payload: dict[str, Any], supplied: str | None = None
) -> str:
    from app.core.submission_identity import compute_canonical_job_idempotency_key

    return compute_canonical_job_idempotency_key(
        client_id=client_id,
        driver_id=driver_id,
        payload=payload,
        supplied_key=supplied,
    )


def _map_attempt_result(outcome: SubmitOutcome) -> str:
    mapping = {
        SubmitOutcome.SUCCESS: AttemptResult.SUCCESS.value,
        SubmitOutcome.AUTH_EXPIRED: AttemptResult.AUTH_EXPIRED.value,
        SubmitOutcome.RATE_LIMITED: AttemptResult.RATE_LIMITED.value,
        SubmitOutcome.TRANSIENT_FAILURE: AttemptResult.TRANSIENT_FAILURE.value,
        SubmitOutcome.VALIDATION_ERROR: AttemptResult.VALIDATION_ERROR.value,
        SubmitOutcome.DUPLICATE: AttemptResult.DUPLICATE.value,
        SubmitOutcome.UNKNOWN_ERROR: AttemptResult.UNKNOWN_ERROR.value,
    }
    return mapping[outcome]


rpa_submit_service = RPAHttpSubmitService()
