"""Regression tests: ``rpa.session.keepalive`` must stay time-bounded.

Live incident (2026-09-29): the keepalive task froze ``barpro-worker-1`` for
381s+ because ``authenticate_driver`` awaited browser/login calls with no
timeout, ``run_async`` blocks the solo-pool main thread on ``future.result()``
with no timeout, and Celery ``time_limit`` is inert on the solo pool
(``celery/concurrency/solo.py`` reports ``'timeouts': ()``).

These tests fail while the keepalive path is unbounded and pass once each
layer carries an ``asyncio.wait_for`` bound:

1. per-driver bound inside ``keepalive_sessions`` (+ browser recycle),
2. guarded ``close_context`` in ``authenticate_driver`` teardown so
   cancellation always unwinds and the driver lock is released,
3. task-level bound in the ``rpa.session.keepalive`` Celery task.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import utcms_config
from app.models_multitenant import Client, Driver
from app.models_rpa import DriverRuntimeState, DriverRuntimeStateValue
from app.services.rpa_auth_service import rpa_auth_service


async def _hang_forever(*args, **kwargs):
    """Simulate a hung browser/network await (the live freeze mode)."""
    await asyncio.sleep(3600)
    raise AssertionError("hung await unexpectedly returned")


@asynccontextmanager
async def _session_factory():
    """Yield a session factory; dispose the engine afterwards.

    Without explicit disposal the aiosqlite worker thread outlives the
    test's event loop and dies with "Event loop is closed", which pytest
    attributes to a random later test (PytestUnhandledThreadExceptionWarning).
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        yield sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    finally:
        await engine.dispose()


async def _seed_expiring_driver(async_session):
    async with async_session() as session:
        client = Client(
            client_code="tenant-ka",
            name="Tenant KA",
            email="ka@example.com",
            hashed_password="hash",
            username="tenant_ka",
            full_name="Tenant KA Admin",
        )
        session.add(client)
        await session.commit()
        await session.refresh(client)
        driver = Driver(
            client_id=client.id,
            driver_national_code="1111111111",
            full_name="Keepalive Driver",
            utcms_username="kadriver",
            utcms_password_encrypted="enc",
        )
        session.add(driver)
        await session.commit()
        await session.refresh(driver)
        runtime_state = DriverRuntimeState(
            client_id=client.id,
            driver_id=driver.id,
            state=DriverRuntimeStateValue.READY.value,
            session_expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=60),
        )
        session.add(runtime_state)
        await session.commit()
        return client.id, driver.id


@pytest.mark.asyncio
async def test_keepalive_bounded_when_authenticate_driver_hangs():
    """A hung per-driver auth must not freeze the whole keepalive run."""
    async with _session_factory() as async_session:
        await _seed_expiring_driver(async_session)
        mock_browser = SimpleNamespace(recycle_browser=AsyncMock())
        with (
            patch("app.services.rpa_auth_service.async_session_factory", new=async_session),
            patch.object(rpa_auth_service, "authenticate_driver", side_effect=_hang_forever),
            patch("app.services.rpa_auth_service.browser_manager", mock_browser),
            # create=True: the timeout knob does not exist yet (added with the fix).
            patch.object(utcms_config, "RPA_KEEPALIVE_DRIVER_TIMEOUT_SECONDS", 2, create=True),
        ):
            result = await asyncio.wait_for(
                rpa_auth_service.keepalive_sessions(),
                timeout=utcms_config.RPA_KEEPALIVE_DRIVER_TIMEOUT_SECONDS + 30,
            )
        assert result["checked"] == 1
        assert result["errors"] == 1
        assert result["details"][0]["outcome"] == "keepalive_timeout"
        mock_browser.recycle_browser.assert_awaited_once()


@pytest.mark.asyncio
async def test_keepalive_releases_lock_when_login_and_close_hang():
    """Cancellation must unwind through guarded teardown and release the lock."""
    async with _session_factory() as async_session:
        client_id, driver_id = await _seed_expiring_driver(async_session)

        release_calls: list[tuple] = []

        async def _record_release(key, token=None):
            release_calls.append((key, token))

        mock_page = SimpleNamespace(close=AsyncMock())
        mock_context = SimpleNamespace()
        mock_browser = SimpleNamespace(
            initialize=AsyncMock(),
            create_context=AsyncMock(return_value=("sid-1", mock_context)),
            new_page=AsyncMock(return_value=mock_page),
            close_context=_hang_forever,
            recycle_browser=AsyncMock(),
        )
        mock_runtime = SimpleNamespace(
            auth_lock_key=lambda c, d: f"auth:{c}:{d}",
            acquire_lock=AsyncMock(return_value="tok"),
            release_lock=_record_release,
            store_session=AsyncMock(),
        )
        mock_rotator = SimpleNamespace(
            get_next=AsyncMock(
                return_value=SimpleNamespace(to_playwright_proxy=lambda: {"server": "http://127.0.0.1:9"})
            )
        )
        mock_vault = SimpleNamespace(
            auth_state_path_for_account=lambda **kwargs: "/tmp/ka_test_state.json",
            ensure_parent_dir=lambda path: None,
        )
        with (
            patch("app.services.rpa_auth_service.async_session_factory", new=async_session),
            patch("app.services.rpa_auth_service.decrypt_driver_password", return_value="pw"),
            patch(
                "app.services.rpa_auth_service.UTCMSAuthenticator",
                return_value=SimpleNamespace(login=_hang_forever, last_error=None),
            ),
            patch("app.services.rpa_auth_service.browser_manager", mock_browser),
            patch("app.services.rpa_auth_service.get_proxy_rotator", return_value=mock_rotator),
            patch("app.services.rpa_auth_service.rpa_runtime", mock_runtime),
            patch("app.services.rpa_auth_service.session_vault", mock_vault),
            patch.object(utcms_config, "RPA_KEEPALIVE_DRIVER_TIMEOUT_SECONDS", 3, create=True),
        ):
            result = await asyncio.wait_for(
                rpa_auth_service.keepalive_sessions(),
                timeout=utcms_config.RPA_KEEPALIVE_DRIVER_TIMEOUT_SECONDS + 40,
            )
        assert result["checked"] == 1
        assert result["errors"] == 1
        assert result["details"][0]["outcome"] == "keepalive_timeout"
        assert result["details"][0]["driver_id"] == driver_id
    assert result["details"][0]["client_id"] == client_id
    assert release_calls, "driver lock was not released after timeout unwind"
    mock_browser.recycle_browser.assert_awaited_once()


def test_keepalive_celery_task_bounded_when_service_hangs():
    """The Celery task wrapper itself must return instead of blocking the worker."""
    from app.workers import phase1_tasks

    with (
        patch.object(rpa_auth_service, "keepalive_sessions", side_effect=_hang_forever),
        patch.object(utcms_config, "RPA_KEEPALIVE_TASK_TIMEOUT_SECONDS", 3, create=True),
    ):
        result = phase1_tasks.keepalive_sessions()
    assert result.get("timeout") is True
