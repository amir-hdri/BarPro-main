import contextlib
import importlib.util
import json
import logging
import os
import time
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.automation import clean_ip_pool as cip
from app.automation.clean_ip_pool import (
    CleanIPPoolManager,
    CleanIPRecord,
    _dedupe_candidates,
    _is_safe_source_url,
    _parse_proxy_line,
    atomic_write,
    classify_probe_response,
    fetch_file_or_env_sources,
    is_valid_port,
    is_valid_public_ip,
    probe_single_proxy,
)
from app.automation.worker_proxy import (
    ProxyUnavailableError,
    _resolve_to_ip,
    clear_proxy_cache,
    get_best_egress_proxy,
    get_playwright_proxy,
    get_worker_proxy_url,
    invalidate_worker_proxy_cache,
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

    # Serialization round-trip (incl. new egress fields)
    rec.observed_country = "IR"
    rec.egress_verified = True
    data = rec.to_dict()
    restored = CleanIPRecord.from_dict(data)
    assert restored is not None
    assert restored.url == rec.url
    assert restored.latency_ms == 120.5
    assert restored.observed_country == "IR"
    assert restored.egress_verified is True


def test_from_dict_validates_and_rejects_malformed_state():
    """Malformed Redis/file state must never re-enter the runtime pool."""
    assert CleanIPRecord.from_dict(None) is None
    assert CleanIPRecord.from_dict("garbage") is None  # type: ignore[arg-type]
    assert CleanIPRecord.from_dict({"url": "", "ip": "1.2.3.4", "port": 80}) is None
    assert CleanIPRecord.from_dict({"url": "ftp://x:1", "protocol": "ftp", "ip": "1.2.3.4", "port": 21}) is None
    assert (
        CleanIPRecord.from_dict({"url": "http://127.0.0.1:8080", "protocol": "http", "ip": "127.0.0.1", "port": 8080})
        is None
    )
    assert (
        CleanIPRecord.from_dict({"url": "http://1.2.3.4:99999", "protocol": "http", "ip": "1.2.3.4", "port": "bad"})
        is None
    )

    ok = CleanIPRecord.from_dict(
        {"url": "socks5://5.56.132.26:1080", "protocol": "SOCKS5", "ip": "5.56.132.26", "port": "1080"}
    )
    assert ok is not None
    assert ok.protocol == "socks5"
    assert ok.port == 1080


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


def test_safe_source_url_rejects_private_hosts_and_credentials():
    public_address = [(None, None, None, None, ("185.100.47.106", 443))]
    private_address = [(None, None, None, None, ("127.0.0.1", 443))]

    with patch("socket.getaddrinfo", return_value=public_address):
        assert _is_safe_source_url("https://feeds.example/proxies.txt") is True
        assert _is_safe_source_url("https://user:secret@feeds.example/proxies.txt") is False
    with patch("socket.getaddrinfo", return_value=private_address):
        assert _is_safe_source_url("https://internal.example/proxies.txt") is False


def test_atomic_write_uses_owner_only_permissions(tmp_path):
    target = tmp_path / "proxy-state.txt"
    atomic_write(str(target), "http://user:secret@185.100.47.106:8080\n")
    assert target.stat().st_mode & 0o777 == 0o600


# ---------------------------------------------------------------------------
# Dedup: identity is protocol + ip + port; country is NEVER defaulted to IR
# ---------------------------------------------------------------------------


def test_dedupe_keeps_http_and_socks_as_independent_candidates():
    items = [
        {"protocol": "http", "ip": "185.100.47.106", "port": 8080, "source": "a"},
        {"protocol": "socks5", "ip": "185.100.47.106", "port": 8080, "source": "b"},
    ]
    deduped = _dedupe_candidates(items)
    assert set(deduped.keys()) == {"http://185.100.47.106:8080", "socks5://185.100.47.106:8080"}


def test_dedupe_does_not_default_country_to_ir():
    """Global-mirror entries without country metadata must stay UNKNOWN."""
    items = [
        {"protocol": "http", "ip": "185.100.47.106", "port": 8080, "source": "global_mirror"},
    ]
    rec = _dedupe_candidates(items)["http://185.100.47.106:8080"]
    assert rec.country == ""
    assert rec.city is None

    declared = _dedupe_candidates(
        [{"protocol": "http", "ip": "5.56.132.26", "port": 3128, "country": "IR", "city": "Tehran"}]
    )["http://5.56.132.26:3128"]
    assert declared.country == "IR"


def test_dedupe_drops_invalid_entries():
    items = [
        {"protocol": "http", "ip": "10.0.0.5", "port": 80},  # private
        {"protocol": "gopher", "ip": "1.2.3.4", "port": 70},  # unsupported proto
        {"protocol": "http", "ip": "1.2.3.4", "port": 0},  # invalid port
    ]
    assert _dedupe_candidates(items) == {}


# ---------------------------------------------------------------------------
# Probe classification: dead vs UTCMS-rejected vs WAF challenge vs healthy
# ---------------------------------------------------------------------------


def test_classify_probe_response_matrix():
    assert classify_probe_response(200, "<html>utcms portal</html>") == "healthy"
    assert classify_probe_response(301, "") == "healthy"
    assert classify_probe_response(200, "Just a moment... enabling JavaScript") == "waf_challenge"
    assert classify_probe_response(200, "Access Denied — captcha required") == "waf_challenge"
    assert classify_probe_response(403, "") == "target_rejected"
    assert classify_probe_response(429, "rate limit") == "target_rejected"
    # A cold issuance deep-link can return 408 even for a healthy IP. It is a
    # transient target/session verdict, never proof that the IP is blocked.
    assert classify_probe_response(408, "") == "target_unavailable"
    assert classify_probe_response(500, "") == "target_unavailable"
    assert classify_probe_response(None, "") == "unacceptable"


def test_probe_defaults_to_stable_login_path_not_issuance_deep_link():
    """Anonymous screening cannot reproduce the authenticated menu flow."""
    candidate = CleanIPRecord(url="http://185.100.47.106:8080", ip="185.100.47.106", port=8080)

    with (
        patch("app.automation.clean_ip_pool._CURL_CFFI_IMPORT_ERROR", None),
        patch("app.automation.clean_ip_pool._probe_via_curl_cffi", return_value=(200, 90.0, "ok")) as probe,
    ):
        probe_single_proxy(candidate)

    assert probe.call_args[0][1] == cip.LOGIN_PROBE_URL
    assert "/Barname/Account/Login" in probe.call_args[0][1]
    assert probe.call_args[0][1] != cip.ISSUANCE_PROBE_URL


def test_probe_single_proxy_success_via_chrome_fingerprint():
    candidate = CleanIPRecord(url="http://185.100.47.106:8080", ip="185.100.47.106", port=8080)

    with (
        patch("app.automation.clean_ip_pool._CURL_CFFI_IMPORT_ERROR", None),
        patch("app.automation.clean_ip_pool._probe_via_curl_cffi", return_value=(200, 142.0, "<html>ok</html>")),
    ):
        res = probe_single_proxy(candidate, target_url="https://utcms.ir", timeout=2.0)

    assert res is candidate
    assert res.fail_count == 0
    assert res.latency_ms == 142.0
    assert res.score >= 20.0


def test_probe_single_proxy_403_is_target_rejection_not_dead_proxy():
    """HTTP 403 from UTCMS means the TARGET refused this IP — the strongest
    possible signal that the address must NOT be stored as working."""
    candidate = CleanIPRecord(url="http://185.100.47.106:8080", ip="185.100.47.106", port=8080, score=100.0)

    with (
        patch("app.automation.clean_ip_pool._CURL_CFFI_IMPORT_ERROR", None),
        patch("app.automation.clean_ip_pool._probe_via_curl_cffi", return_value=(403, 88.0, "")),
    ):
        res = probe_single_proxy(candidate, target_url="https://utcms.ir", timeout=2.0)

    assert res is None
    assert candidate.fail_count == 1
    assert candidate.score == 50.0  # -50 penalty for target rejection
    assert "utcms_rejected" in candidate.tags


def test_probe_single_proxy_waf_challenge_200_page_not_operational():
    """HTTP 200 whose body is a WAF/block page is NOT an operational proxy."""
    candidate = CleanIPRecord(url="http://185.100.47.106:8080", ip="185.100.47.106", port=8080, score=100.0)

    with (
        patch("app.automation.clean_ip_pool._CURL_CFFI_IMPORT_ERROR", None),
        patch(
            "app.automation.clean_ip_pool._probe_via_curl_cffi",
            return_value=(200, 120.0, "just a moment... checking your browser"),
        ),
    ):
        res = probe_single_proxy(candidate, target_url="https://utcms.ir", timeout=2.0)

    assert res is None
    assert "waf_challenge" in candidate.tags
    assert candidate.score == 50.0


def test_probe_single_proxy_408_is_transient_not_ip_rejection():
    candidate = CleanIPRecord(url="http://185.100.47.106:8080", ip="185.100.47.106", port=8080, score=100.0)

    with (
        patch("app.automation.clean_ip_pool._CURL_CFFI_IMPORT_ERROR", None),
        patch("app.automation.clean_ip_pool._probe_via_curl_cffi", return_value=(408, 75.0, "")),
    ):
        res = probe_single_proxy(candidate, timeout=2.0)

    assert res is None
    assert candidate.score == 95.0
    assert "target_unavailable" in candidate.tags
    assert "utcms_rejected" not in candidate.tags


def test_probe_single_proxy_transport_failure_counts_as_dead():
    candidate = CleanIPRecord(url="http://185.100.47.106:8080", ip="185.100.47.106", port=8080)

    with (
        patch("app.automation.clean_ip_pool._CURL_CFFI_IMPORT_ERROR", None),
        patch("app.automation.clean_ip_pool._probe_via_curl_cffi", side_effect=TimeoutError("timed out")),
    ):
        res = probe_single_proxy(candidate, target_url="https://utcms.ir", timeout=2.0)

    assert res is None
    assert candidate.fail_count == 1


def test_probe_urllib_fallback_only_for_http_and_skips_socks():
    candidate_socks = CleanIPRecord(url="socks5://5.56.132.26:1080", protocol="socks5", ip="5.56.132.26", port=1080)
    candidate_http = CleanIPRecord(url="http://185.100.47.106:8080", ip="185.100.47.106", port=8080)

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp

    with (
        patch("app.automation.clean_ip_pool._CURL_CFFI_IMPORT_ERROR", "unavailable"),
        patch("urllib.request.build_opener") as mock_opener,
    ):
        mock_instance = MagicMock()
        mock_instance.open.return_value = mock_resp
        mock_opener.return_value = mock_instance

        # SOCKS cannot be probed by urllib — skipped instead of misjudged dead-by-timeout
        assert probe_single_proxy(candidate_socks, timeout=2.0) is None
        mock_instance.open.assert_not_called()

        res = probe_single_proxy(candidate_http, target_url="https://utcms.ir", timeout=2.0)
        assert res is candidate_http
        assert res.fail_count == 0


def test_probe_success_clears_previous_rejection_tag():
    candidate = CleanIPRecord(url="http://185.100.47.106:8080", ip="185.100.47.106", port=8080, tags=["utcms_rejected"])
    with (
        patch("app.automation.clean_ip_pool._CURL_CFFI_IMPORT_ERROR", None),
        patch("app.automation.clean_ip_pool._probe_via_curl_cffi", return_value=(200, 90.0, "fine")),
    ):
        res = probe_single_proxy(candidate, timeout=2.0)
    assert res is not None
    assert "utcms_rejected" not in candidate.tags


# ---------------------------------------------------------------------------
# Egress verification: measured country beats declared country
# ---------------------------------------------------------------------------


def test_screening_demotes_measured_non_iranian_egress():
    """A source-declared 'IR' proxy whose REAL egress measures as US must be dropped."""
    rec = CleanIPRecord(url="http://185.100.47.106:8080", ip="185.100.47.106", port=8080, country="IR")
    rec.latency_ms = 100.0

    with (
        patch.object(cip, "aggregate_all_candidates", return_value=[rec]),
        patch.object(cip, "probe_single_proxy", return_value=rec),
        patch.object(cip, "_verify_egress_country", return_value="US"),
        patch.object(cip, "atomic_write"),
    ):
        verified = cip.run_screening_cycle(max_pool_size=10)

    assert verified == []
    assert "non_iranian_egress" in rec.tags


def test_screening_keeps_measured_iranian_egress_and_marks_verified():
    rec = CleanIPRecord(url="http://185.100.47.106:8080", ip="185.100.47.106", port=8080, country="")
    rec.latency_ms = 100.0

    with (
        patch.object(cip, "aggregate_all_candidates", return_value=[rec]),
        patch.object(cip, "probe_single_proxy", return_value=rec),
        patch.object(cip, "_verify_egress_country", return_value="IR"),
        patch.object(cip, "atomic_write"),
    ):
        verified = cip.run_screening_cycle(max_pool_size=10)

    assert len(verified) == 1
    assert rec.egress_verified is True
    assert rec.observed_country == "IR"


def test_screening_rejects_geo_unverified_candidate():
    """A missing GeoIP result is fail-closed for production registration."""
    rec = CleanIPRecord(url="http://185.100.47.106:8080", ip="185.100.47.106", port=8080, country="IR")

    with (
        patch.object(cip, "aggregate_all_candidates", return_value=[rec]),
        patch.object(cip, "probe_single_proxy", return_value=rec),
        patch.object(cip, "_verify_egress_country", return_value=None),
        patch.object(cip, "atomic_write"),
    ):
        verified = cip.run_screening_cycle(max_pool_size=10)

    assert verified == []
    assert rec.egress_verified is False
    assert rec.has_measured_iranian_egress is False
    assert "geo_unverified" in rec.tags


def test_screening_drops_unverified_even_when_measured_proxy_is_slower():
    """Production registration never falls back to unknown geography."""
    measured = CleanIPRecord(url="http://185.100.47.106:8080", ip="185.100.47.106", port=8080)
    measured.latency_ms = 900.0
    unmeasured = CleanIPRecord(url="http://46.209.30.11:8080", ip="46.209.30.11", port=8080)
    unmeasured.latency_ms = 50.0

    def _geo(candidate, timeout=8.0):
        return "IR" if candidate.url == measured.url else None

    with (
        patch.object(cip, "aggregate_all_candidates", return_value=[measured, unmeasured]),
        patch.object(cip, "probe_single_proxy", side_effect=lambda c, *a, **k: c),
        patch.object(cip, "_verify_egress_country", side_effect=_geo),
        patch.object(cip, "atomic_write"),
    ):
        verified = cip.run_screening_cycle(max_pool_size=10)

    assert [r.url for r in verified] == [measured.url]


def test_zero_result_screening_invalidates_all_runtime_fallbacks():
    with (
        patch.object(cip, "aggregate_all_candidates", return_value=[]),
        patch.object(cip, "atomic_write") as write,
    ):
        assert cip.run_screening_cycle(max_pool_size=10) == []

    assert write.call_args_list == [
        call(cip.FILE_BEST_TXT, ""),
        call(cip.FILE_WORKING_TXT, ""),
        call(cip.FILE_WORKING_JSON, "[]\n"),
    ]


# ---------------------------------------------------------------------------
# Manager: rotation, blocked-skip, staleness kick, cache invalidation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clean_ip_pool_manager_redis_and_fallback():
    pool_mgr = CleanIPPoolManager()
    pool_mgr.clear_local_cache()

    mock_redis = AsyncMock()
    sample_records = [
        {
            "url": "http://185.100.47.106:8080",
            "protocol": "http",
            "ip": "185.100.47.106",
            "port": 8080,
            "score": 95.0,
            "latency_ms": 50.0,
            "fail_count": 0,
            "blocked_until": 0.0,
            "observed_country": "IR",
            "egress_verified": True,
        },
        {
            "url": "http://5.56.132.26:3128",
            "protocol": "http",
            "ip": "5.56.132.26",
            "port": 3128,
            "score": 85.0,
            "latency_ms": 110.0,
            "fail_count": 0,
            "blocked_until": 0.0,
            "observed_country": "IR",
            "egress_verified": True,
        },
    ]
    mock_redis.get.side_effect = [json.dumps(sample_records), str(time.time())]
    mock_redis.exists.return_value = False

    with patch("app.core.redis_client.redis_manager.get", return_value=mock_redis):
        pool_mgr._local_cache = []
        pool_mgr._local_cache_time = 0.0

        records = await pool_mgr.get_all_clean_ips()
        assert len(records) == 2
        assert records[0].url == "http://185.100.47.106:8080"

        best_url = await pool_mgr.get_clean_ip()
        assert best_url == "http://185.100.47.106:8080"
        pool_mgr.clear_local_cache()


@pytest.mark.asyncio
async def test_get_all_clean_ips_rejects_stale_file_fallback(tmp_path):
    pool_mgr = CleanIPPoolManager()
    pool_mgr.clear_local_cache()
    working_json = tmp_path / "working_iran_proxies.json"
    working_json.write_text(
        json.dumps(
            [
                CleanIPRecord(
                    url="http://185.100.47.106:8080",
                    ip="185.100.47.106",
                    port=8080,
                    observed_country="IR",
                    egress_verified=True,
                ).to_dict()
            ]
        )
    )
    mock_redis = AsyncMock()
    mock_redis.get.side_effect = [None, None]

    with (
        patch("app.core.redis_client.redis_manager.get", return_value=mock_redis),
        patch("app.automation.clean_ip_pool.FILE_WORKING_JSON", str(working_json)),
        patch.object(pool_mgr, "_pool_is_stale", return_value=True),
    ):
        assert await pool_mgr.get_all_clean_ips() == []

    pool_mgr.clear_local_cache()


@pytest.mark.asyncio
async def test_get_clean_ip_rotates_across_whole_pool():
    """Selection must NOT funnel every call into the single lowest-latency proxy."""
    pool_mgr = CleanIPPoolManager()
    pool_mgr.clear_local_cache()
    pool_mgr._local_cache = [
        CleanIPRecord(
            url="http://185.100.47.106:8080",
            ip="185.100.47.106",
            port=8080,
            observed_country="IR",
            egress_verified=True,
        ),
        CleanIPRecord(
            url="http://5.56.132.26:3128",
            ip="5.56.132.26",
            port=3128,
            observed_country="IR",
            egress_verified=True,
        ),
    ]
    pool_mgr._local_cache_time = time.time()

    mock_redis = AsyncMock()
    mock_redis.exists.return_value = False
    with patch("app.core.redis_client.redis_manager.get", return_value=mock_redis):
        picks = [await pool_mgr.get_clean_ip() for _ in range(4)]

    assert picks[0] != picks[1]
    assert picks[0] == picks[2]
    assert picks[1] == picks[3]
    pool_mgr.clear_local_cache()


@pytest.mark.asyncio
async def test_clean_ip_pool_manager_mark_blocked_invalidates_worker_cache():
    pool_mgr = CleanIPPoolManager()
    pool_mgr.clear_local_cache()
    mock_redis = AsyncMock()

    with (
        patch("app.core.redis_client.redis_manager.get", return_value=mock_redis),
        patch("app.automation.worker_proxy.invalidate_worker_proxy_cache") as mock_invalidate,
    ):
        await pool_mgr.mark_blocked("http://185.100.47.106:8080", duration_seconds=600)
        assert mock_redis.set.called
        # The refresh-window worker-side cache must drop the just-blocked proxy NOW
        mock_invalidate.assert_called_once()
        pool_mgr.clear_local_cache()


@pytest.mark.asyncio
async def test_forced_refresh_still_honors_distributed_lock():
    pool_mgr = CleanIPPoolManager()
    pool_mgr.clear_local_cache()
    pool_mgr._local_cache = [CleanIPRecord(url="http://185.100.47.106:8080")]
    pool_mgr._local_cache_time = time.time()
    mock_redis = AsyncMock()
    mock_redis.set.return_value = False

    with (
        patch("app.core.redis_client.redis_manager.get", return_value=mock_redis),
        patch("app.automation.clean_ip_pool.run_screening_cycle") as screening,
    ):
        records = await pool_mgr.refresh_pool(force=True)

    assert len(records) == 1
    screening.assert_not_called()
    mock_redis.set.assert_awaited_once()
    assert mock_redis.set.await_args.kwargs["nx"] is True
    mock_redis.eval.assert_not_awaited()
    pool_mgr.clear_local_cache()


@pytest.mark.asyncio
async def test_refresh_releases_only_its_owned_distributed_lock():
    pool_mgr = CleanIPPoolManager()
    pool_mgr.clear_local_cache()
    mock_redis = AsyncMock()
    mock_redis.set.return_value = True
    verified = [CleanIPRecord(url="http://185.100.47.106:8080")]

    with (
        patch("app.core.redis_client.redis_manager.get", return_value=mock_redis),
        patch("app.automation.clean_ip_pool.run_screening_cycle", return_value=verified),
    ):
        records = await pool_mgr.refresh_pool(force=True)

    assert records == verified
    mock_redis.eval.assert_awaited_once()
    release_args = mock_redis.eval.await_args.args
    assert "redis.call('get', KEYS[1]) == ARGV[1]" in release_args[0]
    assert release_args[2] == pool_mgr.REDIS_LOCK_REFRESH
    pool_mgr.clear_local_cache()


def test_get_clean_ip_sync_skips_redis_blocked_proxy_in_cache():
    """get_clean_ip_sync must skip proxies marked blocked in Redis and return the next usable one."""
    pool_mgr = CleanIPPoolManager()
    pool_mgr.clear_local_cache()

    proxy_a = CleanIPRecord(
        url="http://185.100.47.106:8080",
        ip="185.100.47.106",
        port=8080,
        observed_country="IR",
        egress_verified=True,
    )
    proxy_b = CleanIPRecord(
        url="http://5.56.132.26:3128",
        ip="5.56.132.26",
        port=3128,
        observed_country="IR",
        egress_verified=True,
    )
    pool_mgr._local_cache = [proxy_a, proxy_b]
    pool_mgr._local_cache_time = time.time()

    mock_redis = MagicMock()
    mock_redis.exists.side_effect = [True, False]  # a blocked in Redis, b free

    with patch("app.core.circuit_breaker._get_redis_sync", return_value=mock_redis):
        url = pool_mgr.get_clean_ip_sync()
        assert url == "http://5.56.132.26:3128"
    pool_mgr.clear_local_cache()


def test_get_clean_ip_sync_rotates_across_cache():
    pool_mgr = CleanIPPoolManager()
    pool_mgr.clear_local_cache()
    pool_mgr._local_cache = [
        CleanIPRecord(
            url="http://185.100.47.106:8080",
            ip="185.100.47.106",
            port=8080,
            observed_country="IR",
            egress_verified=True,
        ),
        CleanIPRecord(
            url="http://5.56.132.26:3128",
            ip="5.56.132.26",
            port=3128,
            observed_country="IR",
            egress_verified=True,
        ),
    ]
    pool_mgr._local_cache_time = time.time()

    mock_redis = MagicMock()
    mock_redis.exists.return_value = False

    with patch("app.core.circuit_breaker._get_redis_sync", return_value=mock_redis):
        first = pool_mgr.get_clean_ip_sync()
        second = pool_mgr.get_clean_ip_sync()
        third = pool_mgr.get_clean_ip_sync()

    assert first != second
    assert first == third
    pool_mgr.clear_local_cache()


def test_get_clean_ip_sync_filters_protocols_for_browser_clients():
    pool_mgr = CleanIPPoolManager()
    pool_mgr.clear_local_cache()
    pool_mgr._local_cache = [
        CleanIPRecord(
            url="socks4://185.100.47.106:1080",
            protocol="socks4",
            ip="185.100.47.106",
            port=1080,
            observed_country="IR",
            egress_verified=True,
        ),
        CleanIPRecord(
            url="socks5://5.56.132.26:1080",
            protocol="socks5",
            ip="5.56.132.26",
            port=1080,
            observed_country="IR",
            egress_verified=True,
        ),
    ]
    pool_mgr._local_cache_time = time.time()

    with patch("app.core.circuit_breaker._get_redis_sync") as redis_sync:
        redis_sync.return_value.exists.return_value = False
        assert pool_mgr.get_clean_ip_sync(allowed_protocols={"http", "https", "socks5"}) == (
            "socks5://5.56.132.26:1080"
        )
    pool_mgr.clear_local_cache()


def test_get_clean_ip_sync_json_fallback_respects_blocked(tmp_path):
    """Structured fallback must prove Iranian egress and respect Redis blocks."""
    pool_mgr = CleanIPPoolManager()
    pool_mgr.clear_local_cache()
    working_json = tmp_path / "working_iran_proxies.json"
    working_json.write_text(
        json.dumps(
            [
                CleanIPRecord(
                    url="http://185.100.47.106:8080",
                    ip="185.100.47.106",
                    port=8080,
                    observed_country="IR",
                    egress_verified=True,
                ).to_dict()
            ]
        )
    )
    mock_redis = MagicMock()

    with (
        patch("app.automation.clean_ip_pool.FILE_WORKING_JSON", str(working_json)),
        patch.object(pool_mgr, "_pool_is_stale", return_value=False),
        patch("app.core.circuit_breaker._get_redis_sync", return_value=mock_redis),
    ):
        mock_redis.exists.return_value = True
        assert pool_mgr.get_clean_ip_sync() is None

        mock_redis.exists.return_value = False
        assert pool_mgr.get_clean_ip_sync() == "http://185.100.47.106:8080"

    pool_mgr.clear_local_cache()


def test_get_clean_ip_sync_loads_fresh_shared_redis_pool_on_remote_worker():
    pool_mgr = CleanIPPoolManager()
    pool_mgr.clear_local_cache()
    record = CleanIPRecord(
        url="http://185.100.47.106:8080",
        ip="185.100.47.106",
        port=8080,
        observed_country="IR",
        egress_verified=True,
    )
    mock_redis = MagicMock()

    def redis_get(key):
        if key == pool_mgr.REDIS_KEY_LAST_REFRESH:
            return str(time.time())
        if key == pool_mgr.REDIS_KEY_POOL:
            return json.dumps([record.to_dict()])
        return None

    mock_redis.get.side_effect = redis_get
    mock_redis.exists.return_value = False

    with patch("app.core.circuit_breaker._get_redis_sync", return_value=mock_redis):
        assert pool_mgr.get_clean_ip_sync() == record.url

    assert pool_mgr._local_cache[0].is_operational_iranian_egress is True
    pool_mgr.clear_local_cache()


def test_get_clean_ip_sync_rejects_stale_shared_redis_pool(tmp_path):
    pool_mgr = CleanIPPoolManager()
    pool_mgr.clear_local_cache()
    mock_redis = MagicMock()
    mock_redis.get.side_effect = lambda key: str(time.time() - 7200) if "last_refresh" in key else "[]"

    missing = tmp_path / "missing.json"
    with (
        patch("app.core.circuit_breaker._get_redis_sync", return_value=mock_redis),
        patch("app.automation.clean_ip_pool.FILE_WORKING_JSON", str(missing)),
        patch("app.automation.clean_ip_pool.FILE_BEST_TXT", str(missing)),
        patch("app.automation.clean_ip_pool.FILE_WORKING_TXT", str(missing)),
        patch.object(pool_mgr, "_kick_background_refresh") as kick,
    ):
        assert pool_mgr.get_clean_ip_sync() is None

    kick.assert_called_once()
    pool_mgr.clear_local_cache()


def test_get_clean_ip_sync_kicks_background_refresh_when_stale(tmp_path):
    """Sync path must trigger screening when it has nothing usable and state is stale —
    historically it consumed the same dead best_iran_proxy.txt forever."""
    pool_mgr = CleanIPPoolManager()
    pool_mgr.clear_local_cache()

    missing = tmp_path / "missing"
    with (
        patch("app.automation.clean_ip_pool.FILE_WORKING_JSON", str(missing)),
        patch("app.automation.clean_ip_pool.FILE_BEST_TXT", str(missing)),
        patch("app.automation.clean_ip_pool.FILE_WORKING_TXT", str(missing)),
        patch.object(pool_mgr, "_kick_background_refresh") as kick,
    ):
        assert pool_mgr.get_clean_ip_sync() is None
        kick.assert_called_once()
    pool_mgr.clear_local_cache()


# ---------------------------------------------------------------------------
# worker_proxy integration
# ---------------------------------------------------------------------------


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
            with patch(
                "app.automation.clean_ip_pool.clean_ip_pool.get_clean_ip_sync",
                return_value="http://185.100.47.106:8080",
            ):
                url = get_worker_proxy_url()
                assert url == "http://185.100.47.106:8080"


def test_worker_proxy_clean_pool_only_mode():
    clear_proxy_cache()

    with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
        with (
            patch(
                "app.automation.clean_ip_pool.clean_ip_pool.get_clean_ip_sync", return_value="http://5.56.132.26:3128"
            ),
            patch("app.automation.worker_proxy.utcms_config.EGRESS_PROXY_MODE", "clean_pool_only"),
        ):
            url = get_worker_proxy_url()
            assert url == "http://5.56.132.26:3128"


def test_invalidate_worker_proxy_cache_drops_choice_without_touching_pool():
    import app.automation.worker_proxy as wp

    with patch("app.automation.clean_ip_pool.clean_ip_pool.clear_local_cache") as pool_clear:
        wp._cached_proxy_url = "http://185.100.47.106:8080"
        wp._cached_proxy_timestamp = time.time()

        invalidate_worker_proxy_cache()

        assert wp._cached_proxy_url is None
        assert wp._cached_proxy_timestamp == 0.0
        pool_clear.assert_not_called()


def test_proxy_resolution_preserves_credentials_and_playwright_separates_them():
    clear_proxy_cache()
    raw_url = "http://proxy-user:proxy-pass@proxy.example:8080"
    with patch("socket.gethostbyname", return_value="185.100.47.106"):
        assert _resolve_to_ip(raw_url) == "http://proxy-user:proxy-pass@185.100.47.106:8080"

    with patch("app.automation.worker_proxy.get_worker_proxy_url", return_value=raw_url):
        assert get_playwright_proxy() == {
            "server": "http://proxy.example:8080",
            "username": "proxy-user",
            "password": "proxy-pass",
        }


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


def test_blocked_egress_index_prefers_clean_pool():
    """A blocked egress index must actually move the worker to the pool."""
    import app.automation.worker_proxy as wp

    clear_proxy_cache()

    with patch.dict(
        os.environ,
        {
            "WORKER_ID": "1",
            "WORKER_IP_INDEX": "1",
            "WORKER_1_PROXY": "http://172.20.0.1:3128",
            "EGRESS_PROXY_MODE": "worker_first",
            "ENVIRONMENT": "production",
            "PROXY_FAIL_CLOSED": "true",
        },
    ):
        with (
            patch("socket.create_connection"),
            patch("app.automation.worker_proxy._resolve_to_ip", side_effect=lambda u: u),
            patch("app.core.circuit_breaker._get_redis_sync") as redis_sync,
            patch(
                "app.automation.clean_ip_pool.clean_ip_pool.get_clean_ip_sync",
                return_value="http://46.209.30.11:8080",
            ),
        ):
            redis_sync.return_value.exists.return_value = True
            assert get_best_egress_proxy() == "http://46.209.30.11:8080"
            assert wp._cached_proxy_source == "clean_pool"


def test_blocked_egress_index_with_empty_pool_fails_closed():
    """A reachable Squid whose egress index is marked blocked must fail closed when pool is empty."""
    from app.automation.worker_proxy import ProxyUnavailableError

    clear_proxy_cache()

    with patch.dict(
        os.environ,
        {
            "WORKER_ID": "1",
            "WORKER_IP_INDEX": "1",
            "WORKER_1_PROXY": "http://172.20.0.1:3128",
            "EGRESS_PROXY_MODE": "worker_first",
            "ENVIRONMENT": "production",
            "PROXY_FAIL_CLOSED": "true",
        },
    ):
        with (
            patch("socket.create_connection"),
            patch("app.automation.worker_proxy._resolve_to_ip", side_effect=lambda u: u),
            patch("app.core.circuit_breaker._get_redis_sync") as redis_sync,
            patch("app.automation.clean_ip_pool.clean_ip_pool.get_clean_ip_sync", return_value=None),
        ):
            redis_sync.return_value.exists.return_value = True
            with pytest.raises(ProxyUnavailableError):
                get_best_egress_proxy()


# ---------------------------------------------------------------------------
# Circuit breaker isolation
# ---------------------------------------------------------------------------


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


@pytest.mark.asyncio
async def test_circuit_breaker_unidentified_clean_pool_failure_spares_worker_index():
    """Clean-pool egress failed but identity was lost upstream: blocking the healthy
    worker's own IP index for 30 minutes would drain it — it must stay untouched."""
    mock_redis = AsyncMock()

    with patch("app.core.redis_client.redis_manager.get", return_value=mock_redis):
        with patch("app.automation.clean_ip_pool.clean_ip_pool.mark_blocked", new_callable=AsyncMock) as mock_mark:
            with patch.dict(os.environ, {"WORKER_IP_INDEX": "2"}):
                await check_and_report_failure(
                    error_msg="connection timed out during clean pool request",
                    egress_source="clean_pool",
                    proxy_url=None,
                )

                mock_mark.assert_not_called()
                for call in mock_redis.set.call_args_list:
                    assert "utcms:circuit_breaker:blocked:2" not in str(call)


# ── Source-list parsing ───────────────────────────────────────────────────────
# The harvester that populates these files runs OUTSIDE Iran (the JSON feeds
# resolve to the 10.10.34.36 filtering sinkhole from a worker), so a generated
# feed carrying provenance comments is the normal case, not an edge case.


@pytest.mark.parametrize(
    "line,expected",
    [
        ("http://185.100.47.106:8080", ("http", "185.100.47.106", 8080)),
        # No scheme → default http.
        ("185.100.47.106:8080", ("http", "185.100.47.106", 8080)),
        ("socks5://185.100.47.106:1080", ("socks5", "185.100.47.106", 1080)),
        # Credentials are stripped from the candidate identity.
        ("http://user:pass@185.100.47.106:8080", ("http", "185.100.47.106", 8080)),
        # Inline comment + padding must not leak into the port.
        ("http://185.100.47.106:8080    # 120ms  MCI", ("http", "185.100.47.106", 8080)),
        ("  185.100.47.106:8080  ", ("http", "185.100.47.106", 8080)),
    ],
)
def test_parse_proxy_line_accepts_real_feed_shapes(line, expected):
    parsed = _parse_proxy_line(line)
    assert parsed is not None, line
    assert (parsed["protocol"], parsed["ip"], parsed["port"]) == expected


@pytest.mark.parametrize(
    "line",
    [
        "",
        "   ",
        "# full-line comment",
        "http://185.100.47.106",  # no port
        "http://185.100.47.106:0",  # port out of range
        "http://185.100.47.106:99999",
        "http://10.10.34.36:8080",  # RFC1918 — the Iranian filtering sinkhole
        "http://127.0.0.1:8080",
        "http://not-an-ip:8080",
    ],
)
def test_parse_proxy_line_rejects_unusable(line):
    assert _parse_proxy_line(line) is None


def test_fetch_file_source_skips_comments_and_keeps_provenance(tmp_path):
    """A trailing comment used to fold into the port and silently drop the row."""
    source = tmp_path / "verified_iran_proxies.txt"
    source.write_text(
        "\n".join(
            [
                "# BarPro Clean IP Pool source",
                "# generated_at_epoch: 1756382400",
                "",
                "http://185.100.47.106:8080",
                "socks5://46.249.124.244:1080    # 6257ms",
                "http://10.10.34.36:3128",
            ]
        ),
        encoding="utf-8",
    )

    with patch.dict(os.environ, {"CLEAN_IP_SOURCE_FILE": str(source)}, clear=False):
        os.environ.pop("CLEAN_IP_SOURCE_URL", None)
        results = fetch_file_or_env_sources()

    assert [(r["protocol"], r["ip"], r["port"]) for r in results] == [
        ("http", "185.100.47.106", 8080),
        ("socks5", "46.249.124.244", 1080),
    ]
    assert {r["source"] for r in results} == {"file_source"}


# ── Probe retry semantics ─────────────────────────────────────────────────────
# Free Iranian egress is flaky in a way one attempt cannot tell from death, but
# a UTCMS rejection is a verdict about the IP that retrying cannot change — and
# every extra attempt is another handshake against the per-IP WAF throttle.


def test_probe_retries_transport_failure_then_certifies():
    candidate = CleanIPRecord(url="http://185.100.47.106:8080", ip="185.100.47.106", port=8080)

    with (
        patch("app.automation.clean_ip_pool._CURL_CFFI_IMPORT_ERROR", None),
        patch(
            "app.automation.clean_ip_pool._probe_via_curl_cffi",
            side_effect=[TimeoutError("timed out"), (200, 1700.0, "<html>txtusername</html>")],
        ) as probe,
    ):
        result = probe_single_proxy(candidate)

    assert probe.call_count == 2
    assert result is not None
    assert result.latency_ms == 1700.0
    assert result.fail_count == 0


def test_probe_does_not_retry_a_utcms_rejection():
    candidate = CleanIPRecord(url="http://185.100.47.106:8080", ip="185.100.47.106", port=8080)

    with (
        patch("app.automation.clean_ip_pool._CURL_CFFI_IMPORT_ERROR", None),
        patch("app.automation.clean_ip_pool._probe_via_curl_cffi", return_value=(403, 10.0, "")) as probe,
    ):
        result = probe_single_proxy(candidate)

    assert probe.call_count == 1
    assert result is None
    assert "utcms_rejected" in candidate.tags


def test_probe_gives_up_after_exhausting_transport_attempts():
    candidate = CleanIPRecord(url="http://185.100.47.106:8080", ip="185.100.47.106", port=8080)

    with (
        patch("app.automation.clean_ip_pool._CURL_CFFI_IMPORT_ERROR", None),
        patch(
            "app.automation.clean_ip_pool._probe_via_curl_cffi",
            side_effect=TimeoutError("timed out"),
        ) as probe,
    ):
        result = probe_single_proxy(candidate)

    assert probe.call_count == cip.PROBE_TRANSPORT_ATTEMPTS
    assert result is None
    assert candidate.fail_count >= 1


def test_probe_sessions_verify_tls_certificates():
    """A probe that accepts a MITM'd session would certify the one egress we
    must reject — the pool decides where UTCMS credentials are sent."""
    captured = {}

    class _FakeSession:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.headers = {}

        def get(self, url):
            return MagicMock(status_code=200, text="<html>txtusername</html>")

        def close(self):
            return None

    fake_module = MagicMock()
    fake_module.requests.Session = _FakeSession

    candidate = CleanIPRecord(url="http://185.100.47.106:8080", ip="185.100.47.106", port=8080)
    with patch.dict("sys.modules", {"curl_cffi": fake_module, "curl_cffi.requests": fake_module.requests}):
        cip._probe_via_curl_cffi(candidate, cip.LOGIN_PROBE_URL, 20.0)

    assert captured["verify"] is True


def test_provider_harvest_caching_honors_ttls():
    """Providers must be cached per-provider according to their TTL, unless force_refresh_all is True."""
    cip.clear_harvest_cache()
    mock_spys = MagicMock(return_value=[{"protocol": "http", "ip": "185.100.47.106", "port": 8080, "country": "IR"}])
    empty_mock = MagicMock(return_value=[])

    with (
        patch.object(cip, "fetch_spys_sources", mock_spys),
        patch.object(cip, "fetch_freeproxy_world", empty_mock),
        patch.object(cip, "fetch_geonode_api", empty_mock),
        patch.object(cip, "fetch_monosans_geojson", empty_mock),
        patch.object(cip, "fetch_proxylist_download", empty_mock),
        patch.object(cip, "fetch_vakhov_github", empty_mock),
        patch.object(cip, "fetch_proxyscrape_apis", empty_mock),
        patch.object(cip, "fetch_github_sources", empty_mock),
        patch.object(cip, "fetch_file_or_env_sources", empty_mock),
    ):
        # 1st call: fetches and caches
        res1 = cip.aggregate_all_candidates()
        assert mock_spys.call_count == 1
        assert any(c.ip == "185.100.47.106" for c in res1)

        # 2nd call: within TTL, reuses cache without re-invoking fetch_spys_sources
        res2 = cip.aggregate_all_candidates(force_refresh_all=False)
        assert mock_spys.call_count == 1
        assert any(c.ip == "185.100.47.106" for c in res2)

        # 3rd call with force_refresh_all=True: forces re-fetching
        res3 = cip.aggregate_all_candidates(force_refresh_all=True)
        assert mock_spys.call_count == 2
        assert any(c.ip == "185.100.47.106" for c in res3)

    cip.clear_harvest_cache()


def test_run_screening_cycle_prioritizes_iranian_candidates():
    """Iranian candidates must be screened before generic global mirror candidates."""
    cip.clear_harvest_cache()
    global_cand = CleanIPRecord(url="http://1.1.1.1:8080", ip="1.1.1.1", port=8080, source="github_mirror", country="")
    ir_cand = CleanIPRecord(
        url="http://185.100.47.106:8080", ip="185.100.47.106", port=8080, source="geonode", country="IR"
    )

    probed = []

    def mock_probe(c, target, timeout):
        probed.append(c)
        return c

    with (
        patch.object(cip, "aggregate_all_candidates", return_value=[global_cand, ir_cand]),
        patch.object(cip, "probe_single_proxy", side_effect=mock_probe),
        patch.object(cip, "_verify_egress_country", return_value="IR"),
        patch.object(cip, "atomic_write"),
    ):
        # With max_candidates=1, only the top priority candidate is probed
        verified = cip.run_screening_cycle(max_candidates=1, max_pool_size=10)
        assert len(probed) == 1
        assert probed[0].ip == "185.100.47.106"  # Iranian candidate got the single screening slot
        assert len(verified) == 1


def test_verify_egress_country_uses_ipwho_is_fallback():
    """If api.country.is fails or times out, ipwho.is is used to verify Iranian egress."""
    candidate = CleanIPRecord(url="http://185.100.47.106:8080", ip="185.100.47.106", port=8080)

    class _MockSession:
        def __init__(self, **kwargs):
            self.headers = {}

        def get(self, url):
            if "api.country.is" in url:
                raise TimeoutError("api.country.is timed out")
            if "ipwho.is" in url:
                mock_resp = MagicMock()
                mock_resp.json.return_value = {"country_code": "IR", "country": "Iran"}
                return mock_resp
            raise ValueError(f"Unexpected url {url}")

        def close(self):
            pass

    fake_module = MagicMock()
    fake_module.requests.Session = _MockSession

    with patch.dict("sys.modules", {"curl_cffi": fake_module, "curl_cffi.requests": fake_module.requests}):
        country = cip._verify_egress_country(candidate, timeout=5.0)

    assert country == "IR"


# ---------------------------------------------------------------------------
# Harvest cache: an EMPTY harvest is a failure, not an hour-long answer
# ---------------------------------------------------------------------------

ALL_HARVESTER_ATTRS = (
    "fetch_spys_sources",
    "fetch_freeproxy_world",
    "fetch_geonode_api",
    "fetch_monosans_geojson",
    "fetch_proxylist_download",
    "fetch_vakhov_github",
    "fetch_proxyscrape_apis",
    "fetch_github_sources",
    "fetch_file_or_env_sources",
)

# "GitHub Mirrors" carries the longest success TTL (3600s) AND, per the module's
# own note, raw.githubusercontent.com is the only feed host that still resolves
# from inside Iran — so it is the exact provider whose cached [] starved the pool.
_LONG_TTL_PROVIDER = "GitHub Mirrors"
_LONG_TTL_ATTR = "fetch_github_sources"
_CANDIDATE = {"protocol": "http", "ip": "185.100.47.106", "port": 8080}


@contextlib.contextmanager
def _only_harvester(attr_name: str, replacement):
    """Patch every harvester to return [] except `attr_name`, which gets `replacement`."""
    with contextlib.ExitStack() as stack:
        for name in ALL_HARVESTER_ATTRS:
            stack.enter_context(
                patch.object(cip, name, replacement if name == attr_name else MagicMock(return_value=[]))
            )
        yield


def _rewind_cache(provider: str, seconds: float) -> float:
    """Age a cached harvest entry without touching its payload."""
    timestamp, items = cip._provider_harvest_cache[provider]
    cip._provider_harvest_cache[provider] = (timestamp - seconds, items)
    return timestamp - seconds


def test_empty_harvest_is_not_cached_under_the_long_success_ttl():
    """One transient _safe_fetch failure must not starve the pool for an hour.

    tasks.py runs refresh_pool(force=False) every CLEAN_IP_PROBE_INTERVAL_SECONDS
    (180s). Caching [] under the 3600s success TTL meant ~20 consecutive cycles
    harvesting zero candidates — run_screening_cycle then wipes the runtime files
    and every job raises ProxyUnavailableError. _kick_background_refresh calls the
    same non-forced path, so it could not recover either.
    """
    cip.clear_harvest_cache()
    harvester = MagicMock(side_effect=[[], [_CANDIDATE], [_CANDIDATE]])

    with _only_harvester(_LONG_TTL_ATTR, harvester):
        assert cip.aggregate_all_candidates() == []
        assert harvester.call_count == 1

        # 2 minutes later: far inside the 3600s SUCCESS TTL, but well past the
        # short failure TTL an empty result must be held under.
        assert 120.0 > cip.EMPTY_HARVEST_TTL_SECONDS
        assert 120.0 < cip.PROVIDER_HARVEST_TTLS[_LONG_TTL_PROVIDER]
        _rewind_cache(_LONG_TTL_PROVIDER, 120.0)

        recovered = cip.aggregate_all_candidates(force_refresh_all=False)
        assert harvester.call_count == 2, "an empty harvest must be retried on the next cycle"
        assert [c.ip for c in recovered] == ["185.100.47.106"]

        # ...and a NON-empty harvest still gets the full provider TTL: the point
        # is not to disable caching, only to stop caching failures.
        _rewind_cache(_LONG_TTL_PROVIDER, 120.0)
        still_cached = cip.aggregate_all_candidates(force_refresh_all=False)
        assert harvester.call_count == 2, "a successful harvest must stay cached for its TTL"
        assert [c.ip for c in still_cached] == ["185.100.47.106"]

    cip.clear_harvest_cache()


def test_stale_harvest_replay_is_bounded_then_dropped():
    """A permanently dead feed must stop serving its last payload forever.

    The expired entry is still replayed on a harvester exception (that part is
    deliberate), but only within a bounded multiple of the provider TTL —
    otherwise probe budget is burned against the per-IP WAF handshake throttle on
    addresses nobody has re-published in days.
    """
    cip.clear_harvest_cache()
    ttl = cip.PROVIDER_HARVEST_TTLS[_LONG_TTL_PROVIDER]
    harvester = MagicMock(side_effect=[[_CANDIDATE], RuntimeError("feed dead"), RuntimeError("feed dead")])

    with _only_harvester(_LONG_TTL_ATTR, harvester):
        assert [c.ip for c in cip.aggregate_all_candidates()] == ["185.100.47.106"]

        # Just past the TTL but inside the bounded replay window -> replayed.
        aged_to = _rewind_cache(_LONG_TTL_PROVIDER, ttl + 10)
        assert [c.ip for c in cip.aggregate_all_candidates()] == ["185.100.47.106"]
        assert harvester.call_count == 2
        # A replay must NOT refresh the timestamp, or the feed is never retried.
        assert cip._provider_harvest_cache[_LONG_TTL_PROVIDER][0] == aged_to

        # Beyond the bound -> entry dropped, nothing replayed.
        _rewind_cache(_LONG_TTL_PROVIDER, ttl * cip.STALE_HARVEST_REPLAY_TTL_MULTIPLIER)
        assert cip.aggregate_all_candidates() == []
        assert harvester.call_count == 3
        assert _LONG_TTL_PROVIDER not in cip._provider_harvest_cache

    cip.clear_harvest_cache()


def test_clear_local_cache_does_not_force_a_full_network_reharvest():
    """worker_proxy.clear_proxy_cache runs on every failed Squid health check
    (e.g. a fuel inquiry against a flapping Squid). Wiping all nine providers
    there forced a full re-harvest per failure — the exact rate-limit and
    Cloudflare pressure PROVIDER_HARVEST_TTLS was added to prevent."""
    cip.clear_harvest_cache()
    harvester = MagicMock(return_value=[_CANDIDATE])

    with _only_harvester(_LONG_TTL_ATTR, harvester):
        cip.aggregate_all_candidates()
        assert harvester.call_count == 1

        clear_proxy_cache()  # -> clean_ip_pool.clean_ip_pool.clear_local_cache()

        cip.aggregate_all_candidates()
        assert harvester.call_count == 1, "harvest cache must survive a proxy-choice invalidation"

        # The explicit force path is still the way to re-harvest.
        cip.aggregate_all_candidates(force_refresh_all=True)
        assert harvester.call_count == 2

    cip.clear_harvest_cache()


# ---------------------------------------------------------------------------
# Block-page detection must be STRUCTURAL, not a body substring scan
# ---------------------------------------------------------------------------


def test_proxylist_download_rejects_block_page_carrying_attributes():
    """A literal "<html>" test never fires: a real page carries attributes.

    This page contains no "502"/"503" substring either, so the old guard passed
    it straight into the line parser — which happily lifted the upstream address
    echoed in the error body and served it as a harvested proxy. Only the
    STRUCTURAL check rejects it.
    """
    page = (
        '<!DOCTYPE html>\n<html lang="fa" dir="rtl">\n<head><title>Blocked</title></head>\n'
        "<body>upstream unavailable\n185.100.47.106:8080\n</body>\n</html>"
    )
    assert "<html>" not in page.lower()  # why the old guard was dead
    assert "502" not in page and "503" not in page  # and why nothing else caught it

    with patch.object(cip, "_safe_fetch", return_value=page):
        assert cip.fetch_proxylist_download() == []


def test_proxylist_download_keeps_proxies_whose_port_contains_502():
    """Scanning the WHOLE body for "502"/"503" discarded all four protocol
    pages whenever one harvested proxy happened to listen on port 5020."""
    body = "185.100.47.106:5020\n5.56.132.26:8502\n46.209.30.11:1503\n"
    assert "502" in body and "503" in body  # why the old guard was destructive
    with patch.object(cip, "_safe_fetch", return_value=body):
        results = cip.fetch_proxylist_download()

    assert {r["port"] for r in results} == {5020, 8502, 1503}
    # http + https + socks4 + socks5 pages x 3 rows
    assert len(results) == 12


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("185.100.47.106:8080\n5.56.132.26:3128\n", True),
        ("# generated\n185.100.47.106:8080\n", True),  # comments are not counted against the ratio
        ('<html lang="fa" dir="rtl">x</html>', False),
        ("<!DOCTYPE html><body>nope</body>", False),
        ("Too many requests\nplease retry later\nsee the docs\n", False),
        ("", False),
        ("   \n\n", False),
    ],
)
def test_is_proxy_list_payload_gates_on_structure_and_parse_ratio(raw, expected):
    assert cip._is_proxy_list_payload(raw, origin="unit") is expected


