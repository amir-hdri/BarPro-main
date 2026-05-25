"""Backward-compatible Redis import shim."""

from app.core.redis import RedisConnectionManager, redis_manager

__all__ = ["RedisConnectionManager", "redis_manager"]
