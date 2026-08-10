from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth_multitenant import create_access_token
from app.core.rate_limiter import InMemoryRateLimiter, rate_limiter
from app.core.utils import shutdown_async_bridge
from app.main import app


@pytest.fixture(autouse=True)
def mock_external_services():
    """Isolate every test from shared infrastructure and rate-limit state.

    API tests must not depend on a live Redis instance merely to pass the HTTP
    middleware. A fresh in-memory limiter per test preserves rate-limit
    semantics while preventing one test's requests from leaking into another.
    """
    previous_rate_limit_backend = rate_limiter._backend
    rate_limiter._backend = InMemoryRateLimiter()
    try:
        with (
            patch("app.main.init_db", new_callable=AsyncMock),
            patch("app.core.distributed_traffic.distributed_traffic_controller.initialize", new_callable=AsyncMock),
            patch("app.core.distributed_traffic.distributed_traffic_controller.close", new_callable=AsyncMock),
            patch("app.core.recovery.recovery_manager.watchdog_loop", new_callable=AsyncMock),
            patch("app.realtime.events.event_hub.start_subscriber"),
            patch("app.realtime.events.event_hub.stop_subscriber", new_callable=AsyncMock),
            patch("app.services.task_service.task_service._ensure_queue_depth_seeded", new_callable=AsyncMock),
            patch("app.core.rate_limiter.rate_limiter.close", new_callable=AsyncMock),
            patch("app.auth_multitenant.is_blacklisted", new=AsyncMock(return_value=False)),
            patch("app.automation.worker_proxy.check_proxy_health", new=AsyncMock(return_value=True)),
        ):
            yield
    finally:
        shutdown_async_bridge()
        rate_limiter._backend = previous_rate_limit_backend


@pytest.fixture
async def async_client():
    """Return an AsyncClient for FastAPI testing."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.fixture
def client_token():
    """Return a valid JWT access token for testing tenant 1."""
    return create_access_token(
        client_id=1,
        client_code="TEST_CLIENT_001",
        email="test@barpro.ir",
        role="client",
    )


@pytest.fixture
def admin_token():
    """Return a valid JWT access token for master admin testing."""
    return create_access_token(
        client_id=0,
        client_code="MASTER_ADMIN",
        email="admin@barpro.ir",
        role="master_admin",
    )
