"""Startup validation for critical configuration."""

import logging
import os

logger = logging.getLogger(__name__)


def validate_environment() -> tuple[bool, list[str]]:
    """
    Validate critical environment variables are set.

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    warnings = []
    is_prod = (
        os.getenv("NODE_ENV", "").strip().lower() == "production"
        or os.getenv("ENVIRONMENT", "").strip().lower() == "production"
    )

    # Critical secrets
    jwt_secret = os.getenv("JWT_SECRET", "")
    if not jwt_secret or jwt_secret in [
        "change-me-jwt-secret-required",
        "super-secret-jwt-key-change-in-production",
        "dev-only-insecure-jwt-secret-change-immediately",
    ]:
        errors.append(
            'JWT_SECRET must be set. Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"'
        )
    # CRITICAL_RULES §1: fail fast on short signing keys, not just empty/deny-listed ones.
    elif len(jwt_secret) < 32:
        errors.append(
            "JWT_SECRET must be at least 32 characters long. "
            'Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"'
        )

    driver_key = os.getenv("DRIVER_ENCRYPTION_KEY", "")
    if not driver_key or driver_key in [
        "change-me-encryption-key-required",
        "default-encryption-key-change-in-production",
    ]:
        errors.append(
            'DRIVER_ENCRYPTION_KEY must be set. Generate with: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )

    # OTP Forwarder Webhook Secret
    otp_secret = os.getenv("OTP_WEBHOOK_SECRET", "").strip()
    if not otp_secret:
        if is_prod:
            errors.append(
                "OTP_WEBHOOK_SECRET must be set in production for the SMS OTP intake webhook. "
                'Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"'
            )
        else:
            warnings.append("OTP_WEBHOOK_SECRET is not set; OTP webhook will fail-closed with 503 until configured")
    elif len(otp_secret) < 16:
        errors.append("OTP_WEBHOOK_SECRET must be at least 16 characters long.")

    # Database configuration
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url or "sqlite" in db_url.lower():
        if is_prod:
            errors.append(
                "DATABASE_URL is not set or using SQLite in production. This is a critical security and scalability risk."
            )
        elif not db_url:
            warnings.append("DATABASE_URL not set, using default SQLite")

    # Redis configuration
    redis_url = os.getenv("REDIS_URL", "")
    if not redis_url:
        warnings.append("REDIS_URL not set, some features may not work")

    # Multi-tenant mode stores UTCMS credentials per driver, so global UTCMS_* env vars
    # are optional and should not be treated as a startup requirement.
    utcms_user = os.getenv("UTCMS_USERNAME", "")
    utcms_pass = os.getenv("UTCMS_PASSWORD", "")
    if utcms_user or utcms_pass:
        warnings.append(
            "Global UTCMS_USERNAME/UTCMS_PASSWORD are legacy-only; prefer per-driver credentials in the database"
        )

    master_pass = os.getenv("MASTER_ADMIN_PASSWORD", "")

    insecure_passwords = ["master_bar", "admin", "Amir123", "password", "123456", "admin123"]
    if master_pass in insecure_passwords:
        if is_prod:
            errors.append(
                "MASTER_ADMIN_PASSWORD is set to an insecure default value. This is a critical security risk. Change it before running in production."
            )
        else:
            warnings.append("MASTER_ADMIN_PASSWORD is using default credentials; change it before production")

    # Production settings
    allow_live = os.getenv("ALLOW_LIVE_SUBMIT", "false").lower()
    if allow_live == "true":
        logger.warning("⚠️  ALLOW_LIVE_SUBMIT is enabled - submissions will be sent to production UTCMS")

    # F7: API_AUTH_MODE=off (also "none"/"disabled") silently de-authenticates the
    # legacy surface in app/core/security.py. Documented behavior, no behavior
    # change here — but it must be loud at startup, never a silent default.
    auth_mode = os.getenv("API_AUTH_MODE", "api_key_or_jwt").strip().lower()
    if auth_mode in ("off", "none", "disabled"):
        logger.warning(
            "🔓 SECURITY: API_AUTH_MODE=%r disables authentication on the legacy API surface — "
            "protected endpoints will accept unauthenticated requests. Never use this in production.",
            auth_mode,
        )

    # Log results
    if errors:
        logger.error("❌ Configuration validation failed:")
        for error in errors:
            logger.error(f"  - {error}")

    if warnings:
        logger.warning("⚠️  Configuration warnings:")
        for warning in warnings:
            logger.warning(f"  - {warning}")

    if not errors and not warnings:
        logger.info("✅ Configuration validation passed")

    return len(errors) == 0, errors
