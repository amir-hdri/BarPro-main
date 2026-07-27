from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.models_multitenant import Client
from app.schemas.multitenant import ClientResponse
from app.services.client_service import ClientService


@pytest.mark.asyncio
async def test_get_client_profile_success():
    """Test retrieving a client profile successfully."""
    mock_client = Client(
        id=1,
        client_code="tenant-1",
        name="Tenant 1",
        email="tenant1@example.com",
        phone="1234567890",
        max_drivers=10,
        max_plates=10,
        max_concurrent_tasks=2,
        max_daily_tasks=100,
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )

    mock_session = AsyncMock()

    with patch("app.services.client_service.ClientResponse.model_validate") as mock_validate:
        mock_validate.return_value = ClientResponse(
            id=1,
            client_code="tenant-1",
            name="Tenant 1",
            email="tenant1@example.com",
            phone="1234567890",
            status="active",
            access_level="standard",
            max_drivers=10,
            max_plates=10,
            max_concurrent_tasks=2,
            max_daily_tasks=100,
            created_at=datetime.now(UTC).replace(tzinfo=None),
            last_login_at=datetime.now(UTC).replace(tzinfo=None),
        )

        result = await ClientService.get_client_profile(mock_client, mock_session)

        # Verify session refresh was called
        mock_session.refresh.assert_called_once_with(mock_client)

        # Verify model validation was performed
        mock_validate.assert_called_once_with(mock_client)

        # Verify result is correct
        assert isinstance(result, ClientResponse)
        assert result.id == 1
        assert result.client_code == "tenant-1"
        assert result.email == "tenant1@example.com"


@pytest.mark.asyncio
async def test_get_client_profile_with_db_exception():
    """Test retrieving a client profile when the database throws an exception."""
    mock_client = Client(id=1, client_code="tenant-1", name="Tenant 1", email="tenant1@example.com")

    mock_session = AsyncMock()
    # Simulate a database connection error or similar failure
    mock_session.refresh.side_effect = Exception("Database connection error")

    with pytest.raises(Exception, match="Database connection error"):
        await ClientService.get_client_profile(mock_client, mock_session)

    # Verify session refresh was attempted
    mock_session.refresh.assert_called_once_with(mock_client)
