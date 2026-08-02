import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    admin_alerts,
    admin_reporting,
    itmb_ws,
    location,
    management,
    multitenant,
    realtime,
    reports,
    rpa_phase1,
    system,
    user_reporting,
    waybill_entry,
    waybill_map,
)
from app.automation.browser import browser_manager
from app.automation.captcha import barname_ml_solver
from app.automation.proxy_rotator import get_proxy_rotator
from app.core.config import AUTO_GENERATED_SECRETS, utcms_config
from app.core.database import init_db
from app.core.exceptions import UTCMSException
from app.core.execution_context import bind_execution_context, reset_execution_context
from app.core.logging import configure_logging, reset_request_id, set_request_id
from app.core.rate_limiter import add_rate_limit_headers, rate_limiter
from app.core.tracing import setup_tracing, shutdown_tracing, trace_span

# Configure logging with optional file-based logging
if utcms_config.LOG_FILE:
    configure_logging(
        log_level=utcms_config.LOG_LEVEL,
        log_file=utcms_config.LOG_FILE,
        max_bytes=utcms_config.LOG_MAX_BYTES,
        backup_count=utcms_config.LOG_BACKUP_COUNT,
    )
else:
    configure_logging(utcms_config.LOG_LEVEL)
logger = logging.getLogger(__name__)


def _frontend_origins() -> list[str]:
    """Allow the configured frontend origin(s) plus common localhost variants.

    Reads from:
    - FRONTEND_URL   : primary origin (single value)
    - FRONTEND_URLS  : additional comma-separated origins (e.g. for dual-IP servers)
    - FRONTEND_URL_ALT: alternate origin for dual-IP server setups
    """
    raw_origins: list[str] = []

    # Primary origin
    primary = utcms_config.FRONTEND_URL.strip().rstrip("/")
    if primary:
        raw_origins.append(primary)

    # Additional origins via FRONTEND_URLS (comma-separated)
    if utcms_config.FRONTEND_URLS:
        raw_origins.extend(u.strip().rstrip("/") for u in utcms_config.FRONTEND_URLS.split(",") if u.strip())

    # Alternate URL (dual-IP server support)
    if utcms_config.FRONTEND_URL_ALT:
        raw_origins.append(utcms_config.FRONTEND_URL_ALT.rstrip("/"))

    if not raw_origins:
        return []

    origins: set[str] = set()
    for configured in raw_origins:
        try:
            parsed = urlparse(configured)
            if not parsed.scheme or not parsed.netloc or parsed.hostname is None:
                logger.warning("Ignoring invalid CORS origin", extra={"extra_fields": {"origin": configured}})
                continue

            scheme = parsed.scheme
            if scheme not in ("http", "https"):
                logger.warning(
                    "Ignoring CORS origin with invalid scheme", extra={"extra_fields": {"origin": configured}}
                )
                continue

            origin = f"{scheme}://{parsed.netloc}"
            origins.add(origin)

            if parsed.hostname in ("localhost", "127.0.0.1"):
                for host in ("localhost", "127.0.0.1"):
                    for port in ("", ":3000", ":8000", ":80"):
                        origins.add(f"{scheme}://{host}{port}")
        except Exception as exc:
            logger.warning(
                "Failed to parse CORS origin", extra={"extra_fields": {"origin": configured, "error": str(exc)}}
            )

    return sorted(origins)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if AUTO_GENERATED_SECRETS:
        logger.info(
            "secrets_auto_generated",
            extra={"extra_fields": {"count": len(AUTO_GENERATED_SECRETS)}},
        )

    # 1. Secrets initialization: initialize_secrets
    # Initialize Proxy Rotator from environment or file if configured
    proxy_rotator = get_proxy_rotator()
    if os.getenv("RPA_PROXY_LIST_FILE"):
        proxy_rotator.load_from_file(os.getenv("RPA_PROXY_LIST_FILE"))
    elif os.getenv("RPA_PROXIES"):
        proxy_urls = [p.strip() for p in os.getenv("RPA_PROXIES").split(",") if p.strip()]
        proxy_rotator.load_from_list(proxy_urls)

    if proxy_rotator.proxies:
        logger.info(f"Loaded {len(proxy_rotator.proxies)} proxies for automation")
    else:
        logger.warning("No proxies loaded. RPA will run on local IP.")

    # Initialize tracing
    setup_tracing()

    captcha_ready = await asyncio.to_thread(barname_ml_solver.warmup)
    if captcha_ready:
        logger.info("captcha_cnn_ready")
    else:
        logger.warning(
            "captcha_cnn_unavailable",
            extra={"extra_fields": {"model_path": str(barname_ml_solver.model_path)}},
        )

    # Test Redis connectivity for fail-closed Session Vault
    import sys
    if "pytest" not in sys.modules:
        from app.core.redis import redis_manager
        redis_client = await redis_manager.get()
        if redis_client:
            try:
                await redis_client.ping()
                logger.info("Redis connectivity verified for session vault")
            except Exception as exc:
                logger.critical(
                    "redis_connection_failed",
                    extra={"extra_fields": {"error": str(exc)}},
                    exc_info=True
                )
                raise RuntimeError("Redis connection failed during startup (fail-closed)") from exc
        else:
            logger.critical("Redis client is not available during startup (fail-closed)")
            raise RuntimeError("Redis client is not available during startup (fail-closed)")

    # Initialize database
    try:
        await init_db()
        logger.info("database_initialized")
    except Exception as exc:
        logger.critical(
            "database_initialization_failed",
            extra={"extra_fields": {"error": str(exc)}},
            exc_info=True,
        )
        raise RuntimeError("Database initialization failed during application startup") from exc

    # Initialize distributed traffic controller
    from app.core.distributed_traffic import distributed_traffic_controller
    from app.core.recovery import recovery_manager

    await distributed_traffic_controller.initialize()
    watchdog_task = asyncio.create_task(recovery_manager.watchdog_loop())

    # Bridge cross-process waybill events (workers -> API WebSockets) via Redis pub/sub
    from app.realtime.events import event_hub

    event_hub.start_subscriber()

    # Seed the Redis-backed queue-depth counters from the DB once at startup.
    from app.services.task_service import task_service

    await task_service._ensure_queue_depth_seeded()

    # Periodically reconcile the Redis queue-depth counters with the DB so that
    # any drift caused by status updates that bypass task_service (worker-side
    # writes, direct SQL, crashed processes) self-heals.
    async def _queue_depth_reconcile_loop() -> None:
        from app.services.task_service import task_service as _ts

        while True:
            await asyncio.sleep(60)
            try:
                await _ts.reconcile_queue_depth()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "queue_depth_reconcile_loop_error",
                    extra={"extra_fields": {"error": str(exc)}},
                )

    reconcile_task = asyncio.create_task(_queue_depth_reconcile_loop())

    yield

    # Cleanup
    watchdog_task.cancel()
    reconcile_task.cancel()
    await asyncio.gather(watchdog_task, reconcile_task, return_exceptions=True)
    await distributed_traffic_controller.close()
    await rate_limiter.close()
    await event_hub.stop_subscriber()
    shutdown_tracing()
    await browser_manager.close()


