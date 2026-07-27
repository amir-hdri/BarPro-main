"""JWT token blacklist backed by Redis with automatic TTL expiry.

Tokens are blacklisted by their ``jti`` (JWT ID) claim.  The Redis key
uses a TTL equal to the token's remaining lifetime so that entries are
automatically cleaned up once the token would have expired anyway.

When Redis is unavailable the blacklist degrades gracefully: ``is_blacklisted``
returns ``False`` (fail-open for reads) but ``blacklist_token`` logs a warning
(calls can still invalidate tokens locally in-memory as a secondary defense).
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime

from app.core.redis_client import redis_manager

logger = logging.getLogger(__name__)

_REDIS_KEY_PREFIX = "jwt:blacklist:"

# In-memory fallback set for when Redis is unavailable.  Entries here are
# never cleaned up automatically, so this is a best-effort defense only.
_mem_fallback: set[str] = set()
_mem_lock = threading.Lock()


async def blacklist_token(jti: str, expires_at: datetime) -> None:
    """Add a token's JTI to the blacklist.

    The Redis key TTL is set to the number of seconds between *now* and
    ``expires_at`` so that the entry self-expires when the token would have
    become invalid regardless.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    exp = expires_at
    if exp.tzinfo is not None:
        exp = exp.astimezone(UTC).replace(tzinfo=None)
    ttl_seconds = max(1, int((exp - now).total_seconds()))

    with _mem_lock:
        _mem_fallback.add(jti)

    try:
        redis = await redis_manager.get()
        if redis is None:
            logger.warning("token_blacklist_redis_unavailable", extra={"extra_fields": {"jti": jti}})
            return
        await redis.set(f"{_REDIS_KEY_PREFIX}{jti}", "1", ex=ttl_seconds)
    except Exception:
        logger.warning("token_blacklist_set_failed", exc_info=True, extra={"extra_fields": {"jti": jti}})


async def is_blacklisted(jti: str) -> bool:
    """Return ``True`` if the given JTI has been blacklisted.

    Returns ``False`` when Redis is unavailable (fail-open) to avoid
    blocking all authentication.  The in-memory fallback provides a
    secondary defense for tokens blacklisted in the same process.
    """
    with _mem_lock:
        if jti in _mem_fallback:
            return True

    try:
        redis = await redis_manager.get()
        if redis is None:
            logger.warning("token_blacklist_redis_unavailable_failing_closed", extra={"extra_fields": {"jti": jti}})
            return True
        return bool(await redis.exists(f"{_REDIS_KEY_PREFIX}{jti}"))
    except Exception:
        logger.warning("token_blacklist_check_failed_failing_closed", exc_info=True)
        return True
