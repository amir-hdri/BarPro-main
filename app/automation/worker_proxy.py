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

import asyncio
import logging
import os
import socket
import time
from typing import Any
from urllib.parse import urlparse, urlunparse

from app.core.config import utcms_config

logger = logging.getLogger(__name__)

_WORKER_ID_ENV = "WORKER_ID"
# Docker bridge gateway that routes to the host where Squid listens
# (network_mode: host). This MUST match the actual barpro_platform network
# gateway. compose/backend.yml, proxy_rotator.py and system.py all use
# 172.20.0.1 — keep them in sync. Override via DOCKER_BRIDGE_GATEWAY only if
# the real Docker subnet on the host differs from the convention.
_DOCKER_GATEWAY = os.environ.get("DOCKER_BRIDGE_GATEWAY", "172.20.0.1")

# Public IPs that belong to THIS server. Only these are rewritten to the Docker
# bridge gateway in ``_resolve_to_ip``. Any other public IP (e.g. a remote
# worker node's Squid) is kept untouched — otherwise the "one IP per worker"
# architecture silently collapses (X1) and every worker would egress via the
# central server. Populate from LOCAL_PUBLIC_IPS (comma-separated) or CENTRAL_IP.
_LOCAL_PUBLIC_IPS: set[str] = {
    x.strip() for x in os.environ.get("LOCAL_PUBLIC_IPS", os.environ.get("CENTRAL_IP", "")).split(",") if x.strip()
}


def _safe_proxy_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.hostname:
        return url
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    netloc = f"{host}:{parsed.port}" if parsed.port else host
    return urlunparse(parsed._replace(netloc=netloc))


def _replace_proxy_hostname(url: str, hostname: str) -> str:
    parsed = urlparse(url)
    userinfo = parsed.netloc.rsplit("@", 1)[0] if "@" in parsed.netloc else ""
    host = f"[{hostname}]" if ":" in hostname else hostname
    host_port = f"{host}:{parsed.port}" if parsed.port else host
    netloc = f"{userinfo}@{host_port}" if userinfo else host_port
    return urlunparse(parsed._replace(netloc=netloc))


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
        return _replace_proxy_hostname(url, _DOCKER_GATEWAY)

    try:
        ip = socket.gethostbyname(hostname)
        # Do NOT leak production server IPs into proxy resolution.
        # Any resolved public IP is routed through the Docker bridge gateway.
        # This check prevents accidentally using hardcoded egress IPs in proxy URLs.
        # If the proxy resolves to a non-local address, force it through the gateway.
        try:
            import ipaddress

            parsed_ip = ipaddress.ip_address(ip)
            # Only rewrite THIS server's own public IP to the bridge gateway
            # (so a hardcoded egress IP pointing back at us routes through
            # Squid on the host instead of leaking direct). Any public IP that
            # is NOT ours — e.g. a remote worker node's Squid — is preserved so
            # the one-IP-per-worker architecture keeps working (X1).
            if not parsed_ip.is_private and not parsed_ip.is_loopback and ip in _LOCAL_PUBLIC_IPS:
                ip = _DOCKER_GATEWAY
                logger.info(f"worker_proxy: routed own public IP {hostname} through gateway {ip}")
        except ValueError:
            pass

        if ip != hostname:
            # Rebuild netloc with numeric IP
            resolved = _replace_proxy_hostname(url, ip)
            logger.debug(f"worker_proxy: resolved {hostname} → {ip} in proxy URL")
            return resolved
    except OSError:
        logger.debug(f"worker_proxy: could not resolve {hostname}, keeping original URL")
    return url


_cached_proxy_url: str | None = None
_cached_proxy_source: str | None = None
_cached_proxy_timestamp: float = 0.0
# A selected egress stays assigned until the next clean-pool screening cycle.
# This keeps consecutive waybills on the same verified IP while still allowing
# the configured refresh cadence to replace stale or blocked candidates.
_PROXY_CACHE_TTL_SUCCESS: float = 60.0  # Legacy fallback; runtime TTL is config-driven
_PROXY_CACHE_TTL_FAILURE: float = 5.0  # Retry failed proxy lookup after 5s


