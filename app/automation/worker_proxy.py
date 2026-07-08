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
internal hostnames (host.docker.internal) while Python's socket library succeeds.
"""

import logging
import os
import socket
from functools import lru_cache
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)

_WORKER_ID_ENV = "WORKER_ID"


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
    try:
        ip = socket.gethostbyname(hostname)
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
    to a numeric IP.  Result is cached at module level (per worker process).

    Priority order:
    1. WORKER_{WORKER_ID}_PROXY  (e.g. WORKER_1_PROXY=http://host.docker.internal:3128)
    2. RPA_PROXIES               (first entry in comma-separated list)
    3. None                      (no proxy configured — navigation will likely fail)
    """
    worker_id = os.environ.get(_WORKER_ID_ENV, "1")
    url = os.environ.get(f"WORKER_{worker_id}_PROXY") or (
        os.environ.get("RPA_PROXIES", "").split(",")[0].strip() or None
    )
    if not url:
        logger.warning("worker_proxy: no proxy URL configured — Chromium may not reach external sites")
        return None

    resolved = _resolve_to_ip(url)
    logger.info(f"worker_proxy: using proxy {resolved} (worker_id={worker_id})")
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
