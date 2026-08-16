from __future__ import annotations

import importlib
import logging
import os

from app.automation.proxy_rotator import get_proxy_rotator
from app.core.config import utcms_config

logger = logging.getLogger(__name__)

try:
    from celery import Celery
    from celery.schedules import crontab, schedule
    from celery.signals import worker_process_init
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


def _build_beat_schedule() -> dict:
    schedule_dict = {}

    # Note: DEPRECATE_OLD_EXECUTION_PATH defaults to True, meaning the old execution path is disabled by default.
    # Set to False to enable legacy phase1 scheduler tasks (not recommended for production).
    if not utcms_config.DEPRECATE_OLD_EXECUTION_PATH:
        schedule_dict.update(
            {
                "phase1-scheduler-plan": {
                    "task": "phase1.scheduler.plan",
                    "schedule": schedule(utcms_config.RPA_SCHEDULER_INTERVAL_SECONDS),
                    "options": {
                        "queue": utcms_config.RPA_SCHEDULER_QUEUE,
                        "expires": max(10, utcms_config.RPA_SCHEDULER_INTERVAL_SECONDS - 5),
                    },
                },
                "phase1-scheduler-cleanup": {
                    "task": "phase1.scheduler.cleanup",
                    "schedule": crontab(minute="*/5"),
                    "options": {
                        "queue": utcms_config.RPA_SCHEDULER_QUEUE,
                        "expires": 240,
                    },
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
            }
        )

    schedule_dict.update(
        {
            # rpa-session-keepalive does heavyweight browser re-auth for drivers. It
            # must NOT run on the singleton rpa_scheduler control queue (whose
            # dispatcher fires every 5s and must never sit behind a minutes-long
            # browser task). It is routed to the ordinary waybill worker queue and
            # expires (never accumulates in Redis when no consumer is up — X8).
            "rpa-session-keepalive": {
                "task": "rpa.session.keepalive",
                "schedule": crontab(minute="*/30"),
                "options": {
                    "queue": utcms_config.CELERY_WAYBILL_TASKS_QUEUE,
                    "expires": 1500,
                },
            },
            "orchestrator-scheduler": {
                "task": "orchestrator.scheduler.run",
                "schedule": schedule(utcms_config.RPA_SCHEDULER_INTERVAL_SECONDS),
                "options": {
                    "queue": utcms_config.RPA_SCHEDULER_QUEUE,
                    "expires": max(10, utcms_config.RPA_SCHEDULER_INTERVAL_SECONDS - 5),
                },
            },
            "orchestrator-dispatcher": {
                "task": "orchestrator.dispatcher.run",
                "schedule": schedule(5.0),
                "options": {
                    "queue": utcms_config.RPA_SCHEDULER_QUEUE,
                    "expires": 4,
                },
            },
            "orchestrator-orphan-detector": {
                "task": "orchestrator.orphan_detector.run",
                "schedule": schedule(30.0),
                "options": {
                    "queue": utcms_config.RPA_SCHEDULER_QUEUE,
                    "expires": 25,
                },
            },
            "orchestrator-claim-reaper": {
                "task": "orchestrator.claim_reaper.run",
                "schedule": schedule(60.0),
                "options": {
                    "queue": utcms_config.RPA_SCHEDULER_QUEUE,
                    "expires": 50,
                },
            },
            # Reconciliation opens Playwright + proxies (heavy browser work) — same
            # reasoning as rpa-session-keepalive: keep it off the 5s control queue so
            # the dispatcher is never starved. expires prevents unbounded backlog.
            "orchestrator-reconciliation": {
                "task": "orchestrator.reconciliation.run",
                "schedule": crontab(minute="*/15"),
                "options": {
                    "queue": utcms_config.CELERY_RECONCILIATION_TASKS_QUEUE,
                    "expires": 840,
                },
            },
            "fuel-inquiry-cleanup-stale": {
                "task": "fuel.cleanup_stale_inquiries",
                "schedule": crontab(minute="*/10"),
                "options": {
                    "queue": utcms_config.RPA_SCHEDULER_QUEUE,
                    "expires": 540,
                },
            },
            "utcms-gate-probe": {
                "task": "barpro.gate.probe",
                "schedule": schedule(utcms_config.GATE_PROBE_INTERVAL_SECONDS),
                "options": {
                    "queue": utcms_config.RPA_SCHEDULER_QUEUE,
                    "expires": max(10, utcms_config.GATE_PROBE_INTERVAL_SECONDS - 5),
                },
            },
        }
    )

    return schedule_dict


def _build_celery() -> Celery | None:
    if Celery is None:
        return None

    app = Celery(
        "utcms",
        broker=utcms_config.CELERY_BROKER_URL,
        backend=utcms_config.CELERY_RESULT_BACKEND,
        include=["app.workers.tasks", "app.workers.phase1_tasks", "app.workers.waybill_worker"],
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
        beat_scheduler="redbeat.RedBeatScheduler",
        redbeat_redis_url=utcms_config.REDIS_URL,
        redbeat_lock_timeout=120,
        beat_schedule=_build_beat_schedule(),
    )
    return app


celery_app = _build_celery()

if celery_app is not None:
    # Import for Celery signal-registration side effects.
    importlib.import_module("app.orchestrator.worker_lifecycle")


def is_celery_available() -> bool:
    return celery_app is not None
