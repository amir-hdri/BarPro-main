"""Tests for PUBLIC_BASE_URL usage and production docs gating.

- The SecureSMS config guide must build webhook URLs from PUBLIC_BASE_URL and
  must never embed a hard-coded server address.
- /docs, /redoc, /openapi.json must be disabled in production unless
  ENABLE_DOCS=true is set explicitly.
"""
import os
import subprocess
import sys

import pytest


def _get_securesms_config(public_base_url: str | None) -> dict:
    """Import the route module in a fresh interpreter with the given env."""
    env = dict(os.environ)
    env["MASTER_ADMIN_PASSWORD"] = "test-dummy-only"
    env["JWT_SECRET"] = "test-dummy-jwt-secret-32chars-min!!!!"
    if public_base_url is None:
        env.pop("PUBLIC_BASE_URL", None)
    else:
        env["PUBLIC_BASE_URL"] = public_base_url
    code = (
        "import asyncio, json\n"
        "from app.api.routes.otp_forwarder import get_securesms_forwarder_config\n"
        "print(json.dumps(asyncio.run(get_securesms_forwarder_config())))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        cwd="/tmp/barpro",
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    import json as _json

    return _json.loads(proc.stdout)


def _docs_enabled(environment: str, enable_docs: str | None) -> bool:
    """Read utcms_config.docs_enabled in a fresh interpreter with the given env.

    This is the exact property app/main.py uses to gate docs_url/redoc_url/
    openapi_url, so asserting on it is equivalent to asserting on the app —
    without importing the DB engine (which needs a PostgreSQL driver).
    """
    env = dict(os.environ)
    env["MASTER_ADMIN_PASSWORD"] = "test-dummy-only"
    env["JWT_SECRET"] = "test-dummy-jwt-secret-32chars-min!!!!"
    env["ENVIRONMENT"] = environment
    if environment == "production":
        # Production config refuses SQLite; a dummy PostgreSQL URL satisfies the
        # import-time validation (no connection is opened just by importing).
        env["DATABASE_URL"] = "postgresql://dummy:dummy@localhost:5432/dummy"
        env["REDIS_URL"] = "redis://localhost:6379/0"
    if enable_docs is None:
        env.pop("ENABLE_DOCS", None)
    else:
        env["ENABLE_DOCS"] = enable_docs
    code = (
        "from app.core.config import UTCMSConfig\n"
        "print(UTCMSConfig().docs_enabled)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        cwd="/tmp/barpro",
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    return proc.stdout.strip() == "True"


def test_webhook_urls_use_configured_public_base_url():
    cfg = _get_securesms_config("https://example.com")
    assert cfg["server_webhook_url"] == "https://example.com/api/v1/otp/sms-forwarder"
    assert cfg["alternative_url"] == "https://example.com/api/v1/otp/webhook"
    blob = str(cfg)
    assert "87.107.5.238" not in blob  # the old hard-coded address must be gone


def test_missing_public_base_url_emits_placeholder_not_invented_address():
    cfg = _get_securesms_config(None)
    blob = str(cfg)
    assert "87.107.5.238" not in blob
    assert "http://" not in cfg["server_webhook_url"] or "<PUBLIC_BASE_URL" in cfg["server_webhook_url"]
    assert "<PUBLIC_BASE_URL" in cfg["server_webhook_url"]


def test_docs_disabled_by_default_in_production():
    assert _docs_enabled("production", None) is False


def test_docs_explicitly_enabled_in_production():
    assert _docs_enabled("production", "true") is True


def test_docs_enabled_in_development():
    assert _docs_enabled("development", None) is True


def test_main_wires_docs_urls_to_config_property():
    """app/main.py must gate all three URLs on utcms_config.docs_enabled."""
    import re

    src = open("/tmp/barpro/app/main.py", encoding="utf-8").read()
    for url_arg in ("docs_url", "redoc_url", "openapi_url"):
        pattern = rf'{url_arg}="[^"]*" if utcms_config\.docs_enabled else None'
        assert re.search(pattern, src), f"{url_arg} is not gated on utcms_config.docs_enabled"