def _proxy_cache_ttl_success() -> float:
    """Return the configured egress assignment lifetime.

    Clean-IP screening and Beat refresh use ``CLEAN_IP_PROBE_INTERVAL_SECONDS``.
    Reusing that value here means a worker does not rotate its proxy merely
    because another waybill started, while ``mark_blocked`` can still force an
    immediate reassignment through ``invalidate_worker_proxy_cache``.
    """
    try:
        refresh_interval = float(getattr(utcms_config, "CLEAN_IP_PROBE_INTERVAL_SECONDS", 180))
    except (TypeError, ValueError):
        refresh_interval = 180.0
    return max(1.0, refresh_interval)


def invalidate_worker_proxy_cache() -> None:
    """Drop ONLY this process's cached proxy choice (cheap, targeted).

    Called by CleanIPPoolManager.mark_blocked so a just-blocked clean proxy can
    never be served again from the refresh-window success cache. Unlike
    clear_proxy_cache it does NOT wipe the shared pool cache — blocking one
    address must not force a full pool re-read.
    """
    global _cached_proxy_source, _cached_proxy_url, _cached_proxy_timestamp
    _cached_proxy_url = None
    _cached_proxy_source = None
    _cached_proxy_timestamp = 0.0


def clear_proxy_cache() -> None:
    """Clear cached worker proxy URL to force a fresh health check on next call."""
    global _cached_proxy_source, _cached_proxy_url, _cached_proxy_timestamp
    _cached_proxy_url = None
    _cached_proxy_source = None
    _cached_proxy_timestamp = 0.0
    try:
        from app.automation.clean_ip_pool import clean_ip_pool

        clean_ip_pool.clear_local_cache()
    except Exception:
        pass


