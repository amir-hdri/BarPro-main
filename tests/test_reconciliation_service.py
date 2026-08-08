"""
Unit tests for Reconciliation Service and Scraper.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

from app.core.error_taxonomy import ErrorCategory
from app.models_multitenant import WaybillJob
from app.orchestrator.reconciliation_service import ReconciliationService
from app.orchestrator.state_machine import JobStatus
from app.orchestrator.utcms_reconciliation_scraper import ReconciliationResult, ScraperOutcome


@pytest.fixture(autouse=True)
def dev_env():
    """Ensure tests run in development mode (fail-open for proxy)."""
    with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
        yield


@pytest.fixture
async def async_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async_session = AsyncSession(engine, expire_on_commit=False)

    from app.models_multitenant import Client, Driver
    client = Client(
        id=1,
        client_code="test_client",
        name="Test Client",
        username="testclient",
        full_name="Test Client",
        email="test@client.com",
        hashed_password="hash",
    )
    driver = Driver(
        id=1,
        client_id=1,
        driver_national_code="1234567890",
        full_name="Test Driver",
        utcms_username="test_driver",
        utcms_password_encrypted="enc_pass",
        encrypted_password="enc",
    )
    async_session.add(client)
    async_session.add(driver)
    await async_session.commit()

    yield async_session
    await async_session.close()
    await engine.dispose()


@pytest.mark.asyncio
async def test_reconcile_job_registered(async_db: AsyncSession):
    job = WaybillJob(
        job_id="test_job_1",
        idempotency_key="idemp_job_1",
        client_id=1,
        driver_id=1,
        payload_json={"origin_city_id": 1, "destination_city_id": 2},
        status=JobStatus.UNKNOWN,
    )
    async_db.add(job)
    await async_db.commit()
    await async_db.refresh(job)

    mock_bm = MagicMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_bm.create_context = AsyncMock(return_value=("session-123", mock_context))
    mock_bm.new_page = AsyncMock(return_value=mock_page)

    mock_res = ReconciliationResult(
        outcome=ScraperOutcome.REGISTERED,
        tracking_code="UTC-2026-9999",
    )

    with patch("app.orchestrator.reconciliation_service.reconciliation_scraper.query_waybill_status", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = mock_res

        rec_service = ReconciliationService()
        reconciled_job = await rec_service.reconcile_job(
            session=async_db, job_id=job.id, browser_manager=mock_bm
        )

        assert reconciled_job is not None
        assert reconciled_job.status == JobStatus.SUCCESS
        assert (reconciled_job.result_json or {}).get("tracking_code") == "UTC-2026-9999"


@pytest.mark.asyncio
async def test_reconcile_job_not_found(async_db: AsyncSession):
    job = WaybillJob(
        job_id="test_job_2",
        idempotency_key="idemp_job_2",
        client_id=1,
        driver_id=1,
        payload_json={"origin_city_id": 1, "destination_city_id": 2},
        status=JobStatus.UNKNOWN,
    )
    async_db.add(job)
    await async_db.commit()
    await async_db.refresh(job)

    mock_bm = MagicMock()
    mock_context = AsyncMock()
    mock_context.close = AsyncMock()
    mock_page = AsyncMock()
    mock_page.close = AsyncMock()
    mock_bm.create_context = AsyncMock(return_value=("session-123", mock_context))
    mock_bm.new_page = AsyncMock(return_value=mock_page)

    mock_res = ReconciliationResult(outcome=ScraperOutcome.NOT_FOUND)

    with patch("app.orchestrator.reconciliation_service.reconciliation_scraper.query_waybill_status", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = mock_res

        rec_service = ReconciliationService()
        reconciled_job = await rec_service.reconcile_job(
            session=async_db, job_id=job.id, browser_manager=mock_bm
        )

        assert reconciled_job is not None
        assert reconciled_job.status == JobStatus.FAILED
        assert reconciled_job.error_category == ErrorCategory.SUBMISSION_UNCONFIRMED.value
        assert "not registered" in (reconciled_job.last_error or "").lower()


@pytest.mark.asyncio
async def test_reconcile_job_ambiguous(async_db: AsyncSession):
    job = WaybillJob(
        job_id="test_job_3",
        idempotency_key="idemp_job_3",
        client_id=1,
        driver_id=1,
        payload_json={"origin_city_id": 1, "destination_city_id": 2},
        status=JobStatus.UNKNOWN,
    )
    async_db.add(job)
    await async_db.commit()
    await async_db.refresh(job)

    mock_bm = MagicMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_bm.create_context = AsyncMock(return_value=("session-123", mock_context))
    mock_bm.new_page = AsyncMock(return_value=mock_page)

    mock_res = ReconciliationResult(outcome=ScraperOutcome.AMBIGUOUS)

    with patch("app.orchestrator.reconciliation_service.reconciliation_scraper.query_waybill_status", new_callable=AsyncMock) as mock_query, \
         patch("app.orchestrator.reconciliation_service.admin_alert_service.check_repeated_unknown_submission", new_callable=AsyncMock) as mock_alert_check:
        mock_query.return_value = mock_res

        rec_service = ReconciliationService()
        reconciled_job = await rec_service.reconcile_job(
            session=async_db, job_id=job.id, browser_manager=mock_bm
        )

        assert reconciled_job is not None
        assert reconciled_job.status == JobStatus.NEEDS_REVIEW
        assert reconciled_job.error_category == ErrorCategory.SUBMISSION_UNCONFIRMED.value
        mock_alert_check.assert_awaited_once()
