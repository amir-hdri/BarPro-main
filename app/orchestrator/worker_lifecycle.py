import os
import socket
import logging
import json
import threading
from datetime import UTC, datetime
from sqlmodel import select
from app.core.database import async_session_factory
from app.models_rpa import WorkerRegistry

logger = logging.getLogger(__name__)

_heartbeat_stop = threading.Event()


async def register_worker(worker_id: str, hostname: str, capabilities: list[str], capacity: int = 1) -> None:
    async with async_session_factory() as session:
        try:
            statement = select(WorkerRegistry).where(WorkerRegistry.worker_id == worker_id)
            res = await session.exec(statement)
            worker = res.first()
            
            now = datetime.now(UTC).replace(tzinfo=None)
            if worker is None:
                worker = WorkerRegistry(
                    worker_id=worker_id,
                    hostname=hostname,
                    capabilities_json=json.dumps(capabilities),
                    capacity=capacity,
                    status="active",
                    last_heartbeat_at=now,
                    created_at=now,
                    updated_at=now
                )
                session.add(worker)
            else:
                worker.hostname = hostname
                worker.capabilities_json = json.dumps(capabilities)
                worker.capacity = capacity
                worker.status = "active"
                worker.last_heartbeat_at = now
                worker.updated_at = now
                session.add(worker)
                
            await session.commit()
            logger.info(f"Worker {worker_id} registered successfully.")
        except Exception as e:
            logger.error(f"Failed to register worker {worker_id}: {e}", exc_info=True)
            await session.rollback()
            raise


async def deregister_worker(worker_id: str) -> None:
    async with async_session_factory() as session:
        try:
            statement = select(WorkerRegistry).where(WorkerRegistry.worker_id == worker_id)
            res = await session.exec(statement)
            worker = res.first()
            if worker is not None:
                worker.status = "offline"
                worker.updated_at = datetime.now(UTC).replace(tzinfo=None)
                session.add(worker)
                await session.commit()
                logger.info(f"Worker {worker_id} de-registered successfully (status set to offline).")
        except Exception as e:
            logger.error(f"Failed to deregister worker {worker_id}: {e}", exc_info=True)
            await session.rollback()
            raise


async def send_heartbeat(worker_id: str) -> None:
    async with async_session_factory() as session:
        try:
            statement = select(WorkerRegistry).where(WorkerRegistry.worker_id == worker_id)
            res = await session.exec(statement)
            worker = res.first()
            if worker is not None:
                worker.last_heartbeat_at = datetime.now(UTC).replace(tzinfo=None)
                worker.updated_at = datetime.now(UTC).replace(tzinfo=None)
                session.add(worker)
                await session.commit()
            else:
                # Re-register if somehow missing
                hostname = socket.gethostname()
                await register_worker(worker_id, hostname, ["waybill"], capacity=1)
        except Exception as e:
            logger.warning(f"Failed to send heartbeat for worker {worker_id}: {e}")
            await session.rollback()


def _heartbeat_loop(worker_id: str):
    from app.core.utils import run_async as _run
    while not _heartbeat_stop.wait(timeout=30):
        try:
            _run(send_heartbeat(worker_id))
        except Exception as e:
            logger.warning(f"Heartbeat loop error for worker {worker_id}: {e}")


try:
    from celery.signals import worker_process_init, worker_process_shutdown
except ImportError:
    worker_process_init = None
    worker_process_shutdown = None

if worker_process_init is not None:
    from app.core.utils import run_async as _run

    @worker_process_init.connect
    def on_worker_start(**kwargs):
        worker_id = os.environ.get("WORKER_ID", socket.gethostname())
        try:
            _run(register_worker(
                worker_id=worker_id,
                hostname=socket.gethostname(),
                capabilities=["waybill", "fuel"],
                capacity=1
            ))
            # Start background heartbeat daemon thread
            threading.Thread(target=_heartbeat_loop, args=(worker_id,), daemon=True).start()
        except Exception as e:
            logger.error(f"Error registering worker process start: {e}", exc_info=True)

    @worker_process_shutdown.connect
    def on_worker_stop(**kwargs):
        _heartbeat_stop.set()
        worker_id = os.environ.get("WORKER_ID", socket.gethostname())
        try:
            _run(deregister_worker(worker_id))
        except Exception as e:
            logger.error(f"Error deregistering worker process stop: {e}", exc_info=True)