def get_best_egress_proxy() -> str | None:
    """
    Return the best egress proxy URL based on the configured EGRESS_PROXY_MODE:
    - 'worker_first' (default): Try dedicated worker Squid. If unreachable or blocked,
      fail over to the Clean IP Pool (verified Iranian proxies).
    - 'clean_pool_only': Always use verified proxies from the Clean IP Pool.
    - 'hybrid': Alternates between local worker Squid and the Clean IP Pool.

    Fail-closed: in production (see ``_proxy_fail_closed``), if both the worker proxy
    and the clean IP pool are unavailable, raises ``ProxyUnavailableError``. One
    exception: a worker Squid that is UP but whose egress index is marked blocked is
    still used (degraded) when the pool is empty, so marking an egress blocked can
    never take waybill processing offline.
    """
    global _cached_proxy_source, _cached_proxy_url, _cached_proxy_timestamp

    now = time.time()
    ttl = _proxy_cache_ttl_success() if _cached_proxy_url else _PROXY_CACHE_TTL_FAILURE
    if _cached_proxy_timestamp > 0 and (now - _cached_proxy_timestamp) < ttl:
        return _cached_proxy_url

    mode = utcms_config.EGRESS_PROXY_MODE
    worker_id = os.environ.get(_WORKER_ID_ENV, "1")
    worker_ip_index = os.environ.get("WORKER_IP_INDEX", worker_id)

    from app.automation.clean_ip_pool import clean_ip_pool

    # Helper to check if current worker IP index is marked blocked in Redis
    def _is_worker_index_blocked() -> bool:
        if not worker_ip_index:
            return False
        try:
            from app.core.circuit_breaker import _get_redis_sync

            r = _get_redis_sync()
            return bool(r.exists(f"utcms:circuit_breaker:blocked:{worker_ip_index}"))
        except Exception:
            return False

    # 1. Mode: clean_pool_only
    if mode == "clean_pool_only":
        clean_url = clean_ip_pool.get_clean_ip_sync()
        if clean_url:
            resolved = _resolve_to_ip(clean_url)
            logger.info("worker_proxy: using Clean IP Pool proxy %s (mode=clean_pool_only)", _safe_proxy_url(resolved))
            _cached_proxy_url = resolved
            _cached_proxy_source = "clean_pool"
            _cached_proxy_timestamp = now
            return resolved
        if _proxy_fail_closed():
            _cached_proxy_url = None
            _cached_proxy_source = None
            _cached_proxy_timestamp = now
            raise ProxyUnavailableError("worker_proxy: clean_pool_only requested but no clean Iranian proxy available")
        _cached_proxy_url = None
        _cached_proxy_source = None
        _cached_proxy_timestamp = now
        return None

    # 2. Worker Squid candidate
    url = os.environ.get(f"WORKER_{worker_id}_PROXY") or (
        os.environ.get("RPA_PROXIES", "").split(",")[0].strip() or None
    )

    worker_squid_reachable = False
    worker_index_blocked = _is_worker_index_blocked()
    worker_squid_healthy = False
    resolved_worker_squid = None

    # Reachability is probed even when the index is blocked, because a blocked
    # Squid is still the degraded last resort below. Note what this TCP connect
    # does NOT prove: Squid is local and always answers, and it happily reports
    # ``TCP_TUNNEL/200`` while UTCMS is refusing the TLS handshake behind it. So
    # "reachable" means "the proxy process is up", never "this egress IP is
    # accepted" -- the latter can only come from the blocked-index signal that
    # request-level failures set.
    if url:
        resolved_worker_squid = _resolve_to_ip(url)
        parsed = urlparse(resolved_worker_squid)
        if parsed.hostname and parsed.port:
            try:
                with socket.create_connection((parsed.hostname, parsed.port), timeout=1.0):
                    worker_squid_reachable = True
            except (OSError, TimeoutError):
                logger.debug("worker_proxy: worker proxy %s unreachable", _safe_proxy_url(resolved_worker_squid))
    worker_squid_healthy = worker_squid_reachable and not worker_index_blocked

    # Mode: hybrid
    if mode == "hybrid":
        # Toggle based on timestamp
        use_clean = int(now) % 2 == 0
        if use_clean:
            clean_url = clean_ip_pool.get_clean_ip_sync()
            if clean_url:
                resolved = _resolve_to_ip(clean_url)
                logger.info("worker_proxy: using Clean IP Pool proxy %s (mode=hybrid)", _safe_proxy_url(resolved))
                _cached_proxy_url = resolved
                _cached_proxy_source = "clean_pool"
                _cached_proxy_timestamp = now
                return resolved

    # Default Mode: worker_first
    if worker_squid_healthy and resolved_worker_squid:
        logger.info(
            "worker_proxy: using active worker proxy %s (worker_id=%s)",
            _safe_proxy_url(resolved_worker_squid),
            worker_id,
        )
        _cached_proxy_url = resolved_worker_squid
        _cached_proxy_source = "worker_squid"
        _cached_proxy_timestamp = now
        return resolved_worker_squid

    # Fallback to Clean IP Pool
    clean_url = clean_ip_pool.get_clean_ip_sync()
    if clean_url:
        resolved_clean = _resolve_to_ip(clean_url)
        logger.warning(
            f"worker_proxy: worker Squid unavailable/blocked (worker_id={worker_id}), "
            f"falling back to Clean IP Pool proxy {_safe_proxy_url(resolved_clean)}"
        )
        _cached_proxy_url = resolved_clean
        _cached_proxy_source = "clean_pool"
        _cached_proxy_timestamp = now
        return resolved_clean

    # Last resort: the worker Squid is up but its egress index was marked blocked
    # and the pool had nothing to move to. Use it anyway, degraded.
    #
    # This branch is what makes marking an egress blocked SAFE to do at all.
    # Without it, "blocked" plus an empty pool reaches ``_proxy_fail_closed()``
    # below and raises, i.e. an IP the WAF is throttling would take waybill
    # processing fully OFFLINE instead of degrading it -- strictly worse than
    # continuing to try the throttled address, which does still succeed between
    # throttle windows. Failover remains preferred; this only fires when there is
    # genuinely nowhere else to go.
    if worker_squid_reachable and resolved_worker_squid:
        logger.warning(
            "worker_proxy: egress index %s is marked blocked but the Clean IP Pool is empty; "
            "continuing on the blocked worker Squid %s (degraded, NOT failing closed)",
            worker_ip_index,
            _safe_proxy_url(resolved_worker_squid),
        )
        _cached_proxy_url = resolved_worker_squid
        _cached_proxy_source = "worker_squid_degraded"
        _cached_proxy_timestamp = now
        return resolved_worker_squid

    if _proxy_fail_closed():
        _cached_proxy_url = None
        _cached_proxy_source = None
        _cached_proxy_timestamp = now
        raise ProxyUnavailableError(
            f"worker_proxy: no usable proxy found for worker_id={worker_id} "
            "(worker Squid unreachable/blocked and Clean IP Pool is empty); fail-closed"
        )

    logger.warning("worker_proxy: no proxy available — running direct connection (development fail-open)")
    _cached_proxy_url = None
    _cached_proxy_source = None
    _cached_proxy_timestamp = now
    return None


