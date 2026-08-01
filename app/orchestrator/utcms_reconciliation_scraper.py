"""
UTCMS Reconciliation Scraper for querying waybill status using verified selectors.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
from typing import Any

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)


class ScraperOutcome(str, Enum):
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
    ) -> ReconciliationResult:
        """
        Query waybill status using Playwright page.
        Pre-requisite: page context is authenticated via SessionVault.
        """
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
                    details={"row_count": 0, "message": "No rows found and no 'not found' message matched, layout might have changed"},
                )

            # Parse matching rows
            for i in range(row_count):
                row = table_rows.nth(i)
                text = await row.inner_text()

                # If tracking code matched or status contains registration indicators
                if (tracking_code and tracking_code in text) or any(
                    status_kw in text for status_kw in ("ثبت شده", "تایید شده", "صادر شده", "ثبت اولیه")
                ):
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
