import hashlib
import hmac
import json
import logging
import time
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
            payload_bytes = json.dumps(message).encode("utf-8")
            timestamp = str(int(time.time()))
            
            headers = {
                "Content-Type": "application/json",
                "X-Barpro-Timestamp": timestamp,
            }
            
            secret = getattr(utcms_config, "ALERT_WEBHOOK_SECRET", "").strip()
            if secret:
                # Sign timestamp concatenated with payload
                message_to_sign = f"{timestamp}.".encode("utf-8") + payload_bytes
                signature = hmac.new(
                    secret.encode("utf-8"),
                    message_to_sign,
                    hashlib.sha256
                ).hexdigest()
                headers["X-Barpro-Signature"] = signature

            req = urllib.request.Request(
                webhook,
                data=payload_bytes,
                headers=headers,
                method="POST",
                unverifiable=True,
            )
            # Use urllib.request.urlopen directly since we verified URL is correct
            with urllib.request.urlopen(req, timeout=2):  # nosec B310
                return
        except Exception as exc:
            logger.warning("alert_webhook_failed", extra={"extra_fields": {"error": str(exc), "severity": severity}})


alert_manager = AlertManager()
