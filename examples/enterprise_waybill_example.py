"""
Enterprise-Grade RPA Bot - Complete Integration Example
========================================================
Demonstrates all advanced optimizations working together.
This is a reference implementation for production use.
"""

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from playwright.async_api import BrowserContext, Page, async_playwright

from app.automation.human_interaction import (
    HumanBehaviorSimulator,
    HumanTiming,
    MouseMovementEngine,
    TypingProfile,
    click_with_human_movement,
    human_type,
)
from app.automation.resource_optimizer import (
    MemoryTracker,
    OptimizedBrowserPool,
)

# Import enterprise modules
from app.automation.stealth_advanced import (
    WAFType,
    apply_enterprise_stealth,
    detect_waf,
    get_random_screen_preset,
    get_random_user_agent,
    handle_cloudflare_challenge,
)
from app.core.exceptions import AuthenticationError
from app.core.resilience import (
    ExplicitWaits,
    GracefulDegradation,
    ResilientWorkflow,
)
from app.core.telemetry import (
    evidence_collector,
    report_generator,
    telemetry_collector,
)
from app.automation.resource_optimizer import (
    OptimizedBrowserPool,
    MemoryTracker,
)
from app.core.exceptions import AuthenticationError

logger = logging.getLogger(__name__)


# ============================================================================
# EXAMPLE 1: Complete Enterprise-Grade Login Flow
# ============================================================================

