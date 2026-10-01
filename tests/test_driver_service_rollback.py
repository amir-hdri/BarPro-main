"""Regression tests for DriverService.update_driver plate handling.

Covers the fix where a failed plate commit must roll the session back so the
session is not left with a poisoned transaction.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.multitenant import DriverUpdateRequest
from app.services.driver_service import DriverService


def _make_driver():
    driver = MagicMock()
    driver.id = 1
    driver.client_id = 7
    driver.driver_national_code = "0012345678"
    return driver


@pytest.mark.asyncio
async def test_update_driver_plate_commit_failure_rolls_back():
    session = AsyncMock()
    session.get.return_value = _make_driver()
    exec_result = MagicMock()
    exec_result.first.return_value = None
    session.exec.return_value = exec_result
    # First commit (driver row) succeeds, second commit (plate row) fails.
    session.commit.side_effect = [None, RuntimeError("plate commit boom")]

    req = DriverUpdateRequest(plate_number="12ب34567")

    with patch(
        "app.services.driver_service.DriverResponse.model_validate",
        return_value=MagicMock(),
    ):
        await DriverService.update_driver({"role": "master_admin"}, 1, req, session)

    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_driver_plate_commit_success_no_rollback():
    session = AsyncMock()
    session.get.return_value = _make_driver()
    exec_result = MagicMock()
    exec_result.first.return_value = None
    session.exec.return_value = exec_result
    session.commit.side_effect = [None, None]

    req = DriverUpdateRequest(plate_number="12ب34567")

    with patch(
        "app.services.driver_service.DriverResponse.model_validate",
        return_value=MagicMock(),
    ):
        await DriverService.update_driver({"role": "master_admin"}, 1, req, session)

    session.rollback.assert_not_awaited()
