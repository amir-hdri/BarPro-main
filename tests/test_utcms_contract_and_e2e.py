"""Contract tests and end-to-end flow tests for UTCMS integration."""

import json
from pathlib import Path

from app.core.config import utcms_config
from app.orchestrator.state_machine import ALLOWED_TRANSITIONS

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "utcms"


def test_default_config_redlines():
    """Verify safety default configuration values."""
    assert utcms_config.ALLOW_LIVE_SUBMIT is False
    assert utcms_config.PREDICTED_OTP_FREE_START_HOUR == 17
    assert utcms_config.PREDICTED_OTP_FREE_START_MINUTE == 30
    assert utcms_config.PREDICTED_OTP_FREE_END_HOUR == 8
    assert utcms_config.PREDICTED_OTP_FREE_END_MINUTE == 0


def test_all_fixtures_valid_json_and_contract():
    """Verify all sanitized UTCMS fixtures are valid and comply with schema expectations."""
    fixture_files = list(FIXTURES_DIR.glob("*.json"))
    assert len(fixture_files) >= 7

    for fpath in fixture_files:
        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)
            assert data is not None

            # Verify no plaintext test passwords or credentials leaked in fixtures
            raw_str = json.dumps(data)
            assert "PLACEHOLDER_SSH_PASSWORD" not in raw_str
            assert "driver_pass" not in raw_str


def test_gate_state_transitions_in_state_machine():
    """Verify WAITING_SUBMISSION_WINDOW is a first-class state with legal transitions."""
    assert "waiting_submission_window" in ALLOWED_TRANSITIONS
    # From waiting_submission_window, allowed to transition to queued, pending, in_progress, cancelled, etc.
    allowed = ALLOWED_TRANSITIONS["waiting_submission_window"]
    assert "queued" in allowed
    assert "in_progress" in allowed
    assert "cancelled" in allowed
