"""Rate limiting middleware for FastAPI with Redis and in-memory backends."""

import asyncio
import time
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
            reset_at = now + config.window_seconds

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

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            async with self._lock:
                if self._redis is None:
                    self._redis = aioredis.from_url(
                        self._redis_url,
                        encoding="utf-8",
                        decode_responses=True,
                    )
        return self._redis

    async def check(self, key: str, config: RateLimitConfig) -> RateLimitState:
        redis_client = await self._get_redis()
        now = time.time()
        window_start = now - config.window_seconds
        window_key = f"{config.key_prefix}:{key}"

        pipe = redis_client.pipeline()
        # Remove expired entries
        pipe.zremrangebyscore(window_key, 0, window_start)
        # Count current requests
        pipe.zcard(window_key)
        # Add current request
        pipe.zadd(window_key, {str(now): now})
        # Set expiry
        pipe.expire(window_key, config.window_seconds * 2)
        results = await pipe.execute()

        current_count = results[1]
        reset_at = now + config.window_seconds

        if current_count >= config.max_requests:
            oldest = await redis_client.zrange(window_key, 0, 0, withscores=True)
            if oldest:
                retry_after = oldest[0][1] + config.window_seconds - now
            else:
                retry_after = config.window_seconds
            return RateLimitState(
                remaining=0,
                limit=config.max_requests,
                reset_at=reset_at,
                retry_after=max(0.0, retry_after),
            )

        return RateLimitState(
            remaining=config.max_requests - current_count - 1,
            limit=config.max_requests,
            reset_at=reset_at,
        )

    async def cleanup(self):
        """No cleanup needed for Redis."""
        pass

    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
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


async def rate_limit_dependency(
    request: Request,
    rule: str = "public",
) -> RateLimitState:
    """FastAPI dependency for rate limiting."""
    client_ip = request.client.host if request.client else "unknown"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()

    try:
        state = await rate_limiter.check(rule, client_ip)
    except Exception:
        # Fail open - allow request if rate limiter fails
        return RateLimitState(
            remaining=999,
            limit=999,
            reset_at=time.time() + 60,
        )

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
                "Retry-After": str(int(retry_after)),
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
