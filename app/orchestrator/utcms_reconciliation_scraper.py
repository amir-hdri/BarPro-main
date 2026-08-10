"""
UTCMS Reconciliation Scraper for querying waybill status using verified selectors.
"""

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
    details: dict[str, Any] = field(default_factory=dict)


class UTCMSReconciliationScraper:
    """Scrapes UTCMS portal for waybill status verification."""

    HISTORY_URL = "https://barname.utcms.ir/Barname/Document/History"
    SEARCH_URL = "https://barname.utcms.ir/Barname/Document/HagigiHogugi"

    async def query_waybill_status(
        self,
        page: Page,
        tracking_code: str | None = None,
        national_code: str | None = None,
        job_id: int | None = None,
        reconciliation_fields: dict | None = None,
    ) -> ReconciliationResult:
        """
        Query waybill status using Playwright page.
        Pre-requisite: page context is authenticated via SessionVault.

        reconciliation_fields: Optional dict with keys:
            - national_code
            - plate_number
            - origin_city
            - origin_address
            - dest_city
            - dest_address
            - cargo_weight
            - business_date
            - submission_fingerprint
        """
        # Use reconciliation_fields if provided, fallback to individual params
        if reconciliation_fields:
            tracking_code = tracking_code or reconciliation_fields.get("tracking_code")
            national_code = national_code or reconciliation_fields.get("national_code")
            plate_number = reconciliation_fields.get("plate_number")
            origin_city = reconciliation_fields.get("origin_city")
            dest_city = reconciliation_fields.get("dest_city")
            cargo_weight = reconciliation_fields.get("cargo_weight")
            reconciliation_fields.get("business_date")
        else:
            plate_number = None
            origin_city = None
            dest_city = None
            cargo_weight = None
        try:
            # Navigate to search URL
            url = self.HISTORY_URL if tracking_code else self.SEARCH_URL
            logger.info("Reconciliation scraper navigating to %s for tracking_code=%s", url, tracking_code)
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)

            # Check if redirected to login page
            if "login" in page.url.lower() or "account/login" in page.url.lower():
                logger.warning("Reconciliation session expired; redirected to login")
                return ReconciliationResult(
                    outcome=ScraperOutcome.AMBIGUOUS,
                    details={"error": "session_expired_redirect_to_login", "url": page.url},
                )

            # Fill search parameters
            if tracking_code:
                code_input = page.locator("input[name='TrackingCode'], #TrackingCode, input#trackingCode")
                if await code_input.count() > 0:
                    await code_input.first.fill(tracking_code)

            if national_code:
                nat_input = page.locator("input[name='NationalCode'], #NationalCode")
                if await nat_input.count() > 0:
                    await nat_input.first.fill(national_code)

            # Submit search button
            search_btn = page.locator("button.search-btn, #btnSearch, .search-btn, input[type='submit']")
            if await search_btn.count() > 0:
                await search_btn.first.click()
                await page.wait_for_load_state("domcontentloaded", timeout=10000)

            # Inspect table results
            table_rows = page.locator("table.table tbody tr, .table-responsive table tbody tr")
            row_count = await table_rows.count()

            if row_count == 0:
                # Check for "no data found" message
                no_data_msg = page.locator(".alert-warning, .no-data, :text('اطلاعاتی یافت نشد')")
                if await no_data_msg.count() > 0:
                    return ReconciliationResult(
                        outcome=ScraperOutcome.NOT_FOUND,
                        details={"message": "No records found on UTCMS"},
                    )
                # Check if table even exists to differentiate layouts/load issues
                table_el = page.locator("table")
                if await table_el.count() == 0:
                    return ReconciliationResult(
                        outcome=ScraperOutcome.AMBIGUOUS,
                        details={"message": "Table element not found, likely page load failure or WAF block"},
                    )
                return ReconciliationResult(
                    outcome=ScraperOutcome.AMBIGUOUS,
                    details={
                        "row_count": 0,
                        "message": "No rows found and no 'not found' message matched, layout might have changed",
                    },
                )

            # Parse matching rows
            for i in range(row_count):
                row = table_rows.nth(i)
                text = await row.inner_text()

                # If tracking code matched or status contains registration indicators
                base_match = (tracking_code and tracking_code in text) or any(
                    status_kw in text for status_kw in ("ثبت شده", "تایید شده", "صادر شده", "ثبت اولیه")
                )

                # If we have fingerprint fields, require additional field matches for precision
                if base_match:
                    # If we have reconciliation fields, do precise multi-field matching
                    if plate_number or origin_city or dest_city or cargo_weight:
                        field_matches = 0
                        total_fields = 0

                        if plate_number:
                            total_fields += 1
                            if plate_number in text:
                                field_matches += 1
                        if origin_city:
                            total_fields += 1
                            if origin_city in text:
                                field_matches += 1
                        if dest_city:
                            total_fields += 1
                            if dest_city in text:
                                field_matches += 1
                        if cargo_weight:
                            total_fields += 1
                            if str(cargo_weight) in text:
                                field_matches += 1

                        # Require at least 2 field matches (or all available) for confident match
                        min_required = min(2, total_fields) if total_fields > 0 else 0
                        if field_matches >= min_required:
                            return ReconciliationResult(
                                outcome=ScraperOutcome.REGISTERED,
                                tracking_code=tracking_code,
                                status_text=text[:100],
                                details={"row_text": text[:200], "row_index": i, "field_matches": field_matches},
                            )
                        else:
                            # Fields don't match - this row is not our waybill
                            continue
                    else:
                        # No fingerprint fields, fall back to original logic
                        return ReconciliationResult(
                            outcome=ScraperOutcome.REGISTERED,
                            tracking_code=tracking_code,
                            status_text=text[:100],
                            details={"row_text": text[:200], "row_index": i},
                        )

            # If rows exist but no positive match or ambiguous status
            return ReconciliationResult(
                outcome=ScraperOutcome.AMBIGUOUS,
                details={"row_count": row_count, "summary": "Rows found but no positive keyword match"},
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


reconciliation_scraper = UTCMSReconciliationScraper()
