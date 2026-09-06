from unittest.mock import MagicMock, patch

import pytest

from app.automation.worker_proxy import check_proxy_health
from app.core.config import utcms_config


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
        assert mock_get.call_args.args[0] == "https://utcms.ir"


@pytest.mark.asyncio
async def test_check_proxy_health_default_does_not_follow_login_url():
    """A login-route change must not turn the tunnel probe into a session probe."""
    mock_response = MagicMock(status_code=200, headers={})
    original_login_url = utcms_config.LOGIN_URL
    utcms_config.LOGIN_URL = "https://barname.utcms.ir/Barname/Account/Login"
    try:
        with patch("curl_cffi.requests.Session.get", return_value=mock_response) as mock_get:
            assert await check_proxy_health("http://127.0.0.1:3128") is True
            assert mock_get.call_args.args[0] == "https://utcms.ir"
    finally:
        utcms_config.LOGIN_URL = original_login_url


@pytest.mark.asyncio
async def test_check_proxy_health_does_not_classify_upstream_status_as_proxy_failure():
    """An upstream UTCMS response is still tunnel evidence when Squid reports no error."""
    mock_response = MagicMock(status_code=408, headers={})
    with patch("curl_cffi.requests.Session.get", return_value=mock_response):
        assert await check_proxy_health("http://127.0.0.1:3128") is True


@pytest.mark.asyncio
async def test_check_proxy_health_failure():
    """Ensure check_proxy_health returns False if proxy connection fails."""
    with patch("curl_cffi.requests.Session.get", side_effect=Exception("Connection refused")):
        result = await check_proxy_health("http://127.0.0.1:3128")
        assert result is False
