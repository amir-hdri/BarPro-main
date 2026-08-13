from unittest.mock import MagicMock, patch

import pytest

from app.automation.worker_proxy import check_proxy_health


@pytest.mark.asyncio
async def test_check_proxy_health_success():
    """Ensure check_proxy_health returns True if proxy routes successfully."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {}

    with patch("curl_cffi.requests.Session.get", return_value=mock_response) as mock_get:
        result = await check_proxy_health("http://127.0.0.1:3128")
        assert result is True
        mock_get.assert_called_once()


@pytest.mark.asyncio
async def test_check_proxy_health_failure():
    """Ensure check_proxy_health returns False if proxy connection fails."""
    with patch("curl_cffi.requests.Session.get", side_effect=Exception("Connection refused")):
        result = await check_proxy_health("http://127.0.0.1:3128")
        assert result is False
