import asyncio
import inspect
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from app.automation.browser_pool import BrowserPool
from app.automation.stealth import apply_stealth_mode, get_random_user_agent, get_random_viewport
from app.core.config import utcms_config

logger = logging.getLogger(__name__)

_MAX_CONSOLE_EVENTS = 40
_MAX_NETWORK_EVENTS = 80


class BrowserResourceGuard:
    """Guard against browser resource leaks with automatic cleanup."""

    def __init__(self, max_age_seconds: int = 300, max_pages: int = 5):
        self.max_age_seconds = max_age_seconds
        self.max_pages = max_pages
        self._resources: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    async def register(self, resource_id: str, context: BrowserContext):
        """Register a browser context for tracking."""
        async with self._lock:
            self._resources[resource_id] = {
                "context": context,
                "created_at": time.time(),
                "pages_opened": 0,
                "last_accessed": time.time(),
            }

    async def unregister(self, resource_id: str):
        """Unregister a browser context."""
        async with self._lock:
            self._resources.pop(resource_id, None)

    async def update_access(self, resource_id: str):
        """Update last accessed time."""
        async with self._lock:
            if resource_id in self._resources:
                self._resources[resource_id]["last_accessed"] = time.time()
                self._resources[resource_id]["pages_opened"] = len(
                    self._resources[resource_id]["context"].pages
                )

    async def cleanup_stale_resources(self, browser_manager) -> int:
        """Clean up stale/orphaned browser contexts."""
        cleaned = 0
        now = time.time()

        async with self._lock:
            stale_ids = []
            for resource_id, info in self._resources.items():
                age = now - info["created_at"]
                idle_time = now - info["last_accessed"]

                if (
                    age > self.max_age_seconds
                    or idle_time > self.max_age_seconds / 2
                    or info["pages_opened"] > self.max_pages
                ):
                    stale_ids.append(resource_id)

            for resource_id in stale_ids:
                try:
                    await browser_manager.close_context(resource_id)
                    cleaned += 1
                    logger.info(
                        "stale_browser_context_cleaned",
                        extra={
                            "extra_fields": {
                                "resource_id": resource_id,
                                "age_seconds": round(now - self._resources[resource_id]["created_at"], 2),
                                "pages": self._resources[resource_id]["pages_opened"],
                            }
                        },
                    )
                except Exception as exc:
                    logger.warning(
                        "stale_cleanup_failed",
                        extra={"extra_fields": {"resource_id": resource_id, "error": str(exc)}},
                    )
                finally:
                    del self._resources[resource_id]

        return cleaned

    def get_stats(self) -> dict[str, any]:
        """Get resource usage statistics."""
        now = time.time()
        return {
            "total_tracked": len(self._resources),
            "resources": [
                {
                    "id": rid,
                    "age_seconds": round(now - info["created_at"], 2),
                    "idle_seconds": round(now - info["last_accessed"], 2),
                    "pages_open": info["pages_opened"],
                }
                for rid, info in self._resources.items()
            ],
        }


