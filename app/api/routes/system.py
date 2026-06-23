import asyncio
import logging
from urllib.parse import urlparse

from fastapi import APIRouter, Query, Depends
from fastapi.responses import JSONResponse, Response
from app.core.security import require_sensitive_auth
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.automation.browser import browser_manager
from app.automation.captcha import barname_ml_solver, captcha_engine
from app.core.config import utcms_config
from app.core.database import engine
from app.core.recovery import recovery_manager
from app.core.worker_heartbeat import worker_heartbeat_registry
from app.monitoring.metrics import (
    METRICS_CONTENT_TYPE,
    export_metrics,
    get_captcha_runtime_snapshot,
    set_queue_depth,
    summarize_queue_depth,
)
from app.realtime.events import event_hub
from app.services.itmb_baseinfo_service import itmb_baseinfo_service
from app.services.itmb_ws_service import itmb_ws_service
from app.services.task_service import task_service
from app.workers.celery_app import celery_app, is_celery_available

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])


def _database_host() -> str:
    parsed = urlparse(utcms_config.DATABASE_URL)
    return parsed.hostname or ""


def _is_nonfatal_database_resolution_error(exc: Exception) -> bool:
    host = _database_host().strip().lower()
    message = str(exc).lower()
    transient_markers = (
        "nodename nor servname provided",
        "name or service not known",
        "temporary failure in name resolution",
        "failed to resolve",
    )
    return host in {"postgres", "db"} and any(marker in message for marker in transient_markers)


async def _safe_queue_snapshot() -> dict[str, int] | None:
    try:
        queue_snapshot = await task_service.queue_snapshot()
    except Exception as exc:
        if _is_nonfatal_database_resolution_error(exc):
            logger.warning(
                "queue_snapshot_skipped",
                extra={"extra_fields": {"reason": "database_dns_unavailable", "database_host": _database_host()}},
            )
            return None
        raise

    set_queue_depth(summarize_queue_depth(queue_snapshot))
    return queue_snapshot


class CaptchaDiagnoseRequest(BaseModel):
    text: str = Field(..., description="عبارت کپچا یا متن OCR شده")
    min_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="حداقل confidence مورد انتظار (اختیاری)",
    )


@router.get("/healthz")
async def healthz():
    return {"status": "ok"}


