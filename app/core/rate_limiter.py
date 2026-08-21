"""Rate limiting middleware for FastAPI with Redis and in-memory backends."""

import asyncio
import math
import time
import uuid
from dataclasses import dataclass

from fastapi import HTTPException, Request, Response

from app.core.config import utcms_config

try:
    import redis.asyncio as aioredis

    REDIS_AVAILABLE = True
except ImportError:
    aioredis = None
    REDIS_AVAILABLE = False


@dataclass
class RateLimitConfig:
    """Configuration for a rate limit rule."""

    max_requests: int
    window_seconds: int
    key_prefix: str = "ratelimit"


@dataclass
class RateLimitState:
    """Current state of a rate limiter."""

    remaining: int
    limit: int
    reset_at: float
    retry_after: float | None = None


class InMemoryRateLimiter:
    """In-memory sliding window rate limiter for single-process mode."""

    def __init__(self):
        self._requests: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, key: str, config: RateLimitConfig) -> RateLimitState:
        async with self._lock:
            now = time.time()
            window_start = now - config.window_seconds

            if key not in self._requests:
                self._requests[key] = []

            # Remove expired entries
            self._requests[key] = [ts for ts in self._requests[key] if ts > window_start]

            current_count = len(self._requests[key])
            oldest = self._requests[key][0] if self._requests[key] else now
            reset_at = oldest + config.window_seconds

            if current_count >= config.max_requests:
                oldest = min(self._requests[key]) if self._requests[key] else now
                retry_after = oldest + config.window_seconds - now
                return RateLimitState(
                    remaining=0,
                    limit=config.max_requests,
                    reset_at=reset_at,
                    retry_after=max(0.0, retry_after),
                )

            self._requests[key].append(now)
            return RateLimitState(
                remaining=config.max_requests - current_count - 1,
                limit=config.max_requests,
                reset_at=reset_at,
            )

    async def cleanup(self):
        """Clean up old entries periodically."""
        async with self._lock:
            now = time.time()
            keys_to_remove = []
            for key, timestamps in self._requests.items():
                self._requests[key] = [ts for ts in timestamps if ts > now - 3600]
                if not self._requests[key]:
                    keys_to_remove.append(key)
            for key in keys_to_remove:
                del self._requests[key]


class RedisRateLimiter:
    """Redis-based sliding window rate limiter for distributed mode."""

    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._redis: aioredis.Redis | None = None
        self._lock = asyncio.Lock()

    _SLIDING_WINDOW_SCRIPT = """
    redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
    local current = redis.call('ZCARD', KEYS[1])
    if current >= tonumber(ARGV[3]) then
        local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
        return {0, current, oldest[2] or ARGV[2]}
    end
    redis.call('ZADD', KEYS[1], ARGV[2], ARGV[5])
    redis.call('EXPIRE', KEYS[1], ARGV[4])
    local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
    return {1, current + 1, oldest[2] or ARGV[2]}
    """

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            async with self._lock:
                if self._redis is None:
                    self._redis = aioredis.from_url(
                        self._redis_url,
                        encoding="utf-8",
                        decode_responses=True,
                        max_connections=10,
                        socket_connect_timeout=5,
                        socket_timeout=5,
                        retry_on_timeout=True,
                    )
        return self._redis

    async def check(self, key: str, config: RateLimitConfig) -> RateLimitState:
        redis_client = await self._get_redis()
        now = time.time()
        window_start = now - config.window_seconds
        window_key = f"{config.key_prefix}:{key}"

        allowed, request_count, oldest_score = await redis_client.eval(
            self._SLIDING_WINDOW_SCRIPT,
            1,
            window_key,
            str(window_start),
            str(now),
            str(config.max_requests),
            str(config.window_seconds * 2),
            f"{now}:{uuid.uuid4().hex}",
        )
        request_count = int(request_count)
        reset_at = float(oldest_score) + config.window_seconds

        if not int(allowed):
            retry_after = reset_at - now
            return RateLimitState(
                remaining=0,
                limit=config.max_requests,
                reset_at=reset_at,
                retry_after=max(0.0, retry_after),
            )

        return RateLimitState(
            remaining=config.max_requests - request_count,
            limit=config.max_requests,
            reset_at=reset_at,
        )

    async def cleanup(self):
        """No cleanup needed for Redis."""
        pass

    async def close(self):
        """Close Redis connection."""
        if self._redis:
            # `aclose()`, not the `close()` alias: the latter is deprecated in
            # redis-py >= 5.0.1 and its DeprecationWarning is an error under the
            # suite's `filterwarnings` policy.
            await self._redis.aclose()
            self._redis = None