class BrowserManager:
    """Manages Playwright browser lifecycle"""

    def __init__(self):
        self.playwright = None
        self.browser: Browser | None = None
        self._contexts: dict[str, BrowserContext] = {}
        self._pooled_sessions: set[str] = set()
        self._pool: BrowserPool | None = None
        self._state_lock = asyncio.Lock()
        self._init_lock = asyncio.Lock()
        self._resource_guard = BrowserResourceGuard(
            max_age_seconds=300,
            max_pages=5,
        )

    async def initialize(self):
        """Initialize the browser instance"""
        if self.playwright and self.browser and (
            not utcms_config.BROWSER_POOL_ENABLED or self._pool is not None
        ):
            return

        async with self._init_lock:
            if not self.playwright:
                self.playwright = await async_playwright().start()

            if not self.browser:
                self.browser = await self._launch_browser_with_fallback()
            if utcms_config.BROWSER_POOL_ENABLED and self._pool is None:
                self._pool = BrowserPool(size=utcms_config.BROWSER_POOL_SIZE)
                await self._pool.start(self.browser, context_args=self._build_context_args())

    async def _try_standard_launch(self, launch_options: dict) -> Browser:
        """Attempt to launch Chromium with standard options."""
        return await self.playwright.chromium.launch(**launch_options)

    async def _try_system_chrome_launch(self, launch_options: dict, first_error: Exception) -> Browser:
        """Attempt to launch using system Google Chrome if available."""
        system_chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if os.path.exists(system_chrome):
            logger.warning(
                "browser_launch_retry_system_chrome",
                extra={"extra_fields": {"error": str(first_error), "executable_path": system_chrome}},
            )
            return await self.playwright.chromium.launch(
                **launch_options,
                executable_path=system_chrome,
                channel="chrome",
            )
        raise Exception("System Chrome not found")

    async def _try_local_home_launch(self, launch_options: dict, error_context: Exception) -> Browser:
        """Attempt to launch using a local fallback home directory."""
        fallback_home = os.path.abspath(".playwright-home")
        os.makedirs(fallback_home, exist_ok=True)
        launch_env = os.environ.copy()
        launch_env["HOME"] = fallback_home
        logger.warning(
            "browser_launch_retry_local_home",
            extra={"extra_fields": {"error": str(error_context), "home": fallback_home}},
        )
        return await self.playwright.chromium.launch(**launch_options, env=launch_env)

    async def _launch_browser_with_fallback(self) -> Browser:
        launch_args = [
            "--disable-crashpad-for-testing",
            "--disable-crash-reporter",
            # --- Anti-detection launch flags ---
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-site-isolation-trials",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-accelerated-2d-canvas",
            "--disable-gpu",
            "--window-size=1920,1080",
            "--start-maximized",
            "--disable-infobars",
            "--disable-browser-side-navigation",
            "--disable-extensions",
            "--disable-plugins-discovery",
            "--no-first-run",
            "--no-default-browser-check",
            "--password-store=basic",
            "--use-mock-keychain",
            "--lang=fa-IR",
            "--disable-web-security",
            "--allow-running-insecure-content",
            "--disable-client-side-phishing-detection",
            "--disable-popup-blocking",
            "--ignore-certificate-errors",
            "--ignore-ssl-errors",
            "--ignore-certificate-errors-spki-list",
            "--disable-background-networking",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-breakpad",
            "--disable-component-extensions-with-background-pages",
            "--disable-hang-monitor",
            "--disable-ipc-flooding-protection",
            "--disable-renderer-backgrounding",
            "--force-color-profile=srgb",
            "--metrics-recording-only",
            "--mute-audio",
            "--safebrowsing-disable-auto-update",
        ]
        launch_options = {
            "headless": utcms_config.HEADLESS,
            "args": launch_args,
        }

        try:
            return await self._try_standard_launch(launch_options)
        except Exception as first_error:
            try:
                return await self._try_system_chrome_launch(launch_options, first_error)
            except Exception as system_error:
                first_error = system_error if "System Chrome not found" not in str(system_error) else first_error

            return await self._try_local_home_launch(launch_options, first_error)

    def _build_context_args(self, auth_state_path: str | None = None, proxy_dict: dict | None = None) -> dict:
        # Use random user agent and viewport for anti-detection
        user_agent = get_random_user_agent()
        viewport = get_random_viewport()

        context_args = {
            "user_agent": user_agent,
            "viewport": viewport,
            "locale": "fa-IR",
            "timezone_id": "Asia/Tehran",
            "java_script_enabled": True,
            "ignore_https_errors": True,
            "accept_downloads": True,
            "has_touch": False,
            "is_mobile": False,
            "color_scheme": "light",
            "extra_http_headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
                "Cache-Control": "max-age=0",
                "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            },
        }

        # Add anti-detection launch args
        if hasattr(self, 'browser') and self.browser:
            # These are set at launch time, but we document them here
            pass


        if proxy_dict:
            context_args["proxy"] = proxy_dict

        if utcms_config.USE_PERSISTENT_AUTH_STATE:
            effective_auth_state_path = os.path.abspath(auth_state_path or utcms_config.AUTH_STATE_PATH)
            if os.path.exists(effective_auth_state_path):
                context_args["storage_state"] = effective_auth_state_path
        return context_args

    async def create_context(self, auth_state_path: str | None = None, proxy_dict: dict | None = None) -> tuple[str, BrowserContext]:
        """Create a new browser context with a secure session ID"""
        if not self.browser:
            await self.initialize()

        session_id = str(uuid.uuid4())
        if utcms_config.BROWSER_POOL_ENABLED and self._pool is not None:
            context = await self._pool.acquire()
            self._pooled_sessions.add(session_id)
        else:
            context = await self.browser.new_context(**self._build_context_args(auth_state_path=auth_state_path, proxy_dict=proxy_dict))
        self._contexts[session_id] = context

        # Register with resource guard
        await self._resource_guard.register(session_id, context)

        return session_id, context

    async def save_auth_state(self, context: BrowserContext, auth_state_path: str | None = None):
        """Persist current authenticated state for future sessions."""
        if not utcms_config.USE_PERSISTENT_AUTH_STATE:
            return

        effective_auth_state_path = os.path.abspath(auth_state_path or utcms_config.AUTH_STATE_PATH)
        auth_state_dir = os.path.dirname(effective_auth_state_path)
        if auth_state_dir:
            os.makedirs(auth_state_dir, exist_ok=True)

        async with self._state_lock:
            try:
                await context.storage_state(path=effective_auth_state_path)
            except Exception as exc:
                logger.warning(
                    "save_auth_state_failed",
                    extra={"extra_fields": {"error": str(exc), "path": effective_auth_state_path}},
                )

    async def close_context(self, session_id: str):
        """Close a specific browser context"""
        if session_id in self._contexts:
            context = self._contexts[session_id]

            # Record success in pool if healthy
            if self._pool and session_id not in self._pooled_sessions:
                self._pool.record_success(context)

            if session_id in self._pooled_sessions and self._pool is not None:
                await self._pool.release(context)
                self._pooled_sessions.discard(session_id)
            else:
                await context.close()
            del self._contexts[session_id]

            # Unregister from resource guard
            await self._resource_guard.unregister(session_id)

    async def new_page(self, context: BrowserContext) -> Page:
        """Create a new page in the given context with stealth mode"""
        page = await context.new_page()
        page.set_default_timeout(utcms_config.PAGE_DEFAULT_TIMEOUT)
        page.set_default_navigation_timeout(utcms_config.PAGE_NAVIGATION_TIMEOUT)
        page._telemetry_console_messages = []  # type: ignore[attr-defined]
        page._telemetry_network_events = []  # type: ignore[attr-defined]

        def _capture_console(message) -> None:
            try:
                page._telemetry_console_messages.append(  # type: ignore[attr-defined]
                    {
                        "timestamp": datetime.now(UTC).replace(tzinfo=None).isoformat(),
                        "type": message.type,
                        "text": message.text,
                    }
                )
                self._trim_telemetry(page, "_telemetry_console_messages", _MAX_CONSOLE_EVENTS)
            except Exception:
                return

        def _capture_request(request) -> None:
            try:
                page._telemetry_network_events.append(  # type: ignore[attr-defined]
                    {
                        "timestamp": datetime.now(UTC).replace(tzinfo=None).isoformat(),
                        "kind": "request",
                        "method": request.method,
                        "url": request.url,
                    }
                )
                self._trim_telemetry(page, "_telemetry_network_events", _MAX_NETWORK_EVENTS)
            except Exception:
                return

        def _capture_response(response) -> None:
            try:
                page._telemetry_network_events.append(  # type: ignore[attr-defined]
                    {
                        "timestamp": datetime.now(UTC).replace(tzinfo=None).isoformat(),
                        "kind": "response",
                        "status": response.status,
                        "url": response.url,
                    }
                )
                self._trim_telemetry(page, "_telemetry_network_events", _MAX_NETWORK_EVENTS)
            except Exception:
                return

        await self._register_page_listener(page, "console", _capture_console)
        await self._register_page_listener(page, "request", _capture_request)
        await self._register_page_listener(page, "response", _capture_response)

        # Apply stealth mode to hide automation indicators
        try:
            await apply_stealth_mode(page)
        except Exception as e:
            logger.warning(
                "stealth_mode_apply_failed",
                extra={"extra_fields": {"error": str(e)}},
            )

        # Update resource guard
        for session_id, ctx in self._contexts.items():
            if ctx == context:
                await self._resource_guard.update_access(session_id)
                break

        return page

    @staticmethod
    def _trim_telemetry(page: Page, attribute: str, max_events: int) -> None:
        events = getattr(page, attribute, None)
        if not isinstance(events, list) or len(events) <= max_events:
            return
        del events[:-max_events]

    @staticmethod
    async def _register_page_listener(page: Page, event_name: str, callback) -> None:
        try:
            result = page.on(event_name, callback)
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            logger.warning(
                "page_listener_registration_failed",
                extra={"extra_fields": {"event": event_name, "error": str(exc)}},
            )

    async def close(self):
        """Close browser and playwright"""
        loop = asyncio.get_running_loop()
        previous_exception_handler = loop.get_exception_handler()

        def shutdown_exception_handler(current_loop, context):
            exception = context.get("exception")
            message = str(exception or context.get("message", ""))
            if self._contains_benign_shutdown_marker(message):
                return
            if previous_exception_handler:
                previous_exception_handler(current_loop, context)
            else:
                current_loop.default_exception_handler(context)

        loop.set_exception_handler(shutdown_exception_handler)

        for context in list(self._contexts.values()):
            try:
                await context.close()
            except Exception as exc:
                logger.warning(
                    "context_close_failed_on_shutdown",
                    extra={"extra_fields": {"error": str(exc)}},
                )
        self._contexts.clear()
        self._pooled_sessions.clear()

        if self._pool:
            await self._pool.close()
            self._pool = None

        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception as exc:
                if not self._is_benign_shutdown_error(exc):
                    logger.warning(
                        "playwright_stop_failed_on_shutdown",
                        extra={"extra_fields": {"error": str(exc)}},
                    )
            self.playwright = None
            self.browser = None
            return

        if self.browser:
            try:
                await self.browser.close()
            except Exception as exc:
                if not self._is_benign_shutdown_error(exc):
                    logger.warning(
                        "browser_close_failed_on_shutdown",
                        extra={"extra_fields": {"error": str(exc)}},
                    )
            self.browser = None

    @staticmethod
    def _is_benign_shutdown_error(error: Exception) -> bool:
        return BrowserManager._contains_benign_shutdown_marker(str(error))

    @staticmethod
    def _contains_benign_shutdown_marker(message: str) -> bool:
        normalized_message = (message or "").lower()
        benign_markers = (
            "target page, context or browser has been closed",
            "connection closed while reading from the driver",
            "handler is closed",
            "browser has been closed",
        )
        return any(marker in normalized_message for marker in benign_markers)

    async def cleanup_stale_resources(self) -> int:
        """Public method to clean up stale browser resources."""
        return await self._resource_guard.cleanup_stale_resources(self)

    def get_resource_stats(self) -> dict[str, any]:
        """Get browser resource usage statistics."""
        return {
            "active_contexts": len(self._contexts),
            "pooled_sessions": len(self._pooled_sessions),
            "resource_guard": self._resource_guard.get_stats(),
        }