@router.get("/readyz")
async def readyz():
    checks = {
        "database": "unknown",
        "browser": "unknown",
        "config": "unknown",
        "captcha_model": "unknown",
        "itmb_config": "unknown",
        "itmb_baseinfo_cache": "unknown",
        "itmb_live_probe": "unknown",
        "queue": "unknown",
        "circuit_breaker": "unknown",
    }
    details = {
        "database": {},
        "browser": {},
        "config": {},
        "captcha_model": {},
        "itmb_config": {},
        "itmb_baseinfo_cache": {},
        "itmb_live_probe": {},
        "queue": {},
        "circuit_breaker": {},
    }

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
        details["database"] = {"message": "database connection ok"}
    except Exception as exc:
        if _is_nonfatal_database_resolution_error(exc):
            checks["database"] = "skipped"
            details["database"] = {
                "message": "database host not resolvable in current environment",
                "host": _database_host(),
            }
        else:
            checks["database"] = "error"
            details["database"] = {"message": "database connection failed"}

    try:
        await asyncio.wait_for(
            browser_manager.initialize(),
            timeout=max(1.0, float(utcms_config.READYZ_BROWSER_TIMEOUT_SECONDS)),
        )
        checks["browser"] = "ok"
        details["browser"] = {"message": "browser initialized"}
    except Exception:
        checks["browser"] = "error"
        details["browser"] = {"message": "browser initialization failed"}

    try:
        valid_modes = {"api_key", "jwt", "api_key_or_jwt", "api_key_and_jwt", "off", "none", "disabled"}
        checks["config"] = "ok" if utcms_config.API_AUTH_MODE in valid_modes else "error"
        if checks["config"] == "ok":
            details["config"] = {"message": "api auth mode valid", "mode": utcms_config.API_AUTH_MODE}
        else:
            details["config"] = {"message": "api auth mode invalid", "mode": utcms_config.API_AUTH_MODE}
    except Exception:
        checks["config"] = "error"
        details["config"] = {"message": "config validation failed"}

    try:
        captcha_available = await asyncio.to_thread(barname_ml_solver.warmup)
        checks["captcha_model"] = "ok" if captcha_available else "error"
        details["captcha_model"] = {
            "message": "cnn model loaded" if captcha_available else "cnn model unavailable",
            "provider": utcms_config.CAPTCHA_PROVIDER,
            "mode": utcms_config.CAPTCHA_MODE,
            "auto_only": bool(utcms_config.CAPTCHA_AUTO_ONLY),
            "model_path": str(barname_ml_solver.model_path),
        }
    except Exception:
        checks["captcha_model"] = "error"
        details["captcha_model"] = {"message": "captcha model check failed"}

    try:
        requires_itmb_auth = bool(utcms_config.ITMBOL_VALIDATE_BASEINFO or utcms_config.ITMBOL_READYZ_LIVE_CHECK)
        has_itmb_credentials = bool(
            utcms_config.ITMBOL_COMPANY_CODE.strip() and utcms_config.ITMBOL_SERVICE_PASSWORD.strip()
        )
        if not utcms_config.ITMBOL_SERVICE_URL.strip():
            checks["itmb_config"] = "error"
            details["itmb_config"] = {"message": "ITMBOL_SERVICE_URL is empty"}
        elif requires_itmb_auth and not has_itmb_credentials:
            checks["itmb_config"] = "error"
            details["itmb_config"] = {"message": "ITMB credentials are required but missing"}
        else:
            checks["itmb_config"] = "ok" if has_itmb_credentials else "skipped"
            if has_itmb_credentials:
                details["itmb_config"] = {"message": "ITMB credentials configured"}
            else:
                details["itmb_config"] = {"message": "ITMB credentials optional in current mode"}
    except Exception:
        checks["itmb_config"] = "error"
        details["itmb_config"] = {"message": "itmb config check failed"}

    try:
        if not utcms_config.ITMBOL_VALIDATE_BASEINFO:
            checks["itmb_baseinfo_cache"] = "skipped"
            details["itmb_baseinfo_cache"] = {"message": "baseinfo validation disabled"}
        else:
            cache_snapshot = itmb_baseinfo_service.status()
            has_missing = any(not item.get("cached", False) for item in cache_snapshot.values())
            has_stale = any(item.get("is_stale", False) for item in cache_snapshot.values() if item.get("cached"))
            checks["itmb_baseinfo_cache"] = "error" if (has_missing or has_stale) else "ok"
            details["itmb_baseinfo_cache"] = {
                "message": "baseinfo cache ready"
                if checks["itmb_baseinfo_cache"] == "ok"
                else "baseinfo cache missing or stale",
                "snapshot": cache_snapshot,
            }
    except Exception:
        checks["itmb_baseinfo_cache"] = "error"
        details["itmb_baseinfo_cache"] = {"message": "baseinfo cache check failed"}

    try:
        if not utcms_config.ITMBOL_READYZ_LIVE_CHECK:
            checks["itmb_live_probe"] = "skipped"
            details["itmb_live_probe"] = {"message": "live probe disabled"}
        else:
            probe = await itmb_baseinfo_service.probe_connection()
            checks["itmb_live_probe"] = "ok" if probe.get("ok") else "error"
            details["itmb_live_probe"] = {
                "message": "live probe ok" if checks["itmb_live_probe"] == "ok" else "live probe failed",
                "summary": probe.get("summary", {}),
            }
    except Exception:
        checks["itmb_live_probe"] = "error"
        details["itmb_live_probe"] = {"message": "live probe failed"}

    try:
        if not utcms_config.QUEUE_ENABLED:
            checks["queue"] = "skipped"
            details["queue"] = {"message": "queue disabled"}
        elif not is_celery_available():
            checks["queue"] = "error"
            details["queue"] = {"message": "celery package unavailable"}
        else:
            queue_snapshot = await _safe_queue_snapshot()
            if queue_snapshot is None:
                checks["queue"] = "skipped"
                details["queue"] = {
                    "message": "queue snapshot unavailable because database host is not resolvable",
                    "broker": utcms_config.CELERY_BROKER_URL,
                }
            else:
                checks["queue"] = "ok"
                details["queue"] = {
                    "message": "queue configured",
                    "snapshot": queue_snapshot,
                    "broker": utcms_config.CELERY_BROKER_URL,
                }
            if utcms_config.QUEUE_READYZ_LIVE_CHECK and queue_snapshot is not None:
                ping_result = celery_app.control.ping(timeout=1.0) if celery_app is not None else []
                if not ping_result:
                    checks["queue"] = "error"
                    details["queue"]["message"] = "queue live check failed"
    except Exception:
        checks["queue"] = "error"
        details["queue"] = {"message": "queue check failed"}

    try:
        circuit_status = await itmb_ws_service.circuit_status()
        checks["circuit_breaker"] = "error" if circuit_status["state"] == "open" else "ok"
        details["circuit_breaker"] = {
            "message": "circuit healthy" if checks["circuit_breaker"] == "ok" else "circuit open",
            "status": circuit_status,
        }
    except Exception:
        checks["circuit_breaker"] = "error"
        details["circuit_breaker"] = {"message": "circuit breaker check failed"}

    ready = all(value in {"ok", "skipped"} for value in checks.values())
    content = {
        "status": "ready" if ready else "not_ready",
        "checks": checks,
        "details": details,
    }

    if not ready:
        logger.warning("readiness_check_failed", extra={"extra_fields": content})

    return JSONResponse(status_code=200 if ready else 503, content=content)


