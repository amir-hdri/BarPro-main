from __future__ import annotations

import logging
import os

from app.core.config import utcms_config
from app.automation.proxy_rotator import get_proxy_rotator

logger = logging.getLogger(__name__)

try:
    from celery import Celery
    from celery.signals import worker_process_init
    from celery.schedules import crontab, schedule
except Exception:
    Celery = None  # type: ignore
    schedule = None  # type: ignore
    crontab = None  # type: ignore
    worker_process_init = None  # type: ignore

if worker_process_init is not None:
    @worker_process_init.connect
    def configure_worker_proxies(**kwargs):
        """Initialize proxies in the worker process when it boots."""
        proxy_rotator = get_proxy_rotator()
        
        # Load from file if configured
        if os.getenv("RPA_PROXY_LIST_FILE"):
            proxy_rotator.load_from_file(os.getenv("RPA_PROXY_LIST_FILE"))
        # Load from environment variable (Docker Compose)
        elif os.getenv("RPA_PROXIES"):
            proxy_urls = [p.strip() for p in os.getenv("RPA_PROXIES").split(",") if p.strip()]
            proxy_rotator.load_from_list(proxy_urls)
            
        if proxy_rotator.proxies:
            logger.info(f"Worker initialized with {len(proxy_rotator.proxies)} RPA proxies.")
        else:
            logger.warning("No RPA proxies loaded in worker. Automation will run on local IP.")



def _build_celery() -> Celery | None:
    if Celery is None:
        return None

    app = Celery(
        "utcms",
        broker=utcms_config.CELERY_BROKER_URL,
        backend=utcms_config.CELERY_RESULT_BACKEND,
        include=[
            "app.workers.tasks",
            "app.workers.phase1_tasks",
            "app.workers.waybill_worker"
        ],
    )
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        task_default_queue=utcms_config.CELERY_TASK_QUEUE,
        worker_prefetch_multiplier=max(1, utcms_config.CELERY_WORKER_PREFETCH_MULTIPLIER),
        task_acks_late=True,
        task_track_started=True,
        task_soft_time_limit=utcms_config.CELERY_TASK_SOFT_TIME_LIMIT,
        task_time_limit=utcms_config.CELERY_TASK_TIME_LIMIT,
        beat_schedule={
            "phase1-scheduler-plan": {
                "task": "phase1.scheduler.plan",
                "schedule": schedule(utcms_config.RPA_SCHEDULER_INTERVAL_SECONDS),
                "options": {"queue": utcms_config.RPA_SCHEDULER_QUEUE},
            },
            "phase1-scheduler-cleanup": {
                "task": "phase1.scheduler.cleanup",
                "schedule": crontab(minute="*/5"),
                "options": {"queue": utcms_config.RPA_SCHEDULER_QUEUE},
            },
            "scheduled-waybill-evaluate": {
                "task": "scheduled.waybill.evaluate_and_run",
                "schedule": crontab(minute="*/10"),
                "options": {"queue": "scheduled_tasks"},
            },
            "scheduled-waybill-retry": {
                "task": "scheduled.waybill.retry_failed",
                "schedule": crontab(minute="*/15"),
                "options": {"queue": "scheduled_tasks"},
            },
            "scheduled-waybill-clear-expired": {
                "task": "scheduled.waybill.clear_expired",
                "schedule": crontab(hour="0", minute="0"),
                "options": {"queue": "scheduled_tasks"},
            },
        },
    )
    return app


celery_app = _build_celery()


def is_celery_available() -> bool:
    return celery_app is not None
