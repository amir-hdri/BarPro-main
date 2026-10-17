"""Unit and integration tests for ExternalWaybillAdoptionService and Celery Beat task."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models_multitenant import Driver, WaybillJob
from app.orchestrator.adoption_service import ExternalWaybillAdoptionService
from app.workers.celery_app import celery_app


def test_adoption_task_registration():
    """Verify task is properly registered in Celery and Beat schedule."""
    assert celery_app is not None
    assert "barpro.waybill.adopt_external" in celery_app.tasks

    beat_schedule = celery_app.conf.beat_schedule
    assert "waybill-adopt-external" in beat_schedule
    entry = beat_schedule["waybill-adopt-external"]
    assert entry["task"] == "barpro.waybill.adopt_external"
    assert entry["schedule"].minute == set(range(0, 60, 10))


@pytest.mark.asyncio
async def test_adopt_for_driver_no_credentials():
    service = ExternalWaybillAdoptionService()
    driver = Driver(id=1, client_id=1, driver_national_code="1234567890", utcms_password_encrypted=None)
    mock_session = AsyncMock()

    jobs = await service.adopt_for_driver(mock_session, driver)
    assert jobs == []


@pytest.mark.asyncio
async def test_adopt_for_driver_skips_existing():
    service = ExternalWaybillAdoptionService()
    driver = Driver(id=4, client_id=1, driver_national_code="5720138129", utcms_password_encrypted="secret")

    mock_client = AsyncMock()
    mock_client.get_issued_documents.return_value = {
        "resultCode": 200,
        "obj": [
            {"id": 239321329, "docNo": "1363223066", "sourceCityTitle": "ملایر", "destCityTitle": "ملایر"},
        ],
    }

    mock_session = AsyncMock()
    # Mock existing query returning a WaybillJob
    existing_job = WaybillJob(
        job_id="existing-1",
        idempotency_key="existing-key",
        client_id=1,
        driver_id=4,
        status="success",
        document_id="239321329",
    )
    mock_exec = MagicMock()
    mock_exec.first.return_value = existing_job
    mock_session.exec.return_value = mock_exec

    with (
        patch("app.orchestrator.adoption_service.get_or_login_client", AsyncMock(return_value=mock_client)),
        patch("app.orchestrator.adoption_service.decrypt_driver_password", return_value="pass"),
        patch("app.orchestrator.adoption_service.get_worker_proxy_url", return_value="http://127.0.0.1:3128"),
    ):
        jobs = await service.adopt_for_driver(mock_session, driver)
        assert len(jobs) == 0


@pytest.mark.asyncio
async def test_adopt_for_driver_adopts_new_waybill():
    service = ExternalWaybillAdoptionService()
    driver = Driver(id=4, client_id=1, driver_national_code="5720138129", utcms_password_encrypted="secret")

    mock_client = AsyncMock()
    mock_client.get_issued_documents.return_value = {
        "resultCode": 200,
        "obj": [
            {
                "id": 239321329,
                "docNo": "1363223066",
                "sourceStateTitle": "همدان",
                "sourceCityTitle": "ملایر",
                "destStateTitle": "همدان",
                "destCityTitle": "ملایر",
            },
        ],
    }

    mock_session = AsyncMock()
    # First query (existing check) returns None; second query (route template) returns None
    mock_exec1 = MagicMock()
    mock_exec1.first.return_value = None
    mock_session.exec.return_value = mock_exec1

    with (
        patch("app.orchestrator.adoption_service.get_or_login_client", AsyncMock(return_value=mock_client)),
        patch("app.orchestrator.adoption_service.decrypt_driver_password", return_value="pass"),
        patch("app.orchestrator.adoption_service.get_worker_proxy_url", return_value="http://127.0.0.1:3128"),
        patch("app.orchestrator.adoption_service.init_shipping", AsyncMock()) as mock_init_ship,
        patch(
            "app.orchestrator.adoption_service.auto_start_shipping", AsyncMock(return_value={"status": "started"})
        ) as mock_start,
    ):
        jobs = await service.adopt_for_driver(mock_session, driver)
        assert len(jobs) == 1
        job = jobs[0]
        assert job.document_id == "239321329"
        assert job.result_json["tracking_code"] == "1363223066"
        assert job.status == "success"
        assert job.source == "adopted_external"
        assert mock_init_ship.call_count == 1
        assert mock_start.call_count == 1


@pytest.mark.asyncio
async def test_adopt_all_external_waybills():
    service = ExternalWaybillAdoptionService()
    driver = Driver(id=4, client_id=1, driver_national_code="5720138129", utcms_password_encrypted="secret")

    mock_session = AsyncMock()
    mock_exec = MagicMock()
    mock_exec.all.return_value = [driver]
    mock_session.exec.return_value = mock_exec

    class SessionContext:
        async def __aenter__(self):
            return mock_session

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    adopted_job = WaybillJob(
        job_id="ext-123",
        idempotency_key="adopt-239321329",
        client_id=1,
        driver_id=4,
        status="success",
        document_id="239321329",
        result_json={"tracking_code": "1363223066"},
    )

    with (
        patch("app.orchestrator.adoption_service.async_session_factory", return_value=SessionContext()),
        patch.object(service, "adopt_for_driver", AsyncMock(return_value=[adopted_job])),
    ):
        summary = await service.adopt_all_external_waybills()
        assert summary["scanned_drivers"] == 1
        assert summary["adopted_count"] == 1
        assert summary["error_count"] == 0
        assert summary["adopted"][0]["document_id"] == "239321329"


@pytest.mark.asyncio
async def test_adopt_for_driver_skips_historical_documents():
    """Verify that historical waybills from previous dates are not adopted."""
    service = ExternalWaybillAdoptionService()
    driver = Driver(id=4, client_id=1, driver_national_code="5720138129", utcms_password_encrypted="secret")

    mock_client = AsyncMock()
    mock_client.get_issued_documents.return_value = {
        "resultCode": 200,
        "obj": [
            {
                "id": 239321329,
                "docNo": "1363223066",
                "date": "1405/06/22",
                "time": "10:00:00",
                "sourceStateTitle": "همدان",
                "sourceCityTitle": "ملایر",
            },
        ],
    }

    mock_session = AsyncMock()

    with (
        patch("app.orchestrator.adoption_service.get_or_login_client", AsyncMock(return_value=mock_client)),
        patch("app.orchestrator.adoption_service.decrypt_driver_password", return_value="pass"),
        patch("app.orchestrator.adoption_service.get_worker_proxy_url", return_value="http://127.0.0.1:3128"),
    ):
        jobs = await service.adopt_for_driver(mock_session, driver)
        assert len(jobs) == 0


@pytest.mark.asyncio
async def test_adopt_for_driver_adopts_today_document_with_metadata():
    """Verify that today's waybills are adopted with driver_name, business_date, and correct timestamp."""
    from app.core.jalali import tehran_today_jalali
    from app.schemas.multitenant import WaybillJobResponse

    jy, jm, jd = tehran_today_jalali()
    today_jalali = f"{jy:04d}/{jm:02d}/{jd:02d}"

    service = ExternalWaybillAdoptionService()
    driver = Driver(
        id=4,
        client_id=1,
        full_name="حمیدرضا محمدزاده",
        driver_national_code="5720138129",
        utcms_password_encrypted="secret",
    )

    mock_client = AsyncMock()
    mock_client.get_issued_documents.return_value = {
        "resultCode": 200,
        "obj": [
            {
                "id": 239628695,
                "docNo": "1363532773",
                "date": today_jalali,
                "time": "14:14:43",
                "driverFullName": "حمیدرضا محمدزاده",
                "sourceStateTitle": "همدان",
                "sourceCityTitle": "ملایر",
                "destStateTitle": "همدان",
                "destCityTitle": "ملایر",
            },
        ],
    }

    mock_session = AsyncMock()
    mock_exec = MagicMock()
    mock_exec.first.return_value = None
    mock_session.exec.return_value = mock_exec

    with (
        patch("app.orchestrator.adoption_service.get_or_login_client", AsyncMock(return_value=mock_client)),
        patch("app.orchestrator.adoption_service.decrypt_driver_password", return_value="pass"),
        patch("app.orchestrator.adoption_service.get_worker_proxy_url", return_value="http://127.0.0.1:3128"),
        patch("app.orchestrator.adoption_service.init_shipping", AsyncMock()),
        patch("app.orchestrator.adoption_service.auto_start_shipping", AsyncMock(return_value={"status": "started"})),
    ):
        jobs = await service.adopt_for_driver(mock_session, driver)
        assert len(jobs) == 1
        job = jobs[0]
        assert job.document_id == "239628695"
        assert job.payload_json["driver_name"] == "حمیدرضا محمدزاده"
        assert job.result_json["driver_name"] == "حمیدرضا محمدزاده"
        assert job.business_date is not None

        # Verify schema serialization populates driver_name
        job.id = 1
        resp = WaybillJobResponse.model_validate(job)
        assert resp.driver_name == "حمیدرضا محمدزاده"
