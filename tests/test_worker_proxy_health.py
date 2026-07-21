from unittest.mock import AsyncMock, patch

import pytest

from app.automation.worker_proxy import check_proxy_health


@pytest.mark.asyncio
async def test_check_proxy_health_success():
    """Ensure check_proxy_health returns True if proxy routes successfully."""
    mock_response = AsyncMock()
    mock_response.status_code = 200

    with patch("httpx.AsyncClient.get", return_value=mock_response) as mock_get:
        result = await check_proxy_health("http://127.0.0.1:3128")
        assert result is True
        mock_get.assert_called_once_with("https://barname.utcms.ir/Barname/Account/Login")


@pytest.mark.asyncio
async def test_check_proxy_health_failure():
    """Ensure check_proxy_health returns False if proxy connection fails."""
    with patch("httpx.AsyncClient.get", side_effect=Exception("Connection refused")):
        result = await check_proxy_health("http://127.0.0.1:3128")
        assert result is False
