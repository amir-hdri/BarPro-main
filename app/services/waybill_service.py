import asyncio
import logging
import random
import time
import uuid
from typing import Any

from fastapi import HTTPException

from app.automation.browser import browser_manager
from app.automation.proxy_rotator import get_proxy_rotator
from app.automation.reporting import report_service
from app.automation.traffic_control import waybill_traffic_controller
from app.core.artifacts import failure_artifact_service
from app.core.config import utcms_config
from app.core.error_taxonomy import classify_exception
from app.core.exceptions import WaybillError
from app.core.execution_context import bind_execution_context, generate_correlation_id, reset_execution_context
from app.core.network import is_retryable_network_error
from app.schemas.waybill import OperationMode, WaybillMapRequest
from app.services.session_vault import session_vault

logger = logging.getLogger(__name__)


def _retry_delay_seconds(attempt_number: int) -> float:
    base = max(0.1, utcms_config.WAYBILL_RETRY_BASE_SECONDS)
    jitter = random.uniform(0, max(0.0, utcms_config.WAYBILL_RETRY_JITTER_SECONDS))
    return (base * (2 ** max(0, attempt_number - 1))) + jitter


async def _goto_with_retry(page, url: str, wait_until: str = "domcontentloaded") -> None:
    attempts = max(1, utcms_config.PAGE_GOTO_MAX_RETRIES + 1)
    base_delay = max(0.1, utcms_config.PAGE_GOTO_RETRY_BASE_SECONDS)
    jitter = max(0.0, utcms_config.PAGE_GOTO_RETRY_JITTER_SECONDS)
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            await page.goto(url, wait_until=wait_until, timeout=utcms_config.PAGE_NAVIGATION_TIMEOUT)
            return
        except Exception as exc:
            last_error = exc
            if attempt >= attempts or not is_retryable_network_error(exc):
                raise
            delay = (base_delay * (2 ** (attempt - 1))) + random.uniform(0, jitter)
            await asyncio.sleep(delay)

    if last_error:
        raise last_error


def _is_retryable_exception(error: Exception) -> bool:
    if is_retryable_network_error(error):
        return True
    text = str(error).lower()
    transient_markers = (
        "waybill form",
        "فرم بارنامه پس از بازیابی",
        "صفحه بارنامه",
        "ثبت بارنامه تایید نشد",
    )
    return any(marker in text for marker in transient_markers)


