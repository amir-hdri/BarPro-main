"""
UTCMS Reconciliation Scraper for querying waybill status using verified DataTables APIs and exact field matching.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)


def _canonical_plate(plate: str) -> str:
    if not plate:
        return ""
    norm = str(plate).strip()
    for index, digit in enumerate("۰۱۲۳۴۵۶۷۸۹"):
        norm = norm.replace(digit, str(index))
    for index, digit in enumerate("٠١٢٣٤٥٦٧٨٩"):
        norm = norm.replace(digit, str(index))
    norm = norm.replace("ایران", "")
    return re.sub(r"[^\w\d]", "", norm)


def _canonical_nat_code(code: Any) -> str:
    if not code:
        return ""
    norm = str(code).strip()
    for index, digit in enumerate("۰۱۲۳۴۵۶۷۸۹"):
        norm = norm.replace(digit, str(index))
    for index, digit in enumerate("٠١٢٣٤٥٦٧٨٩"):
        norm = norm.replace(digit, str(index))
    return re.sub(r"\D", "", norm)


def _canonical_text(text: str) -> str:
    if not text:
        return ""
    t = str(text).strip().replace("ي", "ی").replace("ك", "ک").replace("‌", "").replace(" ", "").replace("،", "").replace("-", "")
    return t.lower()


def _parse_iranian_plate_tags(plate_number: str) -> tuple[str, str, str, str]:
    if not plate_number:
        return "", "", "", ""
    norm = str(plate_number).strip().replace(" ", "").replace("‌", "")
    for index, digit in enumerate("۰۱۲۳۴۵۶۷۸۹"):
        norm = norm.replace(digit, str(index))
    for index, digit in enumerate("٠١٢٣٤٥٦٧٨٩"):
        norm = norm.replace(digit, str(index))
    norm = norm.replace("ایران", "")
    match = re.search(r"(\d{2})([^\d]+)(\d{3})(\d{2})", norm)
    if match:
        return match.group(1), match.group(2), match.group(3), match.group(4)
    return "", "", "", ""


class ScraperOutcome(StrEnum):
    REGISTERED = "REGISTERED"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass
class ReconciliationResult:
    outcome: ScraperOutcome
    tracking_code: str | None = None
    issue_date: str | None = None
    status_text: str | None = None
    document_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class UTCMSReconciliationScraper:
    """Scrapes and reconciles waybill status against official UTCMS endpoints."""

    HISTORY_URL = "https://barname.utcms.ir/barname/History/History"
    SEARCH_URL = "https://barname.utcms.ir/Barname/Document/HagigiHogugi"
    HISTORY_LIST_ENDPOINT = "/Barname/History/GetHistoryFirstList"
    ISSUED_DOCUMENTS_ENDPOINT = "/Barname/DocumentList/GetIssuedDocumentsNew"
    SHOW_TRACKING_CODE_ENDPOINT = "/Barname/Document/showTrackingCode"

    async def query_waybill_status(
        self,
        page: Page,
        tracking_code: str | None = None,
        document_id: str | None = None,
        national_code: str | None = None,
        job_id: int | None = None,
        reconciliation_fields: dict[str, Any] | None = None,
    ) -> ReconciliationResult:
        """
        Query waybill status using Playwright page.
        Pre-requisite: page context is authenticated via SessionVault.
        """
        fields = reconciliation_fields or {}
        tracking_code = str(tracking_code or fields.get("tracking_code") or "").strip() or None
        document_id = str(document_id or fields.get("document_id") or "").strip() or None
        national_code = str(national_code or fields.get("national_code") or "").strip() or None
        plate_number = str(fields.get("plate_number") or fields.get("car") or "").strip() or None
        origin_city = str(fields.get("origin_city") or "").strip() or None
        dest_city = str(fields.get("dest_city") or "").strip() or None
        _cargo_weight = fields.get("cargo_weight")
        business_date = str(fields.get("business_date") or "").strip() or None
        driver_name = str(fields.get("driver_name") or "").strip() or None
        sender_name = str(fields.get("sender_name") or "").strip() or None
        receiver_name = str(fields.get("receiver_name") or "").strip() or None

        tag1, tag2, tag3, tag4 = _parse_iranian_plate_tags(plate_number) if plate_number else ("", "", "", "")
        auxiliary_tracking_code: str | None = None

        try:
            # ── 1. showTrackingCode is an auxiliary witness only ──
            if document_id:
                try:
                    show_url = f"{self.SHOW_TRACKING_CODE_ENDPOINT}?id={document_id}"
                    response = await page.request.get(show_url, timeout=10000)
                    if response.status == 200:
                        data = await response.json()
                        if isinstance(data, dict) and data.get("resultCode") == 200:
                            obj = data.get("obj") or {}
                            found_code = str(obj.get("trackingCode") or obj.get("docNo") or "").strip()
                            if found_code:
                                auxiliary_tracking_code = found_code
                except Exception as exc:
                    logger.debug("showTrackingCode query failed: %s", exc)

            if auxiliary_tracking_code:
                tracking_code = auxiliary_tracking_code

            # ── 2. Query History endpoint via History page context ──
            await page.goto(self.HISTORY_URL, wait_until="domcontentloaded", timeout=15000)

            if "login" in page.url.lower() or "account/login" in page.url.lower():
                logger.warning("Reconciliation session expired; redirected to login")
                return ReconciliationResult(
                    outcome=ScraperOutcome.AMBIGUOUS,
                    details={"error": "session_expired_redirect_to_login", "url": page.url},
                )

            # Construct verified DataTables payload structure
            post_filter = {
                "fromDate": business_date or "",
                "toDate": business_date or "",
                "senderName": sender_name or "",
                "reciverName": receiver_name or "",
                "driverName": driver_name or "",
                "driverNationalCode": national_code or "",
                "sourceAddress": origin_city or "",
                "destAddress": dest_city or "",
                "docNo": tracking_code or "",
                "type": 0,
                "irCarTag1": tag1 or "",
                "irCarTag2": tag2 or "",
                "irCarTag3": tag3 or "",
                "irCarTag4": tag4 or "",
                "freeZoneId": "",
                "freeZoneTwoDigit": "",
                "freeZoneNo": "",
                "HasFreezone": True,
            }

            fetch_script = f"""
            async () => {{
                try {{
                    const formData = new URLSearchParams();
                    formData.append('draw', '1');
                    const columns = [
                        ['', 'row', false], ['dateFarsi', 'dateFarsi', true],
                        ['time', 'time', true], ['', 'senderFullName', false],
                        ['', 'receiverFullName', false], ['driverFullName', 'driverFullName', true],
                        ['', 'car', false], ['', 'Value', false],
                        ['insuranceValue', 'insuranceValue', false], ['', 'sourceAddress', false],
                        ['', 'destAddress', false], ['docNo', 'trackingCode', true],
                        ['', 'btnSelect', false]
                    ];
                    columns.forEach((column, index) => {{
                        formData.append(`columns[${{index}}][data]`, column[0]);
                        formData.append(`columns[${{index}}][name]`, column[1]);
                        formData.append(`columns[${{index}}][searchable]`, String(column[2]));
                        formData.append(`columns[${{index}}][orderable]`, 'false');
                        formData.append(`columns[${{index}}][search][value]`, '');
                        formData.append(`columns[${{index}}][search][regex]`, 'false');
                    }});
                    formData.append('start', '0');
                    formData.append('length', '10');
                    formData.append('search[value]', '');
                    formData.append('search[regex]', 'false');
                    formData.append('function', 'GetHistoryFirstList');
                    formData.append('data', JSON.stringify([{json.dumps(post_filter)}]));

                    const res = await fetch('{self.HISTORY_LIST_ENDPOINT}', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                            'X-Requested-With': 'XMLHttpRequest'
                        }},
                        body: formData.toString()
                    }});
                    const resText = await res.text();
                    try {{
                        return {{ status: res.status, json: JSON.parse(resText) }};
                    }} catch (parseErr) {{
                        return {{ status: res.status, text: resText }};
                    }}
                }} catch (e) {{
                    return {{ error: e.toString() }};
                }}
            }}
            """
            result_data = await page.evaluate(fetch_script)

            if isinstance(result_data, dict):
                if result_data.get("error"):
                    logger.warning("History DataTables evaluate error: %s", result_data["error"])
                else:
                    status_code = result_data.get("status")
                    json_body = result_data.get("json") or {}

                    # UTCMS returns 500 with "اطلاعات یافت نشد" when query yields zero records
                    if (
                        status_code == 500
                        and isinstance(json_body, dict)
                        and "یافت نشد" in str(json_body.get("resultMessage", ""))
                    ):
                        return ReconciliationResult(
                            outcome=ScraperOutcome.NOT_FOUND,
                            details={"source": "GetHistoryFirstList", "message": "اطلاعات یافت نشد"},
                        )

                    rows: list[dict[str, Any]] = []
                    if isinstance(json_body, dict):
                        if isinstance(json_body.get("data"), list):
                            rows = json_body["data"]
                        elif isinstance(json_body.get("aaData"), list):
                            rows = json_body["aaData"]
                        elif isinstance(json_body.get("Data"), list):
                            rows = json_body["Data"]
                        elif isinstance(json_body.get("obj"), dict) and isinstance(json_body["obj"].get("data"), list):
                            rows = json_body["obj"]["data"]
                        elif isinstance(json_body.get("obj"), list):
                            rows = json_body["obj"]
                    elif isinstance(json_body, list):
                        rows = json_body

                    if isinstance(rows, list) and len(rows) > 0:
                        for row in rows:
                            if isinstance(row, dict) and self._match_row(
                                row=row,
                                tracking_code=tracking_code,
                                national_code=national_code,
                                plate_number=plate_number,
                                origin_city=origin_city,
                                dest_city=dest_city,
                                business_date=business_date,
                            ):
                                found_code = str(
                                    row.get("docNo")
                                    or row.get("DocNo")
                                    or row.get("trackingCode")
                                    or row.get("TrackingCode")
                                    or row.get("doc_no")
                                    or row.get("tracking_code")
                                    or row.get("printId")
                                    or row.get("PrintId")
                                    or row.get("id")
                                    or row.get("Id")
                                    or ""
                                ).strip()
                                return ReconciliationResult(
                                    outcome=ScraperOutcome.REGISTERED,
                                    tracking_code=found_code if found_code else tracking_code,
                                    issue_date=row.get("dateFarsi") or row.get("DateFarsi") or row.get("date"),
                                    status_text=row.get("status", "ثبت شده"),
                                    details={"source": "GetHistoryFirstList", "matched_row": row},
                                )
                    elif status_code == 200 and isinstance(json_body, dict) and "data" in json_body and len(json_body["data"]) == 0:
                        return ReconciliationResult(
                            outcome=ScraperOutcome.NOT_FOUND,
                            details={"source": "GetHistoryFirstList", "message": "empty_data_list"},
                        )

            # ── 3. DOM Fallback Search (if AJAX evaluate did not return matched records) ──
            if tracking_code:
                code_input = page.locator("input[name='TrackingCode'], #TrackingCode, input#trackingCode, input#docNo")
                if await code_input.count() > 0:
                    await code_input.first.fill(tracking_code)

            if national_code:
                nat_input = page.locator("input[name='NationalCode'], #NationalCode, input#driverNationalCode")
                if await nat_input.count() > 0:
                    await nat_input.first.fill(national_code)

            search_btn = page.locator("button.search-btn, #btnSearch, .search-btn, input[type='submit']")
            if await search_btn.count() > 0:
                await search_btn.first.click()
                await page.wait_for_load_state("domcontentloaded", timeout=10000)

            table_rows = page.locator("table.table tbody tr, .table-responsive table tbody tr")
            row_count = await table_rows.count()

            if row_count == 0:
                return ReconciliationResult(
                    outcome=ScraperOutcome.NOT_FOUND,
                    details={"message": "No matching records found in DOM search"},
                )

            for i in range(row_count):
                row_elem = table_rows.nth(i)
                text = await row_elem.inner_text()

                if tracking_code and tracking_code in text:
                    return ReconciliationResult(
                        outcome=ScraperOutcome.REGISTERED,
                        tracking_code=tracking_code,
                        status_text=text[:100],
                        details={"row_text": text[:200], "row_index": i},
                    )
                else:
                    canon_plate = _canonical_plate(plate_number or "")
                    canon_row_text = _canonical_plate(text)
                    canon_nat = _canonical_nat_code(national_code or "")
                    canon_row_nat = _canonical_nat_code(text)
                    canon_src = _canonical_text(origin_city or "")
                    canon_dst = _canonical_text(dest_city or "")
                    canon_row_txt = _canonical_text(text)

                    plate_ok = bool(canon_plate and (canon_plate in canon_row_text or canon_row_text in canon_plate))
                    nat_ok = bool(canon_nat and (canon_nat in canon_row_nat))
                    src_ok = bool(canon_src and (canon_src in canon_row_txt))
                    dst_ok = bool(canon_dst and (canon_dst in canon_row_txt))

                    if not tracking_code and plate_ok and nat_ok and src_ok and dst_ok:
                        return ReconciliationResult(
                            outcome=ScraperOutcome.REGISTERED,
                            tracking_code=None,
                            status_text=text[:100],
                            details={"row_text": text[:200], "row_index": i},
                        )

            return ReconciliationResult(
                outcome=ScraperOutcome.NOT_FOUND,
                details={"row_count": row_count, "summary": "Rows inspected but no target waybill matched"},
            )

        except PlaywrightTimeoutError as te:
            logger.warning("Timeout in reconciliation scraper: %s", te)
            return ReconciliationResult(
                outcome=ScraperOutcome.AMBIGUOUS,
                details={"error": "timeout", "message": str(te)},
            )
        except Exception as exc:
            logger.error("Error in reconciliation scraper: %s", exc)
            return ReconciliationResult(
                outcome=ScraperOutcome.AMBIGUOUS,
                details={"error": "exception", "message": str(exc)},
            )

    @staticmethod
    def _match_row(
        row: dict[str, Any],
        tracking_code: str | None,
        national_code: str | None,
        plate_number: str | None,
        origin_city: str | None,
        dest_city: str | None,
        business_date: str | None = None,
    ) -> bool:
        """Check if returned DataTables row matches target waybill parameters.

        Rule: Never match on national_code alone. If tracking_code is missing or not matched,
        require a strict composite match of plate, driver national code, origin, and destination.
        """
        row_doc_no = str(
            row.get("docNo")
            or row.get("DocNo")
            or row.get("trackingCode")
            or row.get("TrackingCode")
            or row.get("doc_no")
            or row.get("tracking_code")
            or ""
        ).strip()
        if tracking_code and row_doc_no and row_doc_no == str(tracking_code).strip():
            return True

        row_nat_code = _canonical_nat_code(
            row.get("driverNationalCode")
            or row.get("DriverNationalCode")
            or row.get("nationalCode")
            or row.get("NationalCode")
            or ""
        )
        target_nat_code = _canonical_nat_code(national_code)

        row_car = _canonical_plate(
            row.get("car")
            or row.get("Car")
            or row.get("PelakNumber")
            or row.get("pelakNumber")
            or row.get("pelak")
            or ""
        )
        target_plate = _canonical_plate(plate_number or "")

        row_src = _canonical_text(row.get("sourceAddress") or row.get("SourceAddress") or row.get("sourceCity") or "")
        row_dst = _canonical_text(row.get("destAddress") or row.get("DestAddress") or row.get("destCity") or "")
        target_src = _canonical_text(origin_city or "")
        target_dst = _canonical_text(dest_city or "")

        row_date = str(row.get("dateFarsi") or row.get("DateFarsi") or row.get("date") or "").strip()

        plate_matched = bool(target_plate and (target_plate in row_car or row_car in target_plate))
        nat_matched = bool(target_nat_code and (target_nat_code in row_nat_code or row_nat_code in target_nat_code))
        origin_matched = bool(target_src and (target_src in row_src or row_src in target_src))
        dest_matched = bool(target_dst and (target_dst in row_dst or row_dst in target_dst))
        date_matched = bool(business_date and (business_date in row_date)) if business_date else True

        # Strict composite: Plate + Driver NatCode + Route (Origin + Destination)
        if plate_matched and nat_matched and origin_matched and dest_matched and date_matched:
            return True

        return False


reconciliation_scraper = UTCMSReconciliationScraper()

