import asyncio
import threading
import time
import pytest
from app.core.redis import redis_manager

@pytest.mark.asyncio
async def test_redis_connection_manager_thread_safety():
    if redis_manager is None:
        pytest.skip("redis is not available")
    try:
        client = await redis_manager.get()
        if client is None:
            pytest.skip("redis is not available")
        await client.ping()
    except Exception:
        pytest.skip("redis is not running/available")

    errors = []

    def run_loop_in_thread(thread_name):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def worker():
            for i in range(10):
                try:
                    redis_client = await redis_manager.get()
                    if redis_client is not None:
                        # Perform a basic operation
                        await redis_client.ping()
                except Exception as exc:
                    errors.append(f"Thread {thread_name} failed at step {i}: {exc}")
                await asyncio.sleep(0.05)

        loop.run_until_complete(worker())
        loop.close()

    # Start two threads running distinct event loops using the same singleton
    t1 = threading.Thread(target=run_loop_in_thread, args=("A",))
    t2 = threading.Thread(target=run_loop_in_thread, args=("B",))

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    # If there are errors, connection thrashing occurred!
    # Let's assert that no errors occurred to show if it is thread-safe (it should fail/have errors).
    print("Concurreny errors captured:", errors)
    assert len(errors) == 0, f"Found connection manager thrashing errors: {errors}"