app = FastAPI(
    title="سیستم اتوماسیون UTCMS",
    description="ربات هوشمند صدور بارنامه با قابلیت انتخاب مسیر و گزارش‌گیری",
    version="2.0.0",
    lifespan=lifespan,
)

from pathlib import Path
_screenshots_dir = Path("runtime/screenshots")
_screenshots_dir.mkdir(parents=True, exist_ok=True)
app.mount("/assets/screenshots", StaticFiles(directory=str(_screenshots_dir)), name="screenshots")

cors_origins = _frontend_origins()
if not cors_origins:
    if utcms_config.ENVIRONMENT == "production":
        logger.critical(
            "CORS: FRONTEND_URL is not configured in production environment! "
            "This will block all cross-origin requests from the client. "
            "Exiting application setup due to critical configuration risk."
        )
        raise RuntimeError("FRONTEND_URL must be configured in production environment.")
    cors_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

logger.info("CORS allowed origins configured", extra={"extra_fields": {"cors_origins": cors_origins}})

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-ID", utcms_config.TRACE_HEADER_NAME],
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add security headers to all API responses for direct backend access."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self' ws: wss:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    return response


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    correlation_id = request.headers.get(utcms_config.TRACE_HEADER_NAME) or request_id
    token = set_request_id(request_id)
    execution_tokens = bind_execution_context(correlation_id=correlation_id)
    started = time.perf_counter()
    response = None
    rate_limit_state = None

    # Apply rate limiting to ALL endpoints with categorized rules
    path = request.url.path
    from app.core.rate_limiter import rate_limit_dependency

    rate_rule = "public"
    # Order matters: first match wins
    if any(path.startswith(p) for p in ("/api/v1/admin/login", "/admin/login", "/api/v1/auth/login", "/api/v1/auth/register")):
        rate_rule = "auth"
    elif any(path.startswith(p) for p in ("/api/v1/admin", "/admin", "/management")):
        rate_rule = "admin"
    elif any(path.startswith(p) for p in ("/waybill/", "/api/v1/waybill-jobs/")):
        rate_rule = "waybill"
    elif path.startswith("/api/v1/drivers/"):
        rate_rule = "driver"
    elif path.startswith("/api/v1/"):
        rate_rule = "tenant"

    try:
        rate_limit_state = await rate_limit_dependency(request, rule=rate_rule)
    except HTTPException as exc:
        content = exc.detail if isinstance(exc.detail, dict) else {"detail": exc.detail}
        response = JSONResponse(status_code=exc.status_code, content=content)
        for header_name, header_value in (exc.headers or {}).items():
            response.headers[header_name] = header_value
        response.headers["X-Request-ID"] = request_id
        response.headers[utcms_config.TRACE_HEADER_NAME] = correlation_id
        reset_request_id(token)
        reset_execution_context(execution_tokens)
        return response

    # Trace the request
    with trace_span(
        "http_request",
        method=request.method,
        path=request.url.path,
        request_id=request_id,
        client=request.client.host if request.client else None,
    ):
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "http_request_failed",
                extra={"extra_fields": {"method": request.method, "path": request.url.path}},
            )
            raise
        finally:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.info(
                "http_request",
                extra={
                    "extra_fields": {
                        "method": request.method,
                        "path": request.url.path,
                        "duration_ms": elapsed_ms,
                        "client": request.client.host if request.client else None,
                    }
                },
            )
            reset_request_id(token)
            reset_execution_context(execution_tokens)

    if response is not None:
        response.headers["X-Request-ID"] = request_id
        response.headers[utcms_config.TRACE_HEADER_NAME] = correlation_id
        if rate_limit_state is not None:
            add_rate_limit_headers(response, rate_limit_state)
    return response


