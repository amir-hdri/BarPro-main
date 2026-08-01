import asyncio
import logging

from app.core.alerts import alert_manager
from app.core.config import utcms_config
from app.services.task_service import task_service
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


class RecoveryManager:
    async def recover_stalled_tasks(self) -> dict[str, dict[str, float | str]]:
        from app.orchestrator.orphan_detector import orphan_detector
        # Run the new database-lease based orphan detector
        try:
            await orphan_detector.run()
        except Exception as err:
            logger.error(f"New database-lease orphan detector failed in watchdog: {err}", exc_info=True)

        return {}

    async def watchdog_loop(self) -> None:
        while True:
            try:
                await self.recover_stalled_tasks()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("recovery_watchdog_failed", extra={"extra_fields": {"error": str(exc)}})
            await asyncio.sleep(max(5.0, utcms_config.WORKER_HEARTBEAT_INTERVAL_SECONDS))


recovery_manager = RecoveryManager()
