import os
from unittest.mock import patch

import pytest

from app.automation.proxy_rotator import get_proxy_rotator, test_proxy
from app.automation.worker_proxy import clear_proxy_cache, get_worker_proxy_url


def test_clear_proxy_cache_and_dynamic_lookup():
    """Verify clear_proxy_cache invalidates stale cache and re-evaluates reachability."""
    clear_proxy_cache()
    with patch.dict(os.environ, {"WORKER_1_PROXY": "http://172.20.0.1:3128"}):
        with patch("socket.create_connection") as mock_conn:
            mock_conn.side_effect = TimeoutError("Connection timed out")
            # Unreachable -> returns None
            assert get_worker_proxy_url() is None

            # Force clear cache and test reachable case
            clear_proxy_cache()
            from unittest.mock import MagicMock
            mock_conn.side_effect = None
            mock_conn.return_value = MagicMock()
            assert get_worker_proxy_url() == "http://172.20.0.1:3128"


def test_get_proxy_rotator_thread_safety():
    """Verify get_proxy_rotator returns identical singleton instance across threads."""
    import threading

    instances = []

    def _worker():
        instances.append(get_proxy_rotator())

    threads = [threading.Thread(target=_worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(instances) == 10
    first = instances[0]
    assert all(inst is first for inst in instances)


@pytest.mark.asyncio
async def test_proxy_empty_or_malformed_url():
    """Verify test_proxy handles empty and malformed proxy strings safely without raising IndexError."""
    assert await test_proxy("") is False
    assert await test_proxy("   ") is False
