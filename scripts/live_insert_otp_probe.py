#!/usr/bin/env python3
"""Live end-to-end InsertDocument probe with strict success gate + 4003 artifacts.

Success requires ALL of:
  - UTCMS business resultCode in {0, 200}
  - non-empty document id (docId / id / documentId)
  - a written timestamped JSON artifact under /tmp/barpro_live_e2e/

On captcha rejection (4003), writes side-by-side PNG + JSON (image vs prediction)
under /tmp/captcha_rejections/.

Run inside the backend container on the central server:
  docker compose -f compose/backend.yml exec backend python scripts/live_insert_otp_probe.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

if Path("/app/app").exists():
    PROJECT_ROOT = Path("/app")
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.automation.mobile_payload_adapter import build_mobile_document_payload  # noqa: E402
from app.automation.utcms_mobile_client import UtcmsMobileApiError, UtcmsMobileClient  # noqa: E402
from app.automation.worker_proxy import get_worker_proxy_url  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("live_insert_otp_probe")

ARTIFACT_DIR = Path("/tmp/barpro_live_e2e")
TOKEN_FILE = Path("/tmp/driver_7_mobile_token.json")
SUCCESS_CODES = {"0", "200"}


def _payload() -> dict:
    return {
        "sender": {
            "is_company": False,
            "first_name": "علی",
            "last_name": "موسوی",
            "phone": "09120000000",
            "national_code": "0084575948",
            "postal_code": "3361111111",
        },
        "receiver": {
            "is_company": False,
            "first_name": "حسین",
            "last_name": "احمدی",
            "phone": "09120000000",
            "national_code": "0012345679",
            "postal_code": "3362222222",
        },
        "origin": {
            "province": "البرز",
            "city": "طالقان",
            "address": "طالقان، میر، جاده انجیلاق کلارود اسفاران، پرگه",
            "postal_code": "3361111111",
            "lat": 36.1764,
            "lon": 50.7633,
        },
        "destination": {
            "province": "البرز",
            "city": "طالقان",
            "address": "طالقان، کشرود، مسیر اختصاصی سد، جاده نسا سفلی",
            "postal_code": "3362222222",
            "lat": 36.1764,
            "lon": 50.7633,
        },
        "cargo": {
            "items": [{"product_id": 17, "pack_type_id": 3, "weight": 20000, "count": 1, "description": "آجر"}],
            "value": 35000000,
        },
        "vehicle": {
            "driver_national_code": "0321410408",
            "driver_phone": "09123612956",
            "tag_type": 1,
            "t1": "78",
            "t2": 23,
            "t3": 21,
            "t4": "965",
            "capacity": 20,
            "type": "باری",
            "have_certificate": True,
            "have_3rd_insurance": True,
        },
        "insurance": {"have_insurance": True, "cover": 35000000},
        "financial": {"cost": 5000000, "bearing_cost": 100000, "pre_rent": 1000000, "post_rent": 4000000},
        "shipping_options": {"send_sms": True, "fuel_type": 1},
    }


def _write_artifact(name: str, payload: dict) -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = ARTIFACT_DIR / f"{stamp}_{name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    logger.info("artifact_written path=%s", path)
    return path


async def _login(client: UtcmsMobileClient) -> UtcmsMobileClient:
    from sqlmodel import select

    from app.auth_multitenant import decrypt_driver_password
    from app.core.database import async_session_factory
    from app.models_multitenant import Driver

    async with async_session_factory() as session:
        driver = (await session.exec(select(Driver).where(Driver.id == 7))).first()
        if not driver:
            raise RuntimeError("Driver 7 not found")
        username = driver.utcms_username
        password = decrypt_driver_password(driver.utcms_password_encrypted)

    for attempt in range(1, 15):
        try:
            _, cap_token = await client.auto_solve_captcha("login")
            auth = await client.login(username, password, cap_token)
            client.token = auth.token
            TOKEN_FILE.write_text(
                json.dumps(
                    {
                        "token": auth.token,
                        "refresh_token": auth.refresh_token,
                        "expires_at": auth.expires_at,
                        "created_at": time.time(),
                    }
                )
            )
            logger.info("login_ok expires_at=%s", auth.expires_at)
            return client
        except UtcmsMobileApiError as e:
            if getattr(e, "result_code", None) == 429 or "429" in str(e):
                logger.warning("login_429_cooldown attempt=%d", attempt)
                await asyncio.sleep(30)
            elif str(getattr(e, "result_code", None)) == "1" and attempt == 1:
                # Bare code-1 rejections (obj=null) are flaky UTCMS-side:
                # failed 13:55, succeeded 14:38, failed 14:44. Exactly one
                # retry with a fresh PoW; anything beyond that stays
                # fail-closed instead of hammering the login endpoint.
                logger.warning("login_code1_transient_retry attempt=%d", attempt)
                await asyncio.sleep(10)
            elif "transport failed" in str(e) and attempt <= 3:
                # Intermittent curl-28 timeouts with 0 bytes received: retry
                # bounded with a fresh PoW; business rejections fail fast.
                logger.warning("login_transport_retry attempt=%d", attempt)
                await asyncio.sleep(10 * attempt)
            else:
                # Fail closed on any other login rejection (e.g. code 1
                # "خطا در سامانه"), but keep the sanitized server envelope so
                # the cause can be classified without another live attempt.
                logger.error(
                    "login_rejected code=%s msg=%s sanitized_body=%s",
                    getattr(e, "result_code", None),
                    (getattr(e, "result_message", None) or str(e))[:200],
                    json.dumps(getattr(e, "response_body", None), ensure_ascii=False, default=str)[:2000],
                )
                raise
    raise RuntimeError("login failed after retries")


async def get_client() -> UtcmsMobileClient:
    client = UtcmsMobileClient(proxy_url=get_worker_proxy_url())
    if TOKEN_FILE.exists():
        try:
            cached = json.loads(TOKEN_FILE.read_text())
            if cached.get("token") and cached.get("created_at", 0) + 240 > time.time():
                client.token = cached["token"]
                logger.info("using_cached_token age_s=%.0f", time.time() - cached.get("created_at", 0))
                return client
        except Exception as exc:
            logger.warning("token_cache_error %s", exc)
    return await _login(client)


async def main() -> int:
    started = datetime.now(UTC).isoformat()
    client = await get_client()
    rejections: list[dict] = []
    last_error: str | None = None
    last_rejection_body: object = None
    final_doc_id = None
    final_result_code = None
    otp_needed = None
    raw_success: dict | None = None

    max_attempts = 8
    max_logins = 3
    logins = 1
    for attempt in range(1, max_attempts + 1):
        logger.info("insert_attempt %d/%d", attempt, max_attempts)
        try:
            solution, cap_token = await client.auto_solve_captcha(form_id=1)
        except Exception as exc:
            last_error = f"captcha_solve_failed: {exc}"
            logger.error(last_error)
            await asyncio.sleep(1)
            continue

        logger.info("captcha_prediction value=%r", solution)
        body = build_mobile_document_payload(_payload(), token=client.token, cap_token=cap_token, is_draft=False)
        try:
            res = await client.insert_document(body, allow_live_submit=True, cap_token=cap_token)
        except UtcmsMobileApiError as e:
            code = getattr(e, "result_code", None)
            last_error = f"insert_raise code={code} msg={e}"
            logger.warning(last_error)
            last_rejection_body = getattr(e, "response_body", None)
            if last_rejection_body is not None:
                logger.warning(
                    "insert_rejection_body=%s",
                    json.dumps(last_rejection_body, ensure_ascii=False, default=str)[:2000],
                )
            if str(code) == "401" and "منقضی" in str(e) and logins < max_logins:
                # UTCMS explicitly asks for a fresh login ("ورود شما منقضی
                # شده است"). The driver token lives ~5 minutes, shorter than
                # an 8-attempt loop, so re-login bounded (max 3 total) instead
                # of dying on a stale session.
                rejections.append(
                    {
                        "attempt": attempt,
                        "result_code": code,
                        "note": "session_expired_relogin",
                        "artifact": None,
                    }
                )
                try:
                    TOKEN_FILE.unlink(missing_ok=True)
                except Exception:
                    pass
                logins += 1
                logger.warning("session_expired_relogin login_n=%d", logins)
                client = await _login(UtcmsMobileClient(proxy_url=get_worker_proxy_url()))
                await asyncio.sleep(1)
                continue
            if str(code) == "4003" or "کد امنیتی" in str(e):
                art = client.dump_captcha_rejection(
                    code,
                    extra={"script": "live_insert_otp_probe", "attempt": attempt},
                )
                rejections.append(
                    {
                        "attempt": attempt,
                        "result_code": code,
                        "prediction": (client.last_captcha_debug or {}).get("solution"),
                        "expression": ((client.last_captcha_debug or {}).get("meta") or {}).get("expression"),
                        "artifact": str(art) if art else None,
                    }
                )
                # Also keep a bare PNG next to prior probes
                img = (client.last_captcha_debug or {}).get("image_base64")
                if img:
                    try:
                        Path(f"/tmp/cap_attempt_{attempt}.png").write_bytes(base64.b64decode(str(img).split(",")[-1]))
                    except Exception:
                        pass
                await asyncio.sleep(1)
                continue
            break

        final_result_code = res.get("resultCode")
        code_s = str(final_result_code).strip()
        logger.info("insert_raw resultCode=%s", code_s)
        if code_s not in SUCCESS_CODES:
            last_error = f"non_success_resultCode={final_result_code}"
            if code_s == "4003":
                art = client.dump_captcha_rejection(final_result_code, extra={"attempt": attempt})
                rejections.append(
                    {
                        "attempt": attempt,
                        "result_code": final_result_code,
                        "prediction": (client.last_captcha_debug or {}).get("solution"),
                        "artifact": str(art) if art else None,
                    }
                )
            await asyncio.sleep(1)
            continue

        final_doc_id = client.extract_document_id(res)
        otp_needed = client.extract_otp_required(res)
        if not final_doc_id:
            last_error = "resultCode_ok_but_missing_doc_id"
            logger.error(last_error)
            _write_artifact(
                "fail_missing_doc_id",
                {
                    "started_at": started,
                    "finished_at": datetime.now(UTC).isoformat(),
                    "success": False,
                    "reason": last_error,
                    "result_code": final_result_code,
                    "raw": res,
                    "rejections": rejections,
                },
            )
            return 2

        raw_success = res
        logger.info("insert_verified doc_id=%s otp_needed=%s", final_doc_id, otp_needed)
        break

    success = bool(raw_success and final_doc_id and str(final_result_code).strip() in SUCCESS_CODES)
    artifact = _write_artifact(
        "result",
        {
            "started_at": started,
            "finished_at": datetime.now(UTC).isoformat(),
            "success": success,
            "result_code": final_result_code,
            "doc_id": final_doc_id,
            "is_otp_needed": otp_needed,
            "error": last_error,
            "rejections": rejections,
            "rejection_count": len(rejections),
            "rejection_body": last_rejection_body,
            "raw": raw_success,
            "criteria": ["resultCode in {0,200}", "doc_id present", "timestamped artifact written"],
        },
    )
    if success:
        logger.info("LIVE_E2E_SUCCESS doc_id=%s otp_needed=%s artifact=%s", final_doc_id, otp_needed, artifact)
        # OTP challenge reached or direct success — both are valid "to OTP challenge" outcomes
        return 0
    logger.error("LIVE_E2E_FAIL error=%s artifact=%s", last_error, artifact)
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
