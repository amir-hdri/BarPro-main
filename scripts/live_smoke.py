#!/usr/bin/env python3
"""Safe live smoke test for UTCMS automation API."""

import argparse
import json
import sys

import httpx


def build_payload(
    username: str = "",
    password: str = "",
    login_url: str = "https://barname.utcms.ir/Barname/Account/Login",
) -> dict:
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
    if username and password:
        payload["utcms_auth"] = {
            "username": username,
            "password": password,
            "login_url": login_url,
        }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Safe live smoke test for UTCMS bot API")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument("--api-key", default="", help="API key for sensitive endpoints")
    parser.add_argument("--timeout", type=float, default=300, help="HTTP timeout seconds")
    parser.add_argument("--username", default="", help="UTCMS username/national code")
    parser.add_argument("--password", default="", help="UTCMS password")
    parser.add_argument(
        "--login-url",
        default="https://barname.utcms.ir/Barname/Account/Login",
        help="UTCMS login URL",
    )
    args = parser.parse_args()

    headers = {}
    if args.api_key:
        headers["X-API-Key"] = args.api_key

    payload = build_payload(
        username=args.username.strip(),
        password=args.password.strip(),
        login_url=args.login_url.strip(),
    )

    with httpx.Client(timeout=args.timeout) as client:
        response = client.post(f"{args.base_url.rstrip('/')}/waybill/create-with-map", json=payload, headers=headers)

    print(f"status={response.status_code}")
    try:
        data = response.json()
    except Exception:
        print(response.text)
        return 1

    print(json.dumps(data, ensure_ascii=False, indent=2))

    if response.status_code != 200:
        return 1
    if data.get("mode") != "safe":
        return 1
    if data.get("status") not in ("validated", "submitted"):
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
