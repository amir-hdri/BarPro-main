"""Beat-schedule wiring tests.

Every task name referenced by the Celery beat schedule must have a registered
task handler; otherwise beat fires into the void and the periodic job silently
never runs. Previously this wiring was untested.
"""
import pytest


@pytest.fixture(scope="module")
def beat_wiring():
    from app.workers.celery_app import _build_beat_schedule, celery_app

    # Mirror what a production celery worker does: import every module in the
    # app's `include` list so their @task decorators actually register.
    for module_name in celery_app.conf.include:
        __import__(module_name)

    return _build_beat_schedule(), celery_app


def test_beat_schedule_is_nonempty(beat_wiring):
    schedule, _ = beat_wiring
    assert len(schedule) >= 5, "beat schedule unexpectedly small — tasks may have been dropped"


def test_every_beat_task_has_registered_handler(beat_wiring):
    schedule, celery_app = beat_wiring
    registered = set(celery_app.tasks.keys())
    missing = [
        entry["task"]
        for name, entry in schedule.items()
        if entry["task"] not in registered
    ]
    assert not missing, f"beat entries with no registered task handler: {missing}"


def test_orchestrator_beat_tasks_wired(beat_wiring):
    """The five core orchestrator periodic tasks must be scheduled AND registered."""
    schedule, celery_app = beat_wiring
    scheduled_tasks = {entry["task"] for entry in schedule.values()}
    for task_name in [
        "orchestrator.scheduler.run",
        "orchestrator.dispatcher.run",
        "orchestrator.orphan_detector.run",
        "orchestrator.claim_reaper.run",
        "orchestrator.reconciliation.run",
    ]:
        assert task_name in scheduled_tasks, f"{task_name} missing from beat schedule"
        assert task_name in celery_app.tasks, f"{task_name} has no registered handler"


def test_beat_entries_have_queue_and_expiry(beat_wiring):
    """Every beat entry must route to a queue and expire, so ticks never pile up."""
    schedule, _ = beat_wiring
    for name, entry in schedule.items():
        options = entry.get("options", {})
        assert options.get("queue"), f"beat entry {name!r} has no queue"
        assert options.get("expires"), f"beat entry {name!r} has no expiry"
