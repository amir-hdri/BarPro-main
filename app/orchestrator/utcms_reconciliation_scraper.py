"""
UTCMS Reconciliation Scraper for querying waybill status using verified DataTables APIs and exact field matching.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)


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

    HISTORY_URL = "https://barname.utcms.ir/Barname/Document/History"
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
        tracking_code = tracking_code or fields.get("tracking_code")
        document_id = document_id or fields.get("document_id")
        national_code = national_code or fields.get("national_code")
        plate_number = fields.get("plate_number") or fields.get("car")
        origin_city = fields.get("origin_city")
        dest_city = fields.get("dest_city")
        cargo_weight = fields.get("cargo_weight")
        business_date = fields.get("business_date")

        try:
            # ── 1. If document_id is known, check showTrackingCode directly ──
            if document_id:
                try:
                    show_url = f"{self.SHOW_TRACKING_CODE_ENDPOINT}?id={document_id}"
                    response = await page.request.get(show_url, timeout=10000)
                    if response.status == 200:
                        data = await response.json()
                        if isinstance(data, dict) and data.get("resultCode") == 200:
                            obj = data.get("obj") or {}
                            found_code = obj.get("trackingCode") or obj.get("docNo")
                            if found_code:
                                return ReconciliationResult(
                                    outcome=ScraperOutcome.REGISTERED,
                                    tracking_code=str(found_code),
                                    issue_date=obj.get("issueDate"),
                                    document_id=str(document_id),
                                    status_text=obj.get("status", "صادر شده"),
                                    details={"source": "showTrackingCode", "data": obj},
                                )
                except Exception as exc:
                    logger.debug("showTrackingCode query failed: %s", exc)

            # ── 2. Query History endpoint via History page context ──
            await page.goto(self.HISTORY_URL, wait_until="domcontentloaded", timeout=15000)

            if "login" in page.url.lower() or "account/login" in page.url.lower():
                logger.warning("Reconciliation session expired; redirected to login")
                return ReconciliationResult(
                    outcome=ScraperOutcome.AMBIGUOUS,
                    details={"error": "session_expired_redirect_to_login", "url": page.url},
                )

            # Query DataTables endpoint from within page context
            post_filter = {
                "fromDate": business_date or "",
                "toDate": business_date or "",
                "docNo": tracking_code or "",
                "driverNationalCode": national_code or None,
            }

            fetch_script = f"""
            async () => {{
                try {{
                    const formData = new URLSearchParams();
                    formData.append('draw', '1');
                    formData.append('start', '0');
                    formData.append('length', '20');
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
                    if (res.status === 200) {{
                        return await res.json();
                    }}
                    return {{ status: res.status, text: await res.text() }};
                }} catch (e) {{
                    return {{ error: e.toString() }};
                }}
            }}
            """
            result_data = await page.evaluate(fetch_script)

            if isinstance(result_data, dict):
                if result_data.get("error"):
                    logger.warning("History DataTables evaluate error: %s", result_data["error"])
                elif "data" in result_data and isinstance(result_data["data"], list):
                    rows = result_data["data"]
                    if len(rows) == 0:
                        return ReconciliationResult(
                            outcome=ScraperOutcome.NOT_FOUND,
                            details={"message": "DataTables returned 0 records", "filter": post_filter},
                        )

                    # Match against returned rows
                    for row in rows:
                        if self._match_row(row, tracking_code, national_code, plate_number, origin_city, dest_city):
                            found_code = str(row.get("docNo") or row.get("trackingCode") or "")
                            return ReconciliationResult(
                                outcome=ScraperOutcome.REGISTERED,
                                tracking_code=found_code if found_code else None,
                                issue_date=row.get("dateFarsi") or row.get("date"),
                                status_text=row.get("status", "ثبت شده"),
                                details={"source": "GetHistoryFirstList", "matched_row": row},
                            )

            # ── 3. DOM Fallback Search (if AJAX evaluate did not return records) ──
            if tracking_code:
                code_input = page.locator("input[name='TrackingCode'], #TrackingCode, input#trackingCode")
                if await code_input.count() > 0:
                    await code_input.first.fill(tracking_code)

            if national_code:
                nat_input = page.locator("input[name='NationalCode'], #NationalCode")
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
                row = table_rows.nth(i)
                text = await row.inner_text()

                base_match = (tracking_code and tracking_code in text) or (national_code and national_code in text)
                if base_match:
                    return ReconciliationResult(
                        outcome=ScraperOutcome.REGISTERED,
                        tracking_code=tracking_code,
                        status_text=text[:100],
                        details={"row_text": text[:200], "row_index": i},
                    )

            return ReconciliationResult(
                outcome=ScraperOutcome.AMBIGUOUS,
                details={"row_count": row_count, "summary": "Rows found but specific match unconfirmed"},
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
    ) -> bool:
        """Check if returned DataTables row matches target waybill parameters."""
        row_doc_no = str(row.get("docNo") or row.get("trackingCode") or "").strip()
        if tracking_code and row_doc_no and row_doc_no == str(tracking_code).strip():
            return True

        row_nat_code = str(row.get("driverNationalCode") or "").strip()
        row_car = str(row.get("car") or row.get("PelakNumber") or "").strip()

        matches = 0
        checks = 0

        if national_code:
            checks += 1
            if national_code in row_nat_code:
                matches += 1

        if plate_number:
            checks += 1
            if plate_number in row_car:
                matches += 1

        if origin_city:
            checks += 1
            row_src = str(row.get("sourceAddress") or "")
            if origin_city in row_src:
                matches += 1

        if dest_city:
            checks += 1
            row_dst = str(row.get("destAddress") or "")
            if dest_city in row_dst:
                matches += 1

        return checks > 0 and matches >= min(2, checks)


reconciliation_scraper = UTCMSReconciliationScraper()
