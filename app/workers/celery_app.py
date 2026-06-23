from __future__ import annotations

from app.core.config import utcms_config

try:
    from celery import Celery
    from celery.schedules import crontab, schedule
except Exception:
    Celery = None  # type: ignore
    schedule = None  # type: ignore
    crontab = None  # type: ignore


def _build_celery() -> Celery | None:
    if Celery is None:
        return None

    app = Celery(
        "utcms",
        broker=utcms_config.CELERY_BROKER_URL,
        backend=utcms_config.CELERY_RESULT_BACKEND,
        include=["app.workers.tasks"],
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
