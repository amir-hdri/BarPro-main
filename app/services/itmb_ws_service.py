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
from app.schemas.itmb_ws import WS01InsertBOLRequest
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
            )

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
        max_attempts = max(1, utcms_config.ITMBOL_MAX_RETRIES + 1)
        response: httpx.Response | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=utcms_config.ITMBOL_TIMEOUT_SECONDS) as client:
                    response = await client.post(endpoint, json=payload)
                    response.raise_for_status()
                break
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                if status_code >= 500 and attempt < max_attempts:
                    await self._sleep_before_retry(attempt)
                    continue
                if status_code >= 500:
                    await self._mark_circuit_failure()
                detail = {
                    "message": "وب‌سرویس ITMB پاسخ خطادار برگرداند",
                    "upstream_status": status_code,
                    "upstream_body": exc.response.text[:500],
                }
                raise HTTPException(status_code=502, detail=detail)
            except httpx.RequestError as exc:
                if is_retryable_network_error(exc) and attempt < max_attempts:
                    await self._sleep_before_retry(attempt)
                    continue
                await self._mark_circuit_failure()
                raise HTTPException(
                    status_code=503,
                    detail="ارتباط با وب‌سرویس ITMB برقرار نشد",
                )
            except Exception as exc:
                if is_retryable_network_error(exc) and attempt < max_attempts:
                    await self._sleep_before_retry(attempt)
                    continue
                if is_retryable_network_error(exc):
                    await self._mark_circuit_failure()
                raise HTTPException(
                    status_code=500,
                    detail=f"خطای داخلی در ارتباط با ITMB: {str(exc)}",
                )

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
            "enabled": utcms_config.CIRCUIT_BREAKER_ENABLED,
        }


itmb_ws_service = ITMBWSService()
