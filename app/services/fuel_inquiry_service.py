"""Service layer for managing and executing fuel quota inquiries."""

import json
import logging
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.automation.browser import browser_manager, managed_browser_session
from app.automation.fuel_scraper import FuelScraper
from app.models_multitenant import Client, Driver, DriverPlate, FuelInquiry
from app.schemas.multitenant import (
    FuelInquiryCreateRequest,
    FuelInquiryListResponse,
    FuelInquiryResponse,
)
from app.services.session_vault import session_vault

logger = logging.getLogger(__name__)


class FuelInquiryService:
    """Manages fuel inquiry database states and automation execution."""

    @staticmethod
    async def create_inquiry(
        client: Client,
        request: FuelInquiryCreateRequest,
        session: AsyncSession,
    ) -> FuelInquiryResponse:
        """Create a pending inquiry and dispatch a background worker task."""
        # Verify driver ownership
        driver_stmt = select(Driver).where((Driver.client_id == client.id) & (Driver.id == request.driver_id))
        driver_result = await session.exec(driver_stmt)
        driver = driver_result.first()

        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="راننده مورد نظر یافت نشد",
            )

        # Create DB record
        inquiry = FuelInquiry(
            client_id=client.id,
            driver_id=driver.id,
            status="pending",
            year=request.year,
            month=request.month,
        )
        session.add(inquiry)
        await session.commit()
        await session.refresh(inquiry)

        # Enqueue Celery task
        # Import task inside function to avoid circular imports
        from app.workers.tasks import dispatch_fuel_inquiry_task

        try:
            dispatch_fuel_inquiry_task(inquiry.id)
            logger.info(f"Enqueued fuel inquiry task for inquiry {inquiry.id}")
        except Exception as e:
            logger.error(f"Failed to enqueue Celery task: {e}")
            # Fallback to direct thread execution if Celery is not available
            inquiry.status = "failed"
            inquiry.error_message = f"خطا در ایجاد کار پس‌زمینه: {e}"
            session.add(inquiry)

        # Map to response schema
        response = FuelInquiryResponse.model_validate(inquiry)
        response.driver_name = driver.full_name
        return response

    @staticmethod
    async def list_inquiries(
        client: Client,
        page: int,
        page_size: int,
        session: AsyncSession,
    ) -> FuelInquiryListResponse:
        """Get paginated history of fuel inquiries for a tenant."""
        # Base query joining Driver to get the full name
        statement = select(FuelInquiry).where(FuelInquiry.client_id == client.id)

        # Get total count
        from sqlmodel import func

        count_stmt = select(func.count(FuelInquiry.id)).where(FuelInquiry.client_id == client.id)
        count_result = await session.exec(count_stmt)
        total = count_result.one()

        # Get paginated results
        statement = statement.order_by(col(FuelInquiry.created_at).desc())
        statement = statement.offset((page - 1) * page_size).limit(page_size)

        result = await session.exec(statement)
        inquiries = result.all()

        items = []
        for i in inquiries:
            resp = FuelInquiryResponse.model_validate(i)
            # Find driver name
            driver = await session.get(Driver, i.driver_id)
            if driver:
                resp.driver_name = driver.full_name
            if i.quota_data_json:
                try:
                    resp.quota_data = json.loads(i.quota_data_json)
                except Exception:
                    logger.warning("fuel_inquiry_parse_json_list_failed", exc_info=True)
            items.append(resp)

        total_pages = (total + page_size - 1) // page_size

        return FuelInquiryListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    @staticmethod
    async def get_inquiry(
        client: Client,
        inquiry_id: int,
        session: AsyncSession,
    ) -> FuelInquiryResponse:
        """Get a specific fuel inquiry's status and details."""
        statement = select(FuelInquiry).where((FuelInquiry.client_id == client.id) & (FuelInquiry.id == inquiry_id))
        result = await session.exec(statement)
        inquiry = result.first()

        if not inquiry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="استعلام مورد نظر یافت نشد",
            )

        resp = FuelInquiryResponse.model_validate(inquiry)
        driver = await session.get(Driver, inquiry.driver_id)
        if driver:
            resp.driver_name = driver.full_name
        if inquiry.quota_data_json:
            try:
                resp.quota_data = json.loads(inquiry.quota_data_json)
            except Exception:
                logger.warning("fuel_inquiry_parse_json_get_failed", exc_info=True)
        return resp

    @classmethod
    async def run_automation(cls, inquiry_id: int, session: AsyncSession) -> None:
        """
        Runs the scraper using Playwright and updates the database with results.
        Called by Celery worker or async thread execution.
        """
        inquiry = await session.get(FuelInquiry, inquiry_id)
        if not inquiry:
            logger.error(f"Fuel inquiry {inquiry_id} not found in database")
            return

        inquiry.status = "processing"
        inquiry.updated_at = datetime.now(UTC).replace(tzinfo=None)
        session.add(inquiry)
        await session.commit()

        driver = await session.get(Driver, inquiry.driver_id)
        if not driver:
            inquiry.status = "failed"
            inquiry.error_message = "راننده در پایگاه داده یافت نشد"
            session.add(inquiry)
            await session.commit()
            return

        # Query active driver plate
        plate_stmt = select(DriverPlate).where((DriverPlate.driver_id == driver.id) & (DriverPlate.status == "active"))
        plate_res = await session.exec(plate_stmt)
        driver_plate = plate_res.first()
        if not driver_plate:
            inquiry.status = "failed"
            inquiry.error_message = "پلاک فعال برای راننده در سامانه یافت نشد"
            session.add(inquiry)
            await session.commit()
            return

        plate_number = driver_plate.plate_number
        username = driver.utcms_username

        auth_state_path = session_vault.auth_state_path_for_account(
            username=username,
            national_code=driver.driver_national_code,
            fallback=username,
        )
        # CRITICAL: Chromium inside Docker containers CANNOT reach external sites without proxy.
        # Use simple worker_proxy helper (bypasses proxy_rotator complexity).
        # Hostname is resolved to IP at call time to fix Chromium's Docker DNS issues.
        from app.automation.worker_proxy import get_playwright_proxy

        proxy_dict = get_playwright_proxy()
        if proxy_dict:
            logger.info(f"fuel_inquiry using proxy: {proxy_dict.get('server')}")
        else:
            logger.warning("fuel_inquiry: no proxy configured — Chromium may not reach utcms.ir")

        logger.info(f"Launching browser session for fuel inquiry {inquiry_id}")

        try:
            await browser_manager.initialize()
            async with managed_browser_session(
                auth_state_path=auth_state_path,
                proxy_dict=proxy_dict,
            ) as (_session_id, context):
                page = await browser_manager.new_page(context)

                scraper = FuelScraper(page, context)
                result = await scraper.scrape_fuel_quota(
                    username=username,
                    plate_number=plate_number,
                    inquiry_id=inquiry_id,
                    j_year=inquiry.year,
                    j_month=inquiry.month,
                )

                # Save auth state back in case login was refreshed
                await browser_manager.save_auth_state(context, auth_state_path=auth_state_path)

                # Update database
                quota_data = result.get("quota_data", {})
                if not quota_data or not isinstance(quota_data, dict) or not any(quota_data.values()):
                    inquiry.status = "failed"
                    inquiry.error_message = "104"  # Data not found / Inactive plate
                else:
                    inquiry.status = "success"
                inquiry.quota_data_json = json.dumps(quota_data)
                inquiry.screenshot_url = result.get("screenshot_url")
                inquiry.updated_at = datetime.now(UTC).replace(tzinfo=None)
                session.add(inquiry)
                await session.commit()
                logger.info(f"Fuel inquiry {inquiry_id} completed with status {inquiry.status}")

        except Exception as e:
            logger.exception(f"Error executing fuel inquiry {inquiry_id}")
            inquiry.status = "failed"

            # Map exception to clean numeric error code
            msg = str(e).lower()
            if "کپچا" in msg or "captcha" in msg:
                inquiry.error_message = "101"  # Captcha solving failure
            elif "خطا در سامانه" in msg or "system error" in msg:
                inquiry.error_message = "102"  # Portal system error
            elif "timeout" in msg or "connection" in msg or "network" in msg or "proxy" in msg:
                inquiry.error_message = "103"  # Connection/Network Timeout
            elif "پلاک" in msg or "plate" in msg or "credentials" in msg or "راننده" in msg:
                inquiry.error_message = "104"  # Inactive plate or driver details error
            else:
                inquiry.error_message = "100"  # General unknown failure

            inquiry.updated_at = datetime.now(UTC).replace(tzinfo=None)
            session.add(inquiry)
            await session.commit()


# Singleton instance
fuel_inquiry_service = FuelInquiryService()
