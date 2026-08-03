import sys
from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from unittest.mock import AsyncMock, patch

from app.auth_multitenant import create_access_token
from app.main import app


@pytest.fixture(autouse=True)
def mock_external_services():
    """Autouse fixture to mock Redis, Postgres, and external network/lifespan dependencies for unit tests."""
    with (
        patch("app.main.init_db", new_callable=AsyncMock),
        patch("app.core.distributed_traffic.distributed_traffic_controller.initialize", new_callable=AsyncMock),
        patch("app.core.distributed_traffic.distributed_traffic_controller.close", new_callable=AsyncMock),
        patch("app.realtime.events.event_hub.start_subscriber"),
        patch("app.realtime.events.event_hub.stop_subscriber", new_callable=AsyncMock),
        patch("app.services.task_service.task_service._ensure_queue_depth_seeded", new_callable=AsyncMock),
        patch("app.core.rate_limiter.rate_limiter.close", new_callable=AsyncMock),
        patch("app.auth_multitenant.is_blacklisted", new=AsyncMock(return_value=False)),
        patch("app.automation.worker_proxy.check_proxy_health", new=AsyncMock(return_value=True)),
    ):
        yield


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
