import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.realtime.events import event_hub

router = APIRouter(tags=["realtime"])


@router.websocket("/ws/waybill")
async def waybill_events_socket(
    websocket: WebSocket,
    task_id: str | None = None,
    batch_id: str | None = None,
    correlation_id: str | None = None,
):
    channels: list[str] = ["all"]
    if task_id:
        channels.append(f"task_id:{task_id}")
    if batch_id:
        channels.append(f"batch_id:{batch_id}")
    if correlation_id:
        channels.append(f"correlation_id:{correlation_id}")

    await event_hub.connect(websocket, channels)
    try:
        for event in event_hub.history(task_id=task_id, batch_id=batch_id):
            await websocket.send_json(event)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await event_hub.disconnect(websocket)
    except Exception:
        await event_hub.disconnect(websocket)
        await asyncio.sleep(0)

