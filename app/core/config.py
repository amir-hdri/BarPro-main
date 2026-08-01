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


class UTCMSConfig:
    def __init__(self) -> None:
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
        self.CAPTCHA_MODE = os.getenv("CAPTCHA_MODE", "provider_only").strip().lower()
        self.CAPTCHA_PROVIDER = os.getenv("CAPTCHA_PROVIDER", "auto").strip().lower()
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
        if self.CAPTCHA_PROVIDER not in _valid_captcha_providers:
            raise ValueError(
                f"Invalid CAPTCHA_PROVIDER '{self.CAPTCHA_PROVIDER}'. "
                f"Must be one of: {', '.join(sorted(_valid_captcha_providers))}"
            )
        self.TWOCAPTCHA_API_KEY = os.getenv("TWOCAPTCHA_API_KEY", "").strip()
        self.CAPTCHA_TIMEOUT_SECONDS = int(os.getenv("CAPTCHA_TIMEOUT_SECONDS", "120"))
        self.CAPTCHA_POLL_SECONDS = float(os.getenv("CAPTCHA_POLL_SECONDS", "5"))
        self.CAPTCHA_MAX_RETRIES = int(os.getenv("CAPTCHA_MAX_RETRIES", "2"))
        self.CAPTCHA_LOCAL_FALLBACK_ENABLED = _to_bool(
            os.getenv("CAPTCHA_LOCAL_FALLBACK_ENABLED", "True"),
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
        self.CAPTCHA_VALUE_MIN_LENGTH = int(os.getenv("CAPTCHA_VALUE_MIN_LENGTH", "1"))
        self.CAPTCHA_VALUE_MAX_LENGTH = int(os.getenv("CAPTCHA_VALUE_MAX_LENGTH", "6"))
        self.CAPTCHA_ADAPTIVE_ENABLED = _to_bool(os.getenv("CAPTCHA_ADAPTIVE_ENABLED", "True"), default=True)
        self.CAPTCHA_ADAPTIVE_WINDOW = int(os.getenv("CAPTCHA_ADAPTIVE_WINDOW", "60"))
        self.CAPTCHA_ADAPTIVE_MIN_SAMPLES = int(os.getenv("CAPTCHA_ADAPTIVE_MIN_SAMPLES", "10"))
        self.CAPTCHA_ADAPTIVE_HIGH_FAILURE_RATE = float(os.getenv("CAPTCHA_ADAPTIVE_HIGH_FAILURE_RATE", "0.35"))
        self.CAPTCHA_ADAPTIVE_LOW_FAILURE_RATE = float(os.getenv("CAPTCHA_ADAPTIVE_LOW_FAILURE_RATE", "0.10"))
        self.CAPTCHA_ADAPTIVE_MAX_ATTEMPTS = int(os.getenv("CAPTCHA_ADAPTIVE_MAX_ATTEMPTS", "5"))
        self.CAPTCHA_ADAPTIVE_MAX_DELAY_SECONDS = float(os.getenv("CAPTCHA_ADAPTIVE_MAX_DELAY_SECONDS", "2.5"))
        self.CAPTCHA_DEBUG_SAVE_IMAGES = _to_bool(os.getenv("CAPTCHA_DEBUG_SAVE_IMAGES", "True"), default=True)
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

        self.ALLOW_LIVE_SUBMIT = _to_bool(os.getenv("ALLOW_LIVE_SUBMIT", "False"), default=False)
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
        # self.POSTGRES_DSN = os.getenv("POSTGRES_DSN", "").strip()  # unused — kept as reference

        self.QUEUE_ENABLED = _to_bool(os.getenv("QUEUE_ENABLED", "True"), default=True)
        self.QUEUE_INLINE_FALLBACK = _to_bool(os.getenv("QUEUE_INLINE_FALLBACK", "False"), default=False)
        self.QUEUE_IDEMPOTENCY_HEADER = os.getenv("QUEUE_IDEMPOTENCY_HEADER", "X-Idempotency-Key").strip()
        self.QUEUE_READYZ_LIVE_CHECK = _to_bool(os.getenv("QUEUE_READYZ_LIVE_CHECK", "False"), default=False)

        self.REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0").strip()
        self.REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "").strip()
        self.CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", self.REDIS_URL).strip()
        self.CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", self.REDIS_URL).strip()
        self.CELERY_TASK_QUEUE = os.getenv("CELERY_TASK_QUEUE", "waybill_tasks").strip()
        self.CELERY_DLQ_QUEUE = os.getenv("CELERY_DLQ_QUEUE", "waybill_dlq").strip()
        self.CELERY_TASK_SOFT_TIME_LIMIT = int(os.getenv("CELERY_TASK_SOFT_TIME_LIMIT", "300"))
        self.CELERY_TASK_TIME_LIMIT = int(os.getenv("CELERY_TASK_TIME_LIMIT", "360"))
        self.CELERY_MAX_RETRIES = int(os.getenv("CELERY_MAX_RETRIES", "5"))
        self.CELERY_RETRY_BASE_SECONDS = float(os.getenv("CELERY_RETRY_BASE_SECONDS", "2.0"))
        self.CELERY_RETRY_JITTER_SECONDS = float(os.getenv("CELERY_RETRY_JITTER_SECONDS", "1.5"))
        self.CELERY_WORKER_PREFETCH_MULTIPLIER = int(os.getenv("CELERY_WORKER_PREFETCH_MULTIPLIER", "1"))
        self.WORKER_STALL_TIMEOUT_SECONDS = int(os.getenv("WORKER_STALL_TIMEOUT_SECONDS", "90"))

        self.BROWSER_POOL_ENABLED = _to_bool(os.getenv("BROWSER_POOL_ENABLED", "False"), default=False)
        self.BROWSER_POOL_SIZE = int(os.getenv("BROWSER_POOL_SIZE", "8"))

        self.CIRCUIT_BREAKER_ENABLED = _to_bool(os.getenv("CIRCUIT_BREAKER_ENABLED", "True"), default=True)
        self.CIRCUIT_BREAKER_FAILURE_THRESHOLD = int(os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5"))
        self.CIRCUIT_BREAKER_RECOVERY_SECONDS = int(os.getenv("CIRCUIT_BREAKER_RECOVERY_SECONDS", "30"))
        self.CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS = int(os.getenv("CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS", "2"))

        self.FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000").strip()
        self.FRONTEND_URLS = os.getenv("FRONTEND_URLS", "").strip()
        self.FRONTEND_URL_ALT = os.getenv("FRONTEND_URL_ALT", "").strip()
        self.AUTH_COOKIE_SECURE = _to_bool(
            os.getenv("AUTH_COOKIE_SECURE"),
            default=self.FRONTEND_URL.lower().startswith("https://"),
        )

        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.LATENCY_SAMPLE_MAX = int(os.getenv("LATENCY_SAMPLE_MAX", "2000"))
        self.FAILURE_ARTIFACTS_DIR = os.getenv("FAILURE_ARTIFACTS_DIR", "output/failure_artifacts").strip()
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
        self.WORKER_STALL_TIMEOUT_SECONDS = float(os.getenv("WORKER_STALL_TIMEOUT_SECONDS", "45"))
        self.CELERY_DEFAULT_PRIORITY = int(os.getenv("CELERY_DEFAULT_PRIORITY", "5"))
        self.CELERY_MIN_PRIORITY = int(os.getenv("CELERY_MIN_PRIORITY", "0"))
        self.CELERY_MAX_PRIORITY = int(os.getenv("CELERY_MAX_PRIORITY", "9"))

        # Multi-tenant settings
        self.MULTITENANT_ENABLED = _to_bool(os.getenv("MULTITENANT_ENABLED", "False"), default=False)
        self.DEPRECATE_OLD_EXECUTION_PATH = _to_bool(os.getenv("DEPRECATE_OLD_EXECUTION_PATH", "True"), default=True)

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
        self.RPA_SCHEDULER_INTERVAL_SECONDS = int(os.getenv("RPA_SCHEDULER_INTERVAL_SECONDS", "15"))
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


AUTO_GENERATED_SECRETS = _bootstrap_environment()
utcms_config = UTCMSConfig()
