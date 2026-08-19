import json
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.automation.clean_ip_pool import (
    CleanIPPoolManager,
    CleanIPRecord,
    is_valid_port,
    is_valid_public_ip,
    probe_single_proxy,
)
from app.automation.worker_proxy import (
    ProxyUnavailableError,
    clear_proxy_cache,
    get_best_egress_proxy,
    get_worker_proxy_url,
)
from app.core.circuit_breaker import check_and_report_failure


def test_clean_ip_record_basics():
    rec = CleanIPRecord(
        url="http://user:pass@185.100.47.106:8080",
        protocol="http",
        ip="185.100.47.106",
        port=8080,
        country="IR",
        isp="MCI",
        latency_ms=120.5,
    )
    assert rec.safe_url == "http://185.100.47.106:8080"
    assert rec.is_usable is True

    # High fail count -> not usable
    rec.fail_count = 3
    assert rec.is_usable is False
    rec.fail_count = 0

    # Blocked until future -> not usable
    rec.blocked_until = time.time() + 1000
    assert rec.is_usable is False

    # Serialization
    data = rec.to_dict()
    restored = CleanIPRecord.from_dict(data)
    assert restored.url == rec.url
    assert restored.latency_ms == 120.5


def test_is_valid_public_ip_and_port():
    assert is_valid_public_ip("185.100.47.106") is True
    assert is_valid_public_ip("5.56.132.26") is True
    assert is_valid_public_ip("127.0.0.1") is False  # Loopback
    assert is_valid_public_ip("192.168.1.1") is False  # Private RFC1918
    assert is_valid_public_ip("10.0.0.1") is False  # Private RFC1918
    assert is_valid_public_ip("172.20.0.1") is False  # Docker bridge
    assert is_valid_public_ip("invalid_ip") is False

    assert is_valid_port(80) is True
    assert is_valid_port(8080) is True
    assert is_valid_port(65535) is True
    assert is_valid_port(0) is False
    assert is_valid_port(70000) is False
    assert is_valid_port("invalid") is False


def test_probe_single_proxy_success():
    candidate = CleanIPRecord(
        url="http://185.100.47.106:8080",
        ip="185.100.47.106",
        port=8080,
    )

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.build_opener") as mock_opener:
        mock_instance = MagicMock()
        mock_instance.open.return_value = mock_resp
        mock_opener.return_value = mock_instance

        res = probe_single_proxy(candidate, target_url="https://utcms.ir", timeout=2.0)
        assert res is not None
        assert res.fail_count == 0
        assert res.latency_ms > 0
        assert res.score >= 20.0


def test_probe_single_proxy_failure():
    candidate = CleanIPRecord(
        url="http://185.100.47.106:8080",
        ip="185.100.47.106",
        port=8080,
    )

    with patch("urllib.request.build_opener") as mock_opener:
        mock_instance = MagicMock()
        mock_instance.open.side_effect = TimeoutError("Connection timed out")
        mock_opener.return_value = mock_instance

        res = probe_single_proxy(candidate, target_url="https://utcms.ir", timeout=2.0)
        assert res is None
        assert candidate.fail_count == 1


@pytest.mark.asyncio
async def test_clean_ip_pool_manager_redis_and_fallback():
    pool_mgr = CleanIPPoolManager()

    mock_redis = AsyncMock()
    sample_records = [
        {"url": "http://185.100.47.106:8080", "protocol": "http", "ip": "185.100.47.106", "port": 8080, "score": 95.0, "latency_ms": 50.0, "fail_count": 0, "blocked_until": 0.0},
        {"url": "http://5.56.132.26:3128", "protocol": "http", "ip": "5.56.132.26", "port": 3128, "score": 85.0, "latency_ms": 110.0, "fail_count": 0, "blocked_until": 0.0},
    ]
    mock_redis.get.return_value = json.dumps(sample_records)
    mock_redis.exists.return_value = False

    with patch("app.core.redis_client.redis_manager.get", return_value=mock_redis):
        # Force cache expire
        pool_mgr._local_cache = []
        pool_mgr._local_cache_time = 0.0

        records = await pool_mgr.get_all_clean_ips()
        assert len(records) == 2
        assert records[0].url == "http://185.100.47.106:8080"

        best_url = await pool_mgr.get_clean_ip()
        assert best_url == "http://185.100.47.106:8080"
        pool_mgr.clear_local_cache()


