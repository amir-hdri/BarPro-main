from unittest.mock import patch

import pytest

from app.core.rate_limiter import InMemoryRateLimiter, RateLimitConfig, RedisRateLimiter
from app.main import _rate_limit_rule_for_path


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/api/v1/auth/login", "auth"),
        ("/api/v1/admin/login", "auth"),
        ("/api/v1/admin/clients", "admin"),
        ("/management/summary", "admin"),
        ("/api/v1/waybill-jobs", "waybill"),
        ("/api/v1/waybill-jobs/42", "waybill"),
        ("/waybill/submit", "waybill"),
        ("/api/v1/drivers", "driver"),
        ("/api/v1/drivers/42", "driver"),
        ("/api/v1/fuel-inquiries", "tenant"),
        ("/api/v10/jobs", "public"),
        ("/healthz", "public"),
    ],
)
def test_rate_limit_route_contract(path: str, expected: str) -> None:
    assert _rate_limit_rule_for_path(path) == expected


@pytest.mark.asyncio
async def test_in_memory_rejected_requests_do_not_extend_window() -> None:
    limiter = InMemoryRateLimiter()
    config = RateLimitConfig(max_requests=2, window_seconds=60)

    with patch("app.core.rate_limiter.time.time", side_effect=[0.0, 1.0, 2.0, 60.1]):
        assert (await limiter.check("client", config)).retry_after is None
        assert (await limiter.check("client", config)).retry_after is None
        assert (await limiter.check("client", config)).retry_after == pytest.approx(58.0)
        assert (await limiter.check("client", config)).retry_after is None


class _FakeRedisSlidingWindow:
    def __init__(self) -> None:
        self.entries: list[tuple[float, str]] = []

    async def eval(self, script: str, _numkeys: int, _key: str, *args: str) -> list[object]:
        window_start, now, max_requests, _ttl, member = args
        start = float(window_start)
        current_time = float(now)
        self.entries = [(score, value) for score, value in self.entries if score > start]
        if len(self.entries) >= int(max_requests):
            return [0, len(self.entries), str(self.entries[0][0])]
        self.entries.append((current_time, member))
        self.entries.sort()
        return [1, len(self.entries), str(self.entries[0][0])]


@pytest.mark.asyncio
async def test_redis_rejected_requests_do_not_extend_window() -> None:
    limiter = RedisRateLimiter("redis://unused/0")
    fake_redis = _FakeRedisSlidingWindow()
    limiter._redis = fake_redis  # type: ignore[assignment]
    config = RateLimitConfig(max_requests=2, window_seconds=60)

    assert limiter._SLIDING_WINDOW_SCRIPT.index("if current >=") < limiter._SLIDING_WINDOW_SCRIPT.index("ZADD")
    with patch("app.core.rate_limiter.time.time", side_effect=[0.0, 1.0, 2.0, 60.1]):
        assert (await limiter.check("client", config)).retry_after is None
        assert (await limiter.check("client", config)).retry_after is None
        assert (await limiter.check("client", config)).retry_after == pytest.approx(58.0)
        assert (await limiter.check("client", config)).retry_after is None