browser_manager = BrowserManager()


@asynccontextmanager
async def managed_browser_session(auth_state_path: str | None = None, proxy_dict: dict | None = None):
    """Context manager for safe browser session lifecycle with automatic cleanup."""
    session_id = None
    context = None
    try:
        await browser_manager.initialize()
        session_id, context = await browser_manager.create_context(auth_state_path=auth_state_path, proxy_dict=proxy_dict)
        yield session_id, context
    finally:
        if session_id:
            try:
                await browser_manager.close_context(session_id)
            except Exception as exc:
                logger.warning(
                    "managed_session_close_failed",
                    extra={"extra_fields": {"session_id": session_id, "error": str(exc)}},
                )


@asynccontextmanager
async def managed_page(auth_state_path: str | None = None):
    """Context manager for safe page lifecycle with automatic cleanup."""
    async with managed_browser_session(auth_state_path=auth_state_path) as (session_id, context):
        page = await browser_manager.new_page(context)
        try:
            yield page
        finally:
            try:
                await page.close()
            except Exception as exc:
                logger.warning(
                    "managed_page_close_failed",
                    extra={"extra_fields": {"error": str(exc)}},
                )


class PageInteractor:
    """Helper for safe page interactions with human-like behavior"""

    def __init__(self, page: Page):
        self.page = page

    async def safe_click(self, selector: str, wait_for_navigation: bool = False, timeout: int = 5000):
        """Click an element safely with human-like mouse movement"""
        try:
            from app.automation.stealth import add_random_delay, human_like_mouse_movement

            # Move mouse to element like a human
            try:
                await human_like_mouse_movement(self.page, selector)
            except Exception:
                pass  # Fallback to normal click if movement fails

            element = await self.page.wait_for_selector(selector, state="visible", timeout=timeout)
            if element:
                if wait_for_navigation:
                    async with self.page.expect_navigation(timeout=timeout):
                        await element.click()
                else:
                    await element.click()
                # Add small random delay after click
                await add_random_delay(self.page, 0.2, 0.8)
                return True
        except Exception as exc:
            logger.warning(
                "safe_click_failed",
                extra={"extra_fields": {"selector": selector, "error": str(exc)}},
            )
        return False

    async def safe_fill(self, selector: str, value: str, timeout: int = 5000, human_like: bool = True):
        """Fill an input safely with optional human-like typing"""
        try:
            from app.automation.stealth import add_random_delay, human_like_typing

            element = await self.page.wait_for_selector(selector, state="visible", timeout=timeout)
            if element:
                if human_like:
                    # Type like a human with delays between keystrokes
                    await human_like_typing(self.page, selector, value)
                else:
                    await element.fill(value)
                # Add small random delay after fill
                await add_random_delay(self.page, 0.1, 0.5)
                return True
        except Exception as exc:
            logger.warning(
                "safe_fill_failed",
                extra={"extra_fields": {"selector": selector, "error": str(exc)}},
            )
        return False

    async def screenshot(self, name: str):
        """Take a lightweight screenshot without blocking the workflow for long."""
        try:
            await self.page.screenshot(
                path=f"{name}.png",
                full_page=False,
                timeout=2000,
                animations="disabled",
            )
        except Exception as exc:
            logger.warning(
                "screenshot_failed",
                extra={"extra_fields": {"name": name, "error": str(exc)}},
            )