@pytest.mark.asyncio
async def test_clean_ip_pool_manager_mark_blocked():
    pool_mgr = CleanIPPoolManager()
    pool_mgr.clear_local_cache()
    mock_redis = AsyncMock()

    with patch("app.core.redis_client.redis_manager.get", return_value=mock_redis):
        await pool_mgr.mark_blocked("http://185.100.47.106:8080", duration_seconds=600)
        assert mock_redis.set.called
        pool_mgr.clear_local_cache()


def test_worker_proxy_fallback_to_clean_pool():
    clear_proxy_cache()

    with patch.dict(
        os.environ,
        {
            "WORKER_ID": "1",
            "WORKER_1_PROXY": "http://172.20.0.1:3128",
            "EGRESS_PROXY_MODE": "worker_first",
            "ENVIRONMENT": "development",
        },
    ):
        with patch("socket.create_connection") as mock_conn:
            # Worker Squid is down
            mock_conn.side_effect = TimeoutError("Squid down")

            # Clean IP pool has a verified proxy
            with patch("app.automation.clean_ip_pool.clean_ip_pool.get_clean_ip_sync", return_value="http://185.100.47.106:8080"):
                url = get_worker_proxy_url()
                assert url == "http://185.100.47.106:8080"


def test_worker_proxy_clean_pool_only_mode():
    clear_proxy_cache()

    with patch.dict(
        os.environ,
        {
            "EGRESS_PROXY_MODE": "clean_pool_only",
            "ENVIRONMENT": "development",
        },
    ):
        with patch("app.automation.clean_ip_pool.clean_ip_pool.get_clean_ip_sync", return_value="http://5.56.132.26:3128"):
            url = get_worker_proxy_url()
            assert url == "http://5.56.132.26:3128"


def test_worker_proxy_fail_closed_in_production_when_all_empty():
    clear_proxy_cache()

    with patch.dict(
        os.environ,
        {
            "WORKER_ID": "1",
            "WORKER_1_PROXY": "http://172.20.0.1:3128",
            "EGRESS_PROXY_MODE": "worker_first",
            "ENVIRONMENT": "production",
            "PROXY_FAIL_CLOSED": "true",
        },
    ):
        with patch("socket.create_connection", side_effect=TimeoutError("Squid down")):
            with patch("app.automation.clean_ip_pool.clean_ip_pool.get_clean_ip_sync", return_value=None):
                with pytest.raises(ProxyUnavailableError):
                    get_best_egress_proxy()


@pytest.mark.asyncio
async def test_circuit_breaker_clean_pool_per_ip_isolation():
    """Verify that an error on a clean pool proxy marks only that proxy blocked, not WORKER_IP_INDEX."""
    mock_redis = AsyncMock()

    with patch("app.core.redis_client.redis_manager.get", return_value=mock_redis):
        with patch("app.automation.clean_ip_pool.clean_ip_pool.mark_blocked", new_callable=AsyncMock) as mock_mark:
            with patch.dict(os.environ, {"WORKER_IP_INDEX": "2"}):
                # Report failure with clean pool proxy
                await check_and_report_failure(
                    error_msg="HTTP 429 Too Many Requests rate limit",
                    egress_source="clean_pool",
                    proxy_url="http://185.100.47.106:8080",
                )

                # The clean proxy is marked blocked
                assert mock_mark.called
                assert mock_mark.call_args[0][0] == "http://185.100.47.106:8080"

                # WORKER_IP_INDEX key was NOT set in Redis
                for call in mock_redis.set.call_args_list:
                    assert "utcms:circuit_breaker:blocked:2" not in str(call)