@router.get("/metrics")
async def metrics():
    queue_snapshot = await _safe_queue_snapshot()
    if queue_snapshot is None:
        set_queue_depth(0)
    return Response(content=export_metrics(), media_type=METRICS_CONTENT_TYPE)


@router.get("/events/history")
async def event_history(task_id: str | None = Query(default=None), batch_id: str | None = Query(default=None)):
    return {
        "events": event_hub.history(task_id=task_id, batch_id=batch_id),
        "filters": {"task_id": task_id, "batch_id": batch_id},
    }


@router.get("/workers/heartbeats")
async def worker_heartbeats():
    stalled = worker_heartbeat_registry.detect_stalled(utcms_config.WORKER_STALL_TIMEOUT_SECONDS)
    return {
        "active": worker_heartbeat_registry.snapshot(),
        "stalled": stalled,
        "stall_timeout_seconds": utcms_config.WORKER_STALL_TIMEOUT_SECONDS,
    }


@router.post("/workers/recover-stalled")
async def recover_stalled_workers():
    recovered = await recovery_manager.recover_stalled_tasks()
    return {
        "recovered": recovered,
        "count": len(recovered),
    }


@router.get("/auth-config")
async def auth_config():
    mode = utcms_config.API_AUTH_MODE.strip().lower()
    return {
        "mode": mode,
        "api_key_header": utcms_config.API_KEY_HEADER,
        "api_key_configured": bool(utcms_config.API_KEY.strip()),
        "jwt_configured": bool(utcms_config.JWT_SECRET.strip()),
        "captcha_provider": utcms_config.CAPTCHA_PROVIDER,
        "captcha_mode": utcms_config.CAPTCHA_MODE,
        "captcha_auto_only": bool(utcms_config.CAPTCHA_AUTO_ONLY),
        "captcha_model_available": bool(barname_ml_solver.available),
        "captcha_math_min_confidence": max(0.0, min(1.0, float(utcms_config.CAPTCHA_MATH_MIN_CONFIDENCE))),
    }


@router.post("/captcha/diagnose")
async def captcha_diagnose(request: CaptchaDiagnoseRequest):
    decision = captcha_engine.solve_text_with_confidence(request.text)
    min_confidence = (
        request.min_confidence
        if request.min_confidence is not None
        else max(0.0, min(1.0, float(utcms_config.CAPTCHA_MATH_MIN_CONFIDENCE)))
    )
    accepted = bool(decision.value and decision.confidence >= min_confidence)

    return {
        "input_text": request.text,
        "solved_value": decision.value,
        "confidence": decision.confidence,
        "strategy": decision.strategy,
        "min_confidence": min_confidence,
        "accepted": accepted,
        "status": "accepted" if accepted else "rejected",
    }


@router.get("/captcha/monitor")
async def captcha_monitor(window: int = Query(default=50, ge=5, le=200)):
    snapshot = get_captcha_runtime_snapshot(window_size=window)
    rate = float(snapshot["window"]["failure_rate"])
    sample_size = int(snapshot["window"]["sample_size"])
    min_samples = max(1, int(utcms_config.CAPTCHA_ADAPTIVE_MIN_SAMPLES))

    if sample_size < min_samples:
        alert = "insufficient_data"
    elif rate >= float(utcms_config.CAPTCHA_ADAPTIVE_HIGH_FAILURE_RATE):
        alert = "high"
    elif rate <= float(utcms_config.CAPTCHA_ADAPTIVE_LOW_FAILURE_RATE):
        alert = "low"
    else:
        alert = "normal"

    return {
        **snapshot,
        "alert": {
            "level": alert,
            "high_failure_threshold": float(utcms_config.CAPTCHA_ADAPTIVE_HIGH_FAILURE_RATE),
            "low_failure_threshold": float(utcms_config.CAPTCHA_ADAPTIVE_LOW_FAILURE_RATE),
            "min_samples": min_samples,
        },
    }


