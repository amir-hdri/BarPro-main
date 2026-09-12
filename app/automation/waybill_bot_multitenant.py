"""Multi-tenant waybill bot powered by the project's self-healing automation stack."""

from __future__ import annotations

import logging
from typing import Any

from playwright.async_api import BrowserContext, Page

from app.automation.auth import UTCMSAuthenticator
from app.automation.mobile_payload_adapter import build_mobile_document_payload, validate_mobile_source_payload
from app.automation.multitenant_payload_adapter import (
    build_enhanced_waybill_payload,
    validate_live_waybill_payload,
)
from app.automation.waybill_enhanced import EnhancedWaybillManager
from app.core.config import utcms_config
from app.core.exceptions import WaybillError
from app.models_multitenant import TaskStatus
from app.schemas.task import build_missing_tracking_result, build_tracking_received_result

logger = logging.getLogger(__name__)


class WaybillAutomationBot:
    """Adapter that integrates the multi-tenant worker with the self-healing manager.

    Instead of maintaining a second, weaker automation flow, this class reuses the
    production-grade login/captcha/navigation/map fallback logic from
    `UTCMSAuthenticator` and `EnhancedWaybillManager`.
    """

    def __init__(
        self,
        page: Page | None = None,
        context: BrowserContext | None = None,
        proxy_url: str | None = None,
    ):
        self.page = page
        self.context = context
        self.proxy_url = proxy_url
        self.last_error: str | None = None
        self.last_state: str | None = None
        self.authenticator = UTCMSAuthenticator(page, context) if page is not None and context is not None else None
        self.manager = EnhancedWaybillManager(page, context) if page is not None and context is not None else None

    @staticmethod
    def _compact_plate(value: Any) -> str:
        if not value:
            return ""
        s = str(value).strip().replace(" ", "").replace("-", "").replace("‌", "").replace("ایران", "")
        for idx, digit in enumerate("۰۱۲۳۴۵۶۷۸۹"):
            s = s.replace(digit, str(idx))
        for idx, digit in enumerate("٠١٢٣٤٥٦٧٨٩"):
            s = s.replace(digit, str(idx))
        return s.lower()

    @staticmethod
    def _find_matching_fleet_truck(
        fleet_response: Any,
        vehicle: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Find matching truck object from /Truck/GetUserFleetList response."""
        fleet_items: list[dict[str, Any]] = []
        if isinstance(fleet_response, list):
            fleet_items = [x for x in fleet_response if isinstance(x, dict)]
        elif isinstance(fleet_response, dict):
            for k in ("obj", "data", "result", "fleetList", "trucks", "items", "fleet"):
                val = fleet_response.get(k)
                if isinstance(val, list):
                    fleet_items = [x for x in val if isinstance(x, dict)]
                    break
                elif isinstance(val, dict):
                    nested = val.get("items") or val.get("list") or val.get("obj")
                    if isinstance(nested, list):
                        fleet_items = [x for x in nested if isinstance(x, dict)]
                        break

        if not fleet_items:
            return None

        raw_plate = (
            vehicle.get("plate")
            or vehicle.get("plate_number")
            or payload.get("plate_number")
            or payload.get("plate")
        )
        req_t1 = str(vehicle.get("t1") or "").strip()
        req_t2 = str(vehicle.get("t2") or "").strip()
        req_t3 = str(vehicle.get("t3") or "").strip()
        req_t4 = str(vehicle.get("t4") or "").strip()

        plate_str = str(raw_plate).strip() if raw_plate else ""
        if not plate_str and req_t1 and req_t4:
            plate_str = f"{req_t1}{req_t2}{req_t3}{req_t4}"
        req_compact = WaybillAutomationBot._compact_plate(plate_str)

        for truck in fleet_items:
            candidates: list[str] = []
            for field_name in ("carTag", "plate", "nCarTag", "tag", "carPlate", "tagNumber"):
                val = truck.get(field_name)
                if val and isinstance(val, str):
                    candidates.append(val)

            t1 = str(truck.get("t1") or truck.get("tagPart1") or truck.get("irTagPart1") or "").strip()
            t2 = str(truck.get("t2") or truck.get("tagPart2") or truck.get("irTagPart2") or "").strip()
            t3 = str(truck.get("t3") or truck.get("tagPart3") or truck.get("irTagPart3") or "").strip()
            t4 = str(truck.get("t4") or truck.get("tagPart4") or truck.get("irTagPart4") or "").strip()

            if t1 and t4:
                candidates.append(f"{t1}{t2}{t3}{t4}")
                candidates.append(f"{t1}{t3}{t2}{t4}")

            for cand in candidates:
                cand_compact = WaybillAutomationBot._compact_plate(cand)
                if req_compact and cand_compact:
                    if cand_compact == req_compact:
                        return truck
                    cand_digits = "".join(ch for ch in cand_compact if ch.isdigit())
                    req_digits = "".join(ch for ch in req_compact if ch.isdigit())
                    if len(req_digits) >= 7 and req_digits == cand_digits:
                        return truck

            if req_t1 and req_t4 and t1 and t4:
                if req_t1 == t1 and req_t4 == t4:
                    if (req_t2 and (req_t2 == t2 or req_t2 == t3)) or (req_t3 and (req_t3 == t3 or req_t3 == t2)):
                        return truck

        if len(fleet_items) == 1 and not req_compact:
            return fleet_items[0]

        return None

    @staticmethod
    def _apply_fleet_truck_to_vehicle(vehicle: dict[str, Any], truck: dict[str, Any]) -> None:
        """Enrich vehicle dict with properties from the matched server fleet truck."""
        t1 = truck.get("t1") or truck.get("tagPart1") or truck.get("irTagPart1")
        t2 = truck.get("t2") or truck.get("tagPart2") or truck.get("irTagPart2")
        t3 = truck.get("t3") or truck.get("tagPart3") or truck.get("irTagPart3")
        t4 = truck.get("t4") or truck.get("tagPart4") or truck.get("irTagPart4")

        if t1 is not None and not vehicle.get("t1"):
            vehicle["t1"] = str(t1).strip()
        if t2 is not None and not vehicle.get("t2"):
            vehicle["t2"] = str(t2).strip()
        if t3 is not None and not vehicle.get("t3"):
            vehicle["t3"] = str(t3).strip()
        if t4 is not None and not vehicle.get("t4"):
            vehicle["t4"] = str(t4).strip()

        tag_type = truck.get("tagType") or truck.get("tag_type") or truck.get("carTagType")
        if tag_type is not None and vehicle.get("tag_type") is None and vehicle.get("tagType") is None:
            vehicle["tag_type"] = tag_type

        capacity = truck.get("capacity") or truck.get("tonnage") or truck.get("carCapacity")
        if capacity is not None and vehicle.get("capacity") is None:
            vehicle["capacity"] = capacity

        vtype = truck.get("type") or truck.get("vehicle_type") or truck.get("carType") or truck.get("vehicleType")
        if vtype is not None and vehicle.get("type") is None and vehicle.get("vehicle_type") is None:
            vehicle["type"] = vtype

        if truck.get("haveCertificate") is not None and "have_certificate" not in vehicle and "haveCertificate" not in vehicle:
            vehicle["have_certificate"] = truck["haveCertificate"]
        if truck.get("have3rdInsurance") is not None and "have_3rd_insurance" not in vehicle and "have3rdInsurance" not in vehicle:
            vehicle["have_3rd_insurance"] = truck["have3rdInsurance"]

        freighter_id = truck.get("freighterId") or truck.get("freighter_id")
        if freighter_id is not None and "freighter_id" not in vehicle:
            vehicle["freighter_id"] = freighter_id

        truck_id = truck.get("id") or truck.get("truckId")
        if truck_id is not None and "server_truck_id" not in vehicle:
            vehicle["server_truck_id"] = truck_id

    async def _execute_mobile_waybill_job(
        self,
        *,
        username: str,
        password: str,
        payload: dict[str, Any],
        job_id: str,
        client_id: int,
        allow_live_submit: bool = False,
        proxy_url: str | None = None,
    ) -> dict[str, Any]:
        """Run the APK-derived API contract without opening a UTCMS web page."""
        from app.automation.utcms_mobile_client import UtcmsMobileApiError, UtcmsMobileClient

        result: dict[str, Any] = {
            "job_id": job_id,
            "client_id": client_id,
            "transport": utcms_config.UTCMS_TRANSPORT,
            "status": TaskStatus.PENDING.value,
            "result": None,
            "error": None,
            "error_category": None,
            "steps": [],
        }
        try:
            source_errors = validate_mobile_source_payload(payload)
            if source_errors:
                result.update(
                    status=TaskStatus.NEEDS_REVIEW.value,
                    error="اطلاعات صریح transport موبایل ناقص است: "
                    + "، ".join(source_errors),
                    error_category="mobile_payload_validation_failed",
                )
                return result
            normalized_payload = build_enhanced_waybill_payload(payload)
            # The web normalizer intentionally clears coordinates for user_text
            # browser flows. The mobile DTO needs the map values captured by the
            # app, so restore only coordinates explicitly supplied by the caller.
            for location_key in ("origin", "destination"):
                raw_location = payload.get(location_key)
                normalized_location = normalized_payload.get(location_key)
                if isinstance(raw_location, dict) and isinstance(normalized_location, dict):
                    for source_key in (
                        "postal_code",
                        "postalCode",
                        "lat",
                        "latitude",
                        "lon",
                        "lng",
                        "longitude",
                        "coordinates",
                    ):
                        if raw_location.get(source_key) is not None:
                            normalized_location[source_key] = raw_location[source_key]
            # Preserve mobile-only fields that the web normalizer does not own.
            for mobile_field in (
                "insurance",
                "is_draft",
                "doc_id",
                "self_declared_time_of_start_shipment",
                "fuel_type",
                "send_sms",
            ):
                if payload.get(mobile_field) is not None:
                    normalized_payload[mobile_field] = payload[mobile_field]

            # The shared live validator models the single-cargo web form. For a
            # mobile multi-load payload, validate its first item there while the
            # mobile adapter validates every item and its server IDs.
            validation_payload = dict(normalized_payload)
            normalized_cargo = normalized_payload.get("cargo")
            if isinstance(normalized_cargo, dict) and isinstance(normalized_cargo.get("items"), list):
                items = normalized_cargo.get("items")
                first_item = items[0] if items and isinstance(items[0], dict) else {}
                validation_payload["cargo"] = {**normalized_cargo, **first_item}
            vehicle = (
                normalized_payload.get("vehicle")
                if isinstance(normalized_payload.get("vehicle"), dict)
                else {}
            )
            validation_errors = validate_live_waybill_payload(
                validation_payload,
                expected_driver_mobile=vehicle.get("driver_phone"),
            )
            if isinstance(normalized_cargo, dict) and isinstance(normalized_cargo.get("items"), list):
                validation_errors = [
                    error for error in validation_errors if error not in {"نوع کالا", "نوع بسته‌بندی"}
                ]
            if validation_errors:
                result.update(
                    status=TaskStatus.NEEDS_REVIEW.value,
                    error="اطلاعات اجباری UTCMS ناقص است: " + "، ".join(validation_errors),
                    error_category="payload_validation_failed",
                )
                return result

            client = UtcmsMobileClient(proxy_url=proxy_url or self.proxy_url)
            cap_token = str(
                payload.get("mobile_cap_token")
                or payload.get("cap_token")
                or utcms_config.UTCMS_CAPTCHA_VALUE
                or ""
            ).strip()
            if not cap_token and hasattr(client, "auto_solve_captcha"):
                try:
                    logger.info("cap_token missing for mobile login; attempting auto_solve_captcha")
                    solved = await client.auto_solve_captcha(form_id="login")
                    if isinstance(solved, (tuple, list)):
                        cap_token = str((solved[1] if len(solved) > 1 else solved[0]) or "").strip()
                    else:
                        cap_token = str(solved or "").strip()
                    if cap_token:
                        logger.info("Mobile login CAPTCHA auto-solved successfully")
                except Exception as exc:
                    logger.warning("Mobile auto_solve_captcha failed: %s", exc)

            if not cap_token:
                captcha = await client.get_captcha(form_id="login")
                captcha_obj = captcha.get("obj") if isinstance(captcha.get("obj"), dict) else {}
                result.update(
                    status=TaskStatus.NEEDS_REVIEW.value,
                    error="برای ورود به API موبایل، capToken نیازمند حل CAPTCHA است",
                    error_category="mobile_captcha_required",
                    result={
                        "transport": "mobile",
                        "captcha_received": True,
                        "captcha_type": client.extract_captcha_type(captcha),
                        "captcha_has_image": bool(
                            captcha_obj.get("image")
                            or captcha_obj.get("captcha")
                            or captcha_obj.get("base64")
                        ),
                    },
                )
                return result

            auth = await client.login(username, password, cap_token)
            result["steps"].append({"step": "mobile_login", "status": "success"})

            # Match driver fleet: call get_user_fleet_list to find matching truck/fleet object
            if hasattr(client, "get_user_fleet_list"):
                try:
                    fleet_response = await client.get_user_fleet_list()
                    matched_truck = self._find_matching_fleet_truck(
                        fleet_response=fleet_response,
                        vehicle=normalized_payload.get("vehicle") or {},
                        payload=payload,
                    )
                    if matched_truck:
                        if isinstance(normalized_payload.get("vehicle"), dict):
                            self._apply_fleet_truck_to_vehicle(
                                normalized_payload["vehicle"], matched_truck
                            )
                        result["steps"].append({"step": "mobile_fleet_match", "status": "success"})
                        logger.info(
                            "mobile_fleet_matched",
                            extra={
                                "extra_fields": {
                                    "job_id": job_id,
                                    "truck": matched_truck.get("carTag") or matched_truck.get("id"),
                                }
                            },
                        )
                except Exception as exc:
                    logger.warning("Mobile fleet query/matching failed: %s", exc)

            issue_cap_token = str(
                payload.get("mobile_issue_cap_token") or payload.get("issue_cap_token") or ""
            ).strip()
            # Build the exact APK DTO even for shadow/dry-run. This validates
            # every server ID and required field without dispatching a mutation.
            mobile_body = build_mobile_document_payload(
                normalized_payload,
                token=auth.token,
                cap_token=issue_cap_token or None,
            )
            if utcms_config.UTCMS_TRANSPORT == "shadow":
                query = await client.get_issued_documents(
                    page_number=1,
                    page_size=1,
                    driver_national_code=vehicle.get("driver_national_code"),
                )
                result.update(
                    status="validated",
                    result={
                        "transport": "mobile",
                        "mode": "shadow",
                        "read_only_query_ok": isinstance(query, dict),
                        "token_expiry_present": bool(auth.expires_at),
                        "load_count": len(mobile_body.get("load", [])),
                    },
                )
                result["steps"].append({"step": "mobile_shadow_query", "status": "success"})
                return result

            effective_live_submit = bool(
                allow_live_submit
                or payload.get("allow_live_submit")
                or payload.get("live_submit")
                or utcms_config.ALLOW_LIVE_SUBMIT
            )

            if not effective_live_submit:
                if not bool(normalized_payload.get("is_draft", False)) and not str(
                    payload.get("mobile_issue_cap_token") or payload.get("issue_cap_token") or ""
                ).strip():
                    result.update(
                        status=TaskStatus.NEEDS_REVIEW.value,
                        error="برای CAPTCHA مرحله صدور موبایل، mobile_issue_cap_token لازم است",
                        error_category="mobile_issue_captcha_required",
                        result={"transport": "mobile", "mutation_endpoint_called": False},
                    )
                    result["steps"].append({"step": "mobile_issue_captcha", "status": "required"})
                    return result
                result.update(
                    status="validated",
                    result={
                        "transport": "mobile",
                        "mode": "dry_run",
                        "mutation_endpoint_called": False,
                        "mobile_payload_keys": sorted(
                            {
                                "token",
                                "load",
                                "source",
                                "destination",
                                "sender",
                                "receiver",
                                "driverNationalCode",
                                "truck",
                                "insurance",
                                "value",
                                "bearingCost",
                                "rent",
                                "preRent",
                                "postRent",
                                "fuelType",
                                "sendSMS",
                                "docID",
                                "isDraft",
                                "selfDeclaredTimeOfStartShipment",
                            }
                        ),
                    },
                )
                result["steps"].append({"step": "mobile_dry_run", "status": "success"})
                return result

            response = await client.insert_document(
                normalized_payload,
                allow_live_submit=True,
                cap_token=issue_cap_token or None,
            )
            document_id = client.extract_document_id(response)
            tracking_code = client.extract_tracking_code(response)
            otp_required = client.extract_otp_required(response)

            if document_id:
                result["document_id"] = document_id
            if tracking_code:
                result["tracking_code"] = tracking_code

            if otp_required is True:
                result.update(
                    status=TaskStatus.UNKNOWN.value,
                    error="UTCMS برای صدور نهایی OTP خواسته است؛ ورود اپراتوری لازم است",
                    error_category="otp_required",
                    mutation_status="dispatched" if document_id else "ambiguous",
                    needs_reconciliation=True,
                    requires_operator_otp=True,
                    result={
                        "transport": "mobile",
                        "document_id": document_id,
                        "otp_required": True,
                        "tracking_code": tracking_code,
                    },
                )
                if document_id:
                    result["document_id"] = document_id
                result["steps"].append({"step": "mobile_otp_required", "status": "operator_action"})
                return result
            if tracking_code:
                result["status"] = TaskStatus.SUCCESS.value
                result["mutation_status"] = "dispatched"
                result["result"] = build_tracking_received_result(
                    tracking_code,
                    document_id=document_id,
                    transport="mobile",
                )
                result["steps"].append({"step": "mobile_insert", "status": "success"})
                return result

            result.update(
                status=TaskStatus.UNKNOWN.value,
                error=(
                    "API موبایل سند را پذیرفت اما کد رهگیری بازنگرداند؛ "
                    "تطبیق خواندنی لازم است"
                ),
                error_category="submission_unconfirmed",
                mutation_status="dispatched" if document_id else "ambiguous",
                needs_reconciliation=True,
                result=build_missing_tracking_result(document_id=document_id),
            )
            if document_id:
                result["document_id"] = document_id
            result["steps"].append({"step": "mobile_insert", "status": "unknown"})
            return result
        except UtcmsMobileApiError as exc:
            result.update(
                status=TaskStatus.FAILED.value,
                error=str(exc),
                error_category="mobile_api_error",
            )
            result["steps"].append({"step": "mobile_api", "status": "failed"})
            return result
        except (PermissionError, ValueError) as exc:
            result.update(
                status=TaskStatus.NEEDS_REVIEW.value,
                error=str(exc),
                error_category="mobile_payload_validation_failed",
            )
            return result

    async def execute_waybill_job(
        self,
        username: str,
        password: str,
        payload: dict[str, Any],
        job_id: str,
        client_id: int,
        auth_state_path: str | None = None,
        allow_live_submit: bool = False,
        proxy_url: str | None = None,
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
                "auth_stack": "UTCMSAuthenticator" if self.authenticator else "HeadlessMobile",
                "form_stack": "EnhancedWaybillManager" if self.manager else "HeadlessMobile",
                "payload_adapter": "multitenant_payload_adapter",
            },
        }

        from app.automation.browser import browser_manager
        from app.services.session_vault import session_vault

        if utcms_config.UTCMS_TRANSPORT in {"mobile", "shadow"}:
            try:
                return await self._execute_mobile_waybill_job(
                    username=username,
                    password=password,
                    payload=payload,
                    job_id=job_id,
                    client_id=client_id,
                    allow_live_submit=allow_live_submit,
                    proxy_url=proxy_url or self.proxy_url,
                )
            finally:
                if self.manager is not None:
                    await self.manager.close()

        if self.page is None or self.context is None or self.authenticator is None or self.manager is None:
            raise ValueError("Web transport requires an active Playwright page and context")

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
            vehicle = normalized_payload.get("vehicle") if isinstance(normalized_payload.get("vehicle"), dict) else {}
            validation_errors = validate_live_waybill_payload(
                normalized_payload,
                expected_driver_mobile=vehicle.get("driver_phone"),
            )
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
            manager_result = None
            manager_exc = None
            try:
                manager_result = await self.manager.create_waybill_with_map(
                    normalized_payload, dry_run=dry_run, job_id=job_id
                )
            except WaybillError as exc:
                manager_exc = exc
                manager_result = {"success": False, "error": str(exc), "status": "failed"}

            # Self-healing: if session was reused but creation failed/errored, check if we got redirected to login page
            mutation_may_have_been_dispatched = bool(
                manager_result.get("mutation_dispatched")
                or manager_result.get("mutation_status") == "ambiguous"
                or manager_result.get("needs_reconciliation")
                or str(manager_result.get("status", "")).lower() in {"unknown", "reconciling"}
            )
            if (
                is_logged_in
                and not manager_result.get("success", False)
                and not mutation_may_have_been_dispatched
                and not str(manager_result.get("tracking_code") or "").strip()
            ):
                # ``Page.url`` is a property (str), not a coroutine — awaiting a
                # call on it raises TypeError and would be swallowed by the
                # broad handler below, masking the real submission error.
                # Path-based login detection (bug-class fix): raw substring
                # matching flagged URLs like "/Catalog?ref=LoginBanner" as a
                # login bounce, triggering a needless fresh login AND a second
                # create_waybill run — a duplicate-submission hazard.
                from app.automation.auth_utils import is_login_url

                current_url = self.page.url or ""
                err_text = str(manager_exc or manager_result.get("error") or "")
                session_expired = (
                    is_login_url(current_url)
                    or "فرم بارنامه پس از بازیابی در دسترس نیست" in err_text
                    or "دسترسی" in err_text
                    or "نشست" in err_text
                )
                if session_expired:
                    logger.warning(
                        "Reused session expired/navigation failed. Invalidating cache and retrying with fresh login...",
                        extra={"extra_fields": {"url": current_url, "error": err_text[:160]}},
                    )
                    if auth_state_path:
                        try:
                            from app.services.session_vault import session_vault
                            await session_vault.async_delete_auth_state(auth_state_path)
                        except Exception:
                            pass
                    # Try a fresh login
                    login_success = await self.authenticator.login(username, password)
                    if login_success:
                        await browser_manager.save_auth_state(self.context, auth_state_path=auth_state_path)
                        manager_exc = None
                        try:
                            # Try creation again
                            manager_result = await self.manager.create_waybill_with_map(
                                normalized_payload, dry_run=dry_run, job_id=job_id
                            )
                        except WaybillError as retry_exc:
                            manager_exc = retry_exc
                            manager_result = {"success": False, "error": str(retry_exc), "status": "failed"}

            if manager_exc is not None:
                raise manager_exc

            # A tracking code from any manager outcome (success or a
            # post-boundary failure) is an acknowledged mutation: never
            # re-run create_waybill, never treat it as ambiguous.
            manager_tracking_code = str(manager_result.get("tracking_code") or "").strip()

            # A fresh-login retry produces a new result; recompute the mutation
            # boundary before deciding whether any further submit is safe. A
            # success-shaped result that already carries a tracking code has an
            # unambiguous mutation outcome — it is an acknowledgement, not an
            # ambiguity, and must never enter the retry/boundary path below.
            mutation_may_have_been_dispatched = bool(
                not manager_tracking_code
                and (
                    manager_result.get("mutation_dispatched")
                    or manager_result.get("mutation_status") == "ambiguous"
                    or manager_result.get("needs_reconciliation")
                    or str(manager_result.get("status", "")).lower()
                    in {"unknown", "reconciling", "submitted"}
                    or str(manager_result.get("confirmation_status", "")).lower()
                    == "pending_history_reconciliation"
                )
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
                # Truly ambiguous mutation (no code, boundary possibly crossed):
                # read-only History reconciliation is the only allowed next step.
                if manager_result.get("document_id"):
                    result["document_id"] = manager_result["document_id"]
                result["status"] = TaskStatus.UNKNOWN.value
                result["error"] = manager_result.get("message") or manager_result.get("error")
                result["error_category"] = "submission_unconfirmed"
                result["mutation_status"] = "ambiguous"
                result["needs_reconciliation"] = True
                result["result"] = build_missing_tracking_result(
                    document_id=str(manager_result["document_id"]) if manager_result.get("document_id") else None
                )
                return result

            tracking_code = str(manager_result.get("tracking_code") or "").strip()
            if tracking_code:
                # Tracking-first acknowledgement: the code is shown to the
                # operator immediately. It is NOT final success (the
                # three-witness rule still gates status=success) and never a
                # reason to dispatch reconciliation or resubmit.
                result["status"] = TaskStatus.SUCCESS.value
                result["result"] = build_tracking_received_result(
                    tracking_code,
                    url=manager_result.get("url"),
                    origin_method=manager_result.get("origin_method"),
                    destination_method=manager_result.get("destination_method"),
                    origin_map_type=manager_result.get("origin_map_type"),
                    destination_map_type=manager_result.get("destination_map_type"),
                    route=manager_result.get("route"),
                    waybill_screenshot=manager_result.get("waybill_screenshot"),
                    document_id=(
                        str(manager_result["document_id"]) if manager_result.get("document_id") else None
                    ),
                )
                result["mutation_status"] = "dispatched"
                result["steps"].append(
                    {
                        "step": "submit",
                        "status": "success",
                        "message": tracking_code or "Waybill registered successfully",
                    }
                )
                return result

            if not manager_result.get("success", False):
                result["status"] = TaskStatus.FAILED.value
                result["error"] = (
                    manager_result.get("message") or manager_result.get("error") or "waybill_submission_failed"
                )
                result["error_category"] = "submission_failed"
                return result

            # Success-shaped response without a tracking code: the mutation
            # boundary was crossed, so only read-only UTCMS History
            # reconciliation may confirm it — never a resubmission.
            doc_id = str(manager_result.get("document_id") or "").strip() or None
            result["status"] = TaskStatus.UNKNOWN.value
            result["error"] = "Portal success response did not include a tracking code; reconciliation required"
            result["error_category"] = "submission_unconfirmed"
            result["mutation_status"] = "dispatched" if doc_id else "ambiguous"
            result["needs_reconciliation"] = True
            if doc_id:
                result["document_id"] = doc_id
            result["result"] = build_missing_tracking_result(document_id=doc_id)
            result["steps"].append(
                {
                    "step": "submit",
                    "status": "unknown",
                    "message": result["error"],
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
