import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from app.automation.auth import UTCMSAuthenticator
from app.automation.selectors import AuthSelectors


class _NoopAsyncContext:
    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc, tb):
        return False


class TestUTCMSAuthenticator(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.page = AsyncMock()
        self.page.locator = Mock()
        self.context = AsyncMock()
        self.auth = UTCMSAuthenticator(self.page, self.context)
        self.page.expect_navigation = Mock(return_value=_NoopAsyncContext())

    async def test_login_fails_fast_when_captcha_detected_without_value(self):
        self.auth._candidate_login_urls = lambda: ["https://barname.utcms.ir/Login"]

        async def find_selector(selectors, visible=False, timeout=1000):
            if selectors is AuthSelectors.USERNAME_SELECTORS:
                return "input[name='Username']"
            if selectors is AuthSelectors.PASSWORD_SELECTORS:
                return "input[name='Password']"
            if selectors is AuthSelectors.SUBMIT_SELECTORS:
                return "button[type='submit']"
            if selectors is AuthSelectors.CAPTCHA_SELECTORS:
                return "input[name='DNTCaptchaInputText']"
            return None

        self.auth._find_selector = AsyncMock(side_effect=find_selector)

        with patch("app.automation.auth.utcms_config.UTCMS_CAPTCHA_VALUE", ""), \
             patch("app.automation.auth.utcms_config.UTCMS_ENABLE_MANUAL_CAPTCHA", False):
            success = await self.auth.login("user", "pass")

        self.assertFalse(success)
        self.assertIn("کپچا", self.auth.last_error or "")

    async def test_login_success_with_non_dashboard_redirect(self):
        self.auth._candidate_login_urls = lambda: ["https://barname.utcms.ir/Login"]

        async def find_selector(selectors, visible=False, timeout=1000):
            if selectors is AuthSelectors.USERNAME_SELECTORS:
                return "input[name='Username']"
            if selectors is AuthSelectors.PASSWORD_SELECTORS:
                return "input[name='Password']"
            if selectors is AuthSelectors.SUBMIT_SELECTORS:
                return "button[type='submit']"
            return None

        self.auth._find_selector = AsyncMock(side_effect=find_selector)
        self.auth._wait_for_login_result = AsyncMock(return_value=True)

        with patch("app.automation.auth.utcms_config.UTCMS_CAPTCHA_VALUE", ""):
            success = await self.auth.login("user", "pass")

        self.assertTrue(success)
        self.page.fill.assert_any_await("input[name='Username']", "user")
        self.page.fill.assert_any_await("input[name='Password']", "pass")
        self.page.click.assert_awaited()

    async def test_submit_login_handles_ajax_failure_response(self):
        mock_response = AsyncMock()
        mock_response.url = "https://barname.utcms.ir/Barname/Account/OldLogin"
        mock_response.json = AsyncMock(return_value={"success": False, "message": "کاربری با این مشخصات در سامانه یافت نشد."})
        self.page.wait_for_response = AsyncMock(return_value=mock_response)
        self.page.click = AsyncMock()
        self.page.wait_for_load_state = AsyncMock()

        success = await self.auth._submit_login("button[type='submit']")

        self.assertFalse(success)
        self.assertIn("کاربری", self.auth.last_error or "")

    async def test_submit_login_handles_ajax_success_response(self):
        mock_response = AsyncMock()
        mock_response.url = "https://barname.utcms.ir/Barname/Account/OldLogin"
        mock_response.json = AsyncMock(return_value={"success": True, "data": {"obj": {"firstLogin": False}}})
        self.page.wait_for_response = AsyncMock(return_value=mock_response)
        self.page.click = AsyncMock()
        self.page.wait_for_load_state = AsyncMock()
        self.auth._complete_post_login_steps = AsyncMock(return_value=True)
        self.auth._find_selector = AsyncMock(return_value=None)
        self.auth._current_url = AsyncMock(return_value="https://barname.utcms.ir/Barname/Notification/Notification")
        self.auth._is_logged_in = AsyncMock(return_value=True)

        success = await self.auth._submit_login("button[type='submit']")

        self.assertTrue(success)

    async def test_login_fails_on_headless_manual_captcha(self):
        self.auth._candidate_login_urls = lambda: ["https://barname.utcms.ir/Login"]

        async def find_selector(selectors, visible=False, timeout=1000):
            if selectors is AuthSelectors.USERNAME_SELECTORS:
                return "input[name='Username']"
            if selectors is AuthSelectors.PASSWORD_SELECTORS:
                return "input[name='Password']"
            if selectors is AuthSelectors.SUBMIT_SELECTORS:
                return "button[type='submit']"
            if selectors is AuthSelectors.CAPTCHA_SELECTORS:
                return "input[name='DNTCaptchaInputText']"
            return None

        self.auth._find_selector = AsyncMock(side_effect=find_selector)

        with patch("app.automation.auth.utcms_config.UTCMS_CAPTCHA_VALUE", ""), \
             patch("app.automation.auth.utcms_config.CAPTCHA_AUTO_ONLY", False), \
             patch("app.automation.auth.utcms_config.CAPTCHA_MODE", "manual_only"), \
             patch("app.automation.auth.utcms_config.UTCMS_ENABLE_MANUAL_CAPTCHA", True), \
             patch("app.automation.auth.utcms_config.HEADLESS", True):
            success = await self.auth.login("user", "pass")

        self.assertFalse(success)
        self.assertIn("HEADLESS", self.auth.last_error or "")

    async def test_login_provider_only_fails_without_solver_result(self):
        self.auth._candidate_login_urls = lambda: ["https://barname.utcms.ir/Login"]

        async def find_selector(selectors, visible=False, timeout=1000):
            if selectors is AuthSelectors.USERNAME_SELECTORS:
                return "input[name='Username']"
            if selectors is AuthSelectors.PASSWORD_SELECTORS:
                return "input[name='Password']"
            if selectors is AuthSelectors.SUBMIT_SELECTORS:
                return "button[type='submit']"
            if selectors is AuthSelectors.CAPTCHA_SELECTORS:
                return "input[name='DNTCaptchaInputText']"
            return None

        self.auth._find_selector = AsyncMock(side_effect=find_selector)
        self.auth._solve_captcha_with_provider = AsyncMock(return_value=None)

        with patch("app.automation.auth.utcms_config.UTCMS_CAPTCHA_VALUE", ""), \
             patch("app.automation.auth.utcms_config.CAPTCHA_MODE", "provider_only"), \
             patch("app.automation.auth.utcms_config.UTCMS_ENABLE_MANUAL_CAPTCHA", True):
            success = await self.auth.login("user", "pass")

        self.assertFalse(success)
        self.assertIn("حل خودکار", self.auth.last_error or "")

    async def test_login_surfaces_dns_navigation_failures(self):
        self.auth._candidate_login_urls = lambda: ["https://barname.utcms.ir/Barname/Account/Login"]
        self.auth._goto_with_retry = AsyncMock(side_effect=Exception("net::ERR_NAME_NOT_RESOLVED"))

        success = await self.auth.login("user", "pass")

        self.assertFalse(success)
        self.assertIn("resolve", self.auth.last_error or "")
        self.assertIn("UTCMS", self.auth.last_error or "")

    async def test_login_manual_only_requires_manual_enabled(self):
        self.auth._candidate_login_urls = lambda: ["https://barname.utcms.ir/Login"]

        async def find_selector(selectors, visible=False, timeout=1000):
            if selectors is AuthSelectors.USERNAME_SELECTORS:
                return "input[name='Username']"
            if selectors is AuthSelectors.PASSWORD_SELECTORS:
                return "input[name='Password']"
            if selectors is AuthSelectors.SUBMIT_SELECTORS:
                return "button[type='submit']"
            if selectors is AuthSelectors.CAPTCHA_SELECTORS:
                return "input[name='DNTCaptchaInputText']"
            return None

        self.auth._find_selector = AsyncMock(side_effect=find_selector)

        with patch("app.automation.auth.utcms_config.UTCMS_CAPTCHA_VALUE", ""), \
             patch("app.automation.auth.utcms_config.CAPTCHA_AUTO_ONLY", False), \
             patch("app.automation.auth.utcms_config.CAPTCHA_MODE", "manual_only"), \
             patch("app.automation.auth.utcms_config.UTCMS_ENABLE_MANUAL_CAPTCHA", False):
            success = await self.auth.login("user", "pass")

        self.assertFalse(success)
        self.assertIn("manual_only", self.auth.last_error or "")

    async def test_normalize_captcha_solution_with_persian_digits(self):
        with patch("app.automation.auth.utcms_config.CAPTCHA_VALUE_MIN_LENGTH", 1), \
             patch("app.automation.auth.utcms_config.CAPTCHA_VALUE_MAX_LENGTH", 6):
            normalized = self.auth._normalize_captcha_solution(" ۱۲۳۴ ")
        self.assertEqual(normalized, "1234")

    async def test_normalize_captcha_solution_rejects_non_numeric(self):
        with patch("app.automation.auth.utcms_config.CAPTCHA_VALUE_MIN_LENGTH", 1), \
             patch("app.automation.auth.utcms_config.CAPTCHA_VALUE_MAX_LENGTH", 6):
            normalized = self.auth._normalize_captcha_solution("abc")
        self.assertIsNone(normalized)

    async def test_handle_captcha_auto_only_retries_provider_and_succeeds(self):
        with patch("app.automation.auth.utcms_config.CAPTCHA_AUTO_ONLY", True), \
             patch("app.automation.auth.utcms_config.CAPTCHA_AUTO_MAX_ATTEMPTS", 3), \
             patch("app.automation.auth.utcms_config.CAPTCHA_AUTO_REFRESH_ON_RETRY", True), \
             patch("app.automation.auth.utcms_config.CAPTCHA_MODE", "provider_first"):
            self.auth._solve_math_captcha = AsyncMock(return_value=None)
            self.auth._solve_captcha_with_provider = AsyncMock(side_effect=[None, "7241"])
            self.auth._refresh_captcha = AsyncMock(return_value=True)

            solved = await self.auth._handle_captcha("input[name='DNTCaptchaInputText']")

        self.assertTrue(solved)
        self.auth._refresh_captcha.assert_awaited()

    async def test_handle_captcha_prefers_cnn_provider_before_math_solver(self):
        with patch("app.automation.auth.utcms_config.CAPTCHA_AUTO_ONLY", True), \
             patch("app.automation.auth.utcms_config.CAPTCHA_MODE", "provider_only"):
            self.auth._solve_captcha_with_provider = AsyncMock(return_value="7241")
            self.auth._solve_math_captcha = AsyncMock(return_value="12")

            solved = await self.auth._handle_captcha("input[name='DNTCaptchaInputText']")

        self.assertTrue(solved)
        self.auth._solve_captcha_with_provider.assert_awaited_once()
        self.auth._solve_math_captcha.assert_not_awaited()

    async def test_login_auto_only_retries_submit_on_captcha_error(self):
        self.auth._candidate_login_urls = lambda: ["https://barname.utcms.ir/Login"]

        async def find_selector(selectors, visible=False, timeout=1000):
            if selectors is AuthSelectors.USERNAME_SELECTORS:
                return "input[name='Username']"
            if selectors is AuthSelectors.PASSWORD_SELECTORS:
                return "input[name='Password']"
            if selectors is AuthSelectors.SUBMIT_SELECTORS:
                return "button[type='submit']"
            if selectors is AuthSelectors.CAPTCHA_SELECTORS:
                return "input[name='DNTCaptchaInputText']"
            return None

        self.auth._find_selector = AsyncMock(side_effect=find_selector)
        self.auth._fill_credentials = AsyncMock(return_value=True)
        self.auth._refresh_captcha = AsyncMock(return_value=True)
        self.auth._handle_captcha = AsyncMock(side_effect=[True, True])

        async def submit_side_effect(_selector):
            if not hasattr(self.auth, "_submit_seen"):
                self.auth._submit_seen = True
                self.auth.last_error = "captcha invalid"
                return False
            return True

        self.auth._submit_login = AsyncMock(side_effect=submit_side_effect)

        with patch("app.automation.auth.utcms_config.CAPTCHA_AUTO_ONLY", True), \
             patch("app.automation.auth.utcms_config.CAPTCHA_AUTO_MAX_ATTEMPTS", 3):
            success = await self.auth.login("user", "pass")

        self.assertTrue(success)
        self.assertEqual(self.auth._submit_login.await_count, 2)
        self.auth._refresh_captcha.assert_awaited_once()

    async def test_wait_for_login_result_accepts_non_login_page(self):
        self.page.url = "https://barname.utcms.ir/Barname/Notification"
        self.auth._find_selector = AsyncMock(return_value=None)
        self.auth._looks_like_login_page = AsyncMock(return_value=False)
        self.auth._has_auth_cookie = AsyncMock(return_value=False)
        self.auth._extract_login_error = AsyncMock(return_value=None)

        success = await self.auth._wait_for_login_result(timeout_ms=50)

        self.assertTrue(success)

    async def test_is_logged_in_false_on_login_page(self):
        self.page.url = "https://barname.utcms.ir/Login"
        self.auth._looks_like_login_page = AsyncMock(return_value=True)
        self.auth._find_selector = AsyncMock(return_value=None)
        self.auth._has_auth_cookie = AsyncMock(return_value=False)

        result = await self.auth._is_logged_in()

        self.assertFalse(result)

    async def test_is_logged_in_true_on_waybill_markers(self):
        self.page.url = "https://barname.utcms.ir/Barname/Waybill/Create"
        self.auth._looks_like_login_page = AsyncMock(return_value=False)
        self.auth._looks_like_error_page = AsyncMock(return_value=False)
        self.auth._find_selector = AsyncMock(return_value=None)
        self.auth._has_auth_cookie = AsyncMock(return_value=False)
        self.page.query_selector = AsyncMock(
            side_effect=[object(), None, None, None, None]
        )

        result = await self.auth._is_logged_in()

        self.assertTrue(result)

    async def test_is_logged_in_false_on_error_page_without_login_form(self):
        self.page.url = "https://barname.utcms.ir/barname/Document/HagigiHogugi"
        self.auth._looks_like_login_page = AsyncMock(return_value=False)
        self.auth._looks_like_error_page = AsyncMock(return_value=True)
        self.auth._find_selector = AsyncMock(return_value=None)
        self.auth._has_auth_cookie = AsyncMock(return_value=True)
        self.page.query_selector = AsyncMock(return_value=None)

        result = await self.auth._is_logged_in()

        self.assertFalse(result)
        self.assertIn("خطای سامانه", self.auth.last_error or "")

    async def test_solve_math_captcha_rejects_low_confidence(self):
        self.auth._extract_math_captcha_hints = AsyncMock(return_value=["8 + 2"])

        low_confidence = Mock(value="10", confidence=0.2, strategy="direct_expression")
        with patch("app.automation.auth.utcms_config.CAPTCHA_MATH_MIN_CONFIDENCE", 0.7), \
             patch("app.automation.auth.captcha_engine.solve_text_with_confidence", return_value=low_confidence):
            solved = await self.auth._solve_math_captcha()

        self.assertIsNone(solved)

    async def test_solve_math_captcha_accepts_high_confidence(self):
        self.auth._extract_math_captcha_hints = AsyncMock(return_value=["8 + 2"])

        high_confidence = Mock(value="10", confidence=0.9, strategy="direct_expression")
        with patch("app.automation.auth.utcms_config.CAPTCHA_MATH_MIN_CONFIDENCE", 0.7), \
             patch("app.automation.auth.captcha_engine.solve_text_with_confidence", return_value=high_confidence):
            solved = await self.auth._solve_math_captcha()

        self.assertEqual(solved, "10")

    async def test_detect_and_solve_checkbox_captcha_turnstile(self):
        mock_iframe = AsyncMock()
        mock_iframe.bounding_box = AsyncMock(return_value={"x": 100, "y": 200, "width": 300, "height": 80})
        self.page.query_selector = AsyncMock(return_value=mock_iframe)
        self.page.mouse = AsyncMock()

        result = await self.auth._detect_and_solve_checkbox_captcha()

        self.assertTrue(result)
        self.page.query_selector.assert_called_with('iframe[src*="challenges.cloudflare.com"]')
        self.page.mouse.click.assert_called()

    async def test_detect_and_solve_checkbox_captcha_google_recaptcha(self):
        def query_selector_side_effect(selector):
            if "challenges.cloudflare.com" in selector:
                return None
            if "recaptcha" in selector:
                return AsyncMock()
            return None
        self.page.query_selector = AsyncMock(side_effect=query_selector_side_effect)

        mock_locator = AsyncMock()
        mock_locator.count = AsyncMock(return_value=1)
        mock_locator.click = AsyncMock()

        mock_frame = MagicMock()
        mock_frame.locator = MagicMock(return_value=mock_locator)
        self.page.frame_locator = MagicMock(return_value=mock_frame)

        result = await self.auth._detect_and_solve_checkbox_captcha()

        self.assertTrue(result)
        self.page.frame_locator.assert_called_with('iframe[src*="recaptcha"], iframe[src*="google.com/recaptcha"]')
        mock_locator.click.assert_awaited_once()

    async def test_detect_and_solve_checkbox_captcha_hcaptcha(self):
        def query_selector_side_effect(selector):
            if "challenges.cloudflare.com" in selector or "recaptcha" in selector:
                return None
            if "hcaptcha" in selector:
                return AsyncMock()
            return None
        self.page.query_selector = AsyncMock(side_effect=query_selector_side_effect)

        mock_locator = AsyncMock()
        mock_locator.count = AsyncMock(return_value=1)
        mock_locator.click = AsyncMock()

        mock_frame = MagicMock()
        mock_frame.locator = MagicMock(return_value=mock_locator)
        self.page.frame_locator = MagicMock(return_value=mock_frame)

        result = await self.auth._detect_and_solve_checkbox_captcha()

        self.assertTrue(result)
        self.page.frame_locator.assert_called_with('iframe[src*="hcaptcha"]')
        mock_locator.click.assert_awaited_once()

    async def test_detect_and_solve_checkbox_captcha_custom_selector(self):
        self.page.query_selector = AsyncMock(return_value=None)
        self.page.evaluate = AsyncMock(return_value={"selector": "#my-checkbox", "clickText": False})
        self.page.click = AsyncMock()

        result = await self.auth._detect_and_solve_checkbox_captcha()

        self.assertTrue(result)
        self.page.click.assert_called_with("#my-checkbox")

    async def test_detect_and_solve_checkbox_captcha_custom_text(self):
        self.page.query_selector = AsyncMock(return_value=None)
        self.page.evaluate = AsyncMock(return_value={"selector": None, "clickText": "من ربات نیستم"})

        mock_locator = MagicMock()
        mock_first = AsyncMock()
        mock_locator.first = mock_first
        self.page.locator = MagicMock(return_value=mock_locator)

        result = await self.auth._detect_and_solve_checkbox_captcha()

        self.assertTrue(result)
        self.page.locator.assert_called_with("text=من ربات نیستم")
        mock_first.click.assert_awaited_once()

    async def test_solve_capjs_captcha_success(self):
        mock_locator = AsyncMock()
        mock_locator.count = AsyncMock(return_value=1)
        mock_locator.first = AsyncMock()
        self.page.locator = MagicMock(return_value=mock_locator)

        # evaluate side effect: solve() first, then token value
        self.page.evaluate = AsyncMock(side_effect=[
            None,
            "mock-token-xyz"
        ])

        result = await self.auth._solve_capjs_captcha()
        self.assertTrue(result)
        mock_locator.first.click.assert_awaited_once()

    async def test_solve_capjs_captcha_timeout(self):
        mock_locator = AsyncMock()
        mock_locator.count = AsyncMock(return_value=1)
        mock_locator.first = AsyncMock()
        self.page.locator = MagicMock(return_value=mock_locator)

        # evaluate always returns None for token
        self.page.evaluate = AsyncMock(return_value=None)

        with patch("app.automation.auth.asyncio.sleep", AsyncMock()):
            result = await self.auth._solve_capjs_captcha()

        self.assertFalse(result)
        self.assertIn("Timeout", self.auth.last_error)


if __name__ == "__main__":
    unittest.main()
