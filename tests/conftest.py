import os
import sys
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# The full unit suite is intentionally hermetic. CI may provision PostgreSQL
# and Redis for the dedicated integration job, but forcing those shared
# services into `pytest tests/` makes unrelated unit tests order-dependent.
# Apply these values before importing the application/config singletons.
_running_external_integration_suite = any(
    "tests/test_integration" in argument.replace("\\", "/") for argument in sys.argv
)
if not _running_external_integration_suite:
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"
    os.environ["ENVIRONMENT"] = "test"

from app.auth_multitenant import create_access_token  # noqa: E402
from app.core.rate_limiter import InMemoryRateLimiter, rate_limiter  # noqa: E402
from app.core.redis import redis_manager  # noqa: E402
from app.core.utils import shutdown_async_bridge  # noqa: E402
from app.main import app  # noqa: E402


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
        # pytest-asyncio gives each test its own event loop, and the shared
        # Redis client owns asyncio transports tied to the loop that opened
        # them. Left cached, its sockets outlive that loop and surface as
        # `ResourceWarning: unclosed socket` at an unrelated later test — which,
        # under `filterwarnings = error`, fails whichever test happens to be
        # running when the garbage collector gets to them. Two CI failures were
        # attributed to the wrong tests this way. This must be a *sync* close:
        # the owning loop is already gone by teardown, so nothing can be
        # awaited on it.
        redis_manager.close_sync()
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
