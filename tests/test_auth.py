"""
Authentication tests for UTCMSAuthenticator.
Converted from unittest to pytest (M-021).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, Mock

from app.automation.auth import UTCMSAuthenticator
from app.automation.auth_utils import normalize_captcha_solution
from app.automation.selectors import AuthSelectors


class _NoopAsyncContext:
    """Async context manager that does nothing."""
    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.fixture
def mock_auth():
    """Create a UTCMSAuthenticator instance with mocked page and context."""
    page = AsyncMock()
    page.locator = Mock()
    page.expect_navigation = Mock(return_value=_NoopAsyncContext())
    context = AsyncMock()
    auth = UTCMSAuthenticator(page, context)
    return auth, page, context


# ============================================================================
# CAPTCHA Normalization Tests
# ============================================================================

@pytest.mark.asyncio
async def test_normalize_captcha_solution_with_persian_digits():
    """Test that Persian digits are converted to Arabic numerals."""
    result = normalize_captcha_solution("۱۲۳۴۵")
    assert result == "12345"


@pytest.mark.asyncio
async def test_normalize_captcha_solution_with_mixed_content():
    """Test normalization of captcha with spaces and special characters."""
    result = normalize_captcha_solution(" ۲ + ۳ = ? ")
    assert result is not None


@pytest.mark.asyncio
async def test_normalize_captcha_solution_returns_none_for_invalid():
    """Test that non-numeric, non-math captcha returns None."""
    result = normalize_captcha_solution("abc")
    assert result is None


@pytest.mark.asyncio
async def test_normalize_captcha_solution_handles_none():
    """Test that None input returns None."""
    result = normalize_captcha_solution(None)
    assert result is None


@pytest.mark.asyncio
async def test_normalize_captcha_solution_empty_string():
    """Test that empty string returns None."""
    result = normalize_captcha_solution("")
    assert result is None


@pytest.mark.asyncio
async def test_normalize_captcha_solution_with_equals():
    """Test that equals sign is removed."""
    result = normalize_captcha_solution("5=5")
    assert result is not None


# ============================================================================
# Login URL Tests
# ============================================================================

@pytest.mark.asyncio
async def test_candidate_login_urls_returns_list():
    """Test that _candidate_login_urls returns a list."""
    page = AsyncMock()
    context = AsyncMock()
    auth = UTCMSAuthenticator(page, context)
    urls = auth._candidate_login_urls()
    assert isinstance(urls, list)
    assert len(urls) > 0


@pytest.mark.asyncio
async def test_candidate_login_urls_includes_primary():
    """Test that primary login URL is in the list."""
    page = AsyncMock()
    context = AsyncMock()
    auth = UTCMSAuthenticator(page, context)
    urls = auth._candidate_login_urls()
    assert any("Login" in url for url in urls)


@pytest.mark.asyncio
async def test_authenticator_initialization():
    """Test that UTCMSAuthenticator initializes correctly."""
    page = AsyncMock()
    context = AsyncMock()
    auth = UTCMSAuthenticator(page, context)
    assert auth.page == page
    assert auth.context == context
    assert auth.last_error is None