# ---------------------------------------------------------------------------
# Per-item isolation: one malformed upstream entry costs ONE entry
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("order", ["bad_first", "bad_last"])
def test_monosans_malformed_entry_costs_only_that_entry(order):
    """`names` published as a string makes
    ``(geo.get("city") or {}).get("names", {}).get("en")`` raise AttributeError.
    With the try/except around the whole loop, that one record discarded the
    entire feed — and the yield depended on upstream ORDERING."""
    good = {
        "host": "185.100.47.106",
        "port": 8080,
        "protocol": "http",
        "geolocation": {"country": {"iso_code": "IR"}, "city": {"names": {"en": "Tehran"}}},
    }
    bad = {
        "host": "5.56.132.26",
        "port": 3128,
        "protocol": "http",
        "geolocation": {"country": {"iso_code": "IR"}, "city": {"names": "Tehran"}},
    }
    payload = [bad, good] if order == "bad_first" else [good, bad]

    with patch.object(cip, "_safe_fetch", return_value=json.dumps(payload)):
        results = cip.fetch_monosans_geojson()

    assert [r["ip"] for r in results] == ["185.100.47.106"]


@pytest.mark.parametrize("order", ["bad_first", "bad_last"])
def test_geonode_malformed_entry_costs_only_that_entry(order):
    """An empty ``protocols`` list makes ``protocols[0]`` raise IndexError."""
    good = {"ip": "185.100.47.106", "port": 8080, "protocols": ["http"]}
    bad = {"ip": "5.56.132.26", "port": 3128, "protocols": []}
    payload = {"data": [bad, good] if order == "bad_first" else [good, bad]}

    with patch.object(cip, "_safe_fetch", return_value=json.dumps(payload)):
        results = cip.fetch_geonode_api()

    assert [r["ip"] for r in results] == ["185.100.47.106"]


