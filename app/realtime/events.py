import asyncio
import json
import logging
import time
import uuid
from collections import deque
from typing import Any

from fastapi import WebSocket

from app.core.redis import redis_manager

logger = logging.getLogger(__name__)

# Channel workers (and any process) publish waybill events to; the API process
# subscribes and re-delivers them into its in-process hub for connected WebSockets.
REDIS_EVENT_CHANNEL = "barpro:events"

# Unique id per process so the subscriber can ignore events it published itself
# (avoiding double-delivery of API-originated events to local WebSockets).
PROCESS_ID = uuid.uuid4().hex


class WaybillEventHub:
    def __init__(self, max_history: int = 500) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._history: deque[dict[str, Any]] = deque(maxlen=max_history)
        self._lock = asyncio.Lock()
        self._subscriber_task: asyncio.Task | None = None

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

    async def _deliver(self, event: dict[str, Any]) -> None:
        """Fan an event out to locally connected WebSockets (no Redis publish)."""
        self._history.append(event)

        # Collect targets under lock, then send outside lock to avoid blocking
        async with self._lock:
            targets: set[WebSocket] = set()
            for channel in self._channel_keys(event):
                targets.update(self._connections.get(channel, set()))
            targets_copy = set(targets)

        stale: list[WebSocket] = []
        for websocket in targets_copy:
            try:
                await websocket.send_json(event)
            except Exception:
                stale.append(websocket)
        if stale:
            async with self._lock:
                for websocket in stale:
                    for sockets in self._connections.values():
                        sockets.discard(websocket)
                    logger.warning("websocket_disconnected_during_publish")

    async def publish(self, event: dict[str, Any]) -> None:
        envelope = {
            "event_id": str(uuid.uuid4()),
            "published_at": time.time(),
            "origin": PROCESS_ID,
            **event,
        }
        # Deliver locally first (covers events raised inside this process).
        await self._deliver(envelope)
        # Bridge to other processes (workers) via Redis pub/sub.
        await self._publish_to_redis(envelope)

    async def _publish_to_redis(self, envelope: dict[str, Any]) -> None:
        try:
            redis = await redis_manager.get()
        except Exception:
            return
        if redis is None:
            return
        try:
            await redis.publish(REDIS_EVENT_CHANNEL, json.dumps(envelope, ensure_ascii=False))
        except Exception as exc:
            logger.warning("event_redis_publish_failed", extra={"extra_fields": {"error": str(exc)}})

    async def run_subscriber(self) -> None:
        """Subscribe to the Redis channel and deliver foreign-origin events locally.

        Runs as a long-lived task in the API process. Ignores events this process
        published (same PROCESS_ID) to avoid duplicate delivery to local sockets.
        """
        while True:
            try:
                redis = await redis_manager.get()
                if redis is None:
                    await asyncio.sleep(5)
                    continue
                pubsub = redis.pubsub()
                await pubsub.subscribe(REDIS_EVENT_CHANNEL)
                logger.info("event_subscriber_started", extra={"extra_fields": {"channel": REDIS_EVENT_CHANNEL}})
                try:
                    while True:
                        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                        if message is None or message.get("type") != "message":
                            await asyncio.sleep(0.05)
                            continue
                        raw = message.get("data")
                        if not raw:
                            continue
                        try:
                            event = json.loads(raw)
                        except Exception:
                            continue
                        if event.get("origin") == PROCESS_ID:
                            continue
                        await self._deliver(event)
                finally:
                    try:
                        await pubsub.unsubscribe(REDIS_EVENT_CHANNEL)
                        await pubsub.close()
                    except Exception as exc:
                        logger.warning(
                            "redis_pubsub_cleanup_failed",
                            extra={"extra_fields": {"error": str(exc)}},
                        )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("event_subscriber_error", extra={"extra_fields": {"error": str(exc)}})
                await asyncio.sleep(5)

    def start_subscriber(self) -> None:
        if self._subscriber_task is None or self._subscriber_task.done():
            self._subscriber_task = asyncio.create_task(self.run_subscriber())

    async def stop_subscriber(self) -> None:
        if self._subscriber_task is not None:
            self._subscriber_task.cancel()
            try:
                await self._subscriber_task
            except asyncio.CancelledError:
                logger.debug("subscriber_task_cancelled_on_stop")
            except Exception as exc:
                logger.warning(
                    "subscriber_task_unexpected_error",
                    extra={"extra_fields": {"error": str(exc)}},
                )
            self._subscriber_task = None

    def history(
        self,
        *,
        task_id: str | None = None,
        batch_id: str | None = None,
        tenant_id: int | None = None,
    ) -> list[dict[str, Any]]:
        events = list(self._history)
        if tenant_id is not None:
            events = [event for event in events if str(event.get("tenant_id")) == str(tenant_id)]
        if task_id:
            events = [event for event in events if event.get("task_id") == task_id]
        if batch_id:
            events = [event for event in events if event.get("batch_id") == batch_id]
        return events


event_hub = WaybillEventHub()
