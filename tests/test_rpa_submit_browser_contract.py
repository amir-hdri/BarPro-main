from unittest.mock import AsyncMock, patch

import pytest

from app.rpa.contracts import SubmitOutcome
from app.services.rpa_submit_service import RPAHttpSubmitService


def _valid_payload() -> dict:
    return {
        "sender": {"name": "علی رضایی", "national_code": "0084575948"},
        "receiver": {"name": "حسن محمدی", "national_code": "0084575948"},
        "origin": {"province": "تهران", "city": "تهران", "address": "خیابان آزادی"},
        "destination": {"province": "البرز", "city": "کرج", "address": "بلوار جمهوری"},
        "cargo": {"type": "آهن", "packaging": "فله", "weight": 1000, "value": 1000000},
        "vehicle": {"driver_national_code": "0084575948", "plate": "12ب345ایران11"},
        "financial": {},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ambiguity_marker",
    [
        {"status": "unknown"},
        {"status": "reconciling"},
        {"mutation_status": "ambiguous"},
        {"mutation_dispatched": True},
        {"needs_reconciliation": True},
    ],
)
async def test_browser_submit_ambiguous_mutation_is_never_retryable(ambiguity_marker):
    service = RPAHttpSubmitService()
    manager = AsyncMock()
    manager.create_waybill_with_map.return_value = {
        "success": False,
        "error": "response lost after submit",
        **ambiguity_marker,
    }

    with patch("app.services.rpa_submit_service.EnhancedWaybillManager", return_value=manager):
        result = await service._execute_browser_submit_with_page(
            page=AsyncMock(),
            context=AsyncMock(),
            payload=_valid_payload(),
            prior_error="http submit failed",
            require_auth_check=False,
            job_id="job-1",
        )

    assert result.classification.outcome == SubmitOutcome.UNKNOWN_ERROR
    assert result.classification.reason_code == "submission_unconfirmed"
    assert result.classification.retryable is False
    assert all(result.raw_payload[key] == value for key, value in ambiguity_marker.items())
    manager.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_browser_submit_manager_closes_when_automation_raises():
    service = RPAHttpSubmitService()
    manager = AsyncMock()
    manager.create_waybill_with_map.side_effect = RuntimeError("automation crashed")

    with patch("app.services.rpa_submit_service.EnhancedWaybillManager", return_value=manager):
        with pytest.raises(RuntimeError, match="automation crashed"):
            await service._execute_browser_submit_with_page(
                page=AsyncMock(),
                context=AsyncMock(),
                payload=_valid_payload(),
                prior_error="http submit failed",
                require_auth_check=False,
                job_id="job-2",
            )

    manager.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_browser_submit_tracking_code_witness_keeps_success_input_classification():
    service = RPAHttpSubmitService()
    manager = AsyncMock()
    manager.create_waybill_with_map.return_value = {
        "success": True,
        "status": "submitted",
        "tracking_code": "UTC-TEST-123",
        "confirmation_status": "pending_history_reconciliation",
    }

    with patch("app.services.rpa_submit_service.EnhancedWaybillManager", return_value=manager):
        result = await service._execute_browser_submit_with_page(
            page=AsyncMock(),
            context=AsyncMock(),
            payload=_valid_payload(),
            prior_error="http submit failed",
            require_auth_check=False,
            job_id="job-3",
        )

    assert result.classification.outcome == SubmitOutcome.SUCCESS
    assert result.classification.retryable is False
    assert result.raw_payload["tracking_code"] == "UTC-TEST-123"
    manager.close.assert_awaited_once()
