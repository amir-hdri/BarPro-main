import asyncio
import logging
import time
import uuid
from collections import deque
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WaybillEventHub:
    def __init__(self, max_history: int = 500) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._history: deque[dict[str, Any]] = deque(maxlen=max_history)
        self._lock = asyncio.Lock()

    @staticmethod
    def _channel_keys(event: dict[str, Any]) -> list[str]:
        keys = ["all"]
        for field in ("task_id", "batch_id", "tenant_id", "correlation_id"):
            value = str(event.get(field) or "").strip()
            if value:
                keys.append(f"{field}:{value}")
        return keys

    async def connect(self, websocket: WebSocket, channels: list[str]) -> None:
        await websocket.accept()
        async with self._lock:
            for channel in channels or ["all"]:
                self._connections.setdefault(channel, set()).add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            for sockets in self._connections.values():
                sockets.discard(websocket)

    async def publish(self, event: dict[str, Any]) -> None:
        envelope = {
            "event_id": str(uuid.uuid4()),
            "published_at": time.time(),
            **event,
        }
        self._history.append(envelope)
        async with self._lock:
            targets: set[WebSocket] = set()
            for channel in self._channel_keys(envelope):
                targets.update(self._connections.get(channel, set()))

        stale: list[WebSocket] = []
        for websocket in targets:
            try:
                await websocket.send_json(envelope)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            await self.disconnect(websocket)
            logger.warning("websocket_disconnected_during_publish")

    def history(self, *, task_id: str | None = None, batch_id: str | None = None) -> list[dict[str, Any]]:
        events = list(self._history)
        if task_id:
            events = [event for event in events if event.get("task_id") == task_id]
        if batch_id:
            events = [event for event in events if event.get("batch_id") == batch_id]
        return events


event_hub = WaybillEventHub()