@pytest.mark.parametrize("order", ["bad_first", "bad_last"])
def test_vakhov_malformed_entry_costs_only_that_entry(order):
    """A numeric ``country_code`` makes ``.upper()`` raise AttributeError."""
    good = {"ip": "185.100.47.106", "port": 8080, "country_code": "IR", "type": "http"}
    bad = {"ip": "5.56.132.26", "port": 3128, "country_code": 364, "type": "http"}
    payload = [bad, good] if order == "bad_first" else [good, bad]

    with patch.object(cip, "_safe_fetch", return_value=json.dumps(payload)):
        results = cip.fetch_vakhov_github()

    assert [r["ip"] for r in results] == ["185.100.47.106"]


@pytest.mark.parametrize("order", ["bad_first", "bad_last"])
def test_proxyscrape_v4_malformed_entry_costs_only_that_entry(order):
    """``ip_data`` published as a list makes ``(... or {}).get(...)`` raise."""
    good = {"ip": "185.100.47.106", "port": 8080, "protocol": "http"}
    bad = {"ip": "5.56.132.26", "port": 3128, "protocol": "http", "ip_data": ["Tehran"]}
    payload = {"proxies": [bad, good] if order == "bad_first" else [good, bad]}

    def _fetch(url, timeout=6.0):
        return json.dumps(payload) if "/v4/" in url else None

    with patch.object(cip, "_safe_fetch", side_effect=_fetch):
        results = cip.fetch_proxyscrape_apis()

    assert [r["ip"] for r in results] == ["185.100.47.106"]