class EnterpriseLogin:
    """Enterprise-grade login with all optimizations."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.degradation = GracefulDegradation(
            max_consecutive_failures=5,
            pause_duration=300.0,
        )

    async def login(
        self,
        page: Page,
        username: str,
        password: str,
        workflow_id: str,
    ) -> dict[str, Any]:
        """
        Perform login with stealth, human behavior, and resilience.
        """
        workflow = ResilientWorkflow(
            workflow_name="Portal Login",
            workflow_id=workflow_id,
            page=page,
            max_retries=3,
            capture_evidence_on_failure=True,
        )

        async def execute_login():
            # Step 1: Navigate to login page
            await workflow.execute_step(
                step_name="navigate_to_login",
                step_func=self._navigate_to_login,
                max_retries=3,
                page=page,
            )

            # Step 2: Detect WAF
            await workflow.execute_step(
                step_name="detect_waf",
                step_func=self._detect_and_handle_waf,
                max_retries=2,
                page=page,
            )

            # Step 3: Fill credentials with human-like typing
            await workflow.execute_step(
                step_name="fill_credentials",
                step_func=self._fill_credentials,
                max_retries=2,
                page=page,
                username=username,
                password=password,
            )

            # Step 4: Submit form
            await workflow.execute_step(
                step_name="submit_login",
                step_func=self._submit_form,
                max_retries=3,
                page=page,
            )

            # Step 5: Verify login success
            await workflow.execute_step(
                step_name="verify_login",
                step_func=self._verify_login_success,
                max_retries=2,
                page=page,
            )

            return {"status": "authenticated"}

        result = await workflow.execute(execute_login)

        # Record telemetry
        if result["success"]:
            await self.degradation.record_success()
            await telemetry_collector.record_step_complete(
                workflow_id=workflow_id,
                step_name="login_complete",
                duration_ms=workflow.state.duration_ms or 0,
            )
        else:
            await self.degradation.record_failure(
                error_code=workflow.state.error_code or "UNKNOWN"
            )

        return result

    async def _navigate_to_login(self, page: Page):
        """Navigate to login page with retry."""
        await page.goto(f"{self.base_url}/login", wait_until="domcontentloaded")
        await ExplicitWaits.wait_for_network_idle_smart(page, timeout=10000)

    async def _detect_and_handle_waf(self, page: Page):
        """Detect and handle WAF challenges."""
        waf_type = await detect_waf(page)

        if waf_type == WAFType.CLOUDFLARE:
            logger.info("Cloudflare detected, handling challenge")
            bypassed = await handle_cloudflare_challenge(page, timeout_seconds=30.0)
            if not bypassed:
                raise AuthenticationError(
                    "Cloudflare challenge failed",
                    error_code="AUTH_CAPTCHA_FAILED",
                )

        elif waf_type == WAFType.IMPERVA:
            logger.info("Imperva detected, waiting for validation")
            await HumanTiming.random_delay(3.0, 6.0)

    async def _fill_credentials(self, page: Page, username: str, password: str):
        """Fill credentials with human-like typing."""
        # Simulate human reading the form
        simulator = HumanBehaviorSimulator(page)
        await simulator.simulate_reading(duration_seconds=1.0)

        # Type username with realistic delays
        await human_type(
            page,
            "#username",
            username,
            profile=TypingProfile.AVERAGE,
            add_typos=False,
        )
        await HumanTiming.action_delay("form_fill")

        # Type password with hunt-and-peck profile (slower, more careful)
        await human_type(
            page,
            "#password",
            password,
            profile=TypingProfile.HUNT_AND_PECK,
            add_typos=False,
        )
        await HumanTiming.action_delay("form_fill")

    async def _submit_form(self, page: Page):
        """Submit form with human mouse movement."""
        # Move mouse to submit button with bezier curve
        await MouseMovementEngine.move_to_element(
            page,
            "#login-btn",
            steps=15,
            use_bezier=True,
            hover_before_click=True,
        )

        # Click with human behavior
        clicked = await click_with_human_movement(
            page,
            "#login-btn",
            wait_for_navigation=True,
        )

        if not clicked:
            raise AuthenticationError("Failed to click login button")

        # Wait for navigation
        await ExplicitWaits.wait_for_url_change(
            page,
            current_url=f"{self.base_url}/login",
            timeout=15000,
        )

    async def _verify_login_success(self, page: Page):
        """Verify login was successful."""
        # Wait for dashboard element
        is_visible = await ExplicitWaits.wait_for_element_stable(
            page,
            "#dashboard",
            timeout=10000,
            stable_time=0.5,
        )

        if not is_visible:
            current_url = await page.url()
            raise AuthenticationError(
                f"Login failed, current URL: {current_url}",
                error_code="AUTH_INVALID_CREDENTIALS",
            )


# ============================================================================
# EXAMPLE 2: Enterprise Waybill Creation
# ============================================================================

class EnterpriseWaybillCreator:
    """Enterprise-grade waybill creation with full observability."""

    def __init__(self, page: Page, context: BrowserContext):
        self.page = page
        self.context = context

    async def create_waybill(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create waybill with all enterprise features."""
        workflow_id = f"wb_{uuid.uuid4().hex[:8]}"

        workflow = ResilientWorkflow(
            workflow_name="Waybill Creation",
            workflow_id=workflow_id,
            page=self.page,
            max_retries=3,
            capture_evidence_on_failure=True,
        )

        async def execute_creation():
            # Navigate to waybill form
            await workflow.execute_step(
                step_name="navigate_to_form",
                step_func=self._navigate_to_waybill_form,
                max_retries=3,
            )

            # Fill sender info
            await workflow.execute_step(
                step_name="fill_sender",
                step_func=self._fill_sender_info,
                max_retries=2,
                sender_data=data.get("sender", {}),
            )

            # Fill receiver info
            await workflow.execute_step(
                step_name="fill_receiver",
                step_func=self._fill_receiver_info,
                max_retries=2,
                receiver_data=data.get("receiver", {}),
            )

            # Select origin location
            await workflow.execute_step(
                step_name="select_origin",
                step_func=self._select_location,
                max_retries=3,
                location_data=data.get("origin", {}),
                is_origin=True,
            )

            # Select destination location
            await workflow.execute_step(
                step_name="select_destination",
                step_func=self._select_location,
                max_retries=3,
                location_data=data.get("destination", {}),
                is_origin=False,
            )

            # Submit waybill
            await workflow.execute_step(
                step_name="submit_waybill",
                step_func=self._submit_waybill,
                max_retries=3,
            )

            # Extract tracking code
            await workflow.execute_step(
                step_name="extract_tracking",
                step_func=self._extract_tracking_code,
                max_retries=2,
            )

            return {"workflow_id": workflow_id, "status": "created"}

        result = await workflow.execute(execute_creation)

        # Generate client report
        if not result["success"]:
            report = report_generator.generate_client_report(
                workflow_state=workflow.get_state().to_dict(),
                evidence=workflow._evidence_collected,
            )
            result["client_report"] = report

        return result

    async def _navigate_to_waybill_form(self):
        """Navigate to waybill creation form."""
        await self.page.goto(
            "https://portal.utcms.ir/waybill/create",
            wait_until="domcontentloaded",
        )
        await ExplicitWaits.wait_for_network_idle_smart(self.page)
        await HumanTiming.action_delay("page_load")

    async def _fill_sender_info(self, sender_data: dict[str, Any]):
        """Fill sender information with human-like typing."""
        fields = [
            ("#sender_name", sender_data.get("name", "")),
            ("#sender_phone", sender_data.get("phone", "")),
            ("#sender_address", sender_data.get("address", "")),
        ]

        for selector, value in fields:
            if value:
                await human_type(
                    self.page,
                    selector,
                    value,
                    profile=TypingProfile.AVERAGE,
                )
                await HumanTiming.action_delay("form_fill")

    async def _fill_receiver_info(self, receiver_data: dict[str, Any]):
        """Fill receiver information."""
        fields = [
            ("#receiver_name", receiver_data.get("name", "")),
            ("#receiver_phone", receiver_data.get("phone", "")),
            ("#receiver_address", receiver_data.get("address", "")),
        ]

        for selector, value in fields:
            if value:
                await human_type(
                    self.page,
                    selector,
                    value,
                    profile=TypingProfile.AVERAGE,
                )
                await HumanTiming.action_delay("form_fill")

    async def _select_location(self, location_data: dict[str, Any], is_origin: bool):
        """Select location from map or dropdown."""
        # Implementation depends on your map controller
        # Use human-like interaction with map
        await HumanTiming.action_delay("click")

    async def _submit_waybill(self):
        """Submit waybill form."""
        # Move to submit button with human mouse movement
        await MouseMovementEngine.move_to_element(
            self.page,
            "#submit-btn",
            steps=15,
            use_bezier=True,
            hover_before_click=True,
        )

        # Thinking pause before submission
        await HumanTiming.action_delay("submit")

        # Click submit
        await click_with_human_movement(
            self.page,
            "#submit-btn",
            wait_for_navigation=False,
        )

        # Wait for success message
        await ExplicitWaits.wait_for_element_stable(
            self.page,
            ".success-message",
            timeout=15000,
        )

    async def _extract_tracking_code(self):
        """Extract tracking code from success page."""
        tracking_element = await self.page.query_selector(".tracking-code")
        if tracking_element:
            tracking_code = await tracking_element.text_content()
            return {"tracking_code": tracking_code.strip()}
        return {}


