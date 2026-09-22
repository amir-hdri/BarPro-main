"""The response watcher must use Playwright Python's actual Page API."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from playwright.async_api import Page

from app.automation.waybill_enhanced import EnhancedWaybillManager


async def test_response_watcher_captures_response_before_consumer_awaits():
    page = MagicMock(spec=Page)
    response_future = asyncio.get_running_loop().create_future()
    page.expect_response.return_value.__aenter__.return_value.value = response_future
    manager = EnhancedWaybillManager(page, MagicMock())
    response = MagicMock()
    payload = {"resultCode": 200, "obj": {"id": 123456, "trackingCode": "987654321"}}
    response.json = AsyncMock(return_value=payload)

    watcher = await manager._wait_for_response_match(manager._is_register_submit_response, timeout_ms=1000)
    # The response may arrive between the click and _consume_json_response.
    response_future.set_result(response)
    result = await manager._consume_json_response(watcher, timeout_seconds=1)

    assert result == payload


async def test_tracking_observation_bounds_a_stalled_read():
    manager = EnhancedWaybillManager(MagicMock(spec=Page), MagicMock())
    manager._wait_for_loading_overlays_to_disappear = AsyncMock()
    read_cancelled = asyncio.Event()

    async def stalled_read(**kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            read_cancelled.set()

    manager._extract_tracking_code = stalled_read
    result = await asyncio.wait_for(manager._wait_for_tracking_code(timeout_seconds=0.02), timeout=1)

    assert result is None
    assert read_cancelled.is_set()


async def test_tracking_observation_preserves_caller_cancellation():
    manager = EnhancedWaybillManager(MagicMock(spec=Page), MagicMock())
    started = asyncio.Event()

    async def loading_mask(**kwargs):
        started.set()
        await asyncio.Event().wait()

    manager._wait_for_loading_overlays_to_disappear = loading_mask
    observation = asyncio.create_task(manager._wait_for_tracking_code())
    await asyncio.wait_for(started.wait(), timeout=1)
    observation.cancel()

    with pytest.raises(asyncio.CancelledError):
        await observation


async def test_tracking_from_response_needs_no_further_page_read():
    manager = EnhancedWaybillManager(MagicMock(spec=Page), MagicMock())
    manager._wait_for_loading_overlays_to_disappear = AsyncMock(side_effect=AssertionError("unexpected page wait"))

    assert await manager._wait_for_tracking_code(tracking_code="987654321") == "987654321"
