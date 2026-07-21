from datetime import datetime, UTC
import pytest

from app.rpa.contracts import SchedulerDecision
from app.services.rpa_scheduler_service import _as_utc
from app.services.scheduled_waybill_executor import _parse_weekdays_csv, _resolve_run_times
from app.services.rpa_runtime_service import rpa_runtime


def test_as_utc_conversion():
    now_utc = datetime.now(UTC)
    naive = _as_utc(now_utc)
    assert naive.tzinfo is None
    assert _as_utc(None) is None


def test_parse_weekdays_csv():
    assert _parse_weekdays_csv("0,2,4") == [0, 2, 4]
    assert _parse_weekdays_csv("5, 6, invalid") == [5, 6]
    assert _parse_weekdays_csv(None) == []


def test_resolve_run_times():
    class DummySchedule:
        run_times_csv = "12:00, 08:30, 15:45"
        run_time = "10:00"

    sched = DummySchedule()
    times = _resolve_run_times(sched)
    assert times == ["08:30", "12:00", "15:45"]


from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_rpa_runtime_lock_release_token_fallback():
    lock_key = "test:lock:key:123"
    with patch.object(rpa_runtime, "_get_redis", new_callable=AsyncMock, return_value=None):
        # Acquire lock in memory
        acquired = await rpa_runtime.acquire_lock(lock_key, ttl_seconds=60)
        assert acquired is True
        
        # Releasing lock without passing explicit token (simulating lost ContextVar)
        await rpa_runtime.release_lock(lock_key)
        
        # Should now be free to acquire again
        reacquired = await rpa_runtime.acquire_lock(lock_key, ttl_seconds=60)
        assert reacquired is True
        await rpa_runtime.release_lock(lock_key)
