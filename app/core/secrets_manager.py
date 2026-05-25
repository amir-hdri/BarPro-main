"""Secrets management with auto-generation for secure defaults."""

import hashlib
import logging
import secrets
import string
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def generate_secure_secret(length: int = 64) -> str:
    """Generate a cryptographically secure random secret."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_api_key(prefix: str = "utcms") -> str:
    """Generate a secure API key with prefix."""
    random_part = secrets.token_hex(32)
    return f"{prefix}_{random_part}"


def generate_postgres_password(length: int = 32) -> str:
    """Generate a secure PostgreSQL password without special characters for URI compatibility."""
    alphabet = string.ascii_letters + string.digits
    password = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice(string.digits),
    ]
    password += [secrets.choice(alphabet) for _ in range(length - 4)]
    secrets.SystemRandom().shuffle(password)
    return "".join(password)


def hash_secret(secret: str) -> str:
    """Hash a secret for safe storage/display."""
    return hashlib.sha256(secret.encode()).hexdigest()


def mask_secret(secret: str, visible_chars: int = 8) -> str:
    """Mask a secret for logging/display."""
    if not secret or len(secret) <= visible_chars:
        return "*" * len(secret)
    return secret[:visible_chars] + "*" * (len(secret) - visible_chars)


class SecretsManager:
    """Manage application secrets with auto-generation capabilities."""

    def __init__(self, env_file: str = ".env"):
        self.env_file = Path(env_file)
        self._secrets: Dict[str, str] = {}

    def check_and_generate_secrets(self) -> Dict[str, str]:
        """Check for required secrets and generate if missing."""
        generated = {}
        
        # Read current env
        current_env = self._read_env_file()
        
        # Check API_KEY
        api_key = current_env.get("API_KEY", "").strip()
        if not api_key or api_key.startswith("change-me"):
            new_api_key = generate_api_key()
            generated["API_KEY"] = new_api_key
            logger.info(
                "api_key_auto_generated",
                extra={
                    "extra_fields": {
                        "masked": mask_secret(new_api_key),
                        "hash": hash_secret(new_api_key)[:16],
                    }
                },
            )

        # Check JWT_SECRET
        jwt_secret = current_env.get("JWT_SECRET", "").strip()
        if not jwt_secret or jwt_secret.startswith("change-me"):
            new_jwt_secret = generate_secure_secret(64)
            generated["JWT_SECRET"] = new_jwt_secret
            logger.info(
                "jwt_secret_auto_generated",
                extra={
                    "extra_fields": {
                        "masked": mask_secret(new_jwt_secret),
                        "hash": hash_secret(new_jwt_secret)[:16],
                    }
                },
            )

        # Check DRIVER_ENCRYPTION_KEY
        driver_encryption_key = current_env.get("DRIVER_ENCRYPTION_KEY", "").strip()
        if not driver_encryption_key or driver_encryption_key.startswith("change-me"):
            new_driver_key = generate_secure_secret(64)
            generated["DRIVER_ENCRYPTION_KEY"] = new_driver_key
            logger.info(
                "driver_encryption_key_auto_generated",
                extra={
                    "extra_fields": {
                        "masked": mask_secret(new_driver_key),
                        "hash": hash_secret(new_driver_key)[:16],
                    }
                },
            )

        # Check POSTGRES_PASSWORD
        postgres_password = current_env.get("POSTGRES_PASSWORD", "").strip()
        if not postgres_password or postgres_password.startswith("change-me"):
            new_password = generate_postgres_password()
            generated["POSTGRES_PASSWORD"] = new_password
            logger.info(
                "postgres_password_auto_generated",
                extra={
                    "extra_fields": {
                        "masked": mask_secret(new_password),
                        "hash": hash_secret(new_password)[:16],
                    }
                },
            )

        # Update DATABASE_URL and POSTGRES_DSN if password changed
        if "POSTGRES_PASSWORD" in generated:
            db_url = current_env.get("DATABASE_URL", "")
            if "change-me-postgres-password" in db_url:
                new_password = generated["POSTGRES_PASSWORD"]
                db_url = db_url.replace("change-me-postgres-password", new_password)
                generated["DATABASE_URL"] = db_url
                
                dsn = current_env.get("POSTGRES_DSN", "")
                if "change-me-postgres-password" in dsn:
                    dsn = dsn.replace("change-me-postgres-password", new_password)
                    generated["POSTGRES_DSN"] = dsn

        self._secrets = generated
        return generated

    def apply_secrets_to_env(self, generated: Optional[Dict[str, str]] = None) -> bool:
        """Apply generated secrets to .env file."""
        secrets_to_apply = generated or self._secrets
        if not secrets_to_apply:
            return False

        try:
            # Read current content
            if self.env_file.exists():
                content = self.env_file.read_text(encoding="utf-8")
            else:
                content = ""

            lines = content.splitlines()
            updated_lines = []
            updated_keys = set()

            # Update existing lines
            for line in lines:
                stripped = line.strip()
                if "=" in stripped and not stripped.startswith("#"):
                    key = stripped.split("=", 1)[0].strip()
                    if key in secrets_to_apply:
                        new_value = secrets_to_apply[key]
                        updated_lines.append(f"{key}={new_value}")
                        updated_keys.add(key)
                        continue
                updated_lines.append(line)

            # Add new secrets not in file
            for key, value in secrets_to_apply.items():
                if key not in updated_keys:
                    updated_lines.append(f"{key}={value}")

            # Write back
            self.env_file.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
            
            logger.info(
                "secrets_applied_to_env",
                extra={
                    "extra_fields": {
                        "file": str(self.env_file),
                        "secrets_count": len(secrets_to_apply),
                    }
                },
            )
            return True

        except Exception as exc:
            logger.error(
                "secrets_apply_failed",
                extra={"extra_fields": {"error": str(exc), "file": str(self.env_file)}},
            )
            return False

    def _read_env_file(self) -> Dict[str, str]:
        """Read and parse .env file."""
        env = {}
        if not self.env_file.exists():
            return env

        for line in self.env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()

        return env

    def get_security_report(self) -> Dict[str, any]:
        """Generate a security report."""
        current_env = self._read_env_file()
        
        return {
            "api_key_configured": bool(
                current_env.get("API_KEY", "").strip()
                and not current_env.get("API_KEY", "").startswith("change-me")
            ),
            "jwt_secret_configured": bool(
                current_env.get("JWT_SECRET", "").strip()
                and not current_env.get("JWT_SECRET", "").startswith("change-me")
            ),
            "driver_encryption_key_configured": bool(
                current_env.get("DRIVER_ENCRYPTION_KEY", "").strip()
                and not current_env.get("DRIVER_ENCRYPTION_KEY", "").startswith("change-me")
            ),
            "postgres_password_secure": bool(
                current_env.get("POSTGRES_PASSWORD", "").strip()
                and not current_env.get("POSTGRES_PASSWORD", "").startswith("change-me")
            ),
            "auth_mode": current_env.get("API_AUTH_MODE", "off"),
            "allow_live_submit": current_env.get("ALLOW_LIVE_SUBMIT", "false"),
        }


# Singleton instance
secrets_manager = SecretsManager()


def initialize_secrets(auto_generate: bool = True) -> Dict[str, str]:
    """Initialize secrets with optional auto-generation."""
    if auto_generate:
        generated = secrets_manager.check_and_generate_secrets()
        if generated:
            secrets_manager.apply_secrets_to_env(generated)
            return generated
    return {}
