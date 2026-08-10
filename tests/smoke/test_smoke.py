import pytest
from fastapi.testclient import TestClient

from app.core.config import utcms_config
from app.core.database import async_session_factory
from app.main import app


def test_fastapi_app_boot():
    """Verify FastAPI application boots and health endpoint returns 200."""
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json().get("status") == "ok"


def test_config_loaded():
    """Verify config variables are correctly initialized."""
    assert utcms_config.ENVIRONMENT in ("development", "production", "test", "testing")
    assert utcms_config.CAPTCHA_PROVIDER is not None


@pytest.mark.asyncio
async def test_database_factory():
    """Verify database session factory is callable."""
    assert async_session_factory is not None
    # We don't verify real network connection to Postgres here to keep smoke tests fast
    # but verify the factory function is successfully constructed
    session = async_session_factory()
    assert session is not None
    await session.close()
