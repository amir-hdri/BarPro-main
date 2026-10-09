"""Tests for configuration validation."""

import logging
import os
from unittest.mock import patch

import pytest

from app.core.startup_validation import validate_environment

# CRITICAL_RULES §1: mock secrets must be at least 32 chars (never real secrets).
JWT_32 = "test-jwt-secret-32-chars-long-enough"
ENC_32 = "test-encryption-key-32-chars-long"


class TestConfigValidation:
    """Test configuration validation."""

    def test_validate_with_all_required_vars(self):
        """Test validation passes with all required variables."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": JWT_32,
                "DRIVER_ENCRYPTION_KEY": ENC_32,
                "DATABASE_URL": "postgresql://localhost/test",
                "REDIS_URL": "redis://localhost:6379",
            },
        ):
            is_valid, errors = validate_environment()
            assert is_valid is True
            assert len(errors) == 0

    def test_validate_missing_jwt_secret(self):
        """Test validation fails without JWT_SECRET."""
        with patch.dict(
            os.environ,
            {
                "DRIVER_ENCRYPTION_KEY": ENC_32,
            },
            clear=True,
        ):
            is_valid, errors = validate_environment()
            assert is_valid is False
            assert any("JWT_SECRET" in error for error in errors)

    def test_validate_missing_encryption_key(self):
        """Test validation fails without DRIVER_ENCRYPTION_KEY."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": JWT_32,
            },
            clear=True,
        ):
            is_valid, errors = validate_environment()
            assert is_valid is False
            assert any("DRIVER_ENCRYPTION_KEY" in error for error in errors)

    def test_validate_weak_default_secrets(self):
        """Test validation fails with weak default secrets."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": "change-me-jwt-secret-required",
                "DRIVER_ENCRYPTION_KEY": "change-me-encryption-key-required",
            },
        ):
            is_valid, errors = validate_environment()
            assert is_valid is False
            assert len(errors) >= 2

    def test_validate_missing_db_url_in_production(self):
        """Test validation fails without DATABASE_URL in production."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": JWT_32,
                "DRIVER_ENCRYPTION_KEY": ENC_32,
                "REDIS_URL": "redis://localhost:6379",
                "NODE_ENV": "production",
            },
            clear=True,
        ):
            is_valid, errors = validate_environment()
            assert is_valid is False
            assert any("DATABASE_URL" in error for error in errors)

    def test_validate_short_jwt_secret_rejected(self):
        """CRITICAL_RULES §1: a short-but-non-empty JWT_SECRET fails startup validation."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": "mock-short-key",  # 14 chars — obvious mock, below the 32-char floor
                "DRIVER_ENCRYPTION_KEY": ENC_32,
                "REDIS_URL": "redis://localhost:6379",
            },
            clear=True,
        ):
            is_valid, errors = validate_environment()
            assert is_valid is False
            assert any("JWT_SECRET" in error and "32" in error for error in errors)

    def test_validate_exactly_32_char_jwt_secret_accepted(self):
        """Boundary: exactly 32 chars passes the length gate."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": "x" * 32,
                "DRIVER_ENCRYPTION_KEY": ENC_32,
                "REDIS_URL": "redis://localhost:6379",
            },
            clear=True,
        ):
            is_valid, errors = validate_environment()
            assert is_valid is True
            assert len(errors) == 0

    def test_api_auth_mode_off_logs_security_warning(self, caplog):
        """F7: API_AUTH_MODE=off logs a loud security warning — no exception, no behavior change."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": JWT_32,
                "DRIVER_ENCRYPTION_KEY": ENC_32,
                "REDIS_URL": "redis://localhost:6379",
                "API_AUTH_MODE": "off",
            },
            clear=True,
        ):
            with caplog.at_level(logging.WARNING, logger="app.core.startup_validation"):
                is_valid, errors = validate_environment()
            assert is_valid is True
            assert any(
                "API_AUTH_MODE" in record.message and "off" in record.message
                for record in caplog.records
                if record.levelno >= logging.WARNING
            )

    def test_api_auth_mode_default_does_not_warn(self, caplog):
        """F7: the safe default (api_key_or_jwt) emits no de-authentication warning."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": JWT_32,
                "DRIVER_ENCRYPTION_KEY": ENC_32,
                "REDIS_URL": "redis://localhost:6379",
            },
            clear=True,
        ):
            with caplog.at_level(logging.WARNING, logger="app.core.startup_validation"):
                is_valid, errors = validate_environment()
            assert is_valid is True
            assert not any("API_AUTH_MODE" in record.message for record in caplog.records)

    def test_validate_missing_db_url_in_development(self):
        """Test validation passes but warns without DATABASE_URL in development."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": JWT_32,
                "DRIVER_ENCRYPTION_KEY": ENC_32,
                "REDIS_URL": "redis://localhost:6379",
            },
            clear=True,
        ):
            is_valid, errors = validate_environment()
            assert is_valid is True
            assert len(errors) == 0

    def test_validate_sqlite_db_url_in_production(self):
        """Test validation fails with SQLite DATABASE_URL in production."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": JWT_32,
                "DRIVER_ENCRYPTION_KEY": ENC_32,
                "DATABASE_URL": "sqlite+aiosqlite:///./bot_stats.db",
                "REDIS_URL": "redis://localhost:6379",
                "NODE_ENV": "production",
            },
            clear=True,
        ):
            is_valid, errors = validate_environment()
            assert is_valid is False
            assert any("DATABASE_URL" in error for error in errors)

    @pytest.mark.parametrize("env_var", ["NODE_ENV", "ENVIRONMENT"])
    def test_otp_webhook_secret_required_in_production(self, env_var):
        """Test validation fails when OTP_WEBHOOK_SECRET is missing in production."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": JWT_32,
                "DRIVER_ENCRYPTION_KEY": ENC_32,
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
                "REDIS_URL": "redis://localhost:6379",
                env_var: "production",
                "OTP_WEBHOOK_SECRET": "",
            },
            clear=True,
        ):
            is_valid, errors = validate_environment()
            assert is_valid is False
            assert any("OTP_WEBHOOK_SECRET" in error for error in errors)

    @pytest.mark.parametrize("env_var", ["NODE_ENV", "ENVIRONMENT"])
    def test_otp_webhook_secret_valid_in_production(self, env_var):
        """Test validation passes when OTP_WEBHOOK_SECRET is set in production."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": JWT_32,
                "DRIVER_ENCRYPTION_KEY": ENC_32,
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
                "REDIS_URL": "redis://localhost:6379",
                env_var: "production",
                "OTP_WEBHOOK_SECRET": "a" * 32,
            },
            clear=True,
        ):
            is_valid, errors = validate_environment()
            assert is_valid is True
            assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_lifespan_fails_closed_on_invalid_environment(self):
        """Test that FastAPI lifespan raises RuntimeError when startup validation fails."""
        from app.main import app, lifespan

        with patch("app.core.startup_validation.validate_environment", return_value=(False, ["Mock invalid config"])):
            with pytest.raises(RuntimeError, match="Critical startup validation failed: Mock invalid config"):
                async with lifespan(app):
                    pass
