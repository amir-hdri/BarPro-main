"""Unit tests for Phase 7: Real UTCMS Reconciliation Engine."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.orchestrator.utcms_reconciliation_scraper import (
    ScraperOutcome,
    UTCMSReconciliationScraper,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "utcms"


def test_scraper_match_row_with_tracking_code():
    """Verify exact match when tracking code / docNo is present."""
    scraper = UTCMSReconciliationScraper()
    row = {
        "docNo": "140305159988",
        "driverNationalCode": "0012345678",
        "car": "12ع345ایران67",
        "sourceAddress": "تهران",
        "destAddress": "اصفهان",
    }

    assert (
        scraper._match_row(
            row=row,
            tracking_code="140305159988",
            national_code="0012345678",
            plate_number=None,
            origin_city=None,
            dest_city=None,
        )
        is True
    )


def test_scraper_multi_field_match_without_tracking_code():
    """Verify multi-field matching using national code, plate, and source/dest."""
    scraper = UTCMSReconciliationScraper()
    row = {
        "docNo": "140305159988",
        "driverNationalCode": "0012345678",
        "car": "12ع345ایران67",
        "sourceAddress": "تهران میدان آزادی",
        "destAddress": "اصفهان شهرک صنعتی",
    }

    # Match when national code and origin match
    assert (
        scraper._match_row(
            row=row,
            tracking_code=None,
            national_code="0012345678",
            plate_number="12ع345",
            origin_city="تهران",
            dest_city="اصفهان",
        )
        is True
    )

    # Mismatch when plate and origin do not match
    assert (
        scraper._match_row(
            row=row,
            tracking_code=None,
            national_code="9999999999",
            plate_number="99ب999",
            origin_city="شیراز",
            dest_city="تبریز",
        )
        is False
    )


@pytest.mark.asyncio
async def test_show_tracking_code_requires_history_confirmation():
    """showTrackingCode narrows the query but History remains mandatory."""
    scraper = UTCMSReconciliationScraper()
    mock_page = AsyncMock()

    # Mock fixture response for showTrackingCode
    fixture_path = FIXTURES_DIR / "show_tracking_code_response.json"
    with open(fixture_path, encoding="utf-8") as f:
        fixture_data = json.load(f)

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value=fixture_data)
    mock_page.request.get = AsyncMock(return_value=mock_response)
    mock_page.goto = AsyncMock()
    mock_page.url = scraper.HISTORY_URL
    mock_page.evaluate = AsyncMock(
        return_value={
            "status": 200,
            "json": {
                "data": [
                    {
                        "docNo": "987654321",
                        "dateFarsi": "1405/05/25",
                        "driverNationalCode": "",
                        "car": "",
                        "sourceAddress": "",
                        "destAddress": "",
                    }
                ]
            },
        }
    )

    res = await scraper.query_waybill_status(
        page=mock_page,
        document_id="849201",
    )

    assert res.outcome == ScraperOutcome.REGISTERED
    assert res.tracking_code == "987654321"
    assert res.details["source"] == "GetHistoryFirstList"
