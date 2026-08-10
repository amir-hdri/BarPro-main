import hashlib
import hmac
import json
from unittest import mock

from app.core.alerts import alert_manager
from app.core.config import utcms_config


def test_alert_manager_emit_no_webhook():
    # Test that emit returns immediately when ALERT_WEBHOOK_URL is not set
    with mock.patch.object(utcms_config, "ALERT_WEBHOOK_URL", ""):
        with mock.patch("urllib.request.urlopen") as mock_urlopen:
            alert_manager.emit("high", "Test Alert", {"key": "val"})
            mock_urlopen.assert_not_called()


def test_alert_manager_emit_with_webhook_no_secret():
    # Test alert emission with webhook URL set but no secret
    with (
        mock.patch.object(utcms_config, "ALERT_WEBHOOK_URL", "http://example.com/webhook"),
        mock.patch.object(utcms_config, "ALERT_WEBHOOK_SECRET", ""),
        mock.patch("urllib.request.urlopen") as mock_urlopen,
    ):

        alert_manager.emit("high", "Test Alert", {"key": "val"})

        assert mock_urlopen.call_count == 1
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://example.com/webhook"

        headers_lower = {k.lower(): v for k, v in req.headers.items()}
        assert headers_lower.get("content-type") == "application/json"
        assert "x-barpro-timestamp" in headers_lower
        assert "x-barpro-signature" not in headers_lower

        # Verify body
        body = json.loads(req.data.decode("utf-8"))
        assert body["severity"] == "high"
        assert body["title"] == "Test Alert"
        assert body["payload"] == {"key": "val"}


def test_alert_manager_emit_with_webhook_and_secret():
    # Test signature calculation
    secret = "my_super_secret"
    with (
        mock.patch.object(utcms_config, "ALERT_WEBHOOK_URL", "http://example.com/webhook"),
        mock.patch.object(utcms_config, "ALERT_WEBHOOK_SECRET", secret),
        mock.patch("urllib.request.urlopen") as mock_urlopen,
    ):

        alert_manager.emit("critical", "Auth Failure", {"error": "wrong pass"})

        assert mock_urlopen.call_count == 1
        req = mock_urlopen.call_args[0][0]

        # Verify signature headers
        headers_lower = {k.lower(): v for k, v in req.headers.items()}
        assert "x-barpro-timestamp" in headers_lower
        assert "x-barpro-signature" in headers_lower

        timestamp = headers_lower["x-barpro-timestamp"]
        signature = headers_lower["x-barpro-signature"]

        # Verify signature math
        expected_msg = f"{timestamp}.".encode() + req.data
        expected_sig = hmac.new(secret.encode("utf-8"), expected_msg, hashlib.sha256).hexdigest()

        assert signature == expected_sig
