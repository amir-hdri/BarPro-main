"""Multi-tenant waybill bot powered by the project's self-healing automation stack."""

import logging
from typing import Any

from playwright.async_api import BrowserContext, Page

from app.automation.auth import UTCMSAuthenticator
from app.automation.multitenant_payload_adapter import (
    build_enhanced_waybill_payload,
    validate_enhanced_waybill_payload,
)
from app.automation.waybill_enhanced import EnhancedWaybillManager
from app.core.config import utcms_config
from app.core.exceptions import WaybillError
from app.models_multitenant import TaskStatus

logger = logging.getLogger(__name__)


class WaybillAutomationBot:
    """Adapter that integrates the multi-tenant worker with the self-healing manager.

    Instead of maintaining a second, weaker automation flow, this class reuses the
    production-grade login/captcha/navigation/map fallback logic from
    `UTCMSAuthenticator` and `EnhancedWaybillManager`.
    """

    def __init__(self, page: Page, context: BrowserContext):
        self.page = page
        self.context = context
        self.last_error: str | None = None
        self.last_state: str | None = None
        self.authenticator = UTCMSAuthenticator(page, context)
        self.manager = EnhancedWaybillManager(page, context)

    async def execute_waybill_job(
        self,
        username: str,
        password: str,
        payload: dict[str, Any],
        job_id: str,
        client_id: int,
        auth_state_path: str | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "job_id": job_id,
            "client_id": client_id,
            "status": TaskStatus.PENDING.value,
            "result": None,
            "error": None,
            "error_category": None,
            "steps": [],
            "self_healing": {
                "auth_stack": "UTCMSAuthenticator",
                "form_stack": "EnhancedWaybillManager",
                "payload_adapter": "multitenant_payload_adapter",
            },
        }

        from app.automation.browser import browser_manager
        from app.services.session_vault import session_vault

        driver_national_code = payload.get("driver_national_code") or payload.get("vehicle", {}).get(
            "driver_national_code"
        )
        auth_state_path = auth_state_path or session_vault.auth_state_path_for_account(
            username=username,
            national_code=driver_national_code,
            fallback=username,
            scope=f"client-{client_id}",
        )

        try:
            normalized_payload = build_enhanced_waybill_payload(payload)
            validation_errors = validate_enhanced_waybill_payload(normalized_payload, enforce_live_party_phones=True)
            if validation_errors:
                result["status"] = TaskStatus.NEEDS_REVIEW.value
                result["error"] = "اطلاعات اجباری UTCMS ناقص است: " + "، ".join(validation_errors)
                result["error_category"] = "payload_validation_failed"
                result["steps"].append(
                    {
                        "step": "pre_submit_validation",
                        "status": "needs_review",
                        "message": result["error"],
                    }
                )
                return result

            from app.automation.http_browser_bridge import ensure_utcms_http_browser_bridge

            await ensure_utcms_http_browser_bridge(self.page)
            # Check if we are already logged in via active session cookies
            # Pass probe_login_url=False to avoid slow page navigations on startup!
            is_logged_in = await self.authenticator._is_logged_in(probe_login_url=False)
            login_success = True

            if not is_logged_in:
                login_success = await self.authenticator.login(username, password)
                if login_success:
                    await browser_manager.save_auth_state(self.context, auth_state_path=auth_state_path)
            else:
                logger.info(f"Reusing active authenticated session for driver: {username}")

            if not login_success:
                self.last_error = self.authenticator.last_error or "login_failed"
                self.last_state = self.authenticator.last_state or "failed"
                result["status"] = TaskStatus.FAILED.value
                result["error"] = self.last_error
                result["error_category"] = "captcha_failed" if self.last_state == "captcha_failed" else "login_failed"
                result["steps"].append(
                    {
                        "step": "login",
                        "status": "failed",
                        "message": self.last_error,
                        "state": self.last_state,
                    }
                )
                return result

            result["steps"].append(
                {
                    "step": "login",
                    "status": "success",
                    "message": "Login successful or session reused via self-healing authenticator",
                }
            )

            dry_run = not utcms_config.ALLOW_LIVE_SUBMIT
            manager_result = await self.manager.create_waybill_with_map(
                normalized_payload, dry_run=dry_run, job_id=job_id
            )

            # Self-healing: if session was reused but creation failed, check if we got redirected to login page
            mutation_may_have_been_dispatched = bool(
                manager_result.get("mutation_dispatched")
                or manager_result.get("mutation_status") == "ambiguous"
                or manager_result.get("needs_reconciliation")
                or str(manager_result.get("status", "")).lower() in {"unknown", "reconciling"}
            )
            if is_logged_in and not manager_result.get("success", False) and not mutation_may_have_been_dispatched:
                # ``Page.url`` is a property (str), not a coroutine — awaiting a
                # call on it raises TypeError and would be swallowed by the
                # broad handler below, masking the real submission error.
                # Path-based login detection (bug-class fix): raw substring
                # matching flagged URLs like "/Catalog?ref=LoginBanner" as a
                # login bounce, triggering a needless fresh login AND a second
                # create_waybill run — a duplicate-submission hazard.
                from app.automation.auth_utils import is_login_url

                current_url = self.page.url or ""
                if is_login_url(current_url):
                    logger.warning("Reused session expired/logged out during execution. Retrying with fresh login...")
                    # Try a fresh login
                    login_success = await self.authenticator.login(username, password)
                    if login_success:
                        await browser_manager.save_auth_state(self.context, auth_state_path=auth_state_path)
                        # Try creation again
                        manager_result = await self.manager.create_waybill_with_map(
                            normalized_payload, dry_run=dry_run, job_id=job_id
                        )

            # A fresh-login retry produces a new result; recompute the mutation
            # boundary before deciding whether any further submit is safe.
            mutation_may_have_been_dispatched = bool(
                manager_result.get("mutation_dispatched")
                or manager_result.get("mutation_status") == "ambiguous"
                or manager_result.get("needs_reconciliation")
                or str(manager_result.get("status", "")).lower() in {"unknown", "reconciling", "submitted"}
                or str(manager_result.get("confirmation_status", "")).lower() == "pending_history_reconciliation"
            )

            result["steps"].append(
                {
                    "step": "create_waybill_with_map",
                    "status": "success" if manager_result.get("success") else "failed",
                    "message": manager_result.get("message") or manager_result.get("status") or "waybill_processed",
                }
            )

            if str(manager_result.get("status", "")).strip().lower() == "otp_backoff":
                result["status"] = TaskStatus.OTP_BACKOFF.value
                result["error"] = manager_result.get("message")
                result["error_category"] = "otp_required"
                result["next_retry_at_minutes_add"] = manager_result.get("next_retry_at_minutes_add", 60)
                result["steps"].append(
                    {
                        "step": "otp_backoff",
                        "status": "waiting_retry",
                        "message": manager_result.get("message") or "OTP challenge detected",
                    }
                )
                return result

            if str(manager_result.get("status", "")).strip().lower() == "validated":
                result["status"] = "validated"
                result["result"] = manager_result.get("validation_summary") or {}
                result["steps"].append(
                    {
                        "step": "pre_submit_validation",
                        "status": "success",
                        "message": "Waybill form validated; final submit was disabled",
                    }
                )
                return result

            if mutation_may_have_been_dispatched:
                result["status"] = TaskStatus.UNKNOWN.value
                result["error"] = manager_result.get("message") or manager_result.get("error")
                result["error_category"] = "submission_unconfirmed"
                result["mutation_status"] = "ambiguous"
                result["needs_reconciliation"] = True
                if manager_result.get("document_id"):
                    result["document_id"] = manager_result["document_id"]
                return result

            if not manager_result.get("success", False):
                result["status"] = TaskStatus.FAILED.value
                result["error"] = (
                    manager_result.get("message") or manager_result.get("error") or "waybill_submission_failed"
                )
                result["error_category"] = "submission_failed"
                return result

            tracking_code = manager_result.get("tracking_code")
            if not tracking_code:
                result["status"] = TaskStatus.FAILED.value
                result["error"] = "waybill_submission_unconfirmed"
                result["error_category"] = "submission_unconfirmed"
                return result

            # A browser tracking code is only witness 1/3. Keep the job in the
            # reconciliation path until History/Search confirms the mutation.
            result["status"] = TaskStatus.UNKNOWN.value
            result["result"] = {
                "tracking_code": tracking_code,
                "url": manager_result.get("url"),
                "origin_method": manager_result.get("origin_method"),
                "destination_method": manager_result.get("destination_method"),
                "origin_map_type": manager_result.get("origin_map_type"),
                "destination_map_type": manager_result.get("destination_map_type"),
                "route": manager_result.get("route"),
                "waybill_screenshot": manager_result.get("waybill_screenshot"),
                "confirmation_status": "pending_history_reconciliation",
            }
            result["error_category"] = "submission_unconfirmed"
            result["mutation_status"] = "dispatched"
            result["needs_reconciliation"] = True
            result["steps"].append(
                {
                    "step": "submit",
                    "status": "success",
                    "message": manager_result.get("tracking_code") or "Waybill registered successfully",
                }
            )
            return result

        except WaybillError as exc:
            self.last_error = str(exc)
            result["status"] = TaskStatus.FAILED.value
            result["error"] = self.last_error
            result["error_category"] = self._categorize_waybill_error(exc)
            result["steps"].append(
                {
                    "step": "waybill",
                    "status": "failed",
                    "message": self.last_error,
                }
            )
            logger.warning(
                "multitenant_waybill_failed", extra={"extra_fields": {"job_id": job_id, "error": self.last_error}}
            )
            return result
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            result["status"] = TaskStatus.FAILED.value
            result["error"] = self.last_error
            result["error_category"] = "unknown"
            result["steps"].append(
                {
                    "step": "execution",
                    "status": "failed",
                    "message": self.last_error,
                }
            )
            logger.exception(
                "multitenant_waybill_unexpected_error",
                extra={"extra_fields": {"job_id": job_id, "client_id": client_id, "error": self.last_error}},
            )
            return result
        finally:
            await self.manager.close()

    @staticmethod
    def _categorize_waybill_error(error: WaybillError) -> str:
        text = str(error).lower()
        if "captcha" in text:
            return "captcha_failed"
        if "otp" in text or "پیامک" in text:
            return "otp_required"
        if "map" in text or "مبدا" in text or "مقصد" in text:
            return "form_fill_failed"
        if "access" in text or "دسترسی" in text or "مجوز" in text:
            return "validation_error"
        return "submission_failed"
