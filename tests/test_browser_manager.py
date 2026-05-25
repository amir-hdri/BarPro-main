import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import sys
import os

# Add app to path
sys.path.append(os.getcwd())

from app.automation.browser import BrowserManager
from app.core.config import utcms_config

class TestBrowserManager(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Create a fresh BrowserManager instance for each test
        self.browser_manager = BrowserManager()

        # Create mocks for Playwright components
        self.mock_playwright = AsyncMock()
        self.mock_browser = AsyncMock()
        self.mock_context = AsyncMock()
        self.mock_page = AsyncMock()

        # Configure the mock chain
        # When playwright.chromium.launch() is called, it returns our mock_browser
        self.mock_playwright.chromium.launch.return_value = self.mock_browser

        # When browser.new_context() is called, it returns our mock_context
        self.mock_browser.new_context.return_value = self.mock_context

        # When context.new_page() is called, it returns our mock_page
        self.mock_context.new_page.return_value = self.mock_page

        # set_default_timeout / set_default_navigation_timeout are sync on real Page
        self.mock_page.set_default_timeout = MagicMock()
        self.mock_page.set_default_navigation_timeout = MagicMock()

        # When start() is awaited, return our mock_playwright
        self.mock_start = AsyncMock(return_value=self.mock_playwright)

    @patch('app.automation.browser.async_playwright')
    async def test_initialize(self, mock_async_playwright):
        # Configure the mock to return a context manager that returns our mock_start result
        mock_async_playwright.return_value.start = self.mock_start

        await self.browser_manager.initialize()

        # Verify playwright started
        self.mock_start.assert_awaited_once()
        self.assertEqual(self.browser_manager.playwright, self.mock_playwright)

        # Verify browser launched with resilience args, allowing extra hardening flags.
        self.mock_playwright.chromium.launch.assert_awaited_once()
        launch_kwargs = self.mock_playwright.chromium.launch.await_args.kwargs
        self.assertEqual(launch_kwargs["headless"], utcms_config.HEADLESS)
        self.assertIn("--disable-crashpad-for-testing", launch_kwargs["args"])
        self.assertIn("--disable-crash-reporter", launch_kwargs["args"])
        self.assertEqual(self.browser_manager.browser, self.mock_browser)

    @patch('app.automation.browser.async_playwright')
    async def test_initialize_idempotent(self, mock_async_playwright):
        # Set up already initialized state
        self.browser_manager.playwright = self.mock_playwright
        self.browser_manager.browser = self.mock_browser

        await self.browser_manager.initialize()

        # Verify start() and launch() were NOT called
        mock_async_playwright.assert_not_called()
        self.mock_start.assert_not_called()
        self.mock_playwright.chromium.launch.assert_not_called()

    @patch('app.automation.browser.async_playwright')
    async def test_create_context_new(self, mock_async_playwright):
        # Setup initialization mocks
        mock_async_playwright.return_value.start = self.mock_start

        # create_context doesn't take session_id anymore, returns (session_id, context)
        session_id, context = await self.browser_manager.create_context()

        # Verify initialization happened
        self.mock_start.assert_awaited_once()
        self.mock_playwright.chromium.launch.assert_awaited_once()

        # Verify context creation
        self.mock_browser.new_context.assert_awaited_once()
        self.assertEqual(context, self.mock_context)

        # Verify session ID is tracked
        self.assertIsNotNone(session_id)
        self.assertIn(session_id, self.browser_manager._contexts)
        self.assertEqual(self.browser_manager._contexts[session_id], self.mock_context)

    async def test_close_context(self):
        # Setup existing context
        session_id = "session_to_close"
        self.browser_manager._contexts[session_id] = self.mock_context

        await self.browser_manager.close_context(session_id)

        # Verify context closed and removed
        self.mock_context.close.assert_awaited_once()
        self.assertNotIn(session_id, self.browser_manager._contexts)

    async def test_new_page(self):
        page = await self.browser_manager.new_page(self.mock_context)

        page.set_default_timeout.assert_called_once_with(utcms_config.PAGE_DEFAULT_TIMEOUT)
        page.set_default_navigation_timeout.assert_called_once_with(utcms_config.PAGE_NAVIGATION_TIMEOUT)
        self.mock_context.new_page.assert_awaited_once()
        self.assertEqual(page, self.mock_page)

    async def test_create_context_loads_saved_auth_state(self):
        self.browser_manager.browser = self.mock_browser

        with patch("app.core.config.utcms_config.USE_PERSISTENT_AUTH_STATE", True), \
             patch("app.core.config.utcms_config.AUTH_STATE_PATH", "/tmp/utcms_state.json"), \
             patch("app.automation.browser.os.path.exists", return_value=True):
            _, _ = await self.browser_manager.create_context()

        self.mock_browser.new_context.assert_awaited_once()
        kwargs = self.mock_browser.new_context.await_args.kwargs
        self.assertEqual(kwargs.get("storage_state"), "/tmp/utcms_state.json")

    async def test_create_context_loads_custom_auth_state_path(self):
        self.browser_manager.browser = self.mock_browser

        with patch("app.core.config.utcms_config.USE_PERSISTENT_AUTH_STATE", True), \
             patch("app.automation.browser.os.path.exists", side_effect=lambda path: path == "/tmp/custom_state.json"):
            _, _ = await self.browser_manager.create_context(auth_state_path="/tmp/custom_state.json")

        self.mock_browser.new_context.assert_awaited_once()
        kwargs = self.mock_browser.new_context.await_args.kwargs
        self.assertEqual(kwargs.get("storage_state"), "/tmp/custom_state.json")

    async def test_save_auth_state(self):
        context = AsyncMock()

        with patch("app.core.config.utcms_config.USE_PERSISTENT_AUTH_STATE", True), \
             patch("app.core.config.utcms_config.AUTH_STATE_PATH", "/tmp/utcms_state.json"):
            await self.browser_manager.save_auth_state(context)

        context.storage_state.assert_awaited_once_with(path="/tmp/utcms_state.json")

    async def test_save_auth_state_with_custom_path(self):
        context = AsyncMock()

        with patch("app.core.config.utcms_config.USE_PERSISTENT_AUTH_STATE", True):
            await self.browser_manager.save_auth_state(context, auth_state_path="/tmp/custom_state.json")

        context.storage_state.assert_awaited_once_with(path="/tmp/custom_state.json")

    async def test_close_all(self):
        # Setup state
        self.browser_manager.playwright = self.mock_playwright
        self.browser_manager.browser = self.mock_browser
        self.browser_manager._contexts["ctx1"] = self.mock_context

        # Mock another context
        mock_context2 = AsyncMock()
        self.browser_manager._contexts["ctx2"] = mock_context2

        await self.browser_manager.close()

        # Verify contexts closed
        self.mock_context.close.assert_awaited_once()
        mock_context2.close.assert_awaited_once()
        self.assertEqual(len(self.browser_manager._contexts), 0)

        # Browser is closed by playwright.stop when playwright is available
        self.mock_browser.close.assert_not_awaited()
        self.assertIsNone(self.browser_manager.browser)

        # Verify playwright stopped
        self.mock_playwright.stop.assert_awaited_once()
        self.assertIsNone(self.browser_manager.playwright)

    async def test_close_all_without_playwright_closes_browser(self):
        self.browser_manager.playwright = None
        self.browser_manager.browser = self.mock_browser

        await self.browser_manager.close()

        self.mock_browser.close.assert_awaited_once()

if __name__ == '__main__':
    unittest.main()
