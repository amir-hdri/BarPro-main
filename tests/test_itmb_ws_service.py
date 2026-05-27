import hashlib
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.itmb_ws import BOLCnt, GPSCnt, WS01InsertBOLRequest
from app.services.itmb_ws_service import ITMBWSService


def _sample_payload():
    return {
        "CompanyCode": "COMPANY01",
        "ServicePassword": "secret-pass",
        "InsertTime": 1710000000,
        "InsertPosition": {
            "Latitude": 35.6892,
            "Longitude": 51.3890,
            "Altitude": 1200,
            "Bearing": 90,
            "NumberOfSatellite": 8,
            "PDOP": 2,
            "GPSSpeed": 0,
            "GPSMaxSpeed": 0,
            "GPSTotalTraveledDistance": 0,
        },
        "bol": {
            "PlaqueID": "1234567",
            "PlaqueSN": 12,
            "PlaqueType": "IRI",
            "DriverNationalCode": "1234567890",
            "OWNERNATIONALID": "12345678901",
            "SenderType": 2,
            "SenderName": "ارسال کننده",
            "SenderAddress": "تهران",
            "RecieverType": 2,
            "RecieverName": "گیرنده",
            "RecieverAddress": "مشهد",
            "Freightage": 1000,
            "PreFreightage": 200,
            "FreightageTax": 100,
            "CompanyCommission": 50,
            "ITServiceCost": 30,
            "InfoServiceCost": 20,
            "InsuranceCosts": 10,
            "TotalAmountPayment": 1410,
            "SerialNo": 10001,
            "IssuerNaCode": "0987654321",
            "IssueDate": 1710000000,
            "LoadingPlaceAddress": "مبدا",
            "OffLoadingPlaceAddress": "مقصد",
            "Goods": [
                {
                    "GoodID": 10,
                    "WeightKg": 1500.5,
                    "Value": 2,
                    "PackingTypeID": 3,
                    "GoodtypeID": 1,
                    "Description": "محصول",
                }
            ],
        },
    }


def test_build_hashed_value_matches_sha512_uppercase():
    expected = hashlib.sha512(b"COMP112345pass").hexdigest().upper()
    assert ITMBWSService.build_hashed_value("COMP1", 12345, "pass") == expected


@pytest.mark.asyncio
async def test_insert_bol_returns_trace_code_from_d_wrapper(monkeypatch):
    request = WS01InsertBOLRequest(**_sample_payload())
    service = ITMBWSService()

    class _Response:
        text = '{"d":"BOL123456789"}'

        def raise_for_status(self):
            return None

    class _Client:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json):
            assert url.endswith("/WS01_InsertBOL")
            assert json["CompanyCode"] == "COMPANY01"
            assert isinstance(json["Salt"], int)
            return _Response()

    monkeypatch.setattr("app.services.itmb_ws_service.httpx.AsyncClient", _Client)
    result = await service.insert_bol(request)

    assert result["success"] is True
    assert result["bol_trace_code"] == "BOL123456789"
    assert isinstance(result["used_salt"], int)


@pytest.mark.asyncio
async def test_insert_bol_raises_http_error_on_exceptioncnt(monkeypatch):
    request = WS01InsertBOLRequest(**_sample_payload())
    service = ITMBWSService()

    class _Response:
        text = '{"d":"{\\"ErrCode\\":401,\\"ErrDesc\\":\\"Auth failed\\"}"}'

        def raise_for_status(self):
            return None

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json):
            return _Response()

    monkeypatch.setattr("app.services.itmb_ws_service.httpx.AsyncClient", lambda *args, **kwargs: _Client())

    with pytest.raises(HTTPException) as exc:
        await service.insert_bol(request)

    assert exc.value.status_code == 400
    assert exc.value.detail["err_code"] == 401


def test_ws01_insert_bol_route_calls_service():
    client = TestClient(app)
    payload = _sample_payload()

    with patch("app.core.config.utcms_config.API_AUTH_MODE", "off"), patch(
        "app.services.itmb_ws_service.itmb_ws_service.insert_bol",
        AsyncMock(return_value={"success": True, "bol_trace_code": "BOL1", "used_salt": 123}),
    ) as mocked_insert:
        response = client.post("/waybill/ws01-insert-bol", json=payload)

    assert response.status_code == 200
    assert response.json()["success"] is True
    mocked_insert.assert_awaited_once()


def test_baseinfo_status_route():
    client = TestClient(app)
    with patch("app.core.config.utcms_config.API_AUTH_MODE", "off"), patch(
        "app.services.itmb_baseinfo_service.itmb_baseinfo_service.status",
        return_value={"goods": {"cached": True}},
    ):
        response = client.get("/waybill/baseinfo/status")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "meta" in response.json()


def test_baseinfo_refresh_route():
    client = TestClient(app)
    with patch("app.core.config.utcms_config.API_AUTH_MODE", "off"), patch(
        "app.services.itmb_baseinfo_service.itmb_baseinfo_service.refresh_all",
        AsyncMock(return_value={"updated": True}),
    ) as mocked_refresh:
        response = client.post("/waybill/baseinfo/refresh", json={})
    assert response.status_code == 200
    assert response.json()["updated"] is True
    mocked_refresh.assert_awaited_once()


def test_schema_rejects_invalid_financial_total():
    payload = _sample_payload()
    payload["bol"]["TotalAmountPayment"] = 1
    with pytest.raises(ValueError):
        WS01InsertBOLRequest(**payload)


def test_schema_rejects_invalid_gps_range():
    payload = _sample_payload()
    payload["InsertPosition"]["Latitude"] = 120
    with pytest.raises(ValueError):
        WS01InsertBOLRequest(**payload)


@pytest.mark.asyncio
async def test_insert_bol_retries_on_transient_network_error(monkeypatch):
    request = WS01InsertBOLRequest(**_sample_payload())
    service = ITMBWSService()
    call_counter = {"count": 0}

    class _Response:
        text = "BOL-OK"

        def raise_for_status(self):
            return None

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json):
            call_counter["count"] += 1
            if call_counter["count"] == 1:
                raise Exception("connection reset by peer")
            return _Response()

    async def _no_sleep(self, _attempt):
        return None

    monkeypatch.setattr("app.services.itmb_ws_service.httpx.AsyncClient", lambda *args, **kwargs: _Client())
    monkeypatch.setattr(ITMBWSService, "_sleep_before_retry", _no_sleep)
    result = await service.insert_bol(request)

    assert result["bol_trace_code"] == "BOL-OK"
    assert call_counter["count"] == 2


def test_bolcnt_accepts_real_person_with_required_fields():
    payload = _sample_payload()["bol"]
    payload["SenderType"] = 1
    payload["SenderLastName"] = "SenderFamily"
    payload["SenderNationalID"] = "1234567890"
    payload["RecieverType"] = 1
    payload["RecieverLastName"] = "ReceiverFamily"
    payload["RecieverNationalID"] = "0123456789"

    model = BOLCnt(**payload)
    assert model.SenderType == 1
    assert model.RecieverType == 1


def test_ws_request_hashed_value_normalized_to_uppercase():
    bol = BOLCnt(**_sample_payload()["bol"])
    gps = GPSCnt(**_sample_payload()["InsertPosition"])
    model = WS01InsertBOLRequest(
        CompanyCode="C1",
        Salt=12345,
        HashedValue="a" * 128,
        bol=bol,
        InsertPosition=gps,
    )
    assert model.HashedValue == "A" * 128
