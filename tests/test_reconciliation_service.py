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
        mutation_status="dispatched",
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

    with patch(
        "app.orchestrator.reconciliation_service.reconciliation_scraper.query_waybill_status", new_callable=AsyncMock
    ) as mock_query:
        mock_query.return_value = mock_res

        rec_service = ReconciliationService()
        reconciled_job = await rec_service.reconcile_job(session=async_db, job_id=job.id, browser_manager=mock_bm)

        assert reconciled_job is not None
        assert reconciled_job.status == JobStatus.SUCCESS
        assert (reconciled_job.result_json or {}).get("tracking_code") == "UTC-2026-9999"


@pytest.mark.asyncio
async def test_manual_reconcile_allows_unconfirmed_needs_review(async_db: AsyncSession):
    """A terminal ambiguity can be searched in History without permitting resubmission."""
    job = WaybillJob(
        job_id="test_job_manual_reconcile",
        idempotency_key="idemp_manual_reconcile",
        client_id=1,
        driver_id=1,
        payload_json={"origin_city_id": 1, "destination_city_id": 2},
        status=JobStatus.NEEDS_REVIEW,
        mutation_status="ambiguous",
        error_category=ErrorCategory.SUBMISSION_UNCONFIRMED.value,
    )
    async_db.add(job)
    await async_db.commit()
    await async_db.refresh(job)

    mock_bm = MagicMock()
    mock_bm.create_context = AsyncMock(return_value=("session-manual", AsyncMock()))
    mock_bm.new_page = AsyncMock(return_value=AsyncMock())

    mock_res = ReconciliationResult(
        outcome=ScraperOutcome.REGISTERED,
        tracking_code="UTC-2026-MANUAL",
    )

    with patch(
        "app.orchestrator.reconciliation_service.reconciliation_scraper.query_waybill_status", new_callable=AsyncMock
    ) as mock_query:
        mock_query.return_value = mock_res
        reconciled_job = await ReconciliationService().reconcile_job(
            session=async_db,
            job_id=job.id,
            browser_manager=mock_bm,
        )

    assert reconciled_job is not None
    assert reconciled_job.status == JobStatus.SUCCESS
    assert (reconciled_job.result_json or {}).get("tracking_code") == "UTC-2026-MANUAL"
    mock_query.assert_awaited_once()


