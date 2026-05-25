import unittest
from unittest.mock import AsyncMock, patch

from app.automation.traffic_control import WaybillTrafficController


class TestWaybillTrafficController(unittest.IsolatedAsyncioTestCase):
    async def test_slot_tracks_active_requests(self):
        controller = WaybillTrafficController()

        before = controller.snapshot()
        self.assertEqual(before.active_requests, 0)

        async with controller.slot():
            during = controller.snapshot()
            self.assertEqual(during.active_requests, 1)

        after = controller.snapshot()
        self.assertEqual(after.active_requests, 0)

    async def test_mark_temporary_block_sets_backoff(self):
        controller = WaybillTrafficController()
        await controller.mark_temporary_block(multiplier=1.0)
        snapshot = controller.snapshot()
        self.assertGreaterEqual(snapshot.blocked_for_seconds, 0.0)

    async def test_acquire_error_path_rolls_back_state(self):
        controller = WaybillTrafficController()

        # Pre-condition check
        snapshot_before = controller.snapshot()
        self.assertEqual(snapshot_before.active_requests, 0)
        self.assertEqual(snapshot_before.active_safe, 0)

        # Mock _wait_for_pacing to raise an exception
        with patch.object(controller, '_wait_for_pacing', new_callable=AsyncMock) as mock_pacing:
            mock_pacing.side_effect = RuntimeError("Mocked pacing error")

            # Expect the exception to bubble up
            with self.assertRaisesRegex(RuntimeError, "Mocked pacing error"):
                await controller.acquire(mode="safe")

        # State rollback check
        snapshot_after = controller.snapshot()
        self.assertEqual(snapshot_after.active_requests, 0)
        self.assertEqual(snapshot_after.active_safe, 0)

        # Semaphore release check: we should be able to acquire it now
        # Mock _wait_for_pacing to succeed this time to isolate semaphore logic
        with patch.object(controller, '_wait_for_pacing', new_callable=AsyncMock):
            await controller.acquire(mode="safe")
            snapshot_acquired = controller.snapshot()
            self.assertEqual(snapshot_acquired.active_requests, 1)


if __name__ == "__main__":
    unittest.main()