def get_worker_proxy_url() -> str | None:
    """
    Return the active proxy URL for this worker (Squid or Clean IP Pool fallback).
    Result is cached per worker process with short TTL.
    """
    return get_best_egress_proxy()


def get_current_egress_context() -> tuple[str | None, str | None]:
    """Return the cached egress source and URL for failure attribution."""
    return _cached_proxy_source, _cached_proxy_url


def get_playwright_proxy() -> dict | None:
    """
    Return a Playwright-compatible proxy dict, or None if no proxy is configured.

    Usage:
        proxy_dict = get_playwright_proxy()
        async with managed_browser_session(auth_state_path=..., proxy_dict=proxy_dict) as ...:
            ...
    """
    url = get_worker_proxy_url()
    if not url:
        return None
    parsed = urlparse(url)
    proxy = {"server": _safe_proxy_url(url)}
    if parsed.username:
        proxy["username"] = parsed.username
    if parsed.password:
        proxy["password"] = parsed.password
    return proxy


async def check_proxy_health(proxy_url: str, target_url: str | None = None) -> bool:
    """Verify the proxy tunnel without coupling health checks to the login route.

    The login URL is session-sensitive and may redirect or time out while the
    proxy tunnel itself is healthy.  Use the stable UTCMS root by default;
    callers that need an authenticated/session-specific target can still pass
    ``target_url`` explicitly.
    """
    parsed = urlparse(proxy_url)
    if not parsed.hostname or not parsed.port:
        return False

    from curl_cffi import requests as cc_requests  # type: ignore[import-not-found]

    targets_to_try = [target_url] if target_url else ["https://barname.utcms.ir", "https://api.ipify.org"]
    last_error = ""
    for attempt in range(1, 4):
        for tgt in targets_to_try:
            session = None
            try:
                session = cc_requests.Session(
                    impersonate="chrome120",
                    proxies={"http": proxy_url, "https": proxy_url},
                    verify=True,
                )
                response = await asyncio.to_thread(session.get, tgt, timeout=10.0)
                squid_error = response.headers.get("X-Squid-Error") or response.headers.get("x-squid-error")
                if not squid_error and response.status_code in (200, 301, 302, 403):
                    return True
                last_error = f"X-Squid-Error={squid_error}; status={response.status_code}"
            except Exception as exc:
                last_error = str(exc)
            finally:
                if session is not None:
                    try:
                        await asyncio.to_thread(session.close)
                    except Exception as exc:
                        logger.debug("worker_proxy_health_session_close_failed", extra={"extra_fields": {"error": str(exc)[:200]}})
        if attempt < 3:
            await asyncio.sleep(1.5)

    logger.warning(
        "worker_proxy_health_check_failed",
        extra={
            "extra_fields": {
                "proxy": _safe_proxy_url(proxy_url),
                "target": effective_target,
                "attempts": 3,
                "error": last_error[:240],
            }
        },
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

    # Cancel both the base and this worker's suffixed partition for every routed
    # queue family (a worker drains ITS OWN partitions, so the exact set depends
    # on WORKER_IP_INDEX). cancel_consumer on a queue this worker does not
    # consume is harmless. NOTE: cancel_consumer is a broadcast handled in the
    # main worker process — with --pool=solo it only runs after the current task
    # finishes, so this is best-effort; the real guard is is_worker_draining() at
    # the top of each task.
    idx = os.environ.get("WORKER_IP_INDEX", "").strip()
    bases = [
        utcms_config.CELERY_WAYBILL_TASKS_QUEUE,
        utcms_config.CELERY_RECONCILIATION_TASKS_QUEUE,
        utcms_config.RPA_AUTH_QUEUE,
        utcms_config.RPA_SUBMIT_QUEUE,
        "scheduled_tasks",
    ]
    queues: set[str] = {utcms_config.CELERY_FUEL_INQUIRY_QUEUE, *bases}
    if idx.isdigit():
        queues.update(f"{b}_{idx}" for b in bases)
    for q in queues:
        try:
            task.app.control.cancel_consumer(q, destination=[worker_name])
        except Exception as exc:
            logger.debug(f"Failed to cancel consumer for queue {q} on {worker_name}: {exc}")
