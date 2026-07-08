"""Tests for configuration validation."""

import os
from unittest.mock import patch

from app.core.startup_validation import validate_environment


class TestConfigValidation:
    """Test configuration validation."""

    def test_validate_with_all_required_vars(self):
        """Test validation passes with all required variables."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": "test-jwt-secret-32-chars-long-enough",
                "DRIVER_ENCRYPTION_KEY": "test-encryption-key-32-chars-long",
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
                "DRIVER_ENCRYPTION_KEY": "test-encryption-key",
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
                "JWT_SECRET": "test-jwt-secret",
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
                "JWT_SECRET": "test-jwt-secret-32-chars-long-enough",
                "DRIVER_ENCRYPTION_KEY": "test-encryption-key-32-chars-long",
                "REDIS_URL": "redis://localhost:6379",
                "NODE_ENV": "production",
            },
            clear=True,
        ):
            is_valid, errors = validate_environment()
            assert is_valid is False
            assert any("DATABASE_URL" in error for error in errors)

    def test_validate_missing_db_url_in_development(self):
        """Test validation passes but warns without DATABASE_URL in development."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": "test-jwt-secret-32-chars-long-enough",
                "DRIVER_ENCRYPTION_KEY": "test-encryption-key-32-chars-long",
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
                "JWT_SECRET": "test-jwt-secret-32-chars-long-enough",
                "DRIVER_ENCRYPTION_KEY": "test-encryption-key-32-chars-long",
                "DATABASE_URL": "sqlite+aiosqlite:///./bot_stats.db",
                "REDIS_URL": "redis://localhost:6379",
                "NODE_ENV": "production",
            },
            clear=True,
        ):
            is_valid, errors = validate_environment()
            assert is_valid is False
            assert any("DATABASE_URL" in error for error in errors)
