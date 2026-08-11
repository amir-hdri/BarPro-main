from app.core.config import utcms_config
from app.workers.celery_app import celery_app


def test_celery_redbeat_configuration():
    """Verify that celery-redbeat is configured correctly on the Celery app."""
    assert celery_app is not None
    assert celery_app.conf.beat_scheduler == "redbeat.RedBeatScheduler"
    assert celery_app.conf.redbeat_redis_url == utcms_config.REDIS_URL
    # Lock timeout raised from 30s to 120s to prevent race when scheduler tasks run >30s
    assert celery_app.conf.redbeat_lock_timeout == 120