class WaybillService:
    async def create_waybill_with_map(self, request: WaybillMapRequest) -> dict[str, Any]:
        request_id = str(uuid.uuid4())
        correlation_id = (request.correlation_id or generate_correlation_id()).strip()
        batch_id = (request.batch_id or request.session_id or correlation_id).strip()
        execution_tokens = bind_execution_context(
            correlation_id=correlation_id,
            task_id=request.session_id,
            batch_id=batch_id,
        )
        try:
            mode = self._resolve_operation_mode(request)
            dry_run = mode == OperationMode.SAFE.value
            preflight = self._build_preflight_summary(request)

            if mode == OperationMode.FULL.value and not utcms_config.ALLOW_LIVE_SUBMIT:
                raise HTTPException(
                    status_code=403,
                    detail="ارسال واقعی بارنامه غیرفعال است. برای حالت full مقدار ALLOW_LIVE_SUBMIT=true تنظیم شود",
                )

            if mode == OperationMode.FULL.value and not preflight["ready_for_live_submit"]:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "message": "درخواست برای حالت full آماده نیست",
                        "missing_requirements": preflight["missing_requirements"],
                    },
                )

            await report_service.record_request(mode=mode)

            max_attempts = max(1, utcms_config.WAYBILL_MAX_RETRIES + 1)

            for attempt in range(1, max_attempts + 1):
                internal_session_id: str | None = None
                page = None
                started_at = time.perf_counter()

                try:
                    async with waybill_traffic_controller.slot(mode=mode):
                        await browser_manager.initialize()
                        request_auth = request.utcms_auth
                        auth_state_key = session_vault.build_account_key(
                            username=request_auth.username if request_auth else None,
                            national_code=request.vehicle.driver_national_code,
                            fallback=getattr(request.vehicle, "plate", None),
                        )
                        auth_state_path = session_vault.auth_state_path_for_account(
                            username=request_auth.username if request_auth else None,
                            national_code=request.vehicle.driver_national_code,
                            fallback=getattr(request.vehicle, "plate", None),
                        )
                        proxy_info = await get_proxy_rotator().get_next()
                        proxy_dict = proxy_info.to_playwright_proxy() if proxy_info else None
                        internal_session_id, context = await browser_manager.create_context(
                            auth_state_path=auth_state_path, proxy_dict=proxy_dict
                        )
                        page = await browser_manager.new_page(context)

                        from app.automation.auth import UTCMSAuthenticator
                        from app.automation.waybill_enhanced import EnhancedWaybillManager

                        auth = UTCMSAuthenticator(page, context)
                        login_url = None
                        if request_auth and request_auth.login_url:
                            login_url = request_auth.login_url.strip() or None

                        is_logged_in = await auth._is_logged_in()

                        if not is_logged_in:
                            username = (request_auth.username if request_auth else "").strip()
                            password = (request_auth.password if request_auth else "").strip()

                            if not username or not password:
                                raise HTTPException(
                                    status_code=401,
                                    detail="اطلاعات ورود UTCMS باید به صورت صریح در درخواست ارسال شود",
                                )

                            login_success = await auth.login(
                                username,
                                password,
                                login_url=login_url,
                            )
                            if not login_success:
                                if auth.last_error and is_retryable_network_error(auth.last_error):
                                    raise HTTPException(
                                        status_code=503,
                                        detail=f"اتصال به سامانه بارنامه ناموفق بود: {auth.last_error}",
                                    )

                                detail = "خطا در ورود به سامانه بارنامه"
                                if auth.last_error:
                                    detail = f"{detail}: {auth.last_error}"
                                raise HTTPException(status_code=401, detail=detail)

                            await browser_manager.save_auth_state(context, auth_state_path=auth_state_path)
                        else:
                            await browser_manager.save_auth_state(context, auth_state_path=auth_state_path)

                        manager = EnhancedWaybillManager(page, context)
                        manager_result = await manager.create_waybill_with_map(
                            self._build_waybill_payload(request),
                            dry_run=dry_run,
                        )

                        latency_ms = (time.perf_counter() - started_at) * 1000
                        await report_service.record_success(mode=mode, latency_ms=latency_ms)
                        if proxy_info:
                            proxy_info.record_waybill_result(success=True, latency=latency_ms / 1000.0)

                        if manager_result.get("origin_method") == "map":
                            map_type = (
                                manager_result.get("origin_map_type")
                                or manager_result.get("destination_map_type")
                                or "unknown"
                            )
                            await report_service.record_map_usage(map_type)

                        return self._build_response(
                            request_id=request_id,
                            correlation_id=correlation_id,
                            mode=mode,
                            manager_result=manager_result,
                            auth_state_key=auth_state_key,
                            session_reused=is_logged_in,
                            preflight=preflight,
                        )

                except HTTPException as exc:
                    if proxy_info:
                        proxy_info.record_waybill_result(
                            success=False, latency=time.perf_counter() - started_at, error=str(exc)
                        )
                    is_temporary = exc.status_code in (429, 503)
                    if is_temporary and attempt < max_attempts:
                        await waybill_traffic_controller.mark_temporary_block(multiplier=2.0)
                        await asyncio.sleep(_retry_delay_seconds(attempt))
                        continue

                    await report_service.record_failure(
                        mode=mode,
                        category=self._categorize_http_exception(exc),
                    )
                    if page:
                        await failure_artifact_service.capture_failure_bundle(
                            page,
                            error=exc,
                            stage="waybill_http_exception",
                            metadata={"mode": mode, "attempt": attempt},
                        )
                    raise

                except WaybillError as exc:
                    if proxy_info:
                        proxy_info.record_waybill_result(
                            success=False, latency=time.perf_counter() - started_at, error=str(exc)
                        )
                    retryable = is_retryable_network_error(exc)
                    if retryable and attempt < max_attempts:
                        await waybill_traffic_controller.mark_temporary_block(multiplier=1.0)
                        await asyncio.sleep(_retry_delay_seconds(attempt))
                        continue

                    await report_service.record_failure(
                        mode=mode,
                        category="network" if retryable else "form",
                    )
                    if page:
                        await failure_artifact_service.capture_failure_bundle(
                            page,
                            error=exc,
                            stage="waybill_error",
                            metadata={"mode": mode, "attempt": attempt},
                        )
                    if retryable:
                        raise HTTPException(
                            status_code=503,
                            detail="اختلال موقت در ارتباط با سامانه بارنامه. لطفاً مجدداً تلاش کنید",
                        ) from exc
                    status_code = self._status_code_for_waybill_error(exc)
                    raise HTTPException(status_code=status_code, detail=str(exc)) from exc

                except Exception as exc:
                    if proxy_info:
                        proxy_info.record_waybill_result(
                            success=False, latency=time.perf_counter() - started_at, error=str(exc)
                        )
                    if _is_retryable_exception(exc) and attempt < max_attempts:
                        await waybill_traffic_controller.mark_temporary_block(multiplier=1.0)
                        await asyncio.sleep(_retry_delay_seconds(attempt))
                        continue

                    await report_service.record_failure(
                        mode=mode,
                        category=classify_exception(exc)[0].value,
                    )
                    logger.exception(
                        "create_waybill_with_map_failed",
                        extra={
                            "extra_fields": {
                                "request_id": request_id,
                                "mode": mode,
                                "attempt": attempt,
                                "error": str(exc),
                            }
                        },
                    )
                    if page:
                        category, retryable = classify_exception(exc)
                        await failure_artifact_service.capture_failure_bundle(
                            page,
                            error=exc,
                            stage="waybill_unhandled_exception",
                            metadata={
                                "mode": mode,
                                "attempt": attempt,
                                "category": category.value,
                                "retryable": retryable,
                            },
                        )
                    raise HTTPException(status_code=500, detail="خطای داخلی سرور در ثبت بارنامه") from exc

                finally:
                    if page:
                        try:
                            await page.close()
                        except Exception:
                            logger.warning(
                                "page_close_failed",
                                extra={"extra_fields": {"request_id": request_id}},
                            )

                    if internal_session_id:
                        try:
                            await browser_manager.close_context(internal_session_id)
                        except Exception:
                            logger.warning(
                                "context_close_failed",
                                extra={
                                    "extra_fields": {
                                        "request_id": request_id,
                                        "session_id": internal_session_id,
                                    }
                                },
                            )

            raise HTTPException(status_code=500, detail="خطای داخلی سرور در ثبت بارنامه")
        finally:
            reset_execution_context(execution_tokens)

    @staticmethod
    def _resolve_operation_mode(request: WaybillMapRequest) -> str:
        operation_mode = request.operation_mode
        if isinstance(operation_mode, OperationMode):
            return operation_mode.value
        return str(operation_mode)

    @staticmethod
    def _build_preflight_summary(request: WaybillMapRequest) -> dict[str, Any]:
        shipping_options = request.shipping_options
        request_auth = request.utcms_auth

        has_request_auth = bool(
            request_auth and (request_auth.username or "").strip() and (request_auth.password or "").strip()
        )
        checks = {
            "has_driver_data": bool((request.vehicle.driver_national_code or "").strip()),
            "has_vehicle_plate": bool((request.vehicle.plate or "").strip()),
            "has_origin_coordinates": request.origin.coordinates is not None,
            "has_destination_coordinates": request.destination.coordinates is not None,
            "has_auth_credentials": has_request_auth,
            "two_way": bool(shipping_options and shipping_options.two_way),
            "otp_provided": bool((shipping_options.otp or "").strip()) if shipping_options else False,
        }

        required_for_live = (
            "has_driver_data",
            "has_vehicle_plate",
            "has_origin_coordinates",
            "has_destination_coordinates",
            "has_auth_credentials",
        )
        missing_requirements = [key for key in required_for_live if not checks[key]]

        return {
            **checks,
            "required_for_live": list(required_for_live),
            "missing_requirements": missing_requirements,
            "ready_for_live_submit": len(missing_requirements) == 0,
        }

    async def detect_map(self, session_id: str | None = None) -> dict[str, Any]:
        request_id = str(uuid.uuid4())

        from app.automation.auth import UTCMSAuthenticator
        from app.automation.map_controller import MapController
        from app.automation.waybill_enhanced import EnhancedWaybillManager
        from app.core.exceptions import WaybillError

        await browser_manager.initialize()

        internal_session_id: str | None = None
        page = None
        try:
            proxy_info = await get_proxy_rotator().get_next()
            proxy_dict = proxy_info.to_playwright_proxy() if proxy_info else None
            internal_session_id, context = await browser_manager.create_context(proxy_dict=proxy_dict)
            page = await browser_manager.new_page(context)
            auth = UTCMSAuthenticator(page, context)

            is_logged_in = await auth._is_logged_in()
            current_url = getattr(page, "url", "")

            if not is_logged_in:
                await report_service.record_map_usage("none")
                return {
                    "request_id": request_id,
                    "has_map": False,
                    "map_type": None,
                    "session_id": session_id,
                    "authenticated": False,
                    "current_url": current_url,
                    "reason": auth.last_error or "login_required_or_session_invalid",
                }

            manager = EnhancedWaybillManager(page, context)
            try:
                await manager._ensure_waybill_form_page()
            except WaybillError as exc:
                await report_service.record_map_usage("none")
                return {
                    "request_id": request_id,
                    "has_map": False,
                    "map_type": None,
                    "session_id": session_id,
                    "authenticated": True,
                    "current_url": getattr(page, "url", current_url),
                    "reason": str(exc),
                }

            map_controller = MapController(page)
            map_type = await map_controller.detect_map_type()

            if map_type:
                await report_service.record_map_usage(map_type)
            else:
                await report_service.record_map_usage("none")

            return {
                "request_id": request_id,
                "has_map": map_type is not None,
                "map_type": map_type,
                "session_id": session_id,
                "authenticated": True,
                "current_url": getattr(page, "url", current_url),
                "reason": None,
            }
        except Exception as exc:
            logger.exception(
                "detect_map_failed",
                extra={"extra_fields": {"request_id": request_id, "error": str(exc)}},
            )
            raise HTTPException(status_code=500, detail="خطای داخلی سرور در تشخیص نقشه") from exc
        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    logger.warning(
                        "page_close_failed",
                        extra={"extra_fields": {"request_id": request_id}},
                    )
            if internal_session_id:
                try:
                    await browser_manager.close_context(internal_session_id)
                except Exception:
                    logger.warning(
                        "context_close_failed",
                        extra={"extra_fields": {"request_id": request_id}},
                    )

    @staticmethod
    def _build_waybill_payload(request: WaybillMapRequest) -> dict[str, Any]:
        payload = {
            "sender": request.sender.model_dump(),
            "receiver": request.receiver.model_dump(),
            "origin": request.origin.model_dump(),
            "destination": request.destination.model_dump(),
            "cargo": request.cargo.model_dump(),
            "vehicle": request.vehicle.model_dump(),
            "financial": request.financial.model_dump(),
        }
        if request.shipping_options:
            payload["shipping_options"] = request.shipping_options.model_dump(exclude_none=True)
        return payload

    @staticmethod
    def _build_response(
        request_id: str,
        correlation_id: str,
        mode: str,
        manager_result: dict[str, Any],
        auth_state_key: str | None = None,
        session_reused: bool = False,
        preflight: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response: dict[str, Any] = {
            "success": bool(manager_result.get("success", True)),
            "request_id": request_id,
            "correlation_id": correlation_id,
            "mode": mode,
            "status": manager_result.get("status", "validated" if mode == "safe" else "submitted"),
            "auth_strategy": "session-first",
            "session_reused": session_reused,
        }
        if auth_state_key:
            response["auth_state_key"] = auth_state_key

        if mode == OperationMode.SAFE.value:
            validation_summary = dict(preflight or {})
            validation_summary.update(manager_result.get("validation_summary", {}))
            response["validation_summary"] = validation_summary
        else:
            response["tracking_code"] = manager_result.get("tracking_code")
            if preflight:
                response["preflight"] = preflight

        passthrough_keys = (
            "origin_method",
            "destination_method",
            "origin_map_type",
            "destination_map_type",
            "route",
            "url",
        )
        for key in passthrough_keys:
            if key in manager_result:
                response[key] = manager_result[key]

        return response

    @staticmethod
    def _categorize_http_exception(error: HTTPException) -> str:
        if error.status_code in (401, 403):
            return "auth"
        if error.status_code == 429:
            return "network"
        if error.status_code >= 500:
            return "network"
        return "form"

    @staticmethod
    def _categorize_exception(error: Exception) -> str:
        text = str(error).lower()

        if "captcha" in text:
            return "captcha"
        if "login" in text or "credential" in text or "auth" in text:
            return "auth"
        if "map" in text or "location" in text:
            return "map"
        if is_retryable_network_error(error):
            return "network"
        if "field" in text or "validation" in text or "form" in text:
            return "form"

        return "unknown"

    @staticmethod
    def _status_code_for_waybill_error(error: WaybillError) -> int:
        text = str(error).lower()
        permission_markers = (
            "دسترسی",
            "access",
            "forbidden",
            "permission",
            "مجوز",
            "unauthorized",
        )
        if any(marker in text for marker in permission_markers):
            return 403
        return 400


waybill_service = WaybillService()
