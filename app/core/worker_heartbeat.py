import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class WorkerLease:
    task_id: str
    worker_id: str
    correlation_id: str
    batch_id: str
    status: str
    started_at: float
    last_heartbeat_at: float
    current_step: str = "starting"


class WorkerHeartbeatRegistry:
    def __init__(self) -> None:
        self._leases: Dict[str, WorkerLease] = {}
        self._lock = threading.Lock()

    def start(self, task_id: str, worker_id: str, correlation_id: str, batch_id: str) -> None:
        now = time.time()
        with self._lock:
            self._leases[task_id] = WorkerLease(
                task_id=task_id,
                worker_id=worker_id,
                correlation_id=correlation_id,
                batch_id=batch_id,
                status="running",
                started_at=now,
                last_heartbeat_at=now,
            )

    def beat(self, task_id: str, *, status: Optional[str] = None, current_step: Optional[str] = None) -> None:
        with self._lock:
            lease = self._leases.get(task_id)
            if not lease:
                return
            lease.last_heartbeat_at = time.time()
            if status:
                lease.status = status
            if current_step:
                lease.current_step = current_step

    def finish(self, task_id: str, status: str) -> None:
        with self._lock:
            lease = self._leases.get(task_id)
            if not lease:
                return
            lease.status = status
            lease.last_heartbeat_at = time.time()

    def snapshot(self) -> Dict[str, Dict[str, float | str]]:
        with self._lock:
            return {
                task_id: {
                    "worker_id": lease.worker_id,
                    "correlation_id": lease.correlation_id,
                    "batch_id": lease.batch_id,
                    "status": lease.status,
                    "current_step": lease.current_step,
                    "started_at": lease.started_at,
                    "last_heartbeat_at": lease.last_heartbeat_at,
                }
                for task_id, lease in self._leases.items()
            }

    def detect_stalled(self, timeout_seconds: float) -> Dict[str, Dict[str, float | str]]:
        now = time.time()
        with self._lock:
            stalled = {
                task_id: {
                    "worker_id": lease.worker_id,
                    "correlation_id": lease.correlation_id,
                    "batch_id": lease.batch_id,
                    "status": lease.status,
                    "current_step": lease.current_step,
                    "stalled_for_seconds": round(now - lease.last_heartbeat_at, 2),
                }
                for task_id, lease in self._leases.items()
                if (now - lease.last_heartbeat_at) > timeout_seconds and lease.status not in {"succeeded", "failed", "dead_letter"}
            }
        return stalled


worker_heartbeat_registry = WorkerHeartbeatRegistry()


@contextmanager
def heartbeat_lease(task_id: str, worker_id: str, correlation_id: str, batch_id: str, interval_seconds: float = 5.0):
    stop_event = threading.Event()
    worker_heartbeat_registry.start(task_id, worker_id, correlation_id, batch_id)

    def _pulse() -> None:
        while not stop_event.wait(interval_seconds):
            worker_heartbeat_registry.beat(task_id, status="running")

    thread = threading.Thread(target=_pulse, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop_event.set()
        thread.join(timeout=0.2)

