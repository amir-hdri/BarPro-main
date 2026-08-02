"""Service layer for managing and executing fuel quota inquiries."""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.automation.browser import browser_manager, managed_browser_session
from app.automation.fuel_scraper import FuelScraper, get_current_jalali
from app.core.error_taxonomy import FUEL_INQUIRY_ERROR_CODE, ErrorCategory, classify_fuel_inquiry_exception
from app.core.exceptions import WaybillError
from app.models_multitenant import Client, Driver, DriverPlate, FuelInquiry
from app.orchestrator.state_machine import set_fuel_inquiry_status
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

        # Verify the driver has an active plate before enqueuing.
        # A fuel inquiry cannot succeed without a plate, so reject early
        # instead of creating a record that gets stuck in "pending" / fails later.
        plate_stmt = select(DriverPlate).where(
            (DriverPlate.client_id == client.id)
            & (DriverPlate.driver_id == driver.id)
            & (DriverPlate.status == "active")
        )
        plate_res = await session.exec(plate_stmt)
        if not plate_res.first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="راننده پلاک فعال ندارد؛ ابتدا یک پلاک فعال ثبت کنید",
            )

        current_year, current_month = get_current_jalali()
        inquiry_year = request.year or current_year
        inquiry_month = request.month or current_month

        # Check for existing pending/processing inquiry for same driver/period to prevent duplicates
        existing_stmt = select(FuelInquiry).where(
            (FuelInquiry.driver_id == driver.id)
            & (FuelInquiry.year == inquiry_year)
            & (FuelInquiry.month == inquiry_month)
            & (FuelInquiry.status.in_(["pending", "processing"]))
        )
        existing_res = await session.exec(existing_stmt)
        if existing_res.first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="یک استعلام فعال برای این راننده و دوره در جریان است",
            )

        # Create DB record
        inquiry = FuelInquiry(
            client_id=client.id,
            driver_id=driver.id,
            status="pending",
            year=inquiry_year,
            month=inquiry_month,
        )
        session.add(inquiry)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="یک استعلام فعال برای این راننده و دوره در جریان است",
            ) from exc
        await session.refresh(inquiry)

        # Enqueue Celery task
        # Import task inside function to avoid circular imports
        from app.workers.tasks import dispatch_fuel_inquiry_task

        try:
            dispatch_fuel_inquiry_task(inquiry.id)
            logger.info(f"Enqueued fuel inquiry task for inquiry {inquiry.id}")
        except Exception as e:
            logger.error(f"Failed to enqueue Celery task: {e}")
            set_fuel_inquiry_status(inquiry, "failed")
            inquiry.error_message = f"خطا در ایجاد کار پس‌زمینه: {e}"
            session.add(inquiry)
            await session.commit()

        # Map to response schema
        response = FuelInquiryResponse.model_validate(inquiry)
        response.driver_name = driver.full_name
        return response

    @staticmethod
    async def list_inquiries(
        user_context: dict,
        page: int,
        page_size: int,
        session: AsyncSession,
        driver_id: int | None = None,
        status: str | None = None,
        driver_name: str | None = None,
        plate_number: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> FuelInquiryListResponse:
        if isinstance(user_context, Client):
            user_context = {"role": "client", "user": user_context}
        role = user_context["role"]
        if role == "master_admin":
            statement = select(FuelInquiry)
            count_stmt = select(func.count(FuelInquiry.id))
        else:
            client = user_context["user"]
            statement = select(FuelInquiry).where(FuelInquiry.client_id == client.id)
            count_stmt = select(func.count(FuelInquiry.id)).where(FuelInquiry.client_id == client.id)

        if driver_id is not None:
            statement = statement.where(FuelInquiry.driver_id == driver_id)
            count_stmt = count_stmt.where(FuelInquiry.driver_id == driver_id)
        if status:
            statement = statement.where(FuelInquiry.status == status)
            count_stmt = count_stmt.where(FuelInquiry.status == status)
        if driver_name:
            d_stmt = select(Driver.id).where(Driver.full_name.ilike(f"%{driver_name.strip()}%"))
            d_ids = (await session.exec(d_stmt)).all()
            if d_ids:
                statement = statement.where(col(FuelInquiry.driver_id).in_(d_ids))
                count_stmt = count_stmt.where(col(FuelInquiry.driver_id).in_(d_ids))
            else:
                statement = statement.where(col(FuelInquiry.driver_id) == -1)
                count_stmt = count_stmt.where(col(FuelInquiry.driver_id) == -1)
        if plate_number:
            p_stmt = select(DriverPlate.driver_id).where(DriverPlate.plate_number.ilike(f"%{plate_number.strip()}%"))
            p_driver_ids = (await session.exec(p_stmt)).all()
            if p_driver_ids:
                statement = statement.where(col(FuelInquiry.driver_id).in_(p_driver_ids))
                count_stmt = count_stmt.where(col(FuelInquiry.driver_id).in_(p_driver_ids))
            else:
                statement = statement.where(col(FuelInquiry.driver_id) == -1)
                count_stmt = count_stmt.where(col(FuelInquiry.driver_id) == -1)
        if date_from:
            statement = statement.where(FuelInquiry.created_at >= date_from)
            count_stmt = count_stmt.where(FuelInquiry.created_at >= date_from)
        if date_to:
            statement = statement.where(FuelInquiry.created_at <= date_to)
            count_stmt = count_stmt.where(FuelInquiry.created_at <= date_to)

        # Get total count
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
            # Inject plate number dynamically
            plate_stmt = select(DriverPlate).where(
                (DriverPlate.driver_id == i.driver_id) & (DriverPlate.status == "active")
            )
            plate_res = await session.exec(plate_stmt)
            driver_plate = plate_res.first()
            if driver_plate:
                resp.plate_number = driver_plate.plate_number
            # If admin, inject client info
            if role == "master_admin":
                cl = await session.get(Client, i.client_id)
                if cl:
                    resp.client_name = cl.name
                    resp.client_code = cl.client_code

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
        user_context: dict,
        inquiry_id: int,
        session: AsyncSession,
    ) -> FuelInquiryResponse:
        if isinstance(user_context, Client):
            user_context = {"role": "client", "user": user_context}
        role = user_context["role"]
        if role == "master_admin":
            statement = select(FuelInquiry).where(FuelInquiry.id == inquiry_id)
        else:
            client = user_context["user"]
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
        # Inject plate number dynamically
        plate_stmt = select(DriverPlate).where(
            (DriverPlate.driver_id == inquiry.driver_id) & (DriverPlate.status == "active")
        )
        plate_res = await session.exec(plate_stmt)
        driver_plate = plate_res.first()
        if driver_plate:
            resp.plate_number = driver_plate.plate_number
        # If admin, inject client info
        if role == "master_admin":
            cl = await session.get(Client, inquiry.client_id)
            if cl:
                resp.client_name = cl.name
                resp.client_code = cl.client_code

        return resp

    @classmethod
    async def run_automation(cls, inquiry_id: int, session: AsyncSession) -> None:
        """
        Runs the scraper using Playwright and updates the database with results.
        Called by Celery worker or async thread execution.
        """
        now = datetime.now(UTC).replace(tzinfo=None)
        # Use the underlying SQLAlchemy engine execute for DML (UPDATE).
        # SQLModel's session.exec() is for SELECT only; calling session.execute() on
        # a DML statement triggers a false-positive DeprecationWarning from SQLModel.
        # Accessing session.connection() bypasses the SQLModel shim for DML.
        conn = await session.connection()
        claim = await conn.execute(
            update(FuelInquiry)
            .where((FuelInquiry.id == inquiry_id) & (FuelInquiry.status == "pending"))
            .values(status="processing", updated_at=now)
        )
        if claim.rowcount != 1:
            await session.rollback()
            inquiry = await session.get(FuelInquiry, inquiry_id)
            if inquiry is None:
                logger.error("Fuel inquiry %s not found in database", inquiry_id)
            else:
                logger.info("Fuel inquiry %s skipped because status is %s", inquiry_id, inquiry.status)
            return
        await session.commit()

        try:
            inquiry = await session.get(FuelInquiry, inquiry_id)
            if inquiry is None:
                raise WaybillError("استعلام سوخت پس از دریافت کار یافت نشد")

            driver_stmt = select(Driver).where(
                (Driver.id == inquiry.driver_id) & (Driver.client_id == inquiry.client_id)
            )
            driver = (await session.exec(driver_stmt)).first()
            if driver is None:
                raise WaybillError("راننده در پایگاه داده یافت نشد")

            plate_stmt = select(DriverPlate).where(
                (DriverPlate.client_id == inquiry.client_id)
                & (DriverPlate.driver_id == driver.id)
                & (DriverPlate.status == "active")
            )
            driver_plate = (await session.exec(plate_stmt)).first()
            if driver_plate is None:
                raise WaybillError("پلاک فعال برای راننده در سامانه یافت نشد")

            national_code = driver.driver_national_code
            auth_state_path = session_vault.auth_state_path_for_account(
                username=driver.utcms_username,
                national_code=national_code,
                fallback=national_code,
                scope=f"client-{inquiry.client_id}-driver-{driver.id}",
            )

            from app.automation.worker_proxy import check_proxy_health, get_playwright_proxy

            proxy_dict = get_playwright_proxy()
            if proxy_dict:
                proxy_url = proxy_dict.get("server")
                logger.info("fuel_inquiry using proxy: %s", proxy_url)
                if proxy_url and not await check_proxy_health(proxy_url):
                    raise WaybillError("پروکسی یا شبکه تونل ایران قطع می‌باشد (proxy/network check failed)")
            else:
                logger.warning("fuel_inquiry: no proxy configured; Chromium may not reach utcms.ir")

            logger.info("Launching browser session for fuel inquiry %s", inquiry_id)
            await browser_manager.initialize()
            async with managed_browser_session(
                auth_state_path=auth_state_path,
                proxy_dict=proxy_dict,
            ) as (_session_id, context):
                page = await browser_manager.new_page(context)

                scraper = FuelScraper(page, context)
                result = await scraper.scrape_fuel_quota(
                    national_code=national_code,
                    plate_number=driver_plate.plate_number,
                    inquiry_id=inquiry_id,
                    j_year=inquiry.year,
                    j_month=inquiry.month,
                )

                # Save auth state back in case login was refreshed
                await browser_manager.save_auth_state(context, auth_state_path=auth_state_path)

                # Update database
                quota_data = result.get("quota_data", {})
                tables = quota_data.get("tables") if isinstance(quota_data, dict) else None
                valid_rows = any(
                    isinstance(table, dict) and isinstance(table.get("rows"), list) and bool(table["rows"])
                    for table in (tables or [])
                )
                if result.get("success") is not True or not valid_rows:
                    set_fuel_inquiry_status(inquiry, "failed")
                    inquiry.error_message = FUEL_INQUIRY_ERROR_CODE[ErrorCategory.USER_DATA_ERROR]
                    inquiry.error_category = ErrorCategory.USER_DATA_ERROR.value
                else:
                    set_fuel_inquiry_status(inquiry, "success")
                    inquiry.error_message = None
                    inquiry.error_category = None
                inquiry.quota_data_json = quota_data
                inquiry.screenshot_url = result.get("screenshot_url")
                inquiry.updated_at = datetime.now(UTC).replace(tzinfo=None)
                session.add(inquiry)
                await session.commit()
                logger.info(f"Fuel inquiry {inquiry_id} completed with status {inquiry.status}")

        except Exception as e:
            logger.exception(f"Error executing fuel inquiry {inquiry_id}")

            # Check for browser crash and recycle
            err_msg = str(e).lower()
            if any(msg in err_msg for msg in ("target closed", "browser closed", "context closed", "page closed")):
                logger.warning("Browser crash detected during fuel inquiry. Triggering browser recycle.")
                try:
                    await browser_manager.recycle_browser()
                except Exception as recycle_err:
                    logger.error(f"Failed to recycle browser after crash in fuel inquiry: {recycle_err}")

            await session.rollback()
            inquiry = await session.get(FuelInquiry, inquiry_id)
            if inquiry is None:
                return
            set_fuel_inquiry_status(inquiry, "failed")

            # Map exception to clean numeric error code via the shared classifier.
            # The (category, code) tuple is computed once and both fields are
            # persisted so the frontend can render the right message while the
            # backend keeps a typed category for analytics.
            category, error_code = classify_fuel_inquiry_exception(e)
            inquiry.error_message = error_code
            inquiry.error_category = category.value

            inquiry.updated_at = datetime.now(UTC).replace(tzinfo=None)
            session.add(inquiry)
            await session.commit()

    @staticmethod
    async def cleanup_stale_inquiries() -> int:
        """Fail abandoned inquiries so users can safely create a fresh request."""
        from app.core.database import async_session_factory

        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=30)
        async with async_session_factory() as session:
            result = await session.execute(
                update(FuelInquiry)
                .where(
                    FuelInquiry.status.in_(["pending", "processing"]),
                    FuelInquiry.updated_at < cutoff,
                )
                .values(
                    status="failed",
                    error_message=FUEL_INQUIRY_ERROR_CODE[ErrorCategory.TRANSIENT_INFRA_ERROR],
                    updated_at=datetime.now(UTC).replace(tzinfo=None),
                )
            )
            await session.commit()
            if result.rowcount:
                logger.warning("Recovered %s stale fuel inquiries", result.rowcount)
            return int(result.rowcount or 0)


# Singleton instance
fuel_inquiry_service = FuelInquiryService()
