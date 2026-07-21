import asyncio
import traceback
from app.schemas.waybill import WaybillMapRequest
from app.services.waybill_service import waybill_service

payload = {
    "operation_mode": "safe",
    "session_id": "smoke-safe",
    "sender": {
        "name": "Smoke Sender",
        "phone": "09121234567",
        "address": "Tehran",
        "national_code": "1234567890",
    },
    "receiver": {
        "name": "Smoke Receiver",
        "phone": "09121234567",
        "address": "Mashhad",
    },
    "origin": {
        "province": "تهران",
        "city": "تهران",
        "address": "میدان آزادی",
        "coordinates": {"lat": 35.6997, "lng": 51.3380},
    },
    "destination": {
        "province": "خراسان رضوی",
        "city": "مشهد",
        "address": "بلوار وکیل آباد",
        "coordinates": {"lat": 36.2972, "lng": 59.6067},
    },
    "cargo": {
        "type": "General",
        "weight": 1000,
        "count": 1,
        "description": "Safe live smoke",
    },
    "vehicle": {
        "driver_national_code": "1234567890",
        "driver_phone": "09121234567",
        "plate": "12A34567",
        "type": "Truck",
    },
    "financial": {
        "cost": 100000,
        "payment_method": "Cash",
    },
}


async def main():
    from app.automation.proxy_rotator import get_proxy_rotator

    proxy_rotator = get_proxy_rotator()
    proxy_rotator.require_iran_ip = False
    proxy_rotator.load_from_list(
        [
            "http://barpro-squid-1:3128",
            "http://barpro-squid-2:3128",
            "http://barpro-squid-3:3128",
        ]
    )

    try:
        req = WaybillMapRequest(**payload)
        res = await waybill_service.create_waybill_with_map(req)
        print("SUCCESS:", res)
    except Exception as e:
        print("EXCEPTION OCCURRED:")
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
