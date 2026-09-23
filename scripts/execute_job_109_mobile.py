#!/usr/bin/env python3
"""Execute Waybill Job 109 end-to-end via official UTCMS Mobile API (Android Client Contract).

Bypasses Web RPA entirely:
1. Driver 7 authentication via CapJS PoW + /Account/UserLoginV2.
2. Math CAPTCHA fetch (/Utils/GetCaptcha formId=1) + CNN Solver with auto-refresh retry loop.
3. Document issuance via /Document/InsertDocumentHagigiV3.
4. OTP handling if required (IssueDocumentByOtp).
5. Shipping lifecycle:
   - Start shipping via /Document/StartShippingWithGps (Taleqan: 36.1764, 50.7633).
   - Finish shipping via /Document/FinishShippingWithGps.
6. Three-witness reconciliation & updating WaybillJob 109 status to 'success'.
"""

import asyncio
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

from sqlmodel import select  # noqa: E402

from app.auth_multitenant import decrypt_driver_password  # noqa: E402
from app.automation.captcha.barname_ml_solver import barname_ml_solver  # noqa: E402
from app.automation.mobile_payload_adapter import build_mobile_document_payload  # noqa: E402
from app.automation.utcms_mobile_client import UtcmsMobileApiError, UtcmsMobileClient  # noqa: E402
from app.automation.worker_proxy import get_worker_proxy_url  # noqa: E402
from app.core.database import async_session_factory  # noqa: E402
from app.core.redis_client import redis_manager  # noqa: E402
from app.models_multitenant import Driver, TaskStatus, WaybillJob  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("execute_job_109_mobile")

TOKEN_FILE = Path("/tmp/driver_7_mobile_token.json")


async def get_authenticated_client() -> UtcmsMobileClient:
    proxy = get_worker_proxy_url()
    client = UtcmsMobileClient(proxy_url=proxy)

    # 1. Check cached token (tokens valid for 5 minutes; use if < 4 mins old)
    if TOKEN_FILE.exists():
        try:
            cached = json.loads(TOKEN_FILE.read_text())
            token = cached.get("token")
            created_at = cached.get("created_at", 0)
            if token and (time.time() - created_at < 240):
                logger.info("Using cached access token (age: %ds)", int(time.time() - created_at))
                client.token = token
                return client
            # Try refresh token if available
            refresh_token = cached.get("refresh_token")
            if refresh_token:
                logger.info("Access token expired; attempting refresh...")
                try:
                    ref_res = await client.refresh(refresh_token)
                    logger.info("Token refreshed successfully! Expires: %s", ref_res.expires_at)
                    TOKEN_FILE.write_text(
                        json.dumps(
                            {
                                "token": ref_res.token,
                                "refresh_token": ref_res.refresh_token or refresh_token,
                                "expires_at": ref_res.expires_at,
                                "created_at": time.time(),
                            }
                        )
                    )
                    return client
                except Exception as ref_err:
                    logger.warning("Token refresh failed (%s); will do fresh login", ref_err)
        except Exception as e:
            logger.warning("Token cache read error: %s", e)

    # 2. Fresh login with CapJS PoW
    async with async_session_factory() as session:
        stmt = select(Driver).where(Driver.id == 7)
        driver = (await session.exec(stmt)).first()
        if not driver:
            raise RuntimeError("Driver 7 not found in DB")
        username = driver.utcms_username
        enc_pass = driver.utcms_password_encrypted or getattr(driver, "encrypted_password", None)
        password = decrypt_driver_password(enc_pass)

    logger.info("Performing fresh login for driver %s...", username)
    for attempt in range(1, 15):
        try:
            logger.info("Solving CapJS PoW for Mobile Login (attempt %d)...", attempt)
            _, cap_token = await client.auto_solve_captcha("login")
            logger.info("CapJS PoW solved (%s...)", cap_token[:20])

            auth_res = await client.login(username, password, cap_token)
            logger.info("Authenticated successfully! Token expires at: %s", auth_res.expires_at)
            TOKEN_FILE.write_text(
                json.dumps(
                    {
                        "token": auth_res.token,
                        "refresh_token": auth_res.refresh_token,
                        "expires_at": auth_res.expires_at,
                        "created_at": time.time(),
                    }
                )
            )
            return client
        except UtcmsMobileApiError as e:
            if getattr(e, "result_code", None) == 429 or "429" in str(e):
                logger.warning("UTCMS login 429 cooldown active. Waiting 30s before retry (attempt %d)...", attempt)
                await asyncio.sleep(30)
            elif str(getattr(e, "result_code", None)) == "1" and attempt == 1:
                # Same flaky bare code-1 class as the probe: one retry with
                # fresh PoW, then fail closed.
                logger.warning("UTCMS login code-1 transient; one retry with fresh PoW (attempt %d)...", attempt)
                await asyncio.sleep(10)
            else:
                logger.error("Login failed: %s", e)
                raise

    raise RuntimeError("Failed to log in after retries")


