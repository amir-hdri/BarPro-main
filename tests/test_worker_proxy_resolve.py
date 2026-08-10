"""
Unit tests for worker_proxy._resolve_to_ip (X1 / FIX-D).

The proxy-URL resolver used to rewrite ANY public IP to the Docker bridge
gateway (172.20.0.1). That silently redirected a REMOTE worker node's Squid
(e.g. http://<NODE2_IP>:3128) onto the central server's Squid, collapsing the
one-IP-per-worker architecture and breaking the circuit breaker's index→IP
mapping. The fix restricts the rewrite to this server's OWN public IP
(_LOCAL_PUBLIC_IPS / CENTRAL_IP).
"""

from unittest.mock import patch

from app.automation.worker_proxy import _resolve_to_ip


def test_remote_public_ip_is_not_rewritten():
    """A public IP that is NOT this server's must be preserved."""
    with (
        patch("app.automation.worker_proxy._LOCAL_PUBLIC_IPS", {"8.8.8.8"}),
        patch("socket.gethostbyname", return_value="1.1.1.1"),
    ):
        url = "http://1.1.1.1:3128"
        assert _resolve_to_ip(url) == url


def test_own_public_ip_is_rewritten_to_gateway():
    """This server's own public IP is routed through the Docker bridge gateway."""
    with (
        patch("app.automation.worker_proxy._LOCAL_PUBLIC_IPS", {"8.8.8.8"}),
        patch("socket.gethostbyname", return_value="8.8.8.8"),
    ):
        assert _resolve_to_ip("http://8.8.8.8:3128") == "http://172.20.0.1:3128"


def test_private_ip_is_kept():
    """Private / loopback addresses are never rewritten."""
    with patch("socket.gethostbyname", return_value="172.20.0.1"):
        assert _resolve_to_ip("http://172.20.0.1:3128") == "http://172.20.0.1:3128"


def test_loopback_is_kept():
    with patch("socket.gethostbyname", return_value="127.0.0.1"):
        assert _resolve_to_ip("http://127.0.0.1:3128") == "http://127.0.0.1:3128"
