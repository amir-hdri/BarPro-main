from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.auth_multitenant import get_current_client, get_current_user_or_admin
from app.core.database import get_session
from app.main import app
from app.models_multitenant import Client, Driver


@pytest.fixture
def test_client():
    return TestClient(app)


def test_create_driver_success(test_client):
    mock_client = Client(
        id=1,
        client_code="tenant-1",
        name="Tenant 1",
        email="tenant1@example.com",
        max_drivers=10,
    )

    # Needs to be a mock object but not necessarily AsyncMock for sync methods like add
    mock_session = MagicMock()
    mock_session.exec = AsyncMock()
    mock_session.commit = AsyncMock()

    # Mock for existing drivers count -> returns 0
    mock_existing_drivers = MagicMock()
    mock_existing_drivers.one.return_value = 0

    # Mock for existing national code -> returns None
    mock_existing_national_code = MagicMock()
    mock_existing_national_code.first.return_value = None

    mock_session.exec.side_effect = [
        mock_existing_drivers,
        mock_existing_national_code,
    ]

    # Ensure refresh populates ID since the response needs it
    async def mock_refresh(instance):
        instance.id = 1

    mock_session.refresh = AsyncMock(side_effect=mock_refresh)

    app.dependency_overrides[get_current_client] = lambda: mock_client
    app.dependency_overrides[get_current_user_or_admin] = lambda: {"role": "client", "user": mock_client}
    app.dependency_overrides[get_session] = lambda: mock_session

    payload = {
        "driver_national_code": "1234567890",
        "full_name": "Test Driver",
        "phone": "09123456789",
        "utcms_username": "testuser",
        "utcms_password": "testpassword",
    }

    response = test_client.post("/api/v1/drivers", json=payload)

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["id"] == 1
    assert data["client_id"] == 1
    assert data["driver_national_code"] == payload["driver_national_code"]
    assert data["full_name"] == payload["full_name"]
    assert data["utcms_username"] == payload["utcms_username"]

    # Ensure add and commit were called
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()
    mock_session.refresh.assert_called_once()

    app.dependency_overrides.clear()


def test_create_driver_limit_reached(test_client):
    mock_client = Client(
        id=1,
        client_code="tenant-1",
        name="Tenant 1",
        email="tenant1@example.com",
        max_drivers=1,
    )

    mock_session = MagicMock()
    mock_session.exec = AsyncMock()
    mock_session.commit = AsyncMock()

    # Mock for existing drivers count
    mock_existing_drivers = MagicMock()
    mock_existing_drivers.one.return_value = 1
    mock_session.exec.return_value = mock_existing_drivers

    app.dependency_overrides[get_current_client] = lambda: mock_client
    app.dependency_overrides[get_current_user_or_admin] = lambda: {"role": "client", "user": mock_client}
    app.dependency_overrides[get_session] = lambda: mock_session

    payload = {
        "driver_national_code": "1234567890",
        "full_name": "Test Driver",
        "phone": "09123456789",
        "utcms_username": "testuser",
        "utcms_password": "testpassword",
    }

    response = test_client.post("/api/v1/drivers", json=payload)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "limit reached" in response.json()["message"].lower()

    mock_session.add.assert_not_called()
    mock_session.commit.assert_not_called()

    app.dependency_overrides.clear()


def test_create_driver_duplicate_national_code(test_client):
    mock_client = Client(
        id=1,
        client_code="tenant-1",
        name="Tenant 1",
        email="tenant1@example.com",
        max_drivers=10,
    )

    mock_session = MagicMock()
    mock_session.exec = AsyncMock()
    mock_session.commit = AsyncMock()

    # Mock for existing drivers count
    mock_existing_drivers = MagicMock()
    mock_existing_drivers.one.return_value = 0

    # Mock for existing national code -> returns a driver
    mock_existing_national_code = MagicMock()
    mock_existing_national_code.first.return_value = Driver()

    mock_session.exec.side_effect = [
        mock_existing_drivers,
        mock_existing_national_code,
    ]

    app.dependency_overrides[get_current_client] = lambda: mock_client
    app.dependency_overrides[get_current_user_or_admin] = lambda: {"role": "client", "user": mock_client}
    app.dependency_overrides[get_session] = lambda: mock_session


    payload = {
        "driver_national_code": "1234567890",
        "full_name": "Test Driver",
        "phone": "09123456789",
        "utcms_username": "testuser",
        "utcms_password": "testpassword",
    }

    response = test_client.post("/api/v1/drivers", json=payload)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert "already exists" in response.json()["message"].lower()

    mock_session.add.assert_not_called()
    mock_session.commit.assert_not_called()

    app.dependency_overrides.clear()


def test_list_drivers_success(test_client):
    mock_client = Client(
        id=1,
        client_code="tenant-1",
        name="Tenant 1",
        email="tenant1@example.com",
    )

    mock_session = MagicMock()
    mock_session.exec = AsyncMock()

    mock_driver = Driver(
        id=1,
        client_id=1,
        driver_national_code="1234567890",
        full_name="Test Driver",
        phone="09123456789",
        license_number="123456",
        utcms_username="testuser",
        status="active",
    )

    mock_result = MagicMock()
    mock_result.all.return_value = [mock_driver]
    mock_session.exec.return_value = mock_result

    app.dependency_overrides[get_current_client] = lambda: mock_client
    app.dependency_overrides[get_current_user_or_admin] = lambda: {"role": "client", "user": mock_client}
    app.dependency_overrides[get_session] = lambda: mock_session

    response = test_client.get("/api/v1/drivers")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == 1
    assert data[0]["full_name"] == "Test Driver"

    mock_session.exec.assert_called_once()

    app.dependency_overrides.clear()


def test_list_drivers_with_status_filter(test_client):
    mock_client = Client(
        id=1,
        client_code="tenant-1",
        name="Tenant 1",
        email="tenant1@example.com",
    )

    mock_session = MagicMock()
    mock_session.exec = AsyncMock()

    mock_driver = Driver(
        id=1,
        client_id=1,
        driver_national_code="1234567890",
        full_name="Test Driver",
        phone="09123456789",
        license_number="123456",
        utcms_username="testuser",
        status="active",
    )

    mock_result = MagicMock()
    mock_result.all.return_value = [mock_driver]
    mock_session.exec.return_value = mock_result

    app.dependency_overrides[get_current_client] = lambda: mock_client
    app.dependency_overrides[get_current_user_or_admin] = lambda: {"role": "client", "user": mock_client}
    app.dependency_overrides[get_session] = lambda: mock_session

    response = test_client.get("/api/v1/drivers?status_filter=active")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["status"] == "active"

    mock_session.exec.assert_called_once()

    app.dependency_overrides.clear()
