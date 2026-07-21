"""
Simple worker-level proxy helper.

Chromium inside Docker containers CANNOT reach external sites directly (network
isolation). All Playwright browser sessions MUST route through the worker's
dedicated Squid proxy.

Each worker has its own Squid instance on a different egress IP:
  Worker 1 → Squid 1 (port 3128) → egress via 188.121.123.16
  Worker 2 → Squid 2 (port 3129) → egress via 95.38.233.90
  Worker 3 → Squid 3 (port 3130) → egress via 95.38.233.90

Design decision: We bypass proxy_rotator entirely here because:
1. Each worker already has a dedicated IP — no rotation needed per request.
2. proxy_rotator.get_next() has cooldown/geo-check overhead that can return
   None unexpectedly, leaving Chromium with no proxy → navigation timeout.
3. SSRF risk in proxy_rotator is documented in ISSUES.md and out of scope here.

We also resolve the proxy hostname to a numeric IP at module load time to work
around Chromium's internal DNS resolver sometimes failing to resolve Docker-
internal hostnames while Python's socket library succeeds.

Proxy addressing:
  Workers run in Docker bridge network (barpro_platform, 172.20.0.x).
  Squid runs with network_mode: host, so it binds on the HOST's loopback.
  The Docker bridge gateway (default 172.20.0.1, override via
  DOCKER_BRIDGE_GATEWAY) routes to the host — use this address.
  Do NOT use localhost/127.0.0.1 (refers to the container itself).
  Do NOT use host.docker.internal (unreachable from Linux bridge networks).
"""

import logging
import os
import socket
from functools import lru_cache
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)

_WORKER_ID_ENV = "WORKER_ID"

# Docker bridge gateway that routes to the host where Squid listens
# (network_mode: host). This MUST match the actual barpro_platform network
# gateway. compose/backend.yml, proxy_rotator.py and system.py all use
# 172.20.0.1 — keep them in sync. Override via DOCKER_BRIDGE_GATEWAY only if
# the real Docker subnet on the host differs from the convention.
_DOCKER_GATEWAY = os.environ.get("DOCKER_BRIDGE_GATEWAY", "172.20.0.1")


def _resolve_to_ip(url: str) -> str:
    """
    Replace the hostname in a URL with its resolved IPv4 address.

    This is required because Chromium's built-in DNS resolver inside Docker
    sometimes cannot resolve Docker-internal names (host.docker.internal) even
    though Python's socket.gethostbyname() can, leading to proxy connection
    failures and Playwright timeouts.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    # Force host.docker.internal to route to the Docker bridge gateway
    if hostname == "host.docker.internal":
        port = parsed.port
        netloc = f"{_DOCKER_GATEWAY}:{port}" if port else _DOCKER_GATEWAY
        return urlunparse(parsed._replace(netloc=netloc))

    try:
        ip = socket.gethostbyname(hostname)
        # If IP resolves to a public server IP, force to the bridge gateway
        if ip in ("95.38.233.90", "188.121.123.16"):
            ip = _DOCKER_GATEWAY

        if ip != hostname:
            # Rebuild netloc with numeric IP
            port = parsed.port
            netloc = f"{ip}:{port}" if port else ip
            resolved = urlunparse(parsed._replace(netloc=netloc))
            logger.debug(f"worker_proxy: resolved {hostname} → {ip} in proxy URL")
            return resolved
    except OSError:
        logger.debug(f"worker_proxy: could not resolve {hostname}, keeping original URL")
    return url


@lru_cache(maxsize=1)
def get_worker_proxy_url() -> str | None:
    """
    Return the Squid proxy URL for this Celery worker, with hostname resolved
    to a numeric IP. Result is cached at module level (per worker process).

    Priority order:
    1. WORKER_{WORKER_ID}_PROXY  (e.g. WORKER_1_PROXY=http://172.20.0.1:3128)
    2. RPA_PROXIES               (first entry in comma-separated list)
    3. None                      (no proxy configured)

    If the configured proxy is unreachable (e.g. during local development outside Docker),
    falls back to None for a direct network connection.
    """
    worker_id = os.environ.get(_WORKER_ID_ENV, "1")
    url = os.environ.get(f"WORKER_{worker_id}_PROXY") or (
        os.environ.get("RPA_PROXIES", "").split(",")[0].strip() or None
    )
    if not url:
        logger.warning("worker_proxy: no proxy URL configured — running direct connection")
        return None

    resolved = _resolve_to_ip(url)

    # Health check: verify the proxy socket is reachable
    parsed = urlparse(resolved)
    if parsed.hostname and parsed.port:
        try:
            with socket.create_connection((parsed.hostname, parsed.port), timeout=1.0):
                logger.info(f"worker_proxy: using active proxy {resolved} (worker_id={worker_id})")
                return resolved
        except (OSError, socket.timeout):
            logger.warning(
                f"worker_proxy: configured proxy {resolved} is unreachable; falling back to direct connection"
            )
            return None

    return resolved


def get_playwright_proxy() -> dict | None:
    """
    Return a Playwright-compatible proxy dict, or None if no proxy is configured.

    Usage:
        proxy_dict = get_playwright_proxy()
        async with managed_browser_session(auth_state_path=..., proxy_dict=proxy_dict) as ...:
            ...
    """
    url = get_worker_proxy_url()
    return {"server": url} if url else None


async def check_proxy_health(
    proxy_url: str, target_url: str = "https://barname.utcms.ir/Barname/Account/Login"
) -> bool:
    """
    Verify that Squid can make a real request to the UTCMS login page.
    """
    import httpx

    try:
        async with httpx.AsyncClient(proxy=proxy_url, timeout=5.0, follow_redirects=True) as client:
            response = await client.get(target_url)
        return 200 <= response.status_code < 500
    except Exception as exc:
        logger.warning(
            "worker_proxy_health_check_failed",
            extra={"extra_fields": {"proxy": proxy_url, "target": target_url, "error": str(exc)}},
        )
        return False
