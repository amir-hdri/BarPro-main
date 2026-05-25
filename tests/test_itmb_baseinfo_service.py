import base64
import json
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.schemas.itmb_ws import BOLCnt
from app.services.itmb_baseinfo_service import BaseInfoCacheEntry, ITMBBaseInfoService


def _sample_bol() -> BOLCnt:
    return BOLCnt(
        PlaqueID="1234567",
        PlaqueSN=12,
        PlaqueType="IRI",
        DriverNationalCode="1234567890",
        OWNERNATIONALID="12345678901",
        SenderType=2,
        SenderName="Sender",
        SenderAddress="A",
        SenderCityCode="1001",
        RecieverType=2,
        RecieverName="Receiver",
        RecieverAddress="B",
        RecieverCityCode="1002",
        Freightage=1000,
        PreFreightage=200,
        FreightageTax=100,
        CompanyCommission=50,
        ITServiceCost=30,
        InfoServiceCost=20,
        InsuranceCosts=10,
        TotalAmountPayment=1410,
        SerialNo=1,
        IssuerNaCode="0987654321",
        IssueDate=1710000000,
        LoadingPlaceAddress="L",
        LoadingPlaceCityCode="1001",
        OffLoadingPlaceAddress="O",
        OffLoadingPlaceCityCode="1002",
        LoadingPlaceCountieCode="2001",
        OffLoadingPlaceCountieCode="2002",
        Goods=[
            {
                "GoodID": 10,
                "WeightKg": 100,
                "Value": 1,
                "PackingTypeID": 3,
                "GoodtypeID": 1,
            }
        ],
    )


def _base64_json(payload):
    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")


@pytest.mark.asyncio
async def test_refresh_all_and_status(monkeypatch):
    service = ITMBBaseInfoService()

    responses = {
        "GetBaseInfoPlateType_46WS": [{"Code": "IRI"}],
        "GetBaseInfoProvinceCity_43WS": [{"CityCode": "1001"}, {"CityCode": "1002"}],
        "GetBaseInfoGood_34WS": [{"GoodID": 10}],
        "GetBaseInfoPackingType_33WS": [{"PackingTypeID": 3}],
        "GetBaseInfoGoodType_31WS": [{"GoodtypeID": 1}],
    }

    class _Response:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json):
            method = url.rsplit("/", 1)[-1]
            return _Response(json_module.dumps({"d": _base64_json(responses[method])}))

    json_module = json
    monkeypatch.setattr("app.services.itmb_baseinfo_service.httpx.AsyncClient", lambda *args, **kwargs: _Client())
    await service.refresh_all(company_code="C1", service_password="P1")
    status = service.status()
    assert status["goods"]["cached"] is True
    assert status["plate_types"]["cached"] is True


@pytest.mark.asyncio
async def test_validate_bol_references_success_with_cache():
    service = ITMBBaseInfoService()
    now = service._now()
    service._cache = {
        "goods": BaseInfoCacheEntry(data=[{"GoodID": 10}], fetched_at=now),
        "packing_types": BaseInfoCacheEntry(data=[{"PackingTypeID": 3}], fetched_at=now),
        "good_types": BaseInfoCacheEntry(data=[{"GoodtypeID": 1}], fetched_at=now),
        "plate_types": BaseInfoCacheEntry(data=[{"Code": "IRI"}], fetched_at=now),
        "province_cities": BaseInfoCacheEntry(
            data=[{"CityCode": "1001", "CountieCode": "2001"}, {"CityCode": "1002", "CountieCode": "2002"}],
            fetched_at=now,
        ),
    }

    with patch("app.core.config.utcms_config.ITMBOL_VALIDATE_BASEINFO", True):
        result = await service.validate_bol_references(_sample_bol())
    assert result["validated"] is True


@pytest.mark.asyncio
async def test_validate_bol_references_fails_on_unknown_good():
    service = ITMBBaseInfoService()
    now = service._now()
    service._cache = {
        "goods": BaseInfoCacheEntry(data=[{"GoodID": 99}], fetched_at=now),
        "packing_types": BaseInfoCacheEntry(data=[{"PackingTypeID": 3}], fetched_at=now),
        "good_types": BaseInfoCacheEntry(data=[{"GoodtypeID": 1}], fetched_at=now),
        "plate_types": BaseInfoCacheEntry(data=[{"Code": "IRI"}], fetched_at=now),
        "province_cities": BaseInfoCacheEntry(data=[{"CityCode": "1001"}, {"CityCode": "1002"}], fetched_at=now),
    }

    with patch("app.core.config.utcms_config.ITMBOL_VALIDATE_BASEINFO", True):
        with pytest.raises(HTTPException) as exc:
            await service.validate_bol_references(_sample_bol())
    assert exc.value.status_code == 400
