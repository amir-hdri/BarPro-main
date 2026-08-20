import asyncio
import json
import random
import time
from typing import Any

import httpx
from fastapi import HTTPException

from app.core.circuit_breaker import AsyncCircuitBreaker, CircuitOpenError
from app.core.config import utcms_config
from app.core.network import is_retryable_network_error
from app.monitoring.metrics import set_circuit_breaker_state
from app.schemas.itmb_ws import (
    WS01InsertBOLRequest,
    WS03StartBOLRequest,
    WS04EndBOLRequest,
    WS06InsertBOLTrackRequest,
)
from app.services.itmb_baseinfo_service import itmb_baseinfo_service
from app.services.itmb_common import build_hashed_value, resolve_itmb_auth


class ITMBWSService:
    def __init__(self) -> None:
        self._circuit_breaker = AsyncCircuitBreaker(
            enabled=utcms_config.CIRCUIT_BREAKER_ENABLED,
            failure_threshold=utcms_config.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_seconds=utcms_config.CIRCUIT_BREAKER_RECOVERY_SECONDS,
            half_open_max_calls=utcms_config.CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS,
        )

    @staticmethod
    def build_hashed_value(company_code: str, salt: int, service_password: str) -> str:
        return build_hashed_value(company_code=company_code, salt=salt, service_password=service_password)

    @staticmethod
    def _extract_result_text(response_text: str) -> str:
        text = response_text.strip()
        if not text:
            raise HTTPException(status_code=502, detail="پاسخ خالی از وب‌سرویس دریافت شد")

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return text

        if isinstance(parsed, dict) and "d" in parsed:
            return str(parsed["d"]).strip()
        if isinstance(parsed, str):
            return parsed.strip()

        return text

    @staticmethod
    def _parse_error(result_text: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(result_text)
        except json.JSONDecodeError:
            return None

        if isinstance(parsed, dict) and "ErrCode" in parsed:
            return parsed
        return None

    @staticmethod
    def _retry_delay_seconds(attempt_index: int) -> float:
        base = max(0.1, utcms_config.ITMBOL_RETRY_BASE_SECONDS)
        jitter = random.uniform(0, 0.4)
        return (base * (2 ** max(0, attempt_index - 1))) + jitter

    async def insert_bol(self, request: WS01InsertBOLRequest) -> dict[str, Any]:
        try:
            await self._circuit_breaker.allow_request()
        except CircuitOpenError as exc:
            await self._sync_circuit_metric()
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "ارتباط وب‌سرویس ITMB موقتاً قطع شده (Circuit Open)",
                    "retry_after_seconds": round(exc.retry_after_seconds, 2),
                },
            ) from exc

        company_code, salt, hashed_value = resolve_itmb_auth(
            company_code=request.CompanyCode,
            service_password=request.ServicePassword,
            salt=request.Salt,
            hashed_value=request.HashedValue,
        )
        insert_time = request.InsertTime if request.InsertTime is not None else int(time.time())
        validation_result = await itmb_baseinfo_service.validate_bol_references(
            bol=request.bol,
            company_code=company_code,
            service_password=request.ServicePassword,
        )
        payload = {
            "CompanyCode": company_code,
            "Salt": salt,
            "HashedValue": hashed_value,
            "bol": request.bol.model_dump(),
            "InsertTime": insert_time,
            "InsertPosition": request.InsertPosition.model_dump(),
        }

        endpoint = f"{utcms_config.ITMBOL_SERVICE_URL.rstrip('/')}/WS01_InsertBOL"
        response: httpx.Response | None = None

        # Mutating POST must be executed At-Most-Once (no automatic retries on timeout/5xx)
        try:
            async with httpx.AsyncClient(timeout=utcms_config.ITMBOL_TIMEOUT_SECONDS) as client:
                response = await client.post(endpoint, json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code >= 500:
                await self._mark_circuit_failure()
            detail = {
                "message": "وب‌سرویس ITMB پاسخ خطادار برگرداند",
                "upstream_status": status_code,
                "upstream_body": exc.response.text[:500],
            }
            raise HTTPException(status_code=502, detail=detail) from exc
        except httpx.RequestError as exc:
            await self._mark_circuit_failure()
            raise HTTPException(
                status_code=503,
                detail="ارتباط با وب‌سرویس ITMB برقرار نشد",
            ) from exc
        except Exception as exc:
            if is_retryable_network_error(exc):
                await self._mark_circuit_failure()
            raise HTTPException(
                status_code=500,
                detail=f"خطای داخلی در ارتباط با ITMB: {str(exc)}",
            ) from exc

        if response is None:
            await self._mark_circuit_failure()
            raise HTTPException(status_code=503, detail="ارسال درخواست به ITMB ناموفق بود")

        await self._circuit_breaker.record_success()
        await self._sync_circuit_metric()

        result_text = self._extract_result_text(response.text)
        error_payload = self._parse_error(result_text)
        if error_payload:
            raise HTTPException(
                status_code=400,
                detail={
                    "err_code": error_payload.get("ErrCode"),
                    "err_desc": error_payload.get("ErrDesc", "خطای نامشخص از سرویس UTCM"),
                },
            )

        return {
            "success": True,
            "bol_trace_code": result_text,
            "used_salt": salt,
            "baseinfo_validation": validation_result,
        }

    async def start_bol(self, request: WS03StartBOLRequest) -> dict[str, Any]:
        """WS03_StartBOL: آغاز سفر بارنامه در وب‌سرویس ITMB."""
        try:
            await self._circuit_breaker.allow_request()
        except CircuitOpenError as exc:
            await self._sync_circuit_metric()
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "ارتباط وب‌سرویس ITMB موقتاً قطع شده (Circuit Open)",
                    "retry_after_seconds": round(exc.retry_after_seconds, 2),
                },
            ) from exc

        company_code, salt, hashed_value = resolve_itmb_auth(
            company_code=request.CompanyCode,
            service_password=request.ServicePassword,
            salt=request.Salt,
            hashed_value=request.HashedValue,
        )
        start_time = request.StartTime if request.StartTime is not None else int(time.time())
        payload = {
            "CompanyCode": company_code,
            "Salt": salt,
            "HashedValue": hashed_value,
            "BOLTraceCode": request.BOLTraceCode,
            "StartTime": start_time,
            "StartPosition": request.StartPosition.model_dump(),
        }

        endpoint = f"{utcms_config.ITMBOL_SERVICE_URL.rstrip('/')}/WS03_StartBOL"
        try:
            async with httpx.AsyncClient(timeout=utcms_config.ITMBOL_TIMEOUT_SECONDS) as client:
                response = await client.post(endpoint, json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500:
                await self._mark_circuit_failure()
            raise HTTPException(
                status_code=502,
                detail={"message": "خطای وب‌سرویس ITMB در آغاز بارنامه", "upstream_body": exc.response.text[:500]},
            ) from exc
        except httpx.RequestError as exc:
            await self._mark_circuit_failure()
            raise HTTPException(status_code=503, detail="ارتباط با وب‌سرویس ITMB برقرار نشد") from exc

        await self._circuit_breaker.record_success()
        await self._sync_circuit_metric()
        result_text = self._extract_result_text(response.text)
        error_payload = self._parse_error(result_text)
        if error_payload:
            raise HTTPException(
                status_code=400,
                detail={
                    "err_code": error_payload.get("ErrCode"),
                    "err_desc": error_payload.get("ErrDesc", "خطا در آغاز بارنامه"),
                },
            )

        return {
            "success": True,
            "bol_trace_code": request.BOLTraceCode,
            "result_code": 200,
            "message": "سفر با موفقیت آغاز شد",
        }

    async def end_bol(self, request: WS04EndBOLRequest) -> dict[str, Any]:
        """WS04_EndBOL: پایان سفر بارنامه در وب‌سرویس ITMB."""
        try:
            await self._circuit_breaker.allow_request()
        except CircuitOpenError as exc:
            await self._sync_circuit_metric()
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "ارتباط وب‌سرویس ITMB موقتاً قطع شده (Circuit Open)",
                    "retry_after_seconds": round(exc.retry_after_seconds, 2),
                },
            ) from exc

        company_code, salt, hashed_value = resolve_itmb_auth(
            company_code=request.CompanyCode,
            service_password=request.ServicePassword,
            salt=request.Salt,
            hashed_value=request.HashedValue,
        )
        end_time = request.EndTime if request.EndTime is not None else int(time.time())
        payload = {
            "CompanyCode": company_code,
            "Salt": salt,
            "HashedValue": hashed_value,
            "BOLTraceCode": request.BOLTraceCode,
            "EndTime": end_time,
            "EndPosition": request.EndPosition.model_dump(),
        }

        endpoint = f"{utcms_config.ITMBOL_SERVICE_URL.rstrip('/')}/WS04_EndBOL"
        try:
            async with httpx.AsyncClient(timeout=utcms_config.ITMBOL_TIMEOUT_SECONDS) as client:
                response = await client.post(endpoint, json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500:
                await self._mark_circuit_failure()
            raise HTTPException(
                status_code=502,
                detail={"message": "خطای وب‌سرویس ITMB در پایان بارنامه", "upstream_body": exc.response.text[:500]},
            ) from exc
        except httpx.RequestError as exc:
            await self._mark_circuit_failure()
            raise HTTPException(status_code=503, detail="ارتباط با وب‌سرویس ITMB برقرار نشد") from exc

        await self._circuit_breaker.record_success()
        await self._sync_circuit_metric()
        result_text = self._extract_result_text(response.text)
        error_payload = self._parse_error(result_text)
        if error_payload:
            raise HTTPException(
                status_code=400,
                detail={
                    "err_code": error_payload.get("ErrCode"),
                    "err_desc": error_payload.get("ErrDesc", "خطا در پایان بارنامه"),
                },
            )

        return {
            "success": True,
            "bol_trace_code": request.BOLTraceCode,
            "result_code": 200,
            "message": "سفر با موفقیت پایان یافت",
        }

    async def insert_bol_track(self, request: WS06InsertBOLTrackRequest) -> dict[str, Any]:
        """WS06_InsertBOLTrack: ثبت نقاط پیمایش بارنامه در وب‌سرویس ITMB."""
        try:
            await self._circuit_breaker.allow_request()
        except CircuitOpenError as exc:
            await self._sync_circuit_metric()
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "ارتباط وب‌سرویس ITMB موقتاً قطع شده (Circuit Open)",
                    "retry_after_seconds": round(exc.retry_after_seconds, 2),
                },
            ) from exc

        company_code, salt, hashed_value = resolve_itmb_auth(
            company_code=request.CompanyCode,
            service_password=request.ServicePassword,
            salt=request.Salt,
            hashed_value=request.HashedValue,
        )
        track_time = request.TrackTime if request.TrackTime is not None else int(time.time())
        payload = {
            "CompanyCode": company_code,
            "Salt": salt,
            "HashedValue": hashed_value,
            "BOLTraceCode": request.BOLTraceCode,
            "TrackTime": track_time,
            "TrackPosition": request.TrackPosition.model_dump(),
        }

        endpoint = f"{utcms_config.ITMBOL_SERVICE_URL.rstrip('/')}/WS06_InsertBOLTrack"
        try:
            async with httpx.AsyncClient(timeout=utcms_config.ITMBOL_TIMEOUT_SECONDS) as client:
                response = await client.post(endpoint, json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500:
                await self._mark_circuit_failure()
            raise HTTPException(
                status_code=502,
                detail={"message": "خطای وب‌سرویس ITMB در ثبت موقعیت", "upstream_body": exc.response.text[:500]},
            ) from exc
        except httpx.RequestError as exc:
            await self._mark_circuit_failure()
            raise HTTPException(status_code=503, detail="ارتباط با وب‌سرویس ITMB برقرار نشد") from exc

        await self._circuit_breaker.record_success()
        await self._sync_circuit_metric()
        result_text = self._extract_result_text(response.text)
        error_payload = self._parse_error(result_text)
        if error_payload:
            raise HTTPException(
                status_code=400,
                detail={
                    "err_code": error_payload.get("ErrCode"),
                    "err_desc": error_payload.get("ErrDesc", "خطا در ثبت موقعیت بارنامه"),
                },
            )

        return {
            "success": True,
            "bol_trace_code": request.BOLTraceCode,
            "result_code": 200,
            "message": "موقعیت با موفقیت ثبت شد",
        }

    async def _sleep_before_retry(self, attempt: int) -> None:
        delay = self._retry_delay_seconds(attempt)
        await asyncio.sleep(delay)

    async def _mark_circuit_failure(self) -> None:
        await self._circuit_breaker.record_failure()
        await self._sync_circuit_metric()

    async def _sync_circuit_metric(self) -> None:
        snapshot = await self._circuit_breaker.snapshot()
        set_circuit_breaker_state(snapshot.state)

    async def circuit_status(self) -> dict[str, Any]:
        snapshot = await self._circuit_breaker.snapshot()
        return {
            "state": snapshot.state,
            "failure_count": snapshot.failure_count,
            "retry_after_seconds": round(snapshot.retry_after_seconds, 2),
            "enabled": self._circuit_breaker.enabled,
        }

    def toggle_circuit_breaker(self, enabled: bool) -> None:
        self._circuit_breaker.enabled = enabled


itmb_ws_service = ITMBWSService()
