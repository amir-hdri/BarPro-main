import asyncio
import time
from unittest.mock import AsyncMock, Mock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture(autouse=True)
def reset_readyz_cache():
    """Isolate readiness scenarios from the unrelated external queue check."""
    from app.api.routes.system import _reset_readyz_cache

    with patch("app.core.config.utcms_config.QUEUE_ENABLED", False):
        _reset_readyz_cache()
        yield
        _reset_readyz_cache()


@pytest.mark.asyncio
async def test_readyz_database_down_returns_503():
    # Simulates immediate DB connection failure
    mock_connect_ctx = AsyncMock()
    mock_connect_ctx.__aenter__ = AsyncMock(side_effect=Exception("Connection refused"))
    mock_connect_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_engine = Mock()
    mock_engine.connect = Mock(return_value=mock_connect_ctx)

    with (
        patch("app.api.routes.system.engine", mock_engine),
        patch("app.api.routes.system.browser_manager.initialize", new=AsyncMock(return_value=None)),
        patch("app.api.routes.system.barname_ml_solver.warmup", return_value=True),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/readyz")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["database"] == "error"
    assert payload["details"]["database"]["message"] == "database connection failed"


@pytest.mark.asyncio
async def test_readyz_database_dns_failure_returns_skipped():
    # Simulates DNS name resolution error (transient/nonfatal)
    dns_error = Exception("nodename nor servname provided, or temporary failure in name resolution")

    mock_connect_ctx = AsyncMock()
    mock_connect_ctx.__aenter__ = AsyncMock(side_effect=dns_error)
    mock_connect_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_engine = Mock()
    mock_engine.connect = Mock(return_value=mock_connect_ctx)

    with (
        patch("app.api.routes.system.engine", mock_engine),
        patch("app.api.routes.system.browser_manager.initialize", new=AsyncMock(return_value=None)),
        patch("app.api.routes.system.barname_ml_solver.warmup", return_value=True),
        patch("app.api.routes.system._database_host", return_value="db"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/readyz")

    # Skipped DB is considered "ready" under default setup
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["checks"]["database"] == "skipped"
    assert "not resolvable" in payload["details"]["database"]["message"]


@pytest.mark.asyncio
async def test_readyz_database_delay_does_not_block_healthz():
    # Simulates a slow database response (e.g. 2 seconds delay)
    async def slow_connect(*args, **kwargs):
        await asyncio.sleep(2.0)
        # Mock connection context
        conn = AsyncMock()
        conn.execute = AsyncMock()
        return conn

    mock_connect_ctx = AsyncMock()
    mock_connect_ctx.__aenter__ = slow_connect
    mock_connect_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_engine = Mock()
    mock_engine.connect = Mock(return_value=mock_connect_ctx)

    with (
        patch("app.api.routes.system.engine", mock_engine),
        patch("app.api.routes.system.browser_manager.initialize", new=AsyncMock(return_value=None)),
        patch("app.api.routes.system.barname_ml_solver.warmup", return_value=True),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # Let's fire /readyz and /healthz concurrently
            t1 = time.time()
            readyz_task = asyncio.create_task(ac.get("/readyz"))
            # Wait briefly to ensure readyz_task runs and is blocked
            await asyncio.sleep(0.1)

            # healthz should return instantly
            healthz_resp = await ac.get("/healthz")
            t2 = time.time()

            # healthz duration should be very fast
            assert healthz_resp.status_code == 200
            assert t2 - t1 < 0.5  # healthz returns instantly despite readyz waiting

            # Wait for readyz to finish
            readyz_resp = await readyz_task
            t3 = time.time()

            assert readyz_resp.status_code == 200
            assert t3 - t1 >= 2.0  # readyz took the full database delay


@pytest.mark.asyncio
async def test_readyz_browser_timeout_returns_503():
    # Simulates browser initialization hanging
    async def slow_browser_init(*args, **kwargs):
        await asyncio.sleep(5.0)

    # Mock database connection success
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()
    mock_connect_ctx = AsyncMock()
    mock_connect_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_connect_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_engine = Mock()
    mock_engine.connect = Mock(return_value=mock_connect_ctx)

    # Force a 1 second readyz browser timeout
    with (
        patch("app.api.routes.system.browser_manager.initialize", new=slow_browser_init),
        patch("app.api.routes.system.barname_ml_solver.warmup", return_value=True),
        patch("app.core.config.utcms_config.READYZ_BROWSER_TIMEOUT_SECONDS", 1.0),
        patch("app.api.routes.system.engine", mock_engine),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            t1 = time.time()
            response = await ac.get("/readyz")
            t2 = time.time()

            # The response should return 503 because browser failed to init within timeout
            assert response.status_code == 503
            payload = response.json()
            assert payload["checks"]["browser"] == "error"
            assert payload["details"]["browser"]["message"] == "browser initialization failed"
            # Request duration should be constrained to ~1.0 second (plus slight overhead)
            assert t2 - t1 < 2.0


@pytest.mark.asyncio
async def test_readyz_queue_failure_returns_503():
    # Mock database connection success
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()
    mock_connect_ctx = AsyncMock()
    mock_connect_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_connect_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_engine = Mock()
    mock_engine.connect = Mock(return_value=mock_connect_ctx)

    # Test failure behavior when queue check is enabled and fails
    with (
        patch("app.api.routes.system.browser_manager.initialize", new=AsyncMock(return_value=None)),
        patch("app.api.routes.system.barname_ml_solver.warmup", return_value=True),
        patch("app.core.config.utcms_config.QUEUE_ENABLED", True),
        patch("app.api.routes.system.is_celery_available", return_value=True),
        patch(
            "app.api.routes.system._safe_queue_snapshot", new_callable=AsyncMock, side_effect=Exception("Redis down")
        ),
        patch("app.api.routes.system.engine", mock_engine),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/readyz")

    assert response.status_code == 503
    payload = response.json()
    assert payload["checks"]["queue"] == "error"
    assert payload["details"]["queue"]["message"] == "queue check failed"


@pytest.mark.asyncio
async def test_public_readyz_redacts_internal_details_and_broker_credentials():
    checks = {
        "database": "ok",
        "browser": "ok",
        "config": "ok",
        "captcha_model": "ok",
        "itmb_config": "ok",
        "itmb_baseinfo_cache": "ok",
        "itmb_live_probe": "ok",
        "queue": "ok",
        "circuit_breaker": "ok",
    }
    details = {
        "database": {"message": "database connection ok", "host": "postgres.internal"},
        "captcha_model": {"provider": "cnn", "model_path": "/srv/private/model.pth"},
        "queue": {
            "message": "queue configured",
            "broker": "redis://:do-not-expose@redis:6379/0",
            "snapshot": {"queued": 12},
        },
        "circuit_breaker": {
            "message": "circuit healthy",
            "status": {
                "state": "closed",
                "failure_count": 0,
                "retry_after_seconds": 0,
                "enabled": True,
                "internal_marker": "private",
            },
        },
    }

    with patch("app.api.routes.system._compute_readyz_checks", new=AsyncMock(return_value=(checks, details))):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/readyz")

    assert response.status_code == 200
    payload = response.json()
    serialized = response.text
    assert "do-not-expose" not in serialized
    assert "redis://" not in serialized
    assert "postgres.internal" not in serialized
    assert "/srv/private/model.pth" not in serialized
    assert "snapshot" not in payload["details"]["queue"]
    assert payload["details"]["circuit_breaker"]["status"] == {
        "state": "closed",
        "failure_count": 0,
        "retry_after_seconds": 0,
        "enabled": True,
    }


@pytest.mark.asyncio
async def test_readyz_database_hang_takes_full_delay():
    # This test verifies that the database check currently lacks a timeout,
    # and will block for the full duration of the hang.
    async def hung_connect(*args, **kwargs):
        await asyncio.sleep(4.0)
        conn = AsyncMock()
        conn.execute = AsyncMock()
        return conn

    mock_connect_ctx = AsyncMock()
    mock_connect_ctx.__aenter__ = hung_connect
    mock_connect_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_engine = Mock()
    mock_engine.connect = Mock(return_value=mock_connect_ctx)

    with (
        patch("app.api.routes.system.engine", mock_engine),
        patch("app.api.routes.system.browser_manager.initialize", new=AsyncMock(return_value=None)),
        patch("app.api.routes.system.barname_ml_solver.warmup", return_value=True),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            t1 = time.time()
            response = await ac.get("/readyz")
            t2 = time.time()

            # The test will verify that it took >= 4.0 seconds, showing there is NO timeout protecting it!
            assert response.status_code == 200
            assert t2 - t1 >= 4.0
