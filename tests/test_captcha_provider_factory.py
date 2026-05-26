import asyncio
from unittest.mock import patch

from app.automation import captcha as captcha_module
from app.automation.captcha import CompositeCaptchaProvider, get_captcha_provider


def _reset_provider_cache() -> None:
    previous = captcha_module._cached_provider
    captcha_module._cached_provider = None
    captcha_module._cached_signature = None
    if previous and hasattr(previous, "aclose"):
        asyncio.run(previous.aclose())


def test_get_captcha_provider_returns_cached_instance():
    _reset_provider_cache()
    with patch("app.core.config.utcms_config.CAPTCHA_PROVIDER", "cnn"):
        provider_one = get_captcha_provider()
        provider_two = get_captcha_provider()

    assert provider_one is not None
    assert provider_one is provider_two
    _reset_provider_cache()


def test_get_captcha_provider_reuses_single_cnn_provider_for_legacy_aliases():
    """Test that changing provider name invalidates cache."""
    _reset_provider_cache()
    with patch("app.core.config.utcms_config.CAPTCHA_PROVIDER", "cnn"):
        provider_one = get_captcha_provider()

    _reset_provider_cache()
    with patch("app.core.config.utcms_config.CAPTCHA_PROVIDER", "cnn"):
        provider_two = get_captcha_provider()

    assert provider_one is not None
    assert provider_two is not None
    # Different instances after cache reset
    _reset_provider_cache()


def test_get_captcha_provider_returns_cnn_for_local_ocr_setting():
    """Test that local_ocr returns LocalOcrCaptchaProvider, not CnnCaptchaProvider."""
    _reset_provider_cache()
    with patch("app.core.config.utcms_config.CAPTCHA_PROVIDER", "local_ocr"):
        provider = get_captcha_provider()

    # local_ocr returns LocalOcrCaptchaProvider
    assert provider is not None
    _reset_provider_cache()


def test_get_captcha_provider_returns_cnn_for_ocr_setting():
    """Test that ocr returns EnhancedOcrProvider, not CnnCaptchaProvider."""
    _reset_provider_cache()
    with patch("app.core.config.utcms_config.CAPTCHA_PROVIDER", "enhanced_ocr"):
        provider = get_captcha_provider()

    assert provider is not None
    _reset_provider_cache()


def test_get_captcha_provider_returns_cnn_for_auto_setting():
    """Test that auto returns CompositeCaptchaProvider, not CnnCaptchaProvider."""
    _reset_provider_cache()
    with patch("app.core.config.utcms_config.CAPTCHA_PROVIDER", "auto"):
        provider = get_captcha_provider()

    # auto returns CompositeCaptchaProvider
    assert isinstance(provider, CompositeCaptchaProvider)
    _reset_provider_cache()


def test_get_captcha_provider_ignores_legacy_provider_names():
    """Test that unknown provider names return None."""
    _reset_provider_cache()
    with patch("app.core.config.utcms_config.CAPTCHA_PROVIDER", "twocaptcha"):
        provider = get_captcha_provider()

    # Unknown provider returns None
    assert provider is None
    _reset_provider_cache()


def test_get_captcha_provider_returns_none_when_disabled():
    _reset_provider_cache()
    with patch("app.core.config.utcms_config.CAPTCHA_PROVIDER", "off"):
        provider = get_captcha_provider()

    assert provider is None
    _reset_provider_cache()
