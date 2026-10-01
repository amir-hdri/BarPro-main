from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.automation.clean_ip_pool import probe_and_recover_squid_egress


@pytest.mark.asyncio
async def test_probe_and_recover_squid_egress_success():
    """When Squid returns HTTP 200, any blocked keys in Redis are cleared."""
    fake_redis = MagicMock()
    fake_redis.delete = AsyncMock(return_value=1)
    fake_redis.exists = AsyncMock(return_value=1)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<html><head><title>ورود به سامانه بارنامه</title></head><body>Login</body></html>"

    with (
        patch("app.core.redis_client.redis_manager.get", new=AsyncMock(return_value=fake_redis)),
        patch("app.automation.worker_proxy.invalidate_worker_proxy_cache") as mock_invalidate,
        patch("curl_cffi.requests.Session") as mock_session_cls,
    ):

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_cls.return_value = mock_session

        recovered = await probe_and_recover_squid_egress(worker_id="1")
        assert recovered is True

        # Assert Redis unblock keys were cleared
        assert fake_redis.delete.await_count >= 1
        mock_invalidate.assert_called_once()


@pytest.mark.asyncio
async def test_probe_and_recover_squid_egress_still_blocked():
    """When Squid returns HTTP 444 or fails, keys are not deleted and returns False."""
    fake_redis = MagicMock()
    fake_redis.delete = AsyncMock(return_value=0)

    mock_response = MagicMock()
    mock_response.status_code = 444
    mock_response.text = ""

    with (
        patch("app.core.redis_client.redis_manager.get", new=AsyncMock(return_value=fake_redis)),
        patch("app.automation.worker_proxy.invalidate_worker_proxy_cache") as mock_invalidate,
        patch("curl_cffi.requests.Session") as mock_session_cls,
    ):

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_cls.return_value = mock_session

        recovered = await probe_and_recover_squid_egress(worker_id="1")
        assert recovered is False
        fake_redis.delete.assert_not_called()
        mock_invalidate.assert_not_called()


@pytest.mark.asyncio
async def test_probe_and_recover_squid_egress_exception():
    """When probe raises a transport exception, returns False gracefully."""
    fake_redis = MagicMock()
    fake_redis.delete = AsyncMock(return_value=0)

    with (
        patch("app.core.redis_client.redis_manager.get", new=AsyncMock(return_value=fake_redis)),
        patch("app.automation.worker_proxy.invalidate_worker_proxy_cache") as mock_invalidate,
        patch("curl_cffi.requests.Session", side_effect=Exception("Connection refused")),
    ):

        recovered = await probe_and_recover_squid_egress(worker_id="1")
        assert recovered is False
        fake_redis.delete.assert_not_called()
        mock_invalidate.assert_not_called()
