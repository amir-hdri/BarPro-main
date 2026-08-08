import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlmodel import select

from app.auth_multitenant import decode_access_token
from app.core.config import utcms_config
from app.core.database import async_session_factory
from app.models_multitenant import Client, ClientStatus, WaybillJob
from app.realtime.events import event_hub

router = APIRouter(tags=["realtime"])


@router.websocket("/ws/waybill")
async def waybill_events_socket(
    websocket: WebSocket,
    task_id: str | None = None,
    batch_id: str | None = None,
    correlation_id: str | None = None,
):
    token = websocket.cookies.get("utcms_auth_token")
    if not token:
        await websocket.close(code=4401)
        return
    try:
        payload = decode_access_token(token)
    except Exception:
        await websocket.close(code=4401)
        return
    
    # Check if token has been revoked (logged out)
    from app.core.token_blacklist import is_blacklisted
    jti = payload.get("jti")
    if jti and await is_blacklisted(jti):
        await websocket.close(code=4401)
        return

    role = payload.get("role", "client")
    tenant_id: int | None = None
    if role == "master_admin":
        if payload.get("client_code") != utcms_config.MASTER_ADMIN_USERNAME:
            await websocket.close(code=4403)
            return
        channels: list[str] = ["all"]
    elif role == "client":
        try:
            tenant_id = int(str(payload.get("sub")))
        except (TypeError, ValueError):
            await websocket.close(code=4401)
            return
        async with async_session_factory() as session:
            client = await session.get(Client, tenant_id)
            if client is None or client.status != ClientStatus.ACTIVE.value:
                await websocket.close(code=4403)
                return
            if task_id:
                owned_job = (
                    await session.exec(
                        select(WaybillJob.id).where(
                            WaybillJob.job_id == task_id,
                            WaybillJob.client_id == tenant_id,
                        )
                    )
                ).first()
                if owned_job is None:
                    await websocket.close(code=4403)
                    return
        channels = [f"tenant_id:{tenant_id}"]
    else:
        await websocket.close(code=4403)
        return

    if role == "master_admin":
        if task_id:
            channels.append(f"task_id:{task_id}")
        if batch_id:
            channels.append(f"batch_id:{batch_id}")
        if correlation_id:
            channels.append(f"correlation_id:{correlation_id}")

    await event_hub.connect(websocket, channels)
    try:
        for event in event_hub.history(task_id=task_id, batch_id=batch_id, tenant_id=tenant_id):
            await websocket.send_json(event)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await event_hub.disconnect(websocket)
    except Exception:
        await event_hub.disconnect(websocket)
        await asyncio.sleep(0)
