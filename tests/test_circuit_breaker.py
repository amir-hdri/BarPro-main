import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.circuit_breaker import (
    check_and_report_failure,
    get_next_ip_index_sync,
    get_routed_queue,
)


@pytest.fixture(autouse=True)
def three_ip_indices():
    with patch.dict(os.environ, {"AVAILABLE_IP_INDICES": "1,2,3"}):
        yield


@pytest.fixture(autouse=True)
def clean_redis_cache():
    import app.core.circuit_breaker

    app.core.circuit_breaker._redis_sync_client = None
    yield
    app.core.circuit_breaker._redis_sync_client = None


@pytest.fixture
def mock_redis():
    with patch("redis.Redis.from_url") as mock_from_url:
        mock_client = MagicMock()
        mock_from_url.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_redis_manager():
    with patch("app.core.redis_client.redis_manager.get", new_callable=AsyncMock) as mock_get:
        mock_client = AsyncMock()
        mock_get.return_value = mock_client
        yield mock_client


def test_get_next_ip_index_sync_all_healthy(mock_redis):
    # Mock Redis so that no blocked keys exist
    mock_redis.exists.return_value = False
    mock_redis.incr.return_value = 1  # 1 % 3 = 1 -> selected_ip = healthy_ips[1]

    # healthy_ips = [1, 2, 3]
    # counter = 1 % 3 = 1 -> selected_ip = 2
    ip = get_next_ip_index_sync()
    assert ip == 2

    # Assert exists called for all 3 IPs
    assert mock_redis.exists.call_count == 3
    mock_redis.exists.assert_any_call("utcms:circuit_breaker:blocked:1")
    mock_redis.exists.assert_any_call("utcms:circuit_breaker:blocked:2")
    mock_redis.exists.assert_any_call("utcms:circuit_breaker:blocked:3")


def test_get_next_ip_index_sync_with_blocked(mock_redis):
    # Mock Redis: IP 2 is blocked, others are healthy
    def exists_side_effect(key):
        return key == "utcms:circuit_breaker:blocked:2"

    mock_redis.exists.side_effect = exists_side_effect
    mock_redis.incr.return_value = 0  # 0 % 2 = 0 -> selected_ip = healthy_ips[0] (which is 1)

    # healthy_ips = [1, 3]
    # counter = 0 % 2 = 0 -> selected_ip = 1
    ip = get_next_ip_index_sync()
    assert ip == 1


def test_get_next_ip_index_sync_all_blocked_fallback(mock_redis):
    # Mock Redis: All IPs are blocked
    mock_redis.exists.return_value = True
    mock_redis.incr.return_value = 2  # 2 % 3 = 2 -> selected_ip = healthy_ips[2] (which is 3)

    ip = get_next_ip_index_sync()
    assert ip == 3


def test_get_routed_queue_standard():
    with patch("app.core.circuit_breaker.get_next_ip_index_sync", return_value=2):
        routed = get_routed_queue("waybill_tasks")
        assert routed == "waybill_tasks_2"


def test_get_routed_queue_system_bypass():
    # system queues (rpa_scheduler) should not be routed/suffixed
    routed = get_routed_queue("rpa_scheduler")
    assert routed == "rpa_scheduler"


@pytest.mark.asyncio
async def test_check_and_report_failure_no_match(mock_redis_manager):
    # Try with an error message that does not indicate IP block/timeout
    await check_and_report_failure("Invalid driver national code")

    # Redis set should not have been called
    mock_redis_manager.set.assert_not_called()


@pytest.mark.asyncio
async def test_check_and_report_failure_with_match(mock_redis_manager):
    # Set worker index
    os.environ["WORKER_IP_INDEX"] = "3"

    # Try with a matching error message
    await check_and_report_failure("Connection timed out to gateway server")

    # Redis set should be called for IP index 3
    mock_redis_manager.set.assert_called_once_with("utcms:circuit_breaker:blocked:3", "1", ex=1800)

    # Clean up environment
    os.environ.pop("WORKER_IP_INDEX", None)


def test_get_next_ip_index_sync_custom_indices(mock_redis):
    # Set only 2 IPs in environment
    os.environ["AVAILABLE_IP_INDICES"] = "1,2"
    mock_redis.exists.return_value = False
    mock_redis.incr.return_value = 1  # 1 % 2 = 1 -> selected_ip = healthy_ips[1] (which is 2)

    try:
        ip = get_next_ip_index_sync()
        assert ip == 2

        # Check that only indices 1 and 2 were checked
        assert mock_redis.exists.call_count == 2
        mock_redis.exists.assert_any_call("utcms:circuit_breaker:blocked:1")
        mock_redis.exists.assert_any_call("utcms:circuit_breaker:blocked:2")

        # Ensure index 3 was not checked
        with pytest.raises(AssertionError):
            mock_redis.exists.assert_any_call("utcms:circuit_breaker:blocked:3")
    finally:
        os.environ.pop("AVAILABLE_IP_INDICES", None)