@router.get("/browser-pool/health")
async def browser_pool_health():
    """Health check for browser pool with detailed status."""
    from app.automation.browser import browser_manager

    if not utcms_config.BROWSER_POOL_ENABLED:
        return {
            "enabled": False,
            "status": "disabled",
            "message": "Browser pool is not enabled",
        }

    pool = browser_manager._pool
    if pool is None:
        return {
            "enabled": True,
            "status": "not_initialized",
            "message": "Browser pool not yet initialized",
        }

    health = await pool.check_health()
    health_status = pool.get_health_status()

    # Determine overall status
    if health.unhealthy_contexts > health.healthy_contexts:
        status = "degraded"
    elif health.unhealthy_contexts > 0:
        status = "warning"
    else:
        status = "healthy"

    return {
        "enabled": True,
        "status": status,
        "pool": health_status,
        "summary": {
            "total_contexts": health.total_contexts,
            "healthy": health.healthy_contexts,
            "unhealthy": health.unhealthy_contexts,
            "available": health.available_contexts,
            "utilization_percent": health.pool_utilization,
            "total_errors": health.total_errors,
            "total_successes": health.total_successes,
        },
    }


@router.post("/browser-pool/heal")
async def heal_browser_pool():
    """Heal unhealthy browser contexts."""
    from app.automation.browser import browser_manager

    if not utcms_config.BROWSER_POOL_ENABLED:
        return {"status": "disabled", "message": "Browser pool is not enabled"}

    pool = browser_manager._pool
    if pool is None:
        return {"status": "error", "message": "Browser pool not initialized"}

    try:
        healed = await pool.heal_unhealthy_contexts(
            browser_manager.browser,
            browser_manager._build_context_args(),
        )
        return {
            "status": "success",
            "healed_count": healed,
            "message": f"{healed} browser contexts healed",
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to heal browser contexts: {str(exc)}",
        }


@router.get("/security/report")
async def security_report():
    """Generate security configuration report."""
    from app.core.secrets_manager import secrets_manager

    report = secrets_manager.get_security_report()
    return {
        **report,
        "recommendations": _generate_security_recommendations(report),
    }


@router.get("/errors/stats")
async def error_statistics():
    """Get centralized error statistics."""
    # Temporary mock implementation, will fetch from db later if implemented
    return {
        "status": "success",
        "message": "Error statistics endpoint",
        "supported_categories": [
            "USER_DATA_ERROR",
            "AUTH_FAILURE",
            "CAPTCHA_EXHAUSTION",
            "TARGET_SITE_TIMEOUT",
            "SELECTOR_CHANGED",
            "BOT_DETECTED",
            "TRANSIENT_INFRA_ERROR",
            "WORKER_RESOURCE_ERROR",
            "UNKNOWN_AUTOMATION_ERROR",
        ],
    }


def _generate_security_recommendations(report: dict) -> list[str]:
    """Generate security recommendations based on current config."""
    recommendations = []

    if not report.get("api_key_configured"):
        recommendations.append("API_KEY is not configured. Use auto-generation or set manually.")

    if not report.get("jwt_secret_configured"):
        recommendations.append("JWT_SECRET is not configured. Use auto-generation or set manually.")

    if not report.get("postgres_password_secure"):
        recommendations.append("POSTGRES_PASSWORD is using default value. Change to a secure password.")

    if report.get("auth_mode") == "off":
        recommendations.append("API authentication is disabled. Enable it in production environments.")

    if not recommendations:
        recommendations.append("Security configuration looks good!")

    return recommendations


@router.post("/circuit-breaker/toggle", dependencies=[Depends(require_sensitive_auth)])
async def toggle_circuit_breaker(enabled: bool = Query(...)):
    """فعال یا غیرفعال کردن موقت قطع‌کننده مدار."""
    from app.services.itmb_ws_service import itmb_ws_service
    itmb_ws_service.toggle_circuit_breaker(enabled)
    return {
        "success": True,
        "enabled": enabled,
        "message": f"Circuit breaker {'enabled' if enabled else 'disabled'} successfully",
    }