class RateLimiter:
    """Unified rate limiter with Redis or in-memory backend."""

    def __init__(self):
        self._backend = None
        self._rules: dict[str, RateLimitConfig] = {}
        self._setup_backend()

    def _setup_backend(self):
        """Setup rate limiter backend based on configuration."""
        if REDIS_AVAILABLE and utcms_config.QUEUE_ENABLED:
            self._backend = RedisRateLimiter(utcms_config.REDIS_URL)
        else:
            self._backend = InMemoryRateLimiter()

    def register_rule(self, name: str, max_requests: int, window_seconds: int):
        """Register a rate limit rule."""
        self._rules[name] = RateLimitConfig(
            max_requests=max_requests,
            window_seconds=window_seconds,
            key_prefix=f"ratelimit:{name}",
        )

    async def check(self, rule_name: str, client_id: str) -> RateLimitState:
        """Check if request is allowed under the given rule."""
        if rule_name not in self._rules:
            raise ValueError(f"Unknown rate limit rule: {rule_name}")

        config = self._rules[rule_name]
        key = f"{client_id}"
        return await self._backend.check(key, config)

    async def cleanup(self):
        """Cleanup backend resources."""
        await self._backend.cleanup()

    async def close(self):
        """Close backend resources."""
        if hasattr(self._backend, "close"):
            await self._backend.close()


# Default rate limiter instance
rate_limiter = RateLimiter()

# Register default rules
rate_limiter.register_rule(
    name="public",
    max_requests=60,
    window_seconds=60,
)
rate_limiter.register_rule(
    name="auth",
    max_requests=5,  # Strict: protect login from brute-force
    window_seconds=60,
)
rate_limiter.register_rule(
    name="waybill",
    max_requests=30,
    window_seconds=60,
)
rate_limiter.register_rule(
    name="driver",
    max_requests=60,
    window_seconds=60,
)
rate_limiter.register_rule(
    name="tenant",
    max_requests=100,
    window_seconds=60,
)
rate_limiter.register_rule(
    name="admin",
    max_requests=200,
    window_seconds=60,
)


def _get_tenant_id_from_request(request: Request) -> str | None:
    """Extract tenant_id from JWT token in request headers or cookies."""
    from app.auth_multitenant import _decode_jwt

    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]

    if not token:
        token = request.cookies.get("utcms_auth_token")

    if not token:
        return None

    try:
        payload = _decode_jwt(token)
        # JWT uses "sub" for tenant ID (subject claim), not "client_id"
        return str(payload.get("sub"))
    except Exception:
        return None


async def rate_limit_dependency(
    request: Request,
    rule: str = "public",
) -> RateLimitState:
    """FastAPI dependency for rate limiting."""
    # SECURITY: Use request.client.host (set by Nginx) instead of X-Forwarded-For (spoofable).
    client_ip = request.client.host if request.client else "unknown"
    tenant_id = _get_tenant_id_from_request(request)

    # Use tenant-specific key if available, otherwise fall back to IP-only
    rate_limit_key = f"{client_ip}:{tenant_id}" if tenant_id else client_ip

    try:
        state = await rate_limiter.check(rule, rate_limit_key)
    except Exception:
        # FAIL-CLOSED: If rate limiter backend is unavailable, deny request (429)
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limiter_unavailable",
                "message": "سیاست محدودیت نرخ در دسترس نیست، لطفاً بعداً تلاش کنید",
            },
            headers={"Retry-After": "10"},
        ) from None

    if state.remaining < 0 or state.retry_after is not None:
        retry_after = state.retry_after or 60
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": "تعداد درخواست‌ها بیش از حد مجاز است",
                "retry_after_seconds": round(retry_after, 2),
            },
            headers={
                "Retry-After": str(max(1, math.ceil(retry_after))),
                "X-RateLimit-Limit": str(state.limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(state.reset_at)),
            },
        )

    return state


def add_rate_limit_headers(response: Response, state: RateLimitState) -> Response:
    """Add rate limit headers to response."""
    response.headers["X-RateLimit-Limit"] = str(state.limit)
    response.headers["X-RateLimit-Remaining"] = str(max(0, state.remaining))
    response.headers["X-RateLimit-Reset"] = str(int(state.reset_at))
    return response
