import logging
import time
from contextlib import contextmanager
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class WorkerHeartbeatRegistry:
    def __init__(self):
        self._heartbeats: Dict[str, float] = {}

    def heartbeat(self, worker_id: str) -> None:
        self._heartbeats[worker_id] = time.time()

    def snapshot(self) -> Dict[str, float]:
        return dict(self._heartbeats)

    def detect_stalled(self, timeout_seconds: float) -> List[str]:
        now = time.time()
        stalled = []
        for worker_id, last_ts in self._heartbeats.items():
            if now - last_ts > timeout_seconds:
                stalled.append(worker_id)
        return stalled

    def remove(self, worker_id: str) -> None:
        self._heartbeats.pop(worker_id, None)


worker_heartbeat_registry = WorkerHeartbeatRegistry()


@contextmanager
def heartbeat_lease(worker_id: str):
    worker_heartbeat_registry.heartbeat(worker_id)
    try:
        yield
    finally:
        worker_heartbeat_registry.heartbeat(worker_id)
