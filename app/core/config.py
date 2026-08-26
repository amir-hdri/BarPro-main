import os
from pathlib import Path


def _load_dotenv_if_exists(path: str = ".env") -> None:
    dotenv_path = Path(path)
    if not dotenv_path.exists() or not dotenv_path.is_file():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value and ((value[0] == value[-1]) and value[0] in {"'", '"'}):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _bootstrap_environment() -> dict[str, str]:
    _load_dotenv_if_exists()
    from app.core.secrets_manager import initialize_secrets

    generated = initialize_secrets(auto_generate=True)
    if generated:
        _load_dotenv_if_exists()
    return generated


def _to_bool(value: str | None, default: bool = False, required: bool = False) -> bool:
    if value is None:
        if required:
            raise ValueError("Missing required boolean environment variable (no default)")
        return default
    return value.strip().lower() == "true"


def _validated_choice(name: str, value: str | None, default: str, allowed: set[str]) -> str:
    normalized = (default if value is None else value).strip().lower()
    if normalized not in allowed:
        raise ValueError(f"Invalid {name} '{normalized}'. Must be one of: {', '.join(sorted(allowed))}")
    return normalized


class UTCMSConfig:
    def __init__(self) -> None:
        # NOTE: the three URLs below address the EXTERNAL UTCMS government
        # portal that the RPA drives — they are not BarPro's own address.
        # BarPro serves itself over plain http behind nginx, which has caused
        # repeated "https/http mismatch" reports against these defaults; there
        # is no mismatch, and downgrading them to http would put the portal
        # credentials on the wire in cleartext. BarPro's own public address is
        # configured via NEXT_PUBLIC_API_URL, which is relative ("/api") and so
        # is scheme-agnostic by design.
        self.WAYBILL_URL = os.getenv(
            "WAYBILL_URL",
            "https://barname.utcms.ir/barname/Document/HagigiHogugi",
        )
        self.BASE_URL = os.getenv("BASE_URL", "https://barname.utcms.ir")
        self.LOGIN_URL = os.getenv("LOGIN_URL", f"{self.BASE_URL.rstrip('/')}/Barname/Account/Login")
        self.HEADLESS = _to_bool(os.getenv("HEADLESS"), default=True)

        self.UTCMS_USERNAME = os.getenv("UTCMS_USERNAME", "")
        self.UTCMS_PASSWORD = os.getenv("UTCMS_PASSWORD", "")

        self.UTCMS_CAPTCHA_VALUE = os.getenv("UTCMS_CAPTCHA_VALUE", "").strip()
        self.UTCMS_ENABLE_MANUAL_CAPTCHA = _to_bool(os.getenv("UTCMS_ENABLE_MANUAL_CAPTCHA", "False"), default=False)
        self.UTCMS_MANUAL_CAPTCHA_TIMEOUT_SECONDS = int(os.getenv("UTCMS_MANUAL_CAPTCHA_TIMEOUT_SECONDS", "120"))
        self.UTCMS_MANUAL_CAPTCHA_POLL_SECONDS = float(os.getenv("UTCMS_MANUAL_CAPTCHA_POLL_SECONDS", "0.7"))
        self.CAPTCHA_MODE = _validated_choice(
            "CAPTCHA_MODE",
            os.getenv("CAPTCHA_MODE"),
            "local_only",
            {"local_only", "provider_only", "provider_first", "manual_only"},
        )
        _valid_captcha_providers = {
            "auto",
            "ensemble",
            "composite",
            "cnn",
            "pytorch_fuel",
            "keras_ocr",
            "enhanced_ocr",
            "local_ocr",
            "off",
        }
        self.CAPTCHA_PROVIDER = _validated_choice(
            "CAPTCHA_PROVIDER",
            os.getenv("CAPTCHA_PROVIDER"),
            "auto",
            _valid_captcha_providers,
        )
        self.TWOCAPTCHA_API_KEY = os.getenv("TWOCAPTCHA_API_KEY", "").strip()
        self.CAPTCHA_TIMEOUT_SECONDS = int(os.getenv("CAPTCHA_TIMEOUT_SECONDS", "120"))
        self.CAPTCHA_POLL_SECONDS = float(os.getenv("CAPTCHA_POLL_SECONDS", "5"))
        self.CAPTCHA_MAX_RETRIES = int(os.getenv("CAPTCHA_MAX_RETRIES", "2"))
        self.CAPTCHA_LOCAL_FALLBACK_ENABLED = _to_bool(
            os.getenv("CAPTCHA_LOCAL_FALLBACK_ENABLED", "True"),
            default=True,
        )
        # When True the bot NEVER contacts an external captcha solver service.
        # All captcha solving is performed by the bundled local ML models
        # (CNN / PyTorch fuel / Keras OCR / enhanced OCR / local OCR for the
        # fuel page, and the math-captcha engine for the login page).
        self.CAPTCHA_LOCAL_ONLY = _to_bool(
            os.getenv("CAPTCHA_LOCAL_ONLY", "True"),
            default=True,
        )
        self.CAPTCHA_MATH_MIN_CONFIDENCE = float(os.getenv("CAPTCHA_MATH_MIN_CONFIDENCE", "0.62"))
        self.CAPTCHA_AUTO_ONLY = _to_bool(os.getenv("CAPTCHA_AUTO_ONLY", "True"), default=True)
        self.CAPTCHA_AUTO_MAX_ATTEMPTS = int(os.getenv("CAPTCHA_AUTO_MAX_ATTEMPTS", "3"))
        self.CAPTCHA_AUTO_REFRESH_ON_RETRY = _to_bool(
            os.getenv("CAPTCHA_AUTO_REFRESH_ON_RETRY", "True"),
            default=True,
        )
        self.CAPTCHA_AUTO_RETRY_DELAY_SECONDS = float(os.getenv("CAPTCHA_AUTO_RETRY_DELAY_SECONDS", "0.7"))
        self.CAPTCHA_REFRESH_WAIT_SECONDS = float(os.getenv("CAPTCHA_REFRESH_WAIT_SECONDS", "0.8"))
        self.CAPTCHA_SUBMIT_RETRY_DELAY_SECONDS = float(os.getenv("CAPTCHA_SUBMIT_RETRY_DELAY_SECONDS", "0.8"))
        # How long an inquiry may stay in pending/processing/running before it is
        # considered abandoned and auto-expired (so the user can safely retry).
        self.FUEL_INQUIRY_STALE_MINUTES = int(os.getenv("FUEL_INQUIRY_STALE_MINUTES", "10"))
        self.CAPTCHA_VALUE_MIN_LENGTH = int(os.getenv("CAPTCHA_VALUE_MIN_LENGTH", "1"))
        self.CAPTCHA_VALUE_MAX_LENGTH = int(os.getenv("CAPTCHA_VALUE_MAX_LENGTH", "6"))
        self.CAPTCHA_ADAPTIVE_ENABLED = _to_bool(os.getenv("CAPTCHA_ADAPTIVE_ENABLED", "True"), default=True)
        self.CAPTCHA_ADAPTIVE_WINDOW = int(os.getenv("CAPTCHA_ADAPTIVE_WINDOW", "60"))
        self.CAPTCHA_ADAPTIVE_MIN_SAMPLES = int(os.getenv("CAPTCHA_ADAPTIVE_MIN_SAMPLES", "10"))
        self.CAPTCHA_ADAPTIVE_HIGH_FAILURE_RATE = float(os.getenv("CAPTCHA_ADAPTIVE_HIGH_FAILURE_RATE", "0.35"))
        self.CAPTCHA_ADAPTIVE_LOW_FAILURE_RATE = float(os.getenv("CAPTCHA_ADAPTIVE_LOW_FAILURE_RATE", "0.10"))
        self.CAPTCHA_ADAPTIVE_MAX_ATTEMPTS = int(os.getenv("CAPTCHA_ADAPTIVE_MAX_ATTEMPTS", "5"))
        self.CAPTCHA_ADAPTIVE_MAX_DELAY_SECONDS = float(os.getenv("CAPTCHA_ADAPTIVE_MAX_DELAY_SECONDS", "2.5"))
        # CAPTCHA screenshots can contain security challenges and must be
        # explicitly enabled for a controlled diagnostic run.
        self.CAPTCHA_DEBUG_SAVE_IMAGES = _to_bool(os.getenv("CAPTCHA_DEBUG_SAVE_IMAGES", "False"), default=False)
        self.CAPTCHA_DEBUG_DIR = (
            os.getenv("CAPTCHA_DEBUG_DIR", "output/captcha_debug").strip() or "output/captcha_debug"
        )
        self.KERAS_PYTHON_PATH = os.getenv(
            "KERAS_PYTHON_PATH",
            # Default to system python3; override via KERAS_PYTHON_PATH env var on server
            # (e.g. /opt/barpro/venv/bin/python or a dedicated keras venv)
            "python3",
        ).strip()
        self.KERAS_MODEL_PATH = os.getenv(
            "KERAS_MODEL_PATH",
            "persian_number_ocr.keras",
        ).strip()

        self.AUTH_STATE_PATH = os.getenv("AUTH_STATE_PATH", ".auth/utcms_state.json")
        self.USE_PERSISTENT_AUTH_STATE = _to_bool(os.getenv("USE_PERSISTENT_AUTH_STATE", "True"), default=True)

        # Hybrid login: try an HTTP-only login via curl_cffi (with Chrome
        # TLS impersonation) before launching Playwright. The WAF in
        # front of barname.utcms.ir aggressively flags Chromium's
        # fingerprint, so a clean HTTP session is much more likely to
        # pass. If HTTP login succeeds, the obtained auth cookies are
        # injected into the Playwright context and the rest of the RPA
        # flow continues with a valid session. Disable for diagnosis.
        self.UTCMS_HTTP_LOGIN_ENABLED = _to_bool(os.getenv("UTCMS_HTTP_LOGIN_ENABLED", "True"), default=True)

        self.API_AUTH_MODE = os.getenv("API_AUTH_MODE", "api_key_or_jwt").lower()
        self.API_KEY_HEADER = os.getenv("API_KEY_HEADER", "X-API-Key")
        self.API_KEY = os.getenv("API_KEY", "")
        self.JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
        self.JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "")
        self.JWT_ISSUER = os.getenv("JWT_ISSUER", "")
        self.JWT_LEEWAY_SECONDS = int(os.getenv("JWT_LEEWAY_SECONDS", "10"))
        self.MASTER_ADMIN_USERNAME = os.getenv("MASTER_ADMIN_USERNAME", "").strip() or "admin"
        self.MASTER_ADMIN_PASSWORD = os.getenv("MASTER_ADMIN_PASSWORD", "").strip()
        if not self.MASTER_ADMIN_PASSWORD:
            from app.core.exceptions import ErrorCode, UTCMSException

            raise UTCMSException(
                "MASTER_ADMIN_PASSWORD is not set. "
                "This environment variable is required — no default value is allowed. "
                "Set a strong, unique password before starting the service.",
                error_code=ErrorCode.INTERNAL_CONFIG_ERROR,
                status_code=500,
            )

        # NOTE: ALLOW_LIVE_SUBMIT is intentionally assigned ONCE below in the
        # submission-safety block (Non-negotiable Rule #1). Do not re-read the
        # env var here — duplicate assignment shadowed the canonical value.
        # Defence-in-depth for GET /metrics: when set, the endpoint additionally
        # accepts requests presenting this token in the X-Metrics-Token header
        # (e.g. Prometheus scraping from outside the Docker bridge). When empty,
        # only loopback/RFC1918 peers are served.
        self.METRICS_SCRAPE_TOKEN = os.getenv("METRICS_SCRAPE_TOKEN", "").strip()
        self.JOB_TIMEOUT_SECONDS = int(
            os.getenv("JOB_TIMEOUT_SECONDS", "330")
        )  # inner asyncio.wait_for bound; CELERY_TASK_SOFT/TIME_LIMIT derive from this (see H1 below)
        self.ITMBOL_SERVICE_URL = os.getenv("ITMBOL_SERVICE_URL", "https://services2.sipaad.ir/ITMBOL.asmx")
        self.ITMBOL_COMPANY_CODE = os.getenv("ITMBOL_COMPANY_CODE", "").strip()
        self.ITMBOL_SERVICE_PASSWORD = os.getenv("ITMBOL_SERVICE_PASSWORD", "").strip()
        self.ITMBOL_TIMEOUT_SECONDS = float(os.getenv("ITMBOL_TIMEOUT_SECONDS", "30"))
        self.ITMBOL_MAX_RETRIES = int(os.getenv("ITMBOL_MAX_RETRIES", "2"))
        self.ITMBOL_RETRY_BASE_SECONDS = float(os.getenv("ITMBOL_RETRY_BASE_SECONDS", "0.8"))
        self.ITMBOL_BASEINFO_CACHE_TTL_SECONDS = int(os.getenv("ITMBOL_BASEINFO_CACHE_TTL_SECONDS", "86400"))
        self.ITMBOL_VALIDATE_BASEINFO = _to_bool(os.getenv("ITMBOL_VALIDATE_BASEINFO", "False"), default=False)
        self.ITMBOL_READYZ_LIVE_CHECK = _to_bool(os.getenv("ITMBOL_READYZ_LIVE_CHECK", "False"), default=False)
        self.READYZ_BROWSER_TIMEOUT_SECONDS = float(os.getenv("READYZ_BROWSER_TIMEOUT_SECONDS", "8"))
        self.READYZ_CACHE_TTL_SECONDS = float(os.getenv("READYZ_CACHE_TTL_SECONDS", "30"))

        self.WAYBILL_MAX_CONCURRENT = int(os.getenv("WAYBILL_MAX_CONCURRENT", "2"))
        self.WAYBILL_MIN_GAP_SECONDS = float(os.getenv("WAYBILL_MIN_GAP_SECONDS", "8.0"))
        self.WAYBILL_JITTER_SECONDS = float(os.getenv("WAYBILL_JITTER_SECONDS", "2.0"))
        self.WAYBILL_BLOCK_BACKOFF_SECONDS = float(os.getenv("WAYBILL_BLOCK_BACKOFF_SECONDS", "15"))
        self.WAYBILL_BLOCK_BACKOFF_MAX_SECONDS = float(os.getenv("WAYBILL_BLOCK_BACKOFF_MAX_SECONDS", "180"))
        self.WAYBILL_MAX_RETRIES = int(os.getenv("WAYBILL_MAX_RETRIES", "1"))
        self.WAYBILL_RETRY_BASE_SECONDS = float(os.getenv("WAYBILL_RETRY_BASE_SECONDS", "1.0"))
        self.WAYBILL_RETRY_JITTER_SECONDS = float(os.getenv("WAYBILL_RETRY_JITTER_SECONDS", "0.5"))
        self.PAGE_GOTO_MAX_RETRIES = int(os.getenv("PAGE_GOTO_MAX_RETRIES", "2"))
        self.PAGE_GOTO_RETRY_BASE_SECONDS = float(os.getenv("PAGE_GOTO_RETRY_BASE_SECONDS", "1.0"))
        self.PAGE_GOTO_RETRY_JITTER_SECONDS = float(os.getenv("PAGE_GOTO_RETRY_JITTER_SECONDS", "0.4"))
        self.PAGE_DEFAULT_TIMEOUT = int(os.getenv("PAGE_DEFAULT_TIMEOUT", "30000"))
        self.PAGE_NAVIGATION_TIMEOUT = int(os.getenv("PAGE_NAVIGATION_TIMEOUT", "45000"))

        # Browser route interceptor settings
        self.BLOCK_MAP_TILES = _to_bool(os.getenv("BLOCK_MAP_TILES", "True"), default=True)

        self.ENVIRONMENT = os.getenv("ENVIRONMENT", "development").strip().lower()
        self.DATABASE_URL = os.getenv("DATABASE_URL", "")
        if not self.DATABASE_URL or "sqlite" in self.DATABASE_URL.lower():
            is_prod = os.getenv("NODE_ENV", "").lower() == "production" or self.ENVIRONMENT == "production"
            if is_prod:
                from app.core.exceptions import ErrorCode, UTCMSException

                raise UTCMSException(
                    "DATABASE_URL is not set or using SQLite in production. "
                    "This is a critical security and scalability risk. Please configure a secure PostgreSQL DATABASE_URL.",
                    error_code=ErrorCode.INTERNAL_CONFIG_ERROR,
                    status_code=500,
                )
            if not self.DATABASE_URL:
                import logging

                logging.warning("DATABASE_URL not set, using default SQLite database for development.")
                self.DATABASE_URL = "sqlite+aiosqlite:///./bot_stats.db"
        self.MIGRATION_LOCK_TIMEOUT_SECONDS = max(1, int(os.getenv("MIGRATION_LOCK_TIMEOUT_SECONDS", "300")))
        # self.POSTGRES_DSN = os.getenv("POSTGRES_DSN", "").strip()  # unused — kept as reference

        self.QUEUE_ENABLED = _to_bool(os.getenv("QUEUE_ENABLED", "True"), default=True)
        self.QUEUE_INLINE_FALLBACK = _to_bool(os.getenv("QUEUE_INLINE_FALLBACK", "False"), default=False)
        self.QUEUE_IDEMPOTENCY_HEADER = os.getenv("QUEUE_IDEMPOTENCY_HEADER", "X-Idempotency-Key").strip()
        self.QUEUE_READYZ_LIVE_CHECK = _to_bool(os.getenv("QUEUE_READYZ_LIVE_CHECK", "False"), default=False)
        self.IDEMPOTENCY_KEY_MAX_LENGTH = int(os.getenv("IDEMPOTENCY_KEY_MAX_LENGTH", "200"))

        self.REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0").strip()
        self.REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "").strip()
        self.CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", self.REDIS_URL).strip()
        self.CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", self.REDIS_URL).strip()
        self.CELERY_TASK_QUEUE = os.getenv("CELERY_TASK_QUEUE", "waybill_tasks").strip()
        self.CELERY_DLQ_QUEUE = os.getenv("CELERY_DLQ_QUEUE", "waybill_dlq").strip()
        # ── H1 fix: Celery soft/hard limits are DERIVED from JOB_TIMEOUT_SECONDS.
        # The embedded `asyncio.wait_for(bot, JOB_TIMEOUT_SECONDS)` handler maps a
        # full-length timeout to unknown → reconciliation (the mutation-safe path).
        # If the Celery SOFT limit were smaller than JOB_TIMEOUT_SECONDS (e.g. the
        # old default 300 < 330), SoftTimeLimitExceeded fired FIRST at an arbitrary
        # await point and that safe handler never ran. Soft limit now sits above
        # the bot window (+15s for result processing); hard limit gives the worker
        # a bounded cleanup window after the soft signal, then SIGKILLs.
        self.CELERY_TASK_SOFT_TIME_LIMIT = int(
            os.getenv("CELERY_TASK_SOFT_TIME_LIMIT", str(self.JOB_TIMEOUT_SECONDS + 15))
        )
        if self.CELERY_TASK_SOFT_TIME_LIMIT <= self.JOB_TIMEOUT_SECONDS:
            # Env misconfiguration: never let the soft limit preempt the
            # in-task timeout handler again.
            self.CELERY_TASK_SOFT_TIME_LIMIT = self.JOB_TIMEOUT_SECONDS + 15
        _default_hard_limit = self.CELERY_TASK_SOFT_TIME_LIMIT + 45
        self.CELERY_TASK_TIME_LIMIT = max(
            int(os.getenv("CELERY_TASK_TIME_LIMIT", str(_default_hard_limit))), self.CELERY_TASK_SOFT_TIME_LIMIT + 5
        )
        self.CELERY_MAX_RETRIES = int(os.getenv("CELERY_MAX_RETRIES", "5"))
        self.CELERY_RETRY_BASE_SECONDS = float(os.getenv("CELERY_RETRY_BASE_SECONDS", "2.0"))
        self.CELERY_RETRY_JITTER_SECONDS = float(os.getenv("CELERY_RETRY_JITTER_SECONDS", "1.5"))
        self.CELERY_WORKER_PREFETCH_MULTIPLIER = int(os.getenv("CELERY_WORKER_PREFETCH_MULTIPLIER", "1"))
        self.WORKER_STALL_TIMEOUT_SECONDS = int(os.getenv("WORKER_STALL_TIMEOUT_SECONDS", "90"))
        # Interval (seconds) at which every Celery worker re-writes its
        # worker_registry heartbeat. This is the *registry* heartbeat — NOT the
        # API-side watchdog loop interval (WORKER_HEARTBEAT_INTERVAL_SECONDS,
        # which drives recovery_manager.watchdog_loop). The circuit breaker
        # treats a worker as stale after 3x this interval.
        self.WORKER_REGISTRY_HEARTBEAT_SECONDS = float(os.getenv("WORKER_REGISTRY_HEARTBEAT_SECONDS", "30"))

        self.BROWSER_POOL_ENABLED = _to_bool(os.getenv("BROWSER_POOL_ENABLED", "False"), default=False)
        self.BROWSER_POOL_SIZE = int(os.getenv("BROWSER_POOL_SIZE", "8"))

        self.CIRCUIT_BREAKER_ENABLED = _to_bool(os.getenv("CIRCUIT_BREAKER_ENABLED", "True"), default=True)
        self.CIRCUIT_BREAKER_FAILURE_THRESHOLD = int(os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5"))
        self.CIRCUIT_BREAKER_RECOVERY_SECONDS = int(os.getenv("CIRCUIT_BREAKER_RECOVERY_SECONDS", "30"))
        self.CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS = int(os.getenv("CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS", "2"))

        self.FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000").strip()
        self.FRONTEND_URLS = os.getenv("FRONTEND_URLS", "").strip()
        self.FRONTEND_URL_ALT = os.getenv("FRONTEND_URL_ALT", "").strip()
        # httpOnly JWT cookie name (backend). The Next.js side reads the same
        # value via NEXT_PUBLIC_AUTH_COOKIE_NAME — keep both in sync when
        # customizing; default must stay "utcms_auth_token".
        self.AUTH_COOKIE_NAME = os.getenv("AUTH_COOKIE_NAME", "utcms_auth_token").strip() or "utcms_auth_token"
        self.AUTH_COOKIE_SECURE = _to_bool(
            os.getenv("AUTH_COOKIE_SECURE"),
            default=self.FRONTEND_URL.lower().startswith("https://"),
        )

        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.LATENCY_SAMPLE_MAX = int(os.getenv("LATENCY_SAMPLE_MAX", "2000"))
        self.FAILURE_ARTIFACTS_DIR = os.getenv("FAILURE_ARTIFACTS_DIR", "output/failure_artifacts").strip()
        self.WAYBILL_SUCCESS_SCREENSHOT_ENABLED = _to_bool(
            os.getenv("WAYBILL_SUCCESS_SCREENSHOT_ENABLED", "False"), default=False
        )
        self.TRACE_HEADER_NAME = os.getenv("TRACE_HEADER_NAME", "X-Correlation-ID").strip()

        # Logging configuration
        self.LOG_FILE = os.getenv("LOG_FILE", "").strip()
        self.LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", "104857600"))  # 100MB default
        self.LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))
        self.LOG_DIR = os.getenv("LOG_DIR", "/var/log/barpro").strip()
        self.ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "").strip()
        self.ALERT_WEBHOOK_SECRET = os.getenv("ALERT_WEBHOOK_SECRET", "").strip()
        self.WS_EVENT_HISTORY_LIMIT = int(os.getenv("WS_EVENT_HISTORY_LIMIT", "500"))
        self.WORKER_HEARTBEAT_INTERVAL_SECONDS = float(os.getenv("WORKER_HEARTBEAT_INTERVAL_SECONDS", "5"))
        # Alias WATCHDOG_LOOP_INTERVAL_SECONDS to prevent ambiguity with worker registry heartbeats
        self.WATCHDOG_LOOP_INTERVAL_SECONDS = self.WORKER_HEARTBEAT_INTERVAL_SECONDS
        self.CELERY_DEFAULT_PRIORITY = int(os.getenv("CELERY_DEFAULT_PRIORITY", "5"))
        self.CELERY_MIN_PRIORITY = int(os.getenv("CELERY_MIN_PRIORITY", "0"))
        self.CELERY_MAX_PRIORITY = int(os.getenv("CELERY_MAX_PRIORITY", "9"))

        # Multi-tenant settings
        self.MULTITENANT_ENABLED = _to_bool(os.getenv("MULTITENANT_ENABLED", "False"), default=False)
        self.DEPRECATE_OLD_EXECUTION_PATH = _to_bool(os.getenv("DEPRECATE_OLD_EXECUTION_PATH", "True"), default=True)

        # Job processing settings
        self.STALE_JOB_THRESHOLD_MINUTES = int(os.getenv("STALE_JOB_THRESHOLD_MINUTES", "5"))

        # Celery queue names (configurable for testing)
        self.CELERY_WAYBILL_SUBMIT_QUEUE = os.getenv("CELERY_WAYBILL_SUBMIT_QUEUE", "barpro.waybill.submit")
        self.CELERY_WAYBILL_AUTH_QUEUE = os.getenv("CELERY_WAYBILL_AUTH_QUEUE", "barpro.waybill.auth")
        self.CELERY_FUEL_INQUIRY_QUEUE = os.getenv("CELERY_FUEL_INQUIRY_QUEUE", "barpro.fuel.inquiry")
        self.CELERY_RECOVERY_QUEUE = os.getenv("CELERY_RECOVERY_QUEUE", "barpro.recovery")
        self.CELERY_RECONCILIATION_QUEUE = os.getenv("CELERY_RECONCILIATION_QUEUE", "barpro.reconciliation")
        self.CELERY_WAYBILL_TASKS_QUEUE = os.getenv("CELERY_WAYBILL_TASKS_QUEUE", "waybill_tasks")
        self.CELERY_RECONCILIATION_TASKS_QUEUE = os.getenv("CELERY_RECONCILIATION_TASKS_QUEUE", "reconciliation_tasks")

        # SECURITY: Validate critical secrets are set
        if self.ALERT_WEBHOOK_URL and not self.ALERT_WEBHOOK_SECRET:
            raise ValueError(
                "ALERT_WEBHOOK_SECRET must be configured if ALERT_WEBHOOK_URL is set "
                "to ensure integrity of webhooks via HMAC signatures."
            )

        self.JWT_SECRET = os.getenv("JWT_SECRET", "")
        if not self.JWT_SECRET or self.JWT_SECRET in [
            "change-me-jwt-secret-required",
            "super-secret-jwt-key-change-in-production",
            "dev-only-insecure-jwt-secret-change-immediately",
        ]:
            from app.core.exceptions import ErrorCode, UTCMSException

            raise UTCMSException(
                "JWT_SECRET is not set or using an insecure default. "
                "This is a critical security risk. Please configure a secure JWT_SECRET in your environment "
                'or .env file. Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"',
                error_code=ErrorCode.INTERNAL_CONFIG_ERROR,
                status_code=500,
            )

        self.JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "240"))

        self.DRIVER_ENCRYPTION_KEY = os.getenv("DRIVER_ENCRYPTION_KEY", "")
        if not self.DRIVER_ENCRYPTION_KEY or self.DRIVER_ENCRYPTION_KEY in [
            "change-me-encryption-key-required",
            "default-encryption-key-change-in-production",
        ]:
            from app.core.exceptions import ErrorCode, UTCMSException

            raise UTCMSException(
                "DRIVER_ENCRYPTION_KEY is not set or using an insecure default. "
                "This is a critical security risk. Please configure a secure DRIVER_ENCRYPTION_KEY in your environment "
                'or .env file. Generate with: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"',
                error_code=ErrorCode.INTERNAL_CONFIG_ERROR,
                status_code=500,
            )

        self.BUSINESS_TIMEZONE = os.getenv("BUSINESS_TIMEZONE", "Asia/Tehran").strip()
        self.DRIVER_DAILY_SUCCESS_CAP = int(os.getenv("DRIVER_DAILY_SUCCESS_CAP", "10"))
        self.DRIVER_DAILY_ATTEMPT_CAP = int(os.getenv("DRIVER_DAILY_ATTEMPT_CAP", "200"))
        self.DRIVER_RETRY_DELAY_SECONDS = int(os.getenv("DRIVER_RETRY_DELAY_SECONDS", "1800"))
        self.RPA_LOCK_TTL_SECONDS = int(os.getenv("RPA_LOCK_TTL_SECONDS", "360"))
        self.RPA_SESSION_TTL_SECONDS = int(os.getenv("RPA_SESSION_TTL_SECONDS", "7200"))
        self.RPA_SESSION_REFRESH_SKEW_SECONDS = int(os.getenv("RPA_SESSION_REFRESH_SKEW_SECONDS", "300"))
        self.RPA_SCHEDULER_BATCH_SIZE = int(os.getenv("RPA_SCHEDULER_BATCH_SIZE", "200"))
        self.RPA_SCHEDULER_TENANT_SLICE = int(os.getenv("RPA_SCHEDULER_TENANT_SLICE", "20"))
        self.RPA_SCHEDULER_INTERVAL_SECONDS = int(os.getenv("RPA_SCHEDULER_INTERVAL_SECONDS", "3"))
        self.RPA_AUTH_QUEUE = os.getenv("RPA_AUTH_QUEUE", "rpa_auth").strip()
        self.RPA_SUBMIT_QUEUE = os.getenv("RPA_SUBMIT_QUEUE", "rpa_submit").strip()
        self.RPA_REFRESH_QUEUE = os.getenv("RPA_REFRESH_QUEUE", "rpa_refresh").strip()
        self.RPA_DEADLETTER_QUEUE = os.getenv("RPA_DEADLETTER_QUEUE", "rpa_deadletter").strip()
        self.RPA_SCHEDULER_QUEUE = os.getenv("RPA_SCHEDULER_QUEUE", "rpa_scheduler").strip()
        self.RPA_SUBMIT_ENDPOINT = os.getenv("RPA_SUBMIT_ENDPOINT", "").strip()
        self.RPA_AUTH_CONCURRENCY_PER_TENANT = int(os.getenv("RPA_AUTH_CONCURRENCY_PER_TENANT", "2"))
        self.RPA_SUBMIT_CONCURRENCY_PER_TENANT = int(os.getenv("RPA_SUBMIT_CONCURRENCY_PER_TENANT", "10"))
        self.RPA_PROXY_COOLDOWN_SECONDS = int(os.getenv("RPA_PROXY_COOLDOWN_SECONDS", "900"))

        # Excel upload settings
        self.MAX_UPLOAD_ROWS = int(os.getenv("MAX_UPLOAD_ROWS", "1000"))
        self.ALLOWED_UPLOAD_EXTENSIONS = os.getenv("ALLOWED_UPLOAD_EXTENSIONS", "xlsx,xls,csv").split(",")

        # Map bypass settings
        self.MAP_BYPASS_ENABLED = _to_bool(os.getenv("MAP_BYPASS_ENABLED", "True"), default=True)
        self.ORIGIN_TEXT_SELECTOR = os.getenv("ORIGIN_TEXT_SELECTOR", "input[name='Origin'], #OriginInput")
        self.DESTINATION_TEXT_SELECTOR = os.getenv(
            "DESTINATION_TEXT_SELECTOR", "input[name='Destination'], #DestinationInput"
        )

        # Submission Gate & OTP Adaptive Control
        # Non-negotiable Rule #1: ALLOW_LIVE_SUBMIT default is FALSE.
        self.ALLOW_LIVE_SUBMIT = _to_bool(os.getenv("ALLOW_LIVE_SUBMIT", "False"), default=False)
        self.PREDICTED_OTP_REQUIRED_START_HOUR = int(
            os.getenv("PREDICTED_OTP_REQUIRED_START_HOUR", os.getenv("PREDICTED_OTP_FREE_START_HOUR", "17"))
        )
        self.PREDICTED_OTP_REQUIRED_START_MINUTE = int(
            os.getenv("PREDICTED_OTP_REQUIRED_START_MINUTE", os.getenv("PREDICTED_OTP_FREE_START_MINUTE", "30"))
        )
        self.PREDICTED_OTP_REQUIRED_END_HOUR = int(
            os.getenv("PREDICTED_OTP_REQUIRED_END_HOUR", os.getenv("PREDICTED_OTP_FREE_END_HOUR", "8"))
        )
        self.PREDICTED_OTP_REQUIRED_END_MINUTE = int(
            os.getenv("PREDICTED_OTP_REQUIRED_END_MINUTE", os.getenv("PREDICTED_OTP_FREE_END_MINUTE", "0"))
        )
        # Compatibility aliases
        self.PREDICTED_OTP_FREE_START_HOUR = self.PREDICTED_OTP_REQUIRED_START_HOUR
        self.PREDICTED_OTP_FREE_START_MINUTE = self.PREDICTED_OTP_REQUIRED_START_MINUTE
        self.PREDICTED_OTP_FREE_END_HOUR = self.PREDICTED_OTP_REQUIRED_END_HOUR
        self.PREDICTED_OTP_FREE_END_MINUTE = self.PREDICTED_OTP_REQUIRED_END_MINUTE
        self.GATE_PROBE_INTERVAL_SECONDS = int(os.getenv("GATE_PROBE_INTERVAL_SECONDS", "300"))
        self.GATE_PROBE_LOCK_TTL_SECONDS = int(os.getenv("GATE_PROBE_LOCK_TTL_SECONDS", "60"))
        self.NIGHT_SUBMISSION_MAX_ATTEMPTS = int(os.getenv("NIGHT_SUBMISSION_MAX_ATTEMPTS", "3"))
        self.GATE_OBSERVATION_VALIDITY_SECONDS = int(os.getenv("GATE_OBSERVATION_VALIDITY_SECONDS", "1800"))
        self.GATE_BURST_DISPATCH_JITTER_MAX_SECONDS = float(os.getenv("GATE_BURST_DISPATCH_JITTER_MAX_SECONDS", "3.0"))

        # Clean IP Pool & Egress Proxy Configuration
        self.EGRESS_PROXY_MODE = _validated_choice(
            "EGRESS_PROXY_MODE",
            os.getenv("EGRESS_PROXY_MODE"),
            "worker_first",
            {"worker_first", "clean_pool_only", "hybrid"},
        )
        self.CLEAN_IP_PROBE_INTERVAL_SECONDS = int(os.getenv("CLEAN_IP_PROBE_INTERVAL_SECONDS", "300"))
        self.CLEAN_IP_MAX_POOL = int(os.getenv("CLEAN_IP_MAX_POOL", "50"))
        self.CLEAN_IP_MAX_CANDIDATES = int(os.getenv("CLEAN_IP_MAX_CANDIDATES", "1000"))
        self.CLEAN_IP_MAX_PROBE_WORKERS = int(os.getenv("CLEAN_IP_MAX_PROBE_WORKERS", "35"))
        self.CLEAN_IP_BLOCK_TTL_SECONDS = int(os.getenv("CLEAN_IP_BLOCK_TTL_SECONDS", "1800"))
        self.CLEAN_IP_REFRESH_LOCK_TTL_SECONDS = int(os.getenv("CLEAN_IP_REFRESH_LOCK_TTL_SECONDS", "900"))
        # Max age of the persisted pool before the SYNC selection path kicks a
        # background screening cycle (sync path must never serve a dead file forever).
        self.CLEAN_IP_POOL_MAX_AGE_SECONDS = int(os.getenv("CLEAN_IP_POOL_MAX_AGE_SECONDS", "1800"))
        self.IRAN_PROXY_TIMEOUT_SECONDS = float(os.getenv("IRAN_PROXY_TIMEOUT_SECONDS", "7.5"))
        self.CLEAN_IP_SOURCE_URL = os.getenv("CLEAN_IP_SOURCE_URL", "").strip()
        self.CLEAN_IP_SOURCE_FILE = os.getenv("CLEAN_IP_SOURCE_FILE", "").strip()

        # Neshan routing API for road distance/time (multi-route feature).
        # Optional: when NESHAN_API_KEY is unset, the distance service falls back
        # to the local haversine estimate. The endpoint is a fixed host, so there
        # is no user-controlled URL and no SSRF surface.
        self.NESHAN_API_KEY = os.getenv("NESHAN_API_KEY", "").strip()
        self.NESHAN_TIMEOUT_SECONDS = float(os.getenv("NESHAN_TIMEOUT_SECONDS", "3.0"))
        self.NESHAN_CACHE_TTL_SECONDS = int(os.getenv("NESHAN_CACHE_TTL_SECONDS", str(86400 * 7)))

    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


AUTO_GENERATED_SECRETS = _bootstrap_environment()
utcms_config = UTCMSConfig()
