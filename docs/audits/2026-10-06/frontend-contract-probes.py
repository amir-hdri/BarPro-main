"""Read-only local audit probes; synthetic settings and no real HTTP/Redis I/O.

Run from repository root with .venv/bin/python.
Assertions describe the observed defects, not desired behavior.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
os.environ.update({
    "ENVIRONMENT": "test",
    "DATABASE_URL": "sqlite+aiosqlite:////tmp/barpro-frontend-audit-unused.db",
    "REDIS_URL": "redis://127.0.0.1:1/0",
    "ALLOW_LIVE_SUBMIT": "false",
    "JWT_SECRET": "audit-synthetic-secret-key-32bytes-padding",
})

from fastapi import HTTPException
from starlette.requests import Request
from app.api.routes import otp_forwarder as mod


async def main():
    request = Request({"type": "http", "method": "POST", "path": "/api/v1/otp/sms-forwarder/09120000000", "headers": [], "query_string": b""})
    for secret, expected in (("synthetic-webhook-secret", 401), ("", 503)):
        with patch.object(mod.utcms_config, "OTP_WEBHOOK_SECRET", secret):
            try:
                mod._require_webhook_auth(request)
            except HTTPException as error:
                assert error.status_code == expected
                print(json.dumps({"case": "new_ui_guide_without_auth", "secret_configured": bool(secret), "http_status": error.status_code, "detail": error.detail}))
            else:
                raise AssertionError("Expected fail-closed webhook rejection")

    with patch.object(mod.utcms_config, "OTP_WEBHOOK_SECRET", ""), patch.object(mod.redis_manager, "get", AsyncMock(return_value=AsyncMock(ping=AsyncMock(return_value=True)))):
        result = await mod.health_otp_service(request)
        assert result["status"] == "healthy"
        print(json.dumps({"case": "health_with_missing_secret", "secret_configured": False, "health_status": result["status"], "redis_connected": result["redis_connected"], "post_intake_status": 503}))

    source = (ROOT / "apps/web/src/app/history/page.tsx").read_text()
    assert "دریافت خودکار از فورواردر پیامک فعال است" in source
    assert not any(endpoint in source for endpoint in ("/otp/health", "/otp/ping", "/otp/securesms-config"))
    print(json.dumps({"case": "history_auto_intake_status", "active_label_is_unconditional_jsx": True, "health_configuration_endpoints_used": False}))


asyncio.run(main())
