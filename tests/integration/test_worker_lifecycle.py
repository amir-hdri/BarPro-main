import pytest
import os
import socket
from unittest.mock import AsyncMock, patch, MagicMock
from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models_rpa import WorkerRegistry
from app.orchestrator.worker_lifecycle import (
    register_worker,
    deregister_worker,
    send_heartbeat,
    on_worker_start,
    on_worker_stop
)


@pytest.fixture
async def async_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield async_session
    await engine.dispose()


@pytest.mark.asyncio
async def test_worker_lifecycle_flow(async_db):
    """
    Integration test: startup -> registration -> heartbeat -> shutdown.
    Asserts worker registration is performed once.
    """
    worker_id = "test_lifecycle_worker"
    hostname = "test_lifecycle_host"
    
    with patch("app.orchestrator.worker_lifecycle.async_session_factory", new=async_db), \
         patch.dict(os.environ, {"WORKER_ID": worker_id}), \
         patch("socket.gethostname", return_value=hostname):
         
        # 1. Simulate Worker Startup (on_worker_start)
        on_worker_start()
        
        # Verify registered as active in DB
        async with async_db() as session:
            stmt = select(WorkerRegistry).where(WorkerRegistry.worker_id == worker_id)
            res = await session.exec(stmt)
            worker = res.first()
            assert worker is not None
            assert worker.status == "active"
            assert worker.hostname == hostname
            
            # Store initial registration timestamp
            created_at_first = worker.created_at
            
        # 2. Simulate Heartbeat
        await send_heartbeat(worker_id)
        
        # Verify last_heartbeat_at updated but created_at remains unchanged (signifying single registration)
        async with async_db() as session:
            stmt = select(WorkerRegistry).where(WorkerRegistry.worker_id == worker_id)
            res = await session.exec(stmt)
            worker = res.first()
            assert worker is not None
            assert worker.status == "active"
            assert worker.created_at == created_at_first
            
        # 3. Simulate Worker Shutdown (on_worker_stop)
        on_worker_stop()
        
        # Verify status transitions to offline in DB
        async with async_db() as session:
            stmt = select(WorkerRegistry).where(WorkerRegistry.worker_id == worker_id)
            res = await session.exec(stmt)
            worker = res.first()
            assert worker is not None
            assert worker.status == "offline"