@pytest.mark.asyncio
async def test_reconcile_job_not_found_eventual_consistency(async_db: AsyncSession):
    job = WaybillJob(
        job_id="test_job_2",
        idempotency_key="idemp_job_2",
        client_id=1,
        driver_id=1,
        payload_json={"origin_city_id": 1, "destination_city_id": 2},
        status=JobStatus.UNKNOWN,
        mutation_status="dispatched",
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

    with patch(
        "app.orchestrator.reconciliation_service.reconciliation_scraper.query_waybill_status", new_callable=AsyncMock
    ) as mock_query:
        mock_query.return_value = mock_res

        rec_service = ReconciliationService()
        # Attempt 1: Should remain in RECONCILING with next_retry_at set
        reconciled_job = await rec_service.reconcile_job(session=async_db, job_id=job.id, browser_manager=mock_bm)

        assert reconciled_job is not None
        assert reconciled_job.status == JobStatus.RECONCILING
        assert reconciled_job.next_retry_at is not None
        assert reconciled_job.mutation_status == "dispatched"


@pytest.mark.asyncio
async def test_reconcile_job_not_found_exhausted_moves_to_needs_review(async_db: AsyncSession):
    job = WaybillJob(
        job_id="test_job_2_exhausted",
        idempotency_key="idemp_job_2_ex",
        client_id=1,
        driver_id=1,
        payload_json={"origin_city_id": 1, "destination_city_id": 2, "reconciliation_attempts": 4},
        status=JobStatus.RECONCILING,
    )
    async_db.add(job)
    await async_db.commit()
    await async_db.refresh(job)

    mock_bm = MagicMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_bm.create_context = AsyncMock(return_value=("session-123", mock_context))
    mock_bm.new_page = AsyncMock(return_value=mock_page)

    mock_res = ReconciliationResult(outcome=ScraperOutcome.NOT_FOUND)

    with patch(
        "app.orchestrator.reconciliation_service.reconciliation_scraper.query_waybill_status", new_callable=AsyncMock
    ) as mock_query:
        mock_query.return_value = mock_res

        rec_service = ReconciliationService()
        # Attempt 5: Exhausted -> Should move to NEEDS_REVIEW
        reconciled_job = await rec_service.reconcile_job(session=async_db, job_id=job.id, browser_manager=mock_bm)

        assert reconciled_job is not None
        assert reconciled_job.status == JobStatus.NEEDS_REVIEW
        assert reconciled_job.error_category == ErrorCategory.SUBMISSION_UNCONFIRMED.value


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

    with (
        patch(
            "app.orchestrator.reconciliation_service.reconciliation_scraper.query_waybill_status",
            new_callable=AsyncMock,
        ) as mock_query,
        patch(
            "app.orchestrator.reconciliation_service.admin_alert_service.check_repeated_unknown_submission",
            new_callable=AsyncMock,
        ) as mock_alert_check,
    ):
        mock_query.return_value = mock_res

        rec_service = ReconciliationService()
        reconciled_job = await rec_service.reconcile_job(session=async_db, job_id=job.id, browser_manager=mock_bm)

        assert reconciled_job is not None
        assert reconciled_job.status == JobStatus.NEEDS_REVIEW
        assert reconciled_job.error_category == ErrorCategory.SUBMISSION_UNCONFIRMED.value
        mock_alert_check.assert_awaited_once()


@pytest.mark.asyncio
async def test_tracking_received_job_is_not_auto_reconciled(async_db: AsyncSession):
    """A tracking-received job must never enter the auto reconciliation path."""
    job = WaybillJob(
        job_id="test_job_tracking_ack",
        idempotency_key="idemp_tracking_ack",
        client_id=1,
        driver_id=1,
        payload_json={"origin_city_id": 1, "destination_city_id": 2},
        status=JobStatus.UNKNOWN,
        mutation_status="dispatched",
        result_json={
            "tracking_code": "UTC-ACK-1",
            "confirmation_status": "tracking_received",
            "operator_acknowledged": True,
            "requires_reconciliation": False,
            "requires_resubmission": False,
        },
    )
    async_db.add(job)
    await async_db.commit()
    await async_db.refresh(job)

    mock_bm = MagicMock()

    with patch(
        "app.orchestrator.reconciliation_service.reconciliation_scraper.query_waybill_status", new_callable=AsyncMock
    ) as mock_query:
        rec_service = ReconciliationService()
        reconciled_job = await rec_service.reconcile_job(session=async_db, job_id=job.id, browser_manager=mock_bm)

        mock_query.assert_not_called()
        assert reconciled_job is not None
        assert reconciled_job.status == JobStatus.UNKNOWN
        assert (reconciled_job.result_json or {}).get("tracking_code") == "UTC-ACK-1"
        assert (reconciled_job.result_json or {}).get("confirmation_status") == "tracking_received"


@pytest.mark.asyncio
async def test_audit_only_forces_reconciliation_for_tracking_received_job(async_db: AsyncSession):
    """The manual audit path (audit_only=True) proceeds even for acknowledged jobs."""
    job = WaybillJob(
        job_id="test_job_tracking_audit",
        idempotency_key="idemp_tracking_audit",
        client_id=1,
        driver_id=1,
        payload_json={"origin_city_id": 1, "destination_city_id": 2},
        status=JobStatus.UNKNOWN,
        mutation_status="dispatched",
        result_json={
            "tracking_code": "UTC-ACK-2",
            "confirmation_status": "tracking_received",
            "operator_acknowledged": True,
        },
    )
    async_db.add(job)
    await async_db.commit()
    await async_db.refresh(job)

    mock_bm = MagicMock()
    mock_bm.create_context = AsyncMock(return_value=("session-a", AsyncMock()))
    mock_bm.new_page = AsyncMock(return_value=AsyncMock())

    mock_res = ReconciliationResult(outcome=ScraperOutcome.REGISTERED, tracking_code="UTC-ACK-2")

    with patch(
        "app.orchestrator.reconciliation_service.reconciliation_scraper.query_waybill_status", new_callable=AsyncMock
    ) as mock_query:
        mock_query.return_value = mock_res
        rec_service = ReconciliationService()
        reconciled_job = await rec_service.reconcile_job(
            session=async_db, job_id=job.id, browser_manager=mock_bm, audit_only=True
        )

        mock_query.assert_awaited()
        assert reconciled_job.status == JobStatus.SUCCESS
        assert (reconciled_job.result_json or {}).get("confirmation_status") == "confirmed_by_history"


@pytest.mark.asyncio
async def test_tracking_received_job_in_reconciling_heals_to_unknown(async_db: AsyncSession):
    """A tracking-received job stranded in RECONCILING (claim race) must heal
    to UNKNOWN with the code preserved — never stay stuck, never resubmit."""
    job = WaybillJob(
        job_id="test_job_tracking_heal",
        idempotency_key="idemp_tracking_heal",
        client_id=1,
        driver_id=1,
        payload_json={"origin_city_id": 1, "destination_city_id": 2},
        status=JobStatus.RECONCILING,
        mutation_status="dispatched",
        result_json={
            "tracking_code": "UTC-ACK-3",
            "confirmation_status": "tracking_received",
            "operator_acknowledged": True,
        },
    )
    async_db.add(job)
    await async_db.commit()
    await async_db.refresh(job)

    mock_bm = MagicMock()

    with patch(
        "app.orchestrator.reconciliation_service.reconciliation_scraper.query_waybill_status", new_callable=AsyncMock
    ) as mock_query:
        rec_service = ReconciliationService()
        reconciled_job = await rec_service.reconcile_job(session=async_db, job_id=job.id, browser_manager=mock_bm)

        mock_query.assert_not_called()
        assert reconciled_job is not None
        assert reconciled_job.status == JobStatus.UNKNOWN
        assert (reconciled_job.result_json or {}).get("tracking_code") == "UTC-ACK-3"
        assert (reconciled_job.result_json or {}).get("confirmation_status") == "tracking_received"