@pytest.mark.parametrize(
    "harvester",
    ["fetch_monosans_geojson", "fetch_vakhov_github", "fetch_geonode_api", "fetch_proxyscrape_apis"],
)
def test_feed_level_failure_is_logged_never_silently_swallowed(harvester, caplog):
    """AGENTS.md records `except: pass` as a FIXED pitfall. A feed that stops
    being parseable must be traceable, not turn into a silent empty pool."""
    with patch.object(cip, "_safe_fetch", return_value="{ not json"):
        with caplog.at_level(logging.WARNING, logger="app.automation.clean_ip_pool"):
            assert getattr(cip, harvester)() == []

    assert any("unreadable" in record.getMessage() for record in caplog.records), caplog.text


# ---------------------------------------------------------------------------
# The pool must not feed itself, and must not trust a developer's $HOME
# ---------------------------------------------------------------------------


def _isolate_file_sources(monkeypatch, tmp_path):
    """Neutralise env overrides and the RUNTIME_DATA_DIR-relative default."""
    for var in ("CLEAN_IP_SOURCE_FILE", "RPA_PROXY_LIST_FILE", "CLEAN_IP_SOURCE_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(cip, "BASE_RUNTIME_DIR", str(tmp_path / "runtime"))


def test_pool_output_file_is_never_reingested_as_a_source(monkeypatch, tmp_path):
    """run_screening_cycle WRITES FILE_WORKING_TXT. Harvesting it back fed the
    pool into itself: re-ingested entries returned as source="file_source" ->
    tier 0, ahead of every fresh candidate, so under CLEAN_IP_MAX_CANDIDATES
    pressure the same addresses monopolised the screening budget cycle after
    cycle and concentrated traffic on a shrinking address set."""
    _isolate_file_sources(monkeypatch, tmp_path)
    own_output = tmp_path / "working_iran_proxies.txt"
    own_output.write_text("http://185.100.47.106:8080\nhttp://5.56.132.26:3128\n", encoding="utf-8")

    monkeypatch.setattr(cip, "FILE_WORKING_TXT", str(own_output))
    monkeypatch.setattr(cip, "PROXIES_RUNTIME_DIR", str(tmp_path))

    assert fetch_file_or_env_sources() == []


def test_home_directory_is_never_an_implicitly_trusted_proxy_source(monkeypatch, tmp_path):
    """.env.example ships CLEAN_IP_SOURCE_FILE/RPA_PROXY_LIST_FILE empty, so the
    `~`-relative fallback was the PRODUCTION default. The workers run as root, so
    any file at /root/GitHub/free-proxy-list/... became a top-priority
    (tier-0, implicitly trusted) egress source."""
    _isolate_file_sources(monkeypatch, tmp_path)
    home = tmp_path / "home"
    planted = home / "GitHub" / "free-proxy-list" / "barpro"
    planted.mkdir(parents=True)
    (planted / "verified_iran_proxies.txt").write_text("http://185.100.47.106:8080\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    assert os.path.expanduser("~") == str(home)  # the fallback really would resolve here
    assert fetch_file_or_env_sources() == []


# ---------------------------------------------------------------------------
# Country is never fabricated for a bare ip:port line
# ---------------------------------------------------------------------------


def test_parse_proxy_line_does_not_fabricate_an_iranian_country():
    """Previously ANY line from any file/custom-URL feed came back stamped
    country="IR"/city="Iran" — contradicting the _dedupe_candidates contract
    ("Country is only kept when a source explicitly declares it; there is NO
    'IR' default") and making the ir_declared metric tautological."""
    parsed = _parse_proxy_line("socks5://8.8.8.8:1080")
    assert parsed is not None
    assert (parsed["protocol"], parsed["ip"], parsed["port"]) == ("socks5", "8.8.8.8", 1080)
    assert not parsed.get("country")
    assert not parsed.get("city")


def test_global_operator_feed_is_not_relabelled_iranian(monkeypatch, tmp_path):
    """An operator-supplied GLOBAL feed must not be labelled Iranian; the geo
    gate is what decides country, from a measurement."""
    source = tmp_path / "global_feed.txt"
    source.write_text("http://8.8.8.8:8080\n", encoding="utf-8")
    monkeypatch.setenv("CLEAN_IP_SOURCE_FILE", str(source))
    monkeypatch.delenv("CLEAN_IP_SOURCE_URL", raising=False)

    results = fetch_file_or_env_sources()
    assert [r["ip"] for r in results] == ["8.8.8.8"]
    assert not results[0].get("country")

    record = _dedupe_candidates(results)["http://8.8.8.8:8080"]
    assert record.country == ""
    assert record.city is None
    assert record.source == "file_source"


def test_file_source_keeps_top_screening_priority_without_a_declared_country():
    """Tiering must derive from `source`, so dropping the fabricated country
    does not demote legitimately configured local feeds."""
    file_cand = CleanIPRecord(url="http://8.8.8.8:8080", ip="8.8.8.8", port=8080, source="file_source", country="")
    mirror_cand = CleanIPRecord(url="http://1.1.1.1:8080", ip="1.1.1.1", port=8080, source="github_mirror", country="")
    probed: list[CleanIPRecord] = []

    with (
        patch.object(cip, "aggregate_all_candidates", return_value=[mirror_cand, file_cand]),
        patch.object(cip, "probe_single_proxy", side_effect=lambda c, *a, **k: probed.append(c) or c),
        patch.object(cip, "_verify_egress_country", return_value="IR"),
        patch.object(cip, "atomic_write"),
    ):
        cip.run_screening_cycle(max_candidates=1, max_pool_size=10)

    assert [c.ip for c in probed] == ["8.8.8.8"]


# ---------------------------------------------------------------------------
# Screening telemetry must report what is actually true (gate unchanged)
# ---------------------------------------------------------------------------


def test_screening_log_reports_geo_rejections_not_phantom_admissions(caplog):
    """The old message claimed "N admitted with GeoIP unreachable", computed
    AFTER the fail-closed filter had removed exactly those records — so it was
    always 0 and actively misled the next investigation."""
    rec = CleanIPRecord(url="http://185.100.47.106:8080", ip="185.100.47.106", port=8080, country="IR")
    rec.latency_ms = 10.0

    with (
        patch.object(cip, "aggregate_all_candidates", return_value=[rec]),
        patch.object(cip, "probe_single_proxy", return_value=rec),
        patch.object(cip, "_verify_egress_country", return_value=None),
        patch.object(cip, "atomic_write"),
        caplog.at_level(logging.INFO, logger="app.automation.clean_ip_pool"),
    ):
        assert cip.run_screening_cycle(max_pool_size=10) == []

    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "admitted with GeoIP unreachable" not in messages
    assert "rejected 1 for unverifiable egress" in messages


def test_screening_zero_candidates_still_logs_cleanly():
    """Guards the rejection counters being bound before the shortlist branch."""
    with (
        patch.object(cip, "aggregate_all_candidates", return_value=[]),
        patch.object(cip, "atomic_write"),
    ):
        assert cip.run_screening_cycle(max_pool_size=10) == []


# ---------------------------------------------------------------------------
# The VPN-off diagnostic must never overwrite live pool state by default
# ---------------------------------------------------------------------------


def _load_vpn_off_script():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts/test_when_vpn_off.py")
    spec = importlib.util.spec_from_file_location("_barpro_vpn_off_diagnostic", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_vpn_off_diagnostic_does_not_touch_runtime_pool_by_default(tmp_path):
    """The diagnostic built records from probe_single_proxy only, so
    egress_verified=False / observed_country=None — every written record FAILS
    is_operational_iranian_egress. Overwriting the pool files destroyed the real
    verified proxies, supplied zero usable replacements, AND disabled the
    self-healing (a fresh mtime makes _pool_is_stale() False, so
    _kick_background_refresh is never called for CLEAN_IP_POOL_MAX_AGE_SECONDS)."""
    script = _load_vpn_off_script()
    probed = CleanIPRecord(url="http://185.100.47.106:8080", ip="185.100.47.106", port=8080)
    probed.latency_ms = 50.0
    assert probed.is_operational_iranian_egress is False  # why writing it is destructive

    written: list[str] = []

    with (
        patch.object(cip, "aggregate_all_candidates", return_value=[probed]),
        patch.object(script, "_probe_with_reason", return_value=(probed, "SUCCESS", probed)),
        patch.object(cip, "PROXIES_RUNTIME_DIR", str(tmp_path)),
        patch.object(cip, "atomic_write", side_effect=lambda p, c: written.append(p)),
    ):
        verified = script.run_domestic_proxy_audit(max_candidates=1, timeout=1.0, concurrency=1)

    assert [r.url for r in verified] == [probed.url]
    assert cip.FILE_BEST_TXT not in written
    assert cip.FILE_WORKING_TXT not in written
    assert cip.FILE_WORKING_JSON not in written
    # Findings still land somewhere obvious — just not in runtime pool state.
    assert written == [os.path.join(str(tmp_path), "vpn_off_audit_report.json")]


def test_vpn_off_diagnostic_writes_pool_only_on_explicit_opt_in(tmp_path):
    script = _load_vpn_off_script()
    probed = CleanIPRecord(url="http://185.100.47.106:8080", ip="185.100.47.106", port=8080)
    probed.latency_ms = 50.0
    written: list[str] = []

    with (
        patch.object(cip, "aggregate_all_candidates", return_value=[probed]),
        patch.object(script, "_probe_with_reason", return_value=(probed, "SUCCESS", probed)),
        patch.object(cip, "PROXIES_RUNTIME_DIR", str(tmp_path)),
        patch.object(cip, "atomic_write", side_effect=lambda p, c: written.append(p)),
    ):
        script.run_domestic_proxy_audit(max_candidates=1, timeout=1.0, concurrency=1, write_pool=True)

    assert cip.FILE_BEST_TXT in written
    assert cip.FILE_WORKING_TXT in written
    assert cip.FILE_WORKING_JSON in written


def test_vpn_off_diagnostic_buckets_real_transport_failures():
    """TIMEOUT / CONN_ERROR / SSL_ERROR were unreachable: probe_single_proxy
    catches every exception and returns None, so the wrapper's `except` never
    fired and an operator always saw zeros for exactly the failure modes the
    tool exists to distinguish."""
    script = _load_vpn_off_script()
    candidate = CleanIPRecord(url="http://185.100.47.106:8080", ip="185.100.47.106", port=8080)

    cases = {
        "TIMEOUT": TimeoutError("Operation timed out after 4000 ms"),
        "SSL_ERROR": RuntimeError("SSL_connect: certificate verify failed"),
        "CONN_ERROR": RuntimeError("Failed to connect to proxy: connection refused"),
    }
    for expected, exc in cases.items():
        with (
            patch.object(cip, "_CURL_CFFI_IMPORT_ERROR", None),
            patch.object(cip, "_probe_via_curl_cffi", side_effect=exc),
        ):
            _, bucket, result = script._probe_with_reason(candidate, timeout=1.0)
        assert bucket == expected, f"{exc} should bucket as {expected}"
        assert result is None

    # A UTCMS rejection is still REJECTED, not a transport bucket.
    with (
        patch.object(cip, "_CURL_CFFI_IMPORT_ERROR", None),
        patch.object(cip, "_probe_via_curl_cffi", return_value=(403, 20.0, "")),
    ):
        assert script._probe_with_reason(candidate, timeout=1.0)[1] == "REJECTED"

    with (
        patch.object(cip, "_CURL_CFFI_IMPORT_ERROR", None),
        patch.object(cip, "_probe_via_curl_cffi", return_value=(200, 33.0, "<html>ok</html>")),
    ):
        assert script._probe_with_reason(candidate, timeout=1.0)[1] == "SUCCESS"
