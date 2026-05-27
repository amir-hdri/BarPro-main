import json
import logging
import urllib.request
from typing import Any

from app.core.config import utcms_config

logger = logging.getLogger(__name__)


class AlertManager:
    def emit(self, severity: str, title: str, payload: dict[str, Any]) -> None:
        message = {
            "severity": severity,
            "title": title,
            "payload": payload,
        }
        logger.warning("platform_alert", extra={"extra_fields": message})
        webhook = getattr(utcms_config, "ALERT_WEBHOOK_URL", "").strip()
        if not webhook:
            return
        try:
            req = urllib.request.Request(
                webhook,
                data=json.dumps(message).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=2):
                return
        except Exception as exc:
            logger.warning("alert_webhook_failed", extra={"extra_fields": {"error": str(exc), "severity": severity}})


alert_manager = AlertManager()

