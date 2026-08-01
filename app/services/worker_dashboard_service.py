"""
Worker Dashboard Service
========================
Fetches the live worker list from the ``worker_registry`` table so that
API endpoints (e.g. ``/proxies/health``) are driven by the database rather
than a hardcoded ``(1, 2, 3)`` loop.

Each active Worker registers itself on startup (via Celery signals in
``worker_lifecycle.py``) and deregisters on shutdown.  This service just
queries that authoritative registry.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

from sqlmodel import select

from app.core.database import async_session_factory
from app.models_rpa import WorkerRegistry

logger = logging.getLogger(__name__)


@dataclass
class WorkerProxyInfo:
    """Lightweight DTO: worker identity + its Squid proxy URL."""

    worker_id: str
    hostname: str
    capabilities: list[str]
    capacity: int
    status: str
    proxy_url: str
    display_name: str


def _derive_proxy_url(worker_id: str, hostname: str) -> str:
    """
    Derive the Squid proxy URL for a worker.

    Priority order:
    1. ``WORKER_<WORKER_ID>_PROXY`` env var (explicit override, e.g. for remote workers)
    2. ``WORKER_<N>_PROXY`` env var where N is a numeric suffix of WORKER_ID
       (e.g. WORKER_ID="worker_2" → ``WORKER_2_PROXY``)
    3. Default to localhost on port ``3128 + N`` (local deployment fallback)
    """
    # 1. Explicit env var keyed on full WORKER_ID (underscores → upper)
    env_key_full = f"WORKER_{worker_id.upper()}_PROXY"
    val = os.getenv(env_key_full)
    if val:
        return val

    # 2. Numeric suffix: worker_1 → WORKER_1_PROXY → port 3129, etc.
    suffix = ""
    for part in worker_id.replace("-", "_").split("_"):
        if part.isdigit():
            suffix = part
            break

    if suffix:
        env_key_num = f"WORKER_{suffix}_PROXY"
        val = os.getenv(env_key_num)
        if val:
            return val
        # Default port: squid_1 → 3128, squid_2 → 3129, squid_3 → 3130, …
        port = 3127 + int(suffix)
        return f"http://172.20.0.1:{port}"

    # 3. Absolute fallback: use 3128
    return "http://172.20.0.1:3128"


async def get_active_worker_proxies() -> list[WorkerProxyInfo]:
    """
    Return all workers with status='active' from the worker_registry table,
    enriched with their derived Squid proxy URL.

    Falls back to an empty list (never raises) so callers can always add the
    RPA_PROXIES env-var entries on top.
    """
    try:
        async with async_session_factory() as session:
            stmt = select(WorkerRegistry).where(WorkerRegistry.status == "active")
            result = await session.exec(stmt)
            workers = result.all()

        out: list[WorkerProxyInfo] = []
        for w in workers:
            caps: list[str] = []
            try:
                caps = json.loads(w.capabilities_json or "[]")
            except Exception:
                logger.warning(
                    "worker_capabilities_parse_failed",
                    extra={"extra_fields": {"worker_id": w.worker_id}},
                    exc_info=True,
                )

            proxy_url = _derive_proxy_url(w.worker_id, w.hostname)
            out.append(
                WorkerProxyInfo(
                    worker_id=w.worker_id,
                    hostname=w.hostname,
                    capabilities=caps,
                    capacity=w.capacity,
                    status=w.status,
                    proxy_url=proxy_url,
                    display_name=f"{w.worker_id} ({proxy_url})",
                )
            )

        logger.debug("worker_dashboard_fetched_workers", extra={"extra_fields": {"count": len(out)}})
        return out

    except Exception as exc:
        logger.warning(
            "worker_dashboard_fetch_failed",
            extra={"extra_fields": {"error": str(exc)}},
        )
        return []
