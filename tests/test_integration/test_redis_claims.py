"""Run shipping lock SET-NX and compare/delete Lua against an actual Redis server."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from redis.asyncio import Redis

from app.automation import gps_shipping_manager as shipping

pytestmark = pytest.mark.integration


async def test_concurrent_shipping_claims_have_one_owner(
    redis_claim_store: tuple[Redis, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    redis, job_id = redis_claim_store
    monkeypatch.setattr(shipping, "_get_redis", AsyncMock(return_value=redis))
    results = await asyncio.gather(*(shipping._acquire_completion_claim(job_id) for _ in range(24)))
    owners = [token for token in results if token is not None]
    assert len(owners) == 1
    for template in (shipping.COMPLETION_CLAIM_KEY, shipping.LEGACY_COMPLETION_CLAIM_KEY):
        assert await redis.get(template.format(job_id=job_id)) == owners[0]
    await shipping._release_completion_claim(job_id, owners[0])
    assert await shipping._completion_claim_is_held(job_id) is False


async def test_stale_owner_cannot_delete_reacquired_shipping_claim(
    redis_claim_store: tuple[Redis, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    redis, job_id = redis_claim_store
    monkeypatch.setattr(shipping, "_get_redis", AsyncMock(return_value=redis))
    old_token = await shipping._acquire_completion_claim(job_id)
    assert old_token
    for template in (shipping.COMPLETION_CLAIM_KEY, shipping.LEGACY_COMPLETION_CLAIM_KEY):
        await redis.pexpire(template.format(job_id=job_id), 1)
    await asyncio.sleep(0.02)
    new_token = await shipping._acquire_completion_claim(job_id)
    assert new_token and new_token != old_token
    await shipping._release_completion_claim(job_id, old_token)
    for template in (shipping.COMPLETION_CLAIM_KEY, shipping.LEGACY_COMPLETION_CLAIM_KEY):
        assert await redis.get(template.format(job_id=job_id)) == new_token


async def test_legacy_claim_rolls_back_partial_new_claim(
    redis_claim_store: tuple[Redis, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    redis, job_id = redis_claim_store
    monkeypatch.setattr(shipping, "_get_redis", AsyncMock(return_value=redis))
    legacy_key = shipping.LEGACY_COMPLETION_CLAIM_KEY.format(job_id=job_id)
    current_key = shipping.COMPLETION_CLAIM_KEY.format(job_id=job_id)
    await redis.set(legacy_key, "older-worker", ex=30)
    assert await shipping._acquire_completion_claim(job_id) is None
    assert await redis.get(current_key) is None
    assert await redis.get(legacy_key) == "older-worker"