app.include_router(waybill_map.router)
app.include_router(location.router)
app.include_router(waybill_entry.router)
app.include_router(management.router)
app.include_router(itmb_ws.router)
app.include_router(reports.router)
app.include_router(multitenant.router)
app.include_router(multitenant.alias_router)
app.include_router(rpa_phase1.router)
app.include_router(system.router)
app.include_router(realtime.router)
app.include_router(admin_alerts.router)
app.include_router(admin_reporting.router)
app.include_router(user_reporting.router)


@app.exception_handler(UTCMSException)
async def utcms_exception_handler(request: Request, exc: UTCMSException):
    """Handle structured UTCMS exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code.value,
            "message": str(exc),
            "retryable": exc.retryable,
            "request_id": request.headers.get("X-Request-ID"),
            "correlation_id": request.headers.get(utcms_config.TRACE_HEADER_NAME),
            **exc.details,
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle all uncaught exceptions."""
    logger.exception(
        "unhandled_exception",
        extra={
            "extra_fields": {
                "method": request.method,
                "path": request.url.path,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
        },
    )

    is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"

    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_SERVER_ERROR",
            "message": "خطای داخلی سرور رخ داده است",
            "request_id": request.headers.get("X-Request-ID"),
            "correlation_id": request.headers.get(utcms_config.TRACE_HEADER_NAME),
            # Only expose error_type in non-production environments for debugging
            **(
                {
                    "error_type": type(exc).__name__,
                }
                if not is_production
                else {}
            ),
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions (404, 401, 403, etc.)."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": f"HTTP_{exc.status_code}",
            "message": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
            "request_id": request.headers.get("X-Request-ID"),
            "correlation_id": request.headers.get(utcms_config.TRACE_HEADER_NAME),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with structured response."""
    return JSONResponse(
        status_code=422,
        content={
            "error": "VALIDATION_ERROR",
            "message": "اعتبارسنجی درخواست ناموفق بود",
            "details": exc.errors(),
            "request_id": request.headers.get("X-Request-ID"),
            "correlation_id": request.headers.get(utcms_config.TRACE_HEADER_NAME),
        },
    )


@app.exception_handler(ResponseValidationError)
async def response_validation_exception_handler(request: Request, exc: ResponseValidationError):
    """Handle FastAPI response validation errors with detailed logging and structured response."""
    logger.error(
        "response_validation_error",
        extra={
            "extra_fields": {
                "method": request.method,
                "path": request.url.path,
                "errors": exc.errors(),
            }
        },
    )
    is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"
    response_body: dict = {
        "error": "RESPONSE_VALIDATION_ERROR",
        "message": "خطا در قالب‌بندی پاسخ سرور",
        "request_id": request.headers.get("X-Request-ID"),
        "correlation_id": request.headers.get(utcms_config.TRACE_HEADER_NAME),
    }
    if not is_production:
        response_body["details"] = exc.errors()
    return JSONResponse(status_code=500, content=response_body)



@app.get("/", tags=["وضعیت سیستم"])
async def root():
    return {"message": "سیستم اتوماسیون UTCMS فعال است"}
