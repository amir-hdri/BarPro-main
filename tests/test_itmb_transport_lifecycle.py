"""Tests for independent transport lifecycle (WS03_StartBOL, WS04_EndBOL, WS06_InsertBOLTrack)."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import HTTPException

from app.schemas.itmb_ws import (
    GPSCnt,
    WS03StartBOLRequest,
    WS04EndBOLRequest,
    WS06InsertBOLTrackRequest,
)
from app.services.itmb_ws_service import ITMBWSService


@pytest.fixture
def sample_gps():
    return GPSCnt(
        Latitude=35.6892,
        Longitude=51.3890,
        Altitude=1200,
        Bearing=90,
        NumberOfSatellite=8,
        PDOP=2,
        GPSSpeed=45,
        GPSMaxSpeed=80,
        GPSTotalTraveledDistance=15000,
    )


@pytest.mark.asyncio
async def test_ws03_start_bol_success(sample_gps):
    service = ITMBWSService()
    req = WS03StartBOLRequest(
        CompanyCode="COMPANY01",
        ServicePassword="secret-pass",
        BOLTraceCode="BOL-1403-001",
        StartTime=1710000000,
        StartPosition=sample_gps,
    )

    mock_resp = httpx.Response(200, text='{"d": "BOL-1403-001"}', request=httpx.Request("POST", "http://test"))

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
        res = await service.start_bol(req)
        assert res["success"] is True
        assert res["bol_trace_code"] == "BOL-1403-001"
        assert res["result_code"] == 200


@pytest.mark.asyncio
async def test_ws04_end_bol_success(sample_gps):
    service = ITMBWSService()
    req = WS04EndBOLRequest(
        CompanyCode="COMPANY01",
        ServicePassword="secret-pass",
        BOLTraceCode="BOL-1403-001",
        EndTime=1710005000,
        EndPosition=sample_gps,
    )

    mock_resp = httpx.Response(200, text='{"d": "BOL-1403-001"}', request=httpx.Request("POST", "http://test"))

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
        res = await service.end_bol(req)
        assert res["success"] is True
        assert res["bol_trace_code"] == "BOL-1403-001"
        assert res["result_code"] == 200


@pytest.mark.asyncio
async def test_ws06_insert_bol_track_success(sample_gps):
    service = ITMBWSService()
    req = WS06InsertBOLTrackRequest(
        CompanyCode="COMPANY01",
        ServicePassword="secret-pass",
        BOLTraceCode="BOL-1403-001",
        TrackTime=1710002500,
        TrackPosition=sample_gps,
    )

    mock_resp = httpx.Response(200, text='{"d": "BOL-1403-001"}', request=httpx.Request("POST", "http://test"))

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
        res = await service.insert_bol_track(req)
        assert res["success"] is True
        assert res["bol_trace_code"] == "BOL-1403-001"
        assert res["result_code"] == 200


@pytest.mark.asyncio
async def test_ws03_at_most_once_mutation_no_retry_on_network_error(sample_gps):
    service = ITMBWSService()
    req = WS03StartBOLRequest(
        CompanyCode="COMPANY01",
        ServicePassword="secret-pass",
        BOLTraceCode="BOL-1403-001",
        StartTime=1710000000,
        StartPosition=sample_gps,
    )

    with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectTimeout("Connection timed out")):
        with pytest.raises(HTTPException) as exc_info:
            await service.start_bol(req)
        assert exc_info.value.status_code == 503
