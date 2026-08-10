"""Playwright-heavy auth worker for Phase 1 hybrid RPA."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel import select

from app.auth_multitenant import DriverPasswordDecryptError, decrypt_driver_password
from app.automation.auth import UTCMSAuthenticator
from app.automation.browser import browser_manager
from app.automation.proxy_rotator import get_proxy_rotator
from app.core.config import utcms_config
from app.core.database import async_session_factory
from app.core.error_taxonomy import ErrorCategory
from app.models_multitenant import Driver, DriverStatus, TaskStatus, WaybillJob
from app.models_rpa import DomainEvent, DriverRuntimeState, DriverRuntimeStateValue, DriverSessionMetadata
from app.orchestrator.state_machine import JobStateMachine
from app.rpa.contracts import AuthResult, SessionBundle
from app.rpa.event_taxonomy import AUTH_FAILED, AUTH_SUCCEEDED
from app.services.rpa_runtime_service import rpa_runtime
from app.services.rpa_submit_service import rpa_submit_service
from app.services.session_vault import session_vault

logger = logging.getLogger(__name__)


class RPAAuthService:
    async def authenticate_driver(
        self, client_id: int, driver_id: int, reason: str, resume_job_id: str | None = None
    ) -> AuthResult:
        lock_key = rpa_runtime.auth_lock_key(client_id, driver_id)
        if not await rpa_runtime.acquire_lock(lock_key, utcms_config.RPA_LOCK_TTL_SECONDS):
            return AuthResult(
                ok=False,
                session_bundle=None,
                reason_code="auth_in_progress",
                message="Authentication already in progress",
            )

        session = async_session_factory()
        session_id = None
        page = None
        try:
            driver = await session.get(Driver, driver_id)
            if not driver:
                logger.error(
                    "phase1_auth_driver_not_found",
                    extra={"extra_fields": {"driver_id": driver_id, "client_id": client_id}},
                )
                return AuthResult(ok=False, session_bundle=None, reason_code="driver_not_found")
            if driver.client_id != client_id:
                logger.warning(
                    "phase1_auth_client_id_mismatch_rejected",
                    extra={
                        "extra_fields": {
                            "driver_id": driver_id,
                            "requested_client_id": client_id,
                            "actual_client_id": driver.client_id,
                        }
                    },
                )
                return AuthResult(ok=False, session_bundle=None, reason_code="driver_tenant_mismatch")

            runtime_state = await self._get_or_create_runtime_state(session, client_id, driver_id)
            runtime_state.state = DriverRuntimeStateValue.AUTH_IN_PROGRESS.value
            runtime_state.updated_at = datetime.now(UTC).replace(tzinfo=None)
            await session.commit()

            auth_state_path = session_vault.auth_state_path_for_account(
                username=driver.utcms_username,
                national_code=driver.driver_national_code,
                fallback=str(driver.id),
                scope=f"client-{client_id}-driver-{driver.id}",
            )
            session_vault.ensure_parent_dir(auth_state_path)

            await browser_manager.initialize()
            proxy_info = await get_proxy_rotator().get_next()
            proxy_dict = proxy_info.to_playwright_proxy() if proxy_info else None
            session_id, context = await browser_manager.create_context(
                auth_state_path=auth_state_path, proxy_dict=proxy_dict
            )
            page = await browser_manager.new_page(context)
            authenticator = UTCMSAuthenticator(page, context)
            try:
                driver_password = decrypt_driver_password(driver.utcms_password_encrypted)
            except DriverPasswordDecryptError as exc:
                # Wrong DRIVER_ENCRYPTION_KEY — the ciphertext is undecryptable, so
                # launching a browser is pointless. Fail fast with a clear reason.
                await self._mark_auth_failure(session, driver, runtime_state, "driver_key_mismatch")
                await self._mark_resume_job_for_auth_retry(session, client_id, resume_job_id, "driver_key_mismatch")
                return AuthResult(ok=False, session_bundle=None, reason_code="driver_key_mismatch", message=str(exc))
            ok = await authenticator.login(driver.utcms_username, driver_password)
            if not ok:
                message = authenticator.last_error or "login_failed"
                from app.core.circuit_breaker import check_and_report_failure

                await check_and_report_failure(message)
                await self._mark_auth_failure(session, driver, runtime_state, message)
                await self._mark_resume_job_for_auth_retry(session, client_id, resume_job_id, message)
                return AuthResult(ok=False, session_bundle=None, reason_code="login_failed", message=message)

            cookies = await context.cookies()
            session_expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                seconds=utcms_config.RPA_SESSION_TTL_SECONDS
            )
            bundle = SessionBundle(
                cookies=cookies,
                user_agent=await page.evaluate("() => navigator.userAgent"),
                issued_at=datetime.now(UTC).replace(tzinfo=None).isoformat(),
                expires_at=session_expires_at.isoformat(),
                session_version=runtime_state.session_version + 1,
                proxy_key=runtime_state.proxy_key,
            )
            await browser_manager.save_auth_state(
                context, auth_state_path=auth_state_path, session_version=bundle.session_version
            )
            await rpa_runtime.store_session(client_id, driver_id, bundle)

            metadata = await self._get_or_create_session_metadata(session, client_id, driver_id)
            metadata.session_version = bundle.session_version
            metadata.auth_state_path = auth_state_path
            metadata.user_agent = bundle.user_agent
            metadata.expires_at = session_expires_at
            metadata.last_auth_result = "success"
            metadata.last_auth_at = datetime.now(UTC).replace(tzinfo=None)
            metadata.proxy_key = runtime_state.proxy_key
            metadata.updated_at = datetime.now(UTC).replace(tzinfo=None)

            runtime_state.state = DriverRuntimeStateValue.READY.value
            runtime_state.session_version = bundle.session_version
            runtime_state.last_auth_at = datetime.now(UTC).replace(tzinfo=None)
            runtime_state.session_expires_at = session_expires_at
            runtime_state.last_error_code = None
            runtime_state.next_retry_at = None
            runtime_state.updated_at = datetime.now(UTC).replace(tzinfo=None)

            driver.runtime_status = DriverStatus.READY.value
            driver.last_auth_at = runtime_state.last_auth_at
            driver.last_session_expires_at = session_expires_at
            driver.last_error_code = None

            await self._record_event(
                session,
                client_id=client_id,
                driver_id=driver_id,
                job_id=resume_job_id,
                event_type=AUTH_SUCCEEDED,
                payload={"reason": reason, "session_version": bundle.session_version, "resume_job_id": resume_job_id},
            )

            inline_submit_result = None
            if resume_job_id:
                statement = select(WaybillJob).where(
                    WaybillJob.job_id == resume_job_id, WaybillJob.client_id == client_id
                )
                job = (await session.exec(statement)).first()
                if job and job.status == TaskStatus.WAITING_AUTH.value:
                    now = datetime.now(UTC).replace(tzinfo=None)
                    JobStateMachine.transition(
                        session,
                        job,
                        TaskStatus.QUEUED.value,
                        expected_from={TaskStatus.WAITING_AUTH.value},
                        submit_after=now,
                        next_retry_at=None,
                        last_error=None,
                        error_category=None,
                        celery_task_id=f"inline-auth-{bundle.session_version}",
                    )

            await session.commit()
            if resume_job_id:
                try:
                    inline_submit_result = await rpa_submit_service.process_job_live(
                        client_id=client_id,
                        job_id=resume_job_id,
                        page=page,
                        context=context,
                        session_bundle=bundle,
                    )
                    logger.info(
                        "phase1_auth_inline_submit_finished",
                        extra={
                            "extra_fields": {
                                "client_id": client_id,
                                "driver_id": driver_id,
                                "job_id": resume_job_id,
                                "outcome": inline_submit_result.classification.outcome.value,
                                "reason_code": inline_submit_result.classification.reason_code,
                            }
                        },
                    )
                except Exception as submit_exc:
                    logger.warning(
                        "phase1_auth_inline_submit_failed_but_auth_succeeded",
                        extra={
                            "extra_fields": {
                                "client_id": client_id,
                                "driver_id": driver_id,
                                "job_id": resume_job_id,
                                "error": str(submit_exc),
                            }
                        },
                    )
            return AuthResult(
                ok=True, session_bundle=bundle, reason_code="authenticated", expires_at=session_expires_at
            )
        except Exception as exc:  # pragma: no cover - integration-heavy path
            logger.exception(
                "phase1_auth_failed",
                extra={"extra_fields": {"client_id": client_id, "driver_id": driver_id, "error": str(exc)}},
            )
            from app.core.circuit_breaker import check_and_report_failure

            await check_and_report_failure(str(exc))
            try:
                await session.rollback()
            except Exception:
                logger.warning(
                    "phase1_auth_rollback_failed",
                    extra={"extra_fields": {"client_id": client_id, "driver_id": driver_id}},
                )

            recovery_session = async_session_factory()
            try:
                # Reset runtime state to prevent sticking in AUTH_IN_PROGRESS
                rs = (
                    await recovery_session.exec(
                        select(DriverRuntimeState).where(DriverRuntimeState.driver_id == driver_id)
                    )
                ).first()
                if rs:
                    rs.state = DriverRuntimeStateValue.AUTH_REQUIRED.value
                    rs.updated_at = datetime.now(UTC).replace(tzinfo=None)
                    recovery_session.add(rs)

                await self._mark_resume_job_for_auth_retry(recovery_session, client_id, resume_job_id, str(exc))
                await recovery_session.commit()
            except Exception as rec_exc:
                logger.warning("auth_recovery_failed", extra={"extra_fields": {"error": str(rec_exc)}})
            finally:
                await recovery_session.close()
            return AuthResult(ok=False, session_bundle=None, reason_code="unexpected_auth_error", message=str(exc))
        finally:
            if page is not None:
                try:
                    await page.close()
                except Exception:
                    logger.warning("phase1_auth_page_close_failed", exc_info=True)
            if session_id:
                try:
                    await browser_manager.close_context(session_id)
                except Exception:
                    logger.warning("phase1_auth_context_close_failed", exc_info=True)
            await session.close()
            await rpa_runtime.release_lock(lock_key)

    async def _mark_auth_failure(
        self, session, driver: Driver, runtime_state: DriverRuntimeState, message: str
    ) -> None:
        retry_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=utcms_config.DRIVER_RETRY_DELAY_SECONDS)
        runtime_state.state = (
            DriverRuntimeStateValue.ERROR_REVIEW.value
            if "selector" in message.lower()
            else DriverRuntimeStateValue.AUTH_REQUIRED.value
        )
        runtime_state.last_error_code = "login_failed"
        runtime_state.next_retry_at = retry_at
        runtime_state.updated_at = datetime.now(UTC).replace(tzinfo=None)
        driver.runtime_status = DriverStatus.AUTH_REQUIRED.value
        driver.last_error_code = "login_failed"
        await self._record_event(
            session,
            client_id=driver.client_id,
            driver_id=driver.id,
            job_id=None,
            event_type=AUTH_FAILED,
            payload={"message": message},
        )
        await session.commit()

    async def _mark_resume_job_for_auth_retry(
        self,
        session,
        client_id: int,
        resume_job_id: str | None,
        message: str,
    ) -> None:
        if not resume_job_id:
            return
        retry_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=utcms_config.DRIVER_RETRY_DELAY_SECONDS)
        job = (
            await session.exec(
                select(WaybillJob).where(
                    WaybillJob.client_id == client_id,
                    WaybillJob.job_id == resume_job_id,
                )
            )
        ).first()
        if job is None:
            return
        JobStateMachine.transition(
            session,
            job,
            TaskStatus.WAITING_AUTH.value,
            last_error=message,
            error_category=ErrorCategory.AUTH_FAILURE.value,
            next_retry_at=retry_at,
            submit_after=retry_at,
            celery_task_id=None,
            updated_at=datetime.now(UTC).replace(tzinfo=None),
        )
        session.add(job)
        await session.commit()

    async def _get_or_create_runtime_state(self, session, client_id: int, driver_id: int) -> DriverRuntimeState:
        state = (
            await session.exec(select(DriverRuntimeState).where(DriverRuntimeState.driver_id == driver_id))
        ).first()
        if state is None:
            state = DriverRuntimeState(client_id=client_id, driver_id=driver_id)
            session.add(state)
            await session.flush()
        elif state.client_id != client_id:
            # Self-heal stale client_id in runtime_state
            logger.warning(
                "runtime_state_client_id_self_heal",
                extra={
                    "extra_fields": {
                        "driver_id": driver_id,
                        "old_client_id": state.client_id,
                        "correct_client_id": client_id,
                    }
                },
            )
            state.client_id = client_id
            session.add(state)
            await session.flush()
        return state

    async def _get_or_create_session_metadata(self, session, client_id: int, driver_id: int) -> DriverSessionMetadata:
        item = (
            await session.exec(select(DriverSessionMetadata).where(DriverSessionMetadata.driver_id == driver_id))
        ).first()
        if item is None:
            item = DriverSessionMetadata(client_id=client_id, driver_id=driver_id)
            session.add(item)
            await session.flush()
        elif item.client_id != client_id:
            # Self-heal stale client_id in session_metadata
            item.client_id = client_id
            session.add(item)
            await session.flush()
        return item

    async def keepalive_sessions(self) -> dict[str, Any]:
        """Proactively refresh driver sessions that are close to expiring.

        Runs every 30 minutes via Celery Beat. Queries all active drivers whose
        sessions expire within the next 35 minutes and re-authenticates them.
        """
        session = async_session_factory()
        results: dict[str, Any] = {"checked": 0, "refreshed": 0, "errors": 0, "details": []}
        try:
            now = datetime.now(UTC).replace(tzinfo=None)
            skew = utcms_config.RPA_SESSION_REFRESH_SKEW_SECONDS
            # Only sessions that actually need refreshing soon (within skew window)
            threshold = now + timedelta(seconds=skew)
            stmt = (
                select(DriverRuntimeState)
                .where(DriverRuntimeState.session_expires_at.isnot(None))
                .where(DriverRuntimeState.session_expires_at < threshold)
                .where(
                    DriverRuntimeState.state.in_(
                        [
                            DriverRuntimeStateValue.READY.value,
                            DriverRuntimeStateValue.ACTIVE.value,
                        ]
                    )
                )
            )
            rows = (await session.exec(stmt)).all()
            results["checked"] = len(rows)
            for drs in rows:
                try:
                    auth_result = await self.authenticate_driver(drs.client_id, drs.driver_id, "session_keepalive")
                    if auth_result.ok:
                        results["refreshed"] += 1
                        results["details"].append(
                            {
                                "driver_id": drs.driver_id,
                                "client_id": drs.client_id,
                                "outcome": "refreshed",
                            }
                        )
                    else:
                        results["errors"] += 1
                        results["details"].append(
                            {
                                "driver_id": drs.driver_id,
                                "client_id": drs.client_id,
                                "outcome": "failed",
                                "reason": auth_result.reason_code,
                            }
                        )
                except Exception as e:
                    results["errors"] += 1
                    results["details"].append(
                        {
                            "driver_id": drs.driver_id,
                            "client_id": drs.client_id,
                            "outcome": "exception",
                            "error": str(e),
                        }
                    )
                    logger.exception(f"Session keepalive failed for driver {drs.driver_id}")
        except Exception:
            logger.exception("Session keepalive query failed")
            results["error"] = "query_failed"
        finally:
            await session.close()
        logger.info("session_keepalive_complete", extra={"extra_fields": results})
        return results

    async def _record_event(
        self, session, client_id: int, driver_id: int, job_id: str | None, event_type: str, payload: dict
    ) -> None:
        session.add(
            DomainEvent(
                event_id=f"evt_{datetime.now(UTC).replace(tzinfo=None).timestamp():.6f}_{driver_id}",
                event_type=event_type,
                client_id=client_id,
                driver_id=driver_id,
                job_id=job_id,
                payload_json=json.dumps(payload, ensure_ascii=False),
            )
        )


rpa_auth_service = RPAAuthService()
