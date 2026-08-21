from datetime import datetime

from app.models_multitenant import WaybillJob
from app.services.night_submission_policy import (
    TEHRAN_TZ,
    clear_expired_night_attempts,
    night_window_key,
    register_safe_night_failure,
)


def _job() -> WaybillJob:
    return WaybillJob(
        job_id="night-policy-job",
        idempotency_key="night-policy-idempotency",
        client_id=1,
        payload_json={},
    )


def test_night_window_boundaries() -> None:
    assert night_window_key(datetime(2026, 8, 16, 17, 29, tzinfo=TEHRAN_TZ)) is None
    assert night_window_key(datetime(2026, 8, 16, 17, 30, tzinfo=TEHRAN_TZ)) == "2026-08-16"
    assert night_window_key(datetime(2026, 8, 17, 7, 59, tzinfo=TEHRAN_TZ)) == "2026-08-16"
    assert night_window_key(datetime(2026, 8, 17, 8, 0, tzinfo=TEHRAN_TZ)) is None


def test_third_safe_failure_enters_standby_until_next_tehran_eight() -> None:
    job = _job()
    now = datetime(2026, 8, 16, 17, 30, tzinfo=TEHRAN_TZ)

    assert register_safe_night_failure(job, now).standby is False
    assert register_safe_night_failure(job, now).standby is False
    decision = register_safe_night_failure(job, now)

    assert decision.standby is True
    assert decision.attempt_count == 3
    assert decision.retry_at == datetime(2026, 8, 17, 4, 30)


def test_next_day_rollover_resets_night_allowance() -> None:
    job = _job()
    job.night_attempt_count = 3
    job.night_attempt_window = "2026-08-16"

    clear_expired_night_attempts(job, datetime(2026, 8, 17, 8, 0, tzinfo=TEHRAN_TZ))

    assert job.night_attempt_count == 0
    assert job.night_attempt_window is None
