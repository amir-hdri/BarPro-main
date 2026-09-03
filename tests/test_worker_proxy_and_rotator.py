import os
import time
from unittest.mock import patch

import pytest

from app.automation import test_proxy
from app.automation.proxy_rotator import get_proxy_rotator
from app.automation.worker_proxy import clear_proxy_cache, get_worker_proxy_url


def test_clear_proxy_cache_and_dynamic_lookup():
    """Verify clear_proxy_cache invalidates stale cache and re-evaluates reachability."""
    # Force development mode for fail-open behavior (return None on unreachable)
    clear_proxy_cache()
    with patch.dict(os.environ, {"WORKER_1_PROXY": "http://172.20.0.1:3128", "ENVIRONMENT": "development"}):
        with (
            patch("socket.create_connection") as mock_conn,
            patch("app.automation.clean_ip_pool.clean_ip_pool.get_clean_ip_sync", return_value=None),
        ):
            mock_conn.side_effect = TimeoutError("Connection timed out")
            # Unreachable -> returns None in dev mode (fail-open)
            assert get_worker_proxy_url() is None

            # Force clear cache and test reachable case
            clear_proxy_cache()
            from unittest.mock import MagicMock

            mock_conn.side_effect = None
            mock_conn.return_value = MagicMock()
            assert get_worker_proxy_url() == "http://172.20.0.1:3128"


def test_get_worker_proxy_url_fail_closed_in_production():
    """Verify fail-closed behavior in production when proxy is unreachable."""
    from app.automation.worker_proxy import ProxyUnavailableError

    clear_proxy_cache()
    with patch.dict(
        os.environ,
        {"WORKER_1_PROXY": "http://172.20.0.1:3128", "ENVIRONMENT": "production", "PROXY_FAIL_CLOSED": "true"},
    ):
        with (
            patch("socket.create_connection") as mock_conn,
            patch("app.automation.clean_ip_pool.clean_ip_pool.get_clean_ip_sync", return_value=None),
        ):
            mock_conn.side_effect = TimeoutError("Connection timed out")
            with pytest.raises(ProxyUnavailableError):
                get_worker_proxy_url()


def test_get_worker_proxy_url_clean_pool_fallback():
    """Verify fallback to clean IP pool when worker Squid is unreachable."""
    clear_proxy_cache()
    with patch.dict(os.environ, {"WORKER_1_PROXY": "http://172.20.0.1:3128", "ENVIRONMENT": "production"}):
        with (
            patch("socket.create_connection") as mock_conn,
            patch("app.automation.clean_ip_pool.clean_ip_pool.get_clean_ip_sync", return_value="http://10.0.0.1:3128"),
        ):
            mock_conn.side_effect = TimeoutError("Connection timed out")
            assert get_worker_proxy_url() == "http://10.0.0.1:3128"


def test_worker_proxy_cache_follows_clean_pool_refresh_window():
    """A proxy remains assigned between pool refreshes, then is reselected."""
    import app.automation.worker_proxy as wp

    clear_proxy_cache()
    with patch.dict(os.environ, {"ENVIRONMENT": "production", "PROXY_FAIL_CLOSED": "true"}):
        with (
            patch.object(wp.utcms_config, "EGRESS_PROXY_MODE", "clean_pool_only"),
            patch.object(wp.utcms_config, "CLEAN_IP_PROBE_INTERVAL_SECONDS", 180),
            patch("app.automation.clean_ip_pool.clean_ip_pool.get_clean_ip_sync", side_effect=[
                "http://185.100.47.106:8080",
                "http://5.56.132.26:3128",
            ]) as select_proxy,
        ):
            first = get_worker_proxy_url()
            wp._cached_proxy_timestamp = time.time() - 179
            second = get_worker_proxy_url()
            assert first == second == "http://185.100.47.106:8080"
            select_proxy.assert_called_once()

            wp._cached_proxy_timestamp = time.time() - 181
            third = get_worker_proxy_url()
            assert third == "http://5.56.132.26:3128"
            assert select_proxy.call_count == 2


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


@pytest.mark.asyncio
async def test_proxy_health_check_supports_socks_via_curl_cffi():
    """The Worker checker must use the same SOCKS-capable transport as pool screening."""
    from unittest.mock import MagicMock, patch

    response = MagicMock(status_code=200)
    with patch("curl_cffi.requests.get", return_value=response) as get:
        assert await test_proxy("socks4://192.0.2.10:8080") is True

    get.assert_called_once()
    assert get.call_args.kwargs["proxy"] == "socks4://192.0.2.10:8080"
    assert get.call_args.kwargs["impersonate"] == "chrome120"


@pytest.mark.asyncio
async def test_get_next_require_iran_ip_does_not_grow_pool():
    """Clean IP Pool fallback proxies must be ephemeral — never appended to the persistent rotator pool."""
    from app.automation.clean_ip_pool import CleanIPRecord
    from app.automation.proxy_rotator import ProxyRotator

    rotator = ProxyRotator(require_iran_ip=True)
    assert rotator.proxies == []

    verified_record = CleanIPRecord(
        url="http://185.100.47.106:8080", ip="185.100.47.106", port=8080, observed_country="IR", egress_verified=True
    )

    with patch(
        "app.automation.clean_ip_pool.clean_ip_pool.get_clean_record_sync",
        return_value=verified_record,
    ):
        result = await rotator.get_next(require_iran_ip=True)

    assert result is not None
    assert result.url == "http://185.100.47.106:8080"
    assert rotator.proxies == []  # pool must not grow with ephemeral clean-pool entries

    with patch(
        "app.automation.clean_ip_pool.clean_ip_pool.get_clean_record_sync",
        return_value=None,
    ):
        result = await rotator.get_next(require_iran_ip=True)
    assert result is None
    assert rotator.proxies == []
