import os
import threading
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from app.models_rpa import WorkerRegistry
from app.orchestrator.worker_lifecycle import _heartbeat_loop, on_worker_start, on_worker_stop, send_heartbeat


@pytest.fixture
def worker_session_factory():
    """Provide the synchronous session factory used by worker lifecycle code."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    yield factory
    engine.dispose()


def test_worker_lifecycle_flow(worker_session_factory):
    """Exercise startup, heartbeat, and shutdown against the current sync API."""
    worker_id = "test_lifecycle_worker"
    hostname = "test_lifecycle_host"
    heartbeat_stop = threading.Event()

    with (
        patch("app.orchestrator.worker_lifecycle._WorkerSession", new=worker_session_factory),
        patch("app.orchestrator.worker_lifecycle._heartbeat_stop", new=heartbeat_stop),
        patch("app.orchestrator.worker_lifecycle.threading.Thread") as thread_cls,
        patch.dict(os.environ, {"WORKER_ID": worker_id}),
        patch("app.orchestrator.worker_lifecycle.socket.gethostname", return_value=hostname),
    ):
        on_worker_start()
        thread_cls.assert_called_once_with(
            target=_heartbeat_loop,
            args=(worker_id,),
            daemon=True,
        )
        thread_cls.return_value.start.assert_called_once_with()

        with worker_session_factory() as session:
            worker = session.query(WorkerRegistry).filter(WorkerRegistry.worker_id == worker_id).one()
            assert worker.status == "active"
            assert worker.hostname == hostname
            created_at = worker.created_at
            first_heartbeat = worker.last_heartbeat_at

        send_heartbeat(worker_id)

        with worker_session_factory() as session:
            worker = session.query(WorkerRegistry).filter(WorkerRegistry.worker_id == worker_id).one()
            assert worker.status == "active"
            assert worker.created_at == created_at
            assert worker.last_heartbeat_at >= first_heartbeat

        on_worker_stop()

        with worker_session_factory() as session:
            worker = session.query(WorkerRegistry).filter(WorkerRegistry.worker_id == worker_id).one()
            assert worker.status == "offline"

        assert heartbeat_stop.is_set()
