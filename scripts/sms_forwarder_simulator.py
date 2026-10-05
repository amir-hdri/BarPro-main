#!/usr/bin/env python3
"""SMS Forwarder Simulator for testing BarPro OTP intake and auto-completion.

Simulates an Android SMS Forwarder (e.g. SecureSMS Forwarder) sending
an incoming OTP SMS to the BarPro webhook endpoint.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulate SMS Forwarder webhook to BarPro")
    parser.add_argument("--url", default="http://127.0.0.1:8000/api/v1/otp/sms-forwarder", help="Webhook URL")
    parser.add_argument("--secret", default=os.getenv("OTP_WEBHOOK_SECRET", "test-secret"), help="Webhook secret token")
    parser.add_argument("--phone", required=True, help="Driver phone number (e.g. 09121234567)")
    parser.add_argument("--code", default="54321", help="OTP verification code")
    parser.add_argument("--sender", default="20007777", help="SMS sender address")
    parser.add_argument("--delay", type=float, default=0.0, help="Optional delay in seconds before sending")

    args = parser.parse_args()

    if args.delay > 0:
        print(f"Waiting {args.delay} seconds before sending...")
        time.sleep(args.delay)

    payload = {
        "event": "SMS_RECEIVED",
        "sender": args.sender,
        "from": args.sender,
        "driver_phone": args.phone,
        "text": f"سامانه بارنامه شهرداری: کد تایید صدور بارنامه شما {args.code} می باشد.",
        "timestamp": int(time.time() * 1000),
    }

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        args.url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-OTP-Webhook-Token": args.secret,
        },
        method="POST",
    )

    print(f"Sending OTP {args.code} for driver {args.phone} to {args.url}...")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp_body = resp.read().decode("utf-8")
            print(f"Response ({resp.status}): {resp_body}")
            return 0
    except urllib.error.HTTPError as err:
        err_body = err.read().decode("utf-8")
        print(f"HTTP Error {err.code}: {err_body}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