# ============================================================================
# EXAMPLE 3: Concurrent Processing with Resource Management
# ============================================================================

async def process_waybills_batch(
    waybills: list[dict[str, Any]],
    max_concurrent: int = 4,
) -> list[dict[str, Any]]:
    """
    Process multiple waybills with controlled concurrency and resource management.
    """
    # Initialize resource pool
    resource_pool = OptimizedBrowserPool(
        pool_size=max_concurrent,
        enable_memory_tracking=True,
        enable_lifecycle_management=True,
        auto_cleanup_interval=120.0,
        max_memory_mb=512.0,
    )

    semaphore = asyncio.Semaphore(max_concurrent)
    results = []

    async def process_single_waybill(waybill: dict[str, Any]) -> dict[str, Any]:
        """Process a single waybill with resource management."""
        async with semaphore:
            # Initialize browser
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context_args = {
                    "user_agent": get_random_user_agent(),
                    "viewport": get_random_screen_preset(),
                }

                pool = await resource_pool.initialize_pool(browser, context_args)

                try:
                    # Acquire context with tracking
                    context, context_id = await resource_pool.acquire_context(
                        pool,
                        workflow_id=waybill.get("id", "unknown"),
                    )

                    try:
                        # Create page with stealth
                        page = await context.new_page()
                        await apply_enterprise_stealth(page)

                        # Create waybill
                        creator = EnterpriseWaybillCreator(page, context)
                        result = await creator.create_waybill(waybill)

                        # Release with success
                        await resource_pool.release_context(pool, context, success=True)

                        return {
                            "waybill_id": waybill.get("id"),
                            "success": True,
                            "result": result,
                        }

                    except Exception as e:
                        # Release with failure
                        await resource_pool.release_context(pool, context, success=False)

                        return {
                            "waybill_id": waybill.get("id"),
                            "success": False,
                            "error": str(e),
                        }

                finally:
                    await resource_pool.shutdown(pool)
                    await browser.close()

    # Process all waybills with concurrency limit
    tasks = [process_single_waybill(wb) for wb in waybills]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Final cleanup
    resource_pool.memory_tracker.force_garbage_collection()

    return results