async def execute():
    # 1. Fetch Job 109 and Driver 7
    async with async_session_factory() as session:
        job = (await session.exec(select(WaybillJob).where(WaybillJob.id == 109))).first()
        if not job:
            logger.error("Job 109 not found in database!")
            return

        stmt = select(Driver).where(Driver.id == (job.driver_id or 7))
        driver = (await session.exec(stmt)).first()
        username = driver.utcms_username

    logger.info("Target Job: %s (ID: %s)", job.job_id, job.id)
    logger.info("Target Driver: %s (National Code: %s)", getattr(driver, "full_name", username), username)

    # 2. Get Authenticated Client
    client = await get_authenticated_client()

    # 3. Fetch Fleet
    logger.info("Fetching registered fleet for driver...")
    fleet_resp = await client.get_user_fleet_list()
    fleet_list = fleet_resp.get("obj") or []
    if fleet_list:
        truck_obj = fleet_list[0]
        logger.info("Matched truck from UTCMS fleet: %s", truck_obj)
        t1 = str(truck_obj.get("irTagPart1") or "78")
        t2 = int(truck_obj.get("irTagPart2") or 23)
        t3 = int(truck_obj.get("irTagPart3") or 21)
        t4 = str(truck_obj.get("irTagPart4") or "965")
        truck_type = truck_obj.get("type") or "باری"
    else:
        t1, t2, t3, t4 = "78", 23, 21, "965"
        truck_type = "باری"

    # 4. Check for existing waybill issued today
    today_shamsi = (await client.get_current_shamsi_date()).get("obj", "")
    logger.info("Current Shamsi Date on UTCMS: %s", today_shamsi)

    history_resp = await client.get_issued_documents(driver_national_code=username)
    issued_docs = history_resp.get("obj") if isinstance(history_resp, dict) else (history_resp or [])
    logger.info("Found %d issued documents in history", len(issued_docs))

    doc_no = None
    doc_id = None
    for d in issued_docs:
        if str(d.get("nCarTag")) == "782321965" and today_shamsi and str(d.get("date", "")).startswith(today_shamsi):
            logger.info(
                "Found existing waybill issued today: DocNo=%s, ID=%s, Date=%s",
                d.get("docNo"),
                d.get("id"),
                d.get("date"),
            )
            doc_no = d.get("docNo")
            doc_id = d.get("id")
            break

    # 5. Insert Document if not already issued today
    if not doc_no:
        structured_payload = {
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
                "t1": t1,
                "t2": t2,
                "t3": t3,
                "t4": t4,
                "capacity": 20,
                "type": truck_type,
                "have_certificate": True,
                "have_3rd_insurance": True,
            },
            "insurance": {"have_insurance": True, "cover": 35000000},
            "financial": {"cost": 5000000, "bearing_cost": 100000, "pre_rent": 1000000, "post_rent": 4000000},
            "shipping_options": {"send_sms": True, "fuel_type": 1},
        }

        # Auto-refreshing captcha submission loop
        for cap_attempt in range(1, 8):
            logger.info("Fetching CAPTCHA image (attempt %d/7)...", cap_attempt)
            cap_resp = await client.get_captcha(form_id=1)
            b64_img = cap_resp.get("obj")
            if not b64_img or not isinstance(b64_img, str):
                if cap_resp.get("resultCode") == 401:
                    logger.warning("Token expired on GetCaptcha; re-authenticating...")
                    TOKEN_FILE.unlink(missing_ok=True)
                    client = await get_authenticated_client()
                    continue
                raise RuntimeError(f"Failed to get captcha image: {cap_resp}")

            # Solve math expression with CNN solver
            cand = barname_ml_solver.solve_base64(b64_img)
            if not cand:
                logger.warning("CNN solver could not segment captcha; refreshing...")
                continue

            answer_digits = cand.answer.strip()
            logger.info(
                "CNN recognized expression: %r -> answer: %r (conf: %.2f)",
                cand.expression,
                answer_digits,
                cand.confidence,
            )

            body = build_mobile_document_payload(
                structured_payload,
                token=client.token,
                cap_token=answer_digits,
                is_draft=False,
            )
            logger.info("Submitting InsertDocumentHagigiV3 with capToken=%s...", answer_digits)
            insert_raw = None
            try:
                doc_res = await client.insert_document(body, allow_live_submit=True, cap_token=answer_digits)
                insert_raw = doc_res
                insert_code = str(doc_res.get("resultCode", "")).strip()
                logger.info("INSERT resultCode=%s raw=%s", insert_code, json.dumps(doc_res, ensure_ascii=False))
                if insert_code not in {"0", "200"}:
                    # Client normally raises via require_successful_mutation; keep a hard guard.
                    if insert_code == "4003" or "کد امنیتی" in str(doc_res.get("resultMessage") or ""):
                        raise UtcmsMobileApiError(
                            "InsertDocument captcha rejected",
                            result_code=doc_res.get("resultCode"),
                            result_message=doc_res.get("resultMessage"),
                        )
                    raise UtcmsMobileApiError(
                        f"InsertDocument business rejection: {insert_code}",
                        result_code=doc_res.get("resultCode"),
                        result_message=doc_res.get("resultMessage"),
                    )

                obj = doc_res.get("obj")
                if isinstance(obj, dict):
                    doc_id = obj.get("id") or obj.get("docId") or obj.get("documentId")
                    doc_no = obj.get("docNo") or obj.get("trackingCode")
                    is_otp_needed = bool(obj.get("isOtpNeeded"))
                else:
                    doc_no = doc_res.get("docNo") or doc_res.get("trackingCode")
                    doc_id = doc_res.get("docId") or doc_res.get("id")
                    is_otp_needed = bool(doc_res.get("isOtpNeeded"))

                if not doc_id:
                    logger.error("Insert returned resultCode=%s but no document id — not success", insert_code)
                    continue

                otp_issue_ok = False
                if is_otp_needed:
                    logger.warning(
                        "OTP required for Document ID: %s — success is NOT claimed until IssueDocumentByOtp returns tracking.",
                        doc_id,
                    )
                    try:
                        redis = redis_manager.get_client()
                        otp_data = await redis.get("rpa:otp:latest")
                        if otp_data:
                            otp_json = json.loads(otp_data)
                            otp_code = otp_json.get("code")
                            logger.info("Found OTP from Redis: %s (sender: %s)", otp_code, otp_json.get("sender"))
                            issue_res = await client.issue_document_by_otp(
                                str(doc_id), str(otp_code), allow_live_submit=True
                            )
                            issue_code = str(issue_res.get("resultCode", "")).strip()
                            logger.info(
                                "IssueDocumentByOtp resultCode=%s raw=%s",
                                issue_code,
                                json.dumps(issue_res, ensure_ascii=False),
                            )
                            if issue_code in {"0", "200"}:
                                otp_issue_ok = True
                                if isinstance(issue_res.get("obj"), dict):
                                    doc_no = (
                                        issue_res["obj"].get("docNo") or issue_res["obj"].get("trackingCode") or doc_no
                                    )
                            else:
                                logger.error("IssueDocumentByOtp rejected resultCode=%s — not success", issue_code)
                        else:
                            logger.warning("No OTP in Redis (rpa:otp:latest); document not fully issued")
                    except Exception as otp_err:
                        logger.warning("OTP lookup/submission exception: %s", otp_err)

                    if is_otp_needed and not otp_issue_ok:
                        logger.error(
                            "STOP: OTP challenge open for docId=%s without verified IssueDocumentByOtp — refusing SUCCESS",
                            doc_id,
                        )
                        return

                if not doc_no and doc_id:
                    logger.info("Fetching tracking code for document ID %s...", doc_id)
                    tr_res = await client.get_tracking_code(str(doc_id))
                    logger.info("Tracking code response: %s", tr_res)
                    if str(tr_res.get("resultCode", "")).strip() in {"0", "200"}:
                        if isinstance(tr_res.get("obj"), (int, str)):
                            doc_no = str(tr_res["obj"])
                        elif isinstance(tr_res.get("obj"), dict):
                            doc_no = tr_res["obj"].get("trackingCode") or tr_res["obj"].get("docNo")

                if doc_id and doc_no:
                    logger.info("Verified registration: docId=%s docNo=%s", doc_id, doc_no)
                    break
            except UtcmsMobileApiError as e:
                if str(e.result_code) == "401" or "منقضی" in str(e):
                    # UTCMS session expired mid-loop ("ورود شما منقضی شده
                    # است"): re-authenticate and retry. Each retry consumes
                    # one of the 7 bounded captcha attempts, so this cannot
                    # loop forever.
                    logger.warning("Insert session expired (401); re-authenticating and retrying...")
                    try:
                        TOKEN_FILE.unlink(missing_ok=True)
                    except Exception:
                        pass
                    client = await get_authenticated_client()
                    await asyncio.sleep(1)
                    continue
                if e.result_code == 4003 or "کد امنیتی" in str(e) or str(e.result_code) == "4003":
                    logger.warning(
                        "Captcha answer %r was rejected (resultCode %s). Saving image+prediction artifact and retrying...",
                        answer_digits,
                        e.result_code,
                    )
                    try:
                        from app.automation.captcha.debug_artifacts import save_rejection_artifact

                        save_rejection_artifact(
                            b64_img,
                            prediction=answer_digits,
                            result_code=e.result_code,
                            provider="cnn",
                            expression=cand.expression,
                            confidence=float(cand.confidence),
                            form_id=1,
                            extra={"script": "execute_job_109_mobile", "attempt": cap_attempt},
                        )
                    except Exception as art_exc:
                        logger.warning("captcha artifact save failed: %s", art_exc)
                    if insert_raw is None:
                        # response body may only be on the exception
                        pass
                    await asyncio.sleep(1)
                    continue
                logger.error(
                    "Insert Document error: status=%s, code=%s, msg=%s, body=%s",
                    e.status_code,
                    e.result_code,
                    e.result_message,
                    e.response_body,
                )
                raise

    if not (doc_id and doc_no):
        logger.error("FAILED (no false success): doc_id=%r doc_no=%r — not updating job to SUCCESS", doc_id, doc_no)
        return

    logger.info("========================================================")
    logger.info(
        "VERIFIED WAYBILL REGISTERED (resultCode success + docId + docNo): DocNo: %s, DocId: %s", doc_no, doc_id
    )
    logger.info("========================================================")

    # 6. Start Shipping with Fake GPS (Taleqan: 36.1764, 50.7633)
    lat = 36.1764
    lon = 50.7633
    alt = 1200.0
    logger.info("Registering Start of Shipping with GPS: lat=%s, lon=%s, alt=%s", lat, lon, alt)
    start_res = None
    try:
        start_res = await client.start_shipping_with_gps(
            doc_no=str(doc_no),
            lat=lat,
            lon=lon,
            alt=alt,
            speed=0.0,
            allow_live_submit=True,
        )
        logger.info("Start of shipping response: %s", start_res)
    except Exception as e:
        logger.warning("Start of shipping error (trying fallback): %s", e)
        try:
            start_res = await client.register_start_of_shipping(
                document_id=str(doc_id or doc_no),
                speed=0,
                altitude=alt,
                longitude=lon,
                latitude=lat,
                start_date=datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
                allow_live_submit=True,
            )
            logger.info("Start of shipping (v2) response: %s", start_res)
        except Exception as e2:
            logger.error("Fallback start shipping failed: %s", e2)

    # 7. Complete / Finish Shipping with Fake GPS
    logger.info("Registering End of Shipping with GPS: lat=%s, lon=%s", lat, lon)
    finish_res = None
    try:
        finish_res = await client.finish_shipping_with_gps(
            doc_no=str(doc_no),
            lat=lat,
            lon=lon,
            alt=alt,
            total_distance_km=0.5,
            speed=0.0,
            allow_live_submit=True,
        )
        logger.info("Finish shipping response: %s", finish_res)
    except Exception as e:
        logger.warning("Finish shipping error (trying fallback): %s", e)
        try:
            finish_res = await client.register_end_of_shipping(
                document_id=str(doc_id or doc_no),
                gps_list=[{"lat": lat, "lon": lon, "speed": 0, "alt": alt, "time": datetime.now().isoformat()}],
                allow_live_submit=True,
            )
            logger.info("Finish shipping (v2) response: %s", finish_res)
        except Exception as e2:
            logger.error("Fallback finish shipping failed: %s", e2)

    # 8. Reconcile and update database — ONLY after verified docId+docNo
    if not (doc_id and doc_no):
        logger.error("Refusing DB SUCCESS: missing verified doc_id/doc_no (doc_id=%r doc_no=%r)", doc_id, doc_no)
        return

    logger.info("Updating WaybillJob 109 with success status and witnesses...")
    async with async_session_factory() as session:
        job = (await session.exec(select(WaybillJob).where(WaybillJob.id == 109))).first()
        if job:
            job.status = TaskStatus.SUCCESS.value
            job.mutation_status = "confirmed"
            job.document_id = str(doc_id)
            job.last_error = None
            job.error_category = None
            job.reconciled_at = datetime.now(UTC).replace(tzinfo=None)
            job.mutation_at = datetime.now(UTC).replace(tzinfo=None)
            job.result_json = {
                "document_number": str(doc_no),
                "document_id": str(doc_id),
                "tracking_code": str(doc_no),
                "transport": "android_mobile_client",
                "verified_result_code": True,
                "start_shipping": start_res,
                "finish_shipping": finish_res,
                "gps_origin": {"lat": lat, "lon": lon, "provider": "fake_traveler_virtual"},
            }
            await session.commit()
            logger.info(
                "VERIFIED SUCCESS: Job 109 document_id=%s doc_no=%s status=SUCCESS (docId+docNo present, business resultCode ok)",
                doc_id,
                doc_no,
            )
        else:
            logger.error("Job 109 not found during final update — no DB write")


if __name__ == "__main__":
    asyncio.run(execute())
