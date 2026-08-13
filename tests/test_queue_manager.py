from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.queue.queue_manager import WaybillQueueManager
from app.schemas.task import TaskStatus
from app.schemas.waybill import WaybillMapRequest


def _request_payload():
    return {
        "session_id": "queue-test",
        "sender": {"name": "x", "phone": "1", "address": "a", "national_code": "1234567890"},
        "receiver": {"name": "y", "phone": "2", "address": "b"},
        "origin": {"province": "p", "city": "c", "address": "a", "coordinates": {"lat": 1, "lng": 1}},
        "destination": {"province": "p2", "city": "c2", "address": "a2", "coordinates": {"lat": 2, "lng": 2}},
        "cargo": {"type": "مصالح", "packaging": "فله", "weight": 1000, "value": 1000000},
        "vehicle": {"driver_national_code": "1234567890", "plate": "79ع989ایران84"},
        "financial": {},
    }


@pytest.mark.asyncio
async def test_enqueue_inline_and_reuse_idempotency():
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    manager = WaybillQueueManager()
    request = WaybillMapRequest.model_validate(_request_payload())

    test_session_factory = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    with (
        patch("app.services.task_service.async_session_factory", test_session_factory),
        patch("app.core.config.utcms_config.QUEUE_ENABLED", False),
        patch("app.services.task_service.task_service._emit_task_event", new=AsyncMock()),
        patch("app.services.task_service.task_service._sync_queue_depth", new=AsyncMock()),
        patch("app.services.task_service.task_service._ensure_queue_depth_seeded", new=AsyncMock()),
        patch(
            "app.services.waybill_service.waybill_service.create_waybill_with_map",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "status": "validated",
                    "mode": "safe",
                    "request_id": "r1",
                    "correlation_id": "corr-inline",
                }
            ),
        ),
    ):
        first = await manager.enqueue_waybill(request, idempotency_key="idem-k1")
        second = await manager.enqueue_waybill(request, idempotency_key="idem-k1")

    assert first.status.value == "succeeded"
    assert first.reused is False
    assert second.reused is True
    assert second.status.value == "succeeded"

    await test_engine.dispose()


@pytest.mark.asyncio
async def test_enqueue_succeeds_when_queue_enabled_and_broker_up():
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    manager = WaybillQueueManager()
    request = WaybillMapRequest.model_validate(_request_payload())

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock()

    test_session_factory = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    with (
        patch("app.services.task_service.async_session_factory", test_session_factory),
        patch("app.core.config.utcms_config.QUEUE_ENABLED", True),
        patch("app.core.config.utcms_config.QUEUE_INLINE_FALLBACK", False),
        patch("app.services.task_service.task_service._emit_task_event", new=AsyncMock()),
        patch("app.services.task_service.task_service._sync_queue_depth", new=AsyncMock()),
        patch("app.services.task_service.task_service._ensure_queue_depth_seeded", new=AsyncMock()),
        patch("app.core.redis.redis_manager.get", new=AsyncMock(return_value=mock_redis)),
    ):
        res = await manager.enqueue_waybill(request, idempotency_key="idem-k2")
        assert res.status == TaskStatus.PENDING
        assert res.queued is True

    await test_engine.dispose()


@pytest.mark.asyncio
async def test_enqueue_fails_when_queue_unavailable_and_no_inline_fallback():
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    manager = WaybillQueueManager()
    request = WaybillMapRequest.model_validate(_request_payload())

    test_session_factory = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    with (
        patch("app.services.task_service.async_session_factory", test_session_factory),
        patch("app.core.config.utcms_config.QUEUE_ENABLED", True),
        patch("app.core.config.utcms_config.QUEUE_INLINE_FALLBACK", False),
        patch("app.services.task_service.task_service._emit_task_event", new=AsyncMock()),
        patch("app.services.task_service.task_service._sync_queue_depth", new=AsyncMock()),
        patch("app.services.task_service.task_service._ensure_queue_depth_seeded", new=AsyncMock()),
        patch("app.core.redis.redis_manager.get", new=AsyncMock(side_effect=RuntimeError("broker-down"))),
    ):
        with pytest.raises(HTTPException) as exc:
            await manager.enqueue_waybill(request, idempotency_key="idem-k3")
        assert exc.value.status_code == 503

    await test_engine.dispose()


def test_classify_inline_error_marks_temporary_http_as_retryable():
    category, retryable = WaybillQueueManager._classify_inline_error(HTTPException(status_code=503, detail="temporary"))
    assert category == "TARGET_SITE_TIMEOUT"
    assert retryable is True
