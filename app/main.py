import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    admin_reporting,
    itmb_ws,
    management,
    multitenant,
    realtime,
    reports,
    rpa_phase1,
    system,
    ui,
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

configure_logging(utcms_config.LOG_LEVEL)
logger = logging.getLogger(__name__)


def _frontend_origins() -> list[str]:
    """Allow the configured frontend origin plus common localhost variants."""
    configured = utcms_config.FRONTEND_URL.strip().rstrip("/")
    if not configured:
        return []

    try:
        parsed = urlparse(configured)
        if not parsed.scheme or not parsed.netloc:
            return [configured]

        origin = f"{parsed.scheme}://{parsed.netloc}"
        origins = {origin}

        if parsed.hostname == "localhost":
            variant_netloc = parsed.netloc.replace("localhost", "127.0.0.1", 1)
            origins.add(f"{parsed.scheme}://{variant_netloc}")
        elif parsed.hostname == "127.0.0.1":
            variant_netloc = parsed.netloc.replace("127.0.0.1", "localhost", 1)
            origins.add(f"{parsed.scheme}://{variant_netloc}")

        return sorted(origins)
    except Exception:
        return [configured]


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

    # Initialize distributed traffic controller
    from app.core.distributed_traffic import distributed_traffic_controller
    from app.core.recovery import recovery_manager
    await distributed_traffic_controller.initialize()
    watchdog_task = asyncio.create_task(recovery_manager.watchdog_loop())

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

    yield

    # Cleanup
    watchdog_task.cancel()
    await asyncio.gather(watchdog_task, return_exceptions=True)
    await distributed_traffic_controller.close()
    await rate_limiter.close()
    shutdown_tracing()
    await browser_manager.close()


app = FastAPI(
    title="سیستم اتوماسیون UTCMS",
    description="ربات هوشمند صدور بارنامه با قابلیت انتخاب مسیر و گزارش‌گیری",
    version="2.0.0",
    lifespan=lifespan,
)

app.mount("/assets", StaticFiles(directory="app/ui/assets"), name="assets")

cors_origins = _frontend_origins()
if not cors_origins:
    cors_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"] if os.getenv("ENVIRONMENT", "development").lower() != "production" else ["Authorization", "Content-Type", "X-API-Key", "X-Request-ID", utcms_config.TRACE_HEADER_NAME],
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    correlation_id = request.headers.get(utcms_config.TRACE_HEADER_NAME) or request_id
    token = set_request_id(request_id)
    execution_tokens = bind_execution_context(correlation_id=correlation_id)
    started = time.perf_counter()
    response = None
    rate_limit_state = None

    # Apply rate limiting for public and auth endpoints
    path = request.url.path
    rate_rule = None
    if path.startswith("/waybill/calculate-route") or path == "/":
        rate_rule = "public"
    elif path in ("/api/v1/auth/login", "/api/v1/admin/login", "/admin/login"):
        rate_rule = "auth"

    if rate_rule is not None:
        from app.core.rate_limiter import rate_limit_dependency

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
app.include_router(waybill_entry.router)
app.include_router(management.router)
app.include_router(itmb_ws.router)
app.include_router(reports.router)
app.include_router(multitenant.router)
app.include_router(multitenant.alias_router)
app.include_router(rpa_phase1.router)
app.include_router(system.router)
app.include_router(ui.router)
app.include_router(realtime.router)
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
            **({
                "error_type": type(exc).__name__,
            } if not is_production else {}),
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


@app.get("/", tags=["وضعیت سیستم"])
async def root():
    return {"message": "سیستم اتوماسیون UTCMS فعال است"}