# ============================================================================
# EXAMPLE 4: Monitoring & Health Check
# ============================================================================

async def get_system_health() -> dict[str, Any]:
    """Get comprehensive system health status."""
    from app.core.telemetry import evidence_collector, telemetry_collector

    # Get telemetry summary
    telemetry_summary = await telemetry_collector.get_performance_summary()

    # Get evidence storage usage
    evidence_usage = evidence_collector.get_storage_usage()

    # Get memory status
    memory_tracker = MemoryTracker()
    memory_status = memory_tracker.check_memory_usage()

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "telemetry": telemetry_summary,
        "evidence_storage": evidence_usage,
        "memory": memory_status,
        "status": "healthy" if memory_status["status"] == "healthy" else "degraded",
    }


# ============================================================================
# EXAMPLE 5: Complete Workflow with All Features
# ============================================================================

async def complete_enterprise_workflow(waybill_data: dict[str, Any]) -> dict[str, Any]:
    """
    Complete workflow demonstrating all enterprise features.
    This is the recommended production pattern.
    """
    workflow_id = f"wb_{uuid.uuid4().hex[:8]}"

    # Record workflow start
    await telemetry_collector.record_event(
        event_type="workflow_start",
        workflow_id=workflow_id,
        metadata={"waybill_data_keys": list(waybill_data.keys())},
    )

    start_time = time.time()

    try:
        # Initialize browser
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=get_random_user_agent(),
                viewport=get_random_screen_preset(),
                locale="fa-IR",
                timezone_id="Asia/Tehran",
            )

            page = await context.new_page()

            # Apply enterprise stealth
            stealth_applied = await apply_enterprise_stealth(page)
            logger.info(
                "stealth_applied",
                extra={"extra_fields": {"workflow_id": workflow_id, "stealth": stealth_applied}}
            )

            # Login
            login = EnterpriseLogin(base_url="https://portal.utcms.ir")
            login_result = await login.login(
                page=page,
                username="your_username",
                password="your_password",
                workflow_id=workflow_id,
            )

            if not login_result["success"]:
                raise AuthenticationError("Login failed")

            # Create waybill
            creator = EnterpriseWaybillCreator(page, context)
            waybill_result = await creator.create_waybill(waybill_data)

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Record success
            await telemetry_collector.record_event(
                event_type="workflow_complete",
                workflow_id=workflow_id,
                duration_ms=duration_ms,
                status="success",
                metadata={"waybill_result": waybill_result},
            )

            # Cleanup
            await context.close()
            await browser.close()

            return {
                "success": True,
                "workflow_id": workflow_id,
                "duration_ms": round(duration_ms, 2),
                "result": waybill_result,
            }

    except Exception as e:
        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000

        # Record failure
        await telemetry_collector.record_event(
            event_type="workflow_failed",
            workflow_id=workflow_id,
            duration_ms=duration_ms,
            status="failure",
            error_code=getattr(e, "error_code", "UNKNOWN"),
            error_message=str(e),
        )

        # Capture evidence if we have a page
        if 'page' in locals():
            await evidence_collector.capture_failure_evidence(
                page=page,
                workflow_id=workflow_id,
                step_name="workflow_execution",
                error_code=getattr(e, "error_code", "UNKNOWN"),
                error_message=str(e),
            )

        raise
