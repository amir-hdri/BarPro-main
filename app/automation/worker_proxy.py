"""
Simple worker-level proxy helper.

Chromium inside Docker containers CANNOT reach external sites directly (network
isolation). All Playwright browser sessions MUST route through the worker's
dedicated Squid proxy.

Each worker has its own Squid instance on a different egress IP:
  Worker 1 → Squid 1 (port 3128) → egress via <CENTRAL_IP>
  Worker 2 → Squid 2 (port 3129) → egress via <SECONDARY_EGRESS_IP>
  Worker 3 → Squid 3 (port 3130) → egress via <SECONDARY_EGRESS_IP>

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
import time
from typing import Any
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)

_WORKER_ID_ENV = "WORKER_ID"
# Docker bridge gateway that routes to the host where Squid listens
# (network_mode: host). This MUST match the actual barpro_platform network
# gateway. compose/backend.yml, proxy_rotator.py and system.py all use
# 172.20.0.1 — keep them in sync. Override via DOCKER_BRIDGE_GATEWAY only if
# the real Docker subnet on the host differs from the convention.
_DOCKER_GATEWAY = os.environ.get("DOCKER_BRIDGE_GATEWAY", "172.20.0.1")


class ProxyUnavailableError(RuntimeError):
    """Raised when a required Squid proxy is unconfigured/unreachable.

    In production the RPA worker MUST fail closed: a browser session without
    the worker's dedicated proxy would either time out waiting UTCMS or leak
    the central server egress IP — both are silent failures. Callers should
    treat this as a transient infrastructure error and move the job to
    WAITING_RETRY instead of proceeding direct.
    """


def _proxy_fail_closed() -> bool:
    """Decide whether a missing/unreachable proxy must abort execution.

    Fail-closed is the default when ENVIRONMENT=production and can be
    forced with PROXY_FAIL_CLOSED=true. Development remains permissive
    (proxy optional) so local bots and unit tests keep working.
    """
    env = (os.environ.get("ENVIRONMENT") or "").lower()
    if env == "production":
        return os.environ.get("PROXY_FAIL_CLOSED", "true").lower() == "true"
    return os.environ.get("PROXY_FAIL_CLOSED", "false").lower() == "true"


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
        # Do NOT leak production server IPs into proxy resolution.
        # Any resolved public IP is routed through the Docker bridge gateway.
        # This check prevents accidentally using hardcoded egress IPs in proxy URLs.
        # If the proxy resolves to a non-local address, force it through the gateway.
        try:
            import ipaddress
            parsed_ip = ipaddress.ip_address(ip)
            if not parsed_ip.is_private and not parsed_ip.is_loopback:
                ip = _DOCKER_GATEWAY
        except ValueError:
            pass

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


_cached_proxy_url: str | None = None
_cached_proxy_timestamp: float = 0.0
_PROXY_CACHE_TTL_SUCCESS: float = 60.0  # Cache valid proxy for 60s
_PROXY_CACHE_TTL_FAILURE: float = 5.0   # Retry failed proxy lookup after 5s


def clear_proxy_cache() -> None:
    """Clear cached worker proxy URL to force a fresh health check on next call."""
    global _cached_proxy_url, _cached_proxy_timestamp
    _cached_proxy_url = None
    _cached_proxy_timestamp = 0.0


def get_worker_proxy_url() -> str | None:
    """
    Return the Squid proxy URL for this Celery worker, with hostname resolved
    to a numeric IP. Result is cached per worker process with short TTL.

    Priority order:
    1. WORKER_{WORKER_ID}_PROXY  (e.g. WORKER_1_PROXY=http://172.20.0.1:3128)
    2. RPA_PROXIES               (first entry in comma-separated list)
    3. None                      (no proxy configured — development only)

    Fail-closed: in production (see ``_proxy_fail_closed``) a missing or
    unreachable proxy raises ``ProxyUnavailableError`` instead of falling back
    to a direct connection. The caller is expected to classify it as a
    transient infrastructure error and requeue the job.
    """
    global _cached_proxy_url, _cached_proxy_timestamp

    now = time.time()
    ttl = _PROXY_CACHE_TTL_SUCCESS if _cached_proxy_url else _PROXY_CACHE_TTL_FAILURE
    if _cached_proxy_timestamp > 0 and (now - _cached_proxy_timestamp) < ttl:
        return _cached_proxy_url

    worker_id = os.environ.get(_WORKER_ID_ENV, "1")
    url = os.environ.get(f"WORKER_{worker_id}_PROXY") or (
        os.environ.get("RPA_PROXIES", "").split(",")[0].strip() or None
    )
    if not url:
        if _proxy_fail_closed():
            _cached_proxy_url = None
            _cached_proxy_timestamp = now
            raise ProxyUnavailableError(
                f"worker_proxy: no proxy URL configured for worker_id={worker_id}; "
                "fail-closed — refusing to run without dedicated egress proxy"
            )
        logger.warning("worker_proxy: no proxy URL configured — running direct connection")
        _cached_proxy_url = None
        _cached_proxy_timestamp = now
        return None

    resolved = _resolve_to_ip(url)

    # Health check: verify the proxy socket is reachable
    parsed = urlparse(resolved)
    if parsed.hostname and parsed.port:
        try:
            with socket.create_connection((parsed.hostname, parsed.port), timeout=1.0):
                logger.info(f"worker_proxy: using active proxy {resolved} (worker_id={worker_id})")
                _cached_proxy_url = resolved
                _cached_proxy_timestamp = now
                return resolved
        except (OSError, TimeoutError):
            if _proxy_fail_closed():
                _cached_proxy_url = None
                _cached_proxy_timestamp = now
                raise ProxyUnavailableError(
                    f"worker_proxy: configured proxy {resolved} is unreachable; "
                    "fail-closed (refusing to fall back to direct connection)"
                ) from None
            logger.warning(
                f"worker_proxy: configured proxy {resolved} is unreachable; falling back to direct connection"
            )
            _cached_proxy_url = None
            _cached_proxy_timestamp = now
            return None

    _cached_proxy_url = resolved
    _cached_proxy_timestamp = now
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


async def increment_worker_failures(worker_id: str) -> int:
    """Increment the sequential failure counter for this worker in Redis (1 minute window)."""
    from app.core.redis import redis_manager
    try:
        client = await redis_manager.get()
        if client:
            key = f"worker_retry_attempts:{worker_id}"
            val = await client.incr(key)
            if val == 1:
                await client.expire(key, 60)
            return val
    except Exception as e:
        logger.warning(f"Failed to increment worker failure counter in Redis: {e}")
    return 0


async def transition_worker_to_draining(worker_id: str) -> None:
    """Transition the worker registry status to 'draining' in the database."""
    from datetime import UTC, datetime

    from sqlmodel import select

    from app.core.database import async_session_factory
    from app.models_rpa import WorkerRegistry

    async with async_session_factory() as session:
        try:
            stmt = select(WorkerRegistry).where(WorkerRegistry.worker_id == worker_id)
            res = await session.exec(stmt)
            worker = res.first()
            if worker and worker.status != "draining":
                worker.status = "draining"
                worker.updated_at = datetime.now(UTC).replace(tzinfo=None)
                session.add(worker)
                await session.commit()
                logger.warning(f"Worker {worker_id} has been transitioned to draining due to excessive failures.")
        except Exception as e:
            logger.error(f"Failed to transition worker {worker_id} to draining: {e}", exc_info=True)
            await session.rollback()


async def is_worker_draining(worker_id: str) -> bool:
    """Check if the worker registry status is marked as 'draining'."""
    from sqlmodel import select

    from app.core.database import async_session_factory
    from app.models_rpa import WorkerRegistry

    async with async_session_factory() as session:
        try:
            stmt = select(WorkerRegistry).where(WorkerRegistry.worker_id == worker_id)
            res = await session.exec(stmt)
            worker = res.first()
            return worker is not None and worker.status == "draining"
        except Exception:
            return False


def drain_worker_consumers(task: Any) -> None:
    """Stop consuming from all waybill and reconciliation queues on this worker process.

    Note: any IN_PROGRESS jobs on this worker should be transitioned to WAITING_RETRY
    with error_category='worker_drained' after calling this, so reconciliation does
    not later mark them as orphaned.
    """
    from app.core.config import utcms_config

    worker_name = task.request.hostname
    logger.warning(f"Draining worker {worker_name} consumers...")
    queues = [
        utcms_config.CELERY_WAYBILL_SUBMIT_QUEUE,
        utcms_config.CELERY_WAYBILL_AUTH_QUEUE,
        utcms_config.CELERY_FUEL_INQUIRY_QUEUE,
        utcms_config.CELERY_RECOVERY_QUEUE,
        utcms_config.CELERY_RECONCILIATION_QUEUE,
        utcms_config.CELERY_WAYBILL_TASKS_QUEUE,
        utcms_config.CELERY_RECONCILIATION_TASKS_QUEUE,
    ]
    for q in queues:
        try:
            task.app.control.cancel_consumer(q, destination=[worker_name])
        except Exception as exc:
            logger.debug(f"Failed to cancel consumer for queue {q} on {worker_name}: {exc}")
