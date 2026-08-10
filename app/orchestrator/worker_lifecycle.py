import os
import re
import socket
import logging
import json
import threading
from datetime import UTC, datetime

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import utcms_config
from app.models_rpa import WorkerRegistry

logger = logging.getLogger(__name__)

_heartbeat_stop = threading.Event()

# Worker registry uses a dedicated *synchronous* (psycopg2) engine.
#
# The heartbeat runs in a background thread (see ``_heartbeat_loop``), and that
# thread drives its own asyncio event loop. Opening connections from the shared
# asyncpg engine inside that thread triggered "Future attached to a different
# loop" / "unknown protocol state 3" because the pooled asyncpg connections are
# bound to the engine's event loop, not the heartbeat thread's loop.
#
# A plain synchronous engine has no event loop at all, so it is safe to call from
# any thread (heartbeat thread, worker_process_init, worker_process_shutdown).
_SYNC_DB_URL = utcms_config.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
_worker_engine = create_engine(_SYNC_DB_URL, pool_size=2, max_overflow=1, pool_pre_ping=True)
_WorkerSession = sessionmaker(_worker_engine, expire_on_commit=False)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# Matches a standalone or trailing-separated integer: "2", "worker_3", "node-4"
_IP_INDEX_RE = re.compile(r"(?:^|[-_])(\d+)$")


def resolve_ip_index(worker_id: str, hostname: str) -> int | None:
    """Map this worker to its numeric IP index.

    Precedence:
    1. ``WORKER_IP_INDEX`` env var (explicit — set in compose files and on
       remote worker nodes; must match ``AVAILABLE_IP_INDICES`` on central).
    2. Numeric ``WORKER_ID`` / ``worker_id`` (the docs convention sets it to
       the IP index, e.g. ``WORKER_ID=2``).
    3. Trailing numeric suffix of the hostname (e.g. ``worker-node-2``).

    Returns ``None`` when the index cannot be determined safely — the worker
    is then registered without an index and the router simply cannot
    attribute any IP index to it (fail-safe: it never removes an index from
    the routing pool on this worker's behalf).
    """
    raw = os.environ.get("WORKER_IP_INDEX", "").strip()
    for candidate in (raw, worker_id, hostname):
        if not candidate:
            continue
        match = _IP_INDEX_RE.search(str(candidate).strip())
        if match:
            value = int(match.group(1))
            # Sanity bound — avoids nonsense values (e.g. a year in a hostname)
            if 1 <= value <= 999:
                return value
    return None


def register_worker(worker_id: str, hostname: str, capabilities: list[str], capacity: int = 1) -> None:
    with _WorkerSession() as session:
        try:
            worker = (
                session.query(WorkerRegistry)
                .filter(WorkerRegistry.worker_id == worker_id)
                .first()
            )
            now = _now()
            ip_index = resolve_ip_index(worker_id, hostname)
            if worker is None:
                worker = WorkerRegistry(
                    worker_id=worker_id,
                    hostname=hostname,
                    capabilities_json=json.dumps(capabilities),
                    capacity=capacity,
                    status="active",
                    ip_index=ip_index,
                    last_heartbeat_at=now,
                    created_at=now,
                    updated_at=now,
                )
                session.add(worker)
            else:
                worker.hostname = hostname
                worker.capabilities_json = json.dumps(capabilities)
                worker.capacity = capacity
                worker.status = "active"
                worker.ip_index = ip_index
                worker.last_heartbeat_at = now
                worker.updated_at = now
                session.add(worker)
            session.commit()
            logger.info(f"Worker {worker_id} registered successfully.")
        except Exception as e:
            logger.error(f"Failed to register worker {worker_id}: {e}", exc_info=True)
            session.rollback()
            raise


def deregister_worker(worker_id: str) -> None:
    with _WorkerSession() as session:
        try:
            worker = (
                session.query(WorkerRegistry)
                .filter(WorkerRegistry.worker_id == worker_id)
                .first()
            )
            if worker is not None:
                worker.status = "offline"
                worker.updated_at = _now()
                session.add(worker)
                session.commit()
                logger.info(f"Worker {worker_id} de-registered successfully (status set to offline).")
        except Exception as e:
            logger.error(f"Failed to deregister worker {worker_id}: {e}", exc_info=True)
            session.rollback()
            raise


def send_heartbeat(worker_id: str) -> None:
    try:
        with _WorkerSession() as session:
            worker = (
                session.query(WorkerRegistry)
                .filter(WorkerRegistry.worker_id == worker_id)
                .first()
            )
            if worker is not None:
                worker.last_heartbeat_at = _now()
                # Refresh the index on every heartbeat too — covers workers
                # that were registered before the env var was set correctly.
                worker.ip_index = resolve_ip_index(worker_id, worker.hostname or socket.gethostname())
                worker.updated_at = _now()
                session.add(worker)
                session.commit()
            else:
                # Re-register if somehow missing
                hostname = socket.gethostname()
                register_worker(worker_id, hostname, ["waybill"], capacity=1)
    except Exception as e:
        logger.warning(f"Failed to send heartbeat for worker {worker_id}: {e}")


def _heartbeat_loop(worker_id: str):
    while not _heartbeat_stop.wait(timeout=30):
        try:
            send_heartbeat(worker_id)
        except Exception as e:
            logger.warning(f"Heartbeat loop error for worker {worker_id}: {e}")


try:
    from celery.signals import worker_process_init, worker_process_shutdown
except ImportError:
    worker_process_init = None
    worker_process_shutdown = None

if worker_process_init is not None:

    @worker_process_init.connect
    def on_worker_start(**kwargs):
        worker_id = os.environ.get("WORKER_ID", socket.gethostname())
        try:
            register_worker(
                worker_id=worker_id,
                hostname=socket.gethostname(),
                capabilities=["waybill", "fuel"],
                capacity=1,
            )
            # Start background heartbeat daemon thread
            threading.Thread(target=_heartbeat_loop, args=(worker_id,), daemon=True).start()
        except Exception as e:
            logger.error(f"Error registering worker process start: {e}", exc_info=True)

    @worker_process_shutdown.connect
    def on_worker_stop(**kwargs):
        _heartbeat_stop.set()
        worker_id = os.environ.get("WORKER_ID", socket.gethostname())
        try:
            deregister_worker(worker_id)
        except Exception as e:
            logger.error(f"Error deregistering worker process stop: {e}", exc_info=True)
