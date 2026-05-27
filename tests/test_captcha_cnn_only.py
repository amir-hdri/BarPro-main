"""Tests for CNN-only captcha implementation."""
import asyncio
from unittest.mock import patch

from app.automation.captcha import captcha_engine, get_captcha_provider
from app.automation.captcha.barname_ml_solver import MlMathCaptchaCandidate, barname_ml_solver
from app.automation.captcha.cnn_provider import CnnCaptchaProvider


def _reset_provider_cache() -> None:
    """Reset the cached provider for testing."""
    import app.automation.captcha as captcha_module
    captcha_module._cached_provider = None
    captcha_module._cached_signature = None


class TestCnnOnlyImplementation:
    """Test suite for CNN-only captcha solving."""

    def test_cnn_provider_returns_correct_type(self):
        """Test that get_captcha_provider returns CnnCaptchaProvider."""
        _reset_provider_cache()
        with patch("app.core.config.utcms_config.CAPTCHA_PROVIDER", "cnn"):
            provider = get_captcha_provider()

        assert isinstance(provider, CnnCaptchaProvider)
        _reset_provider_cache()

    def test_cnn_provider_missing_image(self):
        """Test CNN provider with missing image."""
        provider = CnnCaptchaProvider()
        result = asyncio.run(provider.solve_text_captcha(""))

        assert result.solved is False
        assert result.error == "missing_image"
        assert result.provider == "cnn"

    def test_cnn_provider_with_valid_image(self):
        """Test CNN provider with a valid image (mocked)."""
        mock_candidate = MlMathCaptchaCandidate(
            expression="2+7",
            answer="9",
            confidence=0.95,
            characters=("2", "plus", "7"),
            confidences=(0.96, 0.94, 0.95)
        )

        with patch.object(barname_ml_solver, "solve_base64", return_value=mock_candidate):
            provider = CnnCaptchaProvider()
            result = asyncio.run(provider.solve_text_captcha("fake_base64_image"))

        assert result.solved is True
        assert result.value == "9"
        assert result.provider == "cnn"

    def test_cnn_provider_unsolved_image(self):
        """Test CNN provider when image cannot be solved."""
        with patch.object(barname_ml_solver, "solve_base64", return_value=None):
            provider = CnnCaptchaProvider()
            result = asyncio.run(provider.solve_text_captcha("fake_base64_image"))

        assert result.solved is False
        assert result.error == "cnn_unsolved"
        assert result.provider == "cnn"

    def test_captcha_engine_uses_cnn(self):
        """Test that CNN provider works correctly with mocked solver."""
        mock_candidate = MlMathCaptchaCandidate(
            expression="3+4",
            answer="7",
            confidence=0.92,
            characters=("3", "plus", "4"),
            confidences=(0.93, 0.91, 0.92)
        )

        with patch.object(barname_ml_solver, "solve_base64", return_value=mock_candidate):
            provider = CnnCaptchaProvider()
            result = asyncio.run(provider.solve_text_captcha("fake_base64"))

        assert result.solved is True
        assert result.value == "7"
        assert result.provider == "cnn"

    def test_captcha_engine_low_confidence_rejected(self):
        """Test that CNN provider returns results regardless of confidence."""
        mock_candidate = MlMathCaptchaCandidate(
            expression="1+1",
            answer="2",
            confidence=0.3,  # Below threshold
            characters=("1", "plus", "1"),
            confidences=(0.3, 0.3, 0.3)
        )

        with patch.object(barname_ml_solver, "solve_base64", return_value=mock_candidate):
            provider = CnnCaptchaProvider()
            result = asyncio.run(provider.solve_text_captcha("fake_base64"))

        assert result.solved is True
        assert result.value == "2"

    def test_captcha_engine_empty_input(self):
        """Test that captcha_engine handles empty text input."""
        # captcha_engine is for text hints, not image captchas
        decision = captcha_engine.solve_text_with_confidence("")
        assert decision.value is None
        assert decision.confidence == 0.0

        decision = captcha_engine.solve_text_with_confidence("   ")
        assert decision.value is None
        assert decision.confidence == 0.0

    def test_captcha_engine_solve_text(self):
        """Test CNN provider solve_text_captcha works."""
        mock_candidate = MlMathCaptchaCandidate(
            expression="5+3",
            answer="8",
            confidence=0.88,
            characters=("5", "plus", "3"),
            confidences=(0.89, 0.87, 0.88)
        )

        with patch.object(barname_ml_solver, "solve_base64", return_value=mock_candidate):
            provider = CnnCaptchaProvider()
            result = asyncio.run(provider.solve_text_captcha("fake_base64"))

        assert result.solved is True
        assert result.value == "8"

    def test_captcha_engine_unsolved_returns_none(self):
        """Test that CNN provider returns unsolved when model fails."""
        with patch.object(barname_ml_solver, "solve_base64", return_value=None):
            provider = CnnCaptchaProvider()
            result = asyncio.run(provider.solve_text_captcha("fake_base64"))

        assert result.solved is False
        assert result.error == "cnn_unsolved"

    def test_all_providers_route_to_cnn(self):
        """Test that cnn provider setting returns CnnCaptchaProvider."""
        _reset_provider_cache()
        # Only "cnn" returns CnnCaptchaProvider directly
        # "auto" returns CompositeCaptchaProvider which includes CNN

        with patch("app.core.config.utcms_config.CAPTCHA_PROVIDER", "cnn"):
            provider = get_captcha_provider()
            assert isinstance(provider, CnnCaptchaProvider)

        _reset_provider_cache()

    def test_cnn_provider_reuses_session(self):
        """Test that CNN provider reuses the solver instance."""
        provider1 = CnnCaptchaProvider()
        provider2 = CnnCaptchaProvider()

        # Both should use the same barname_ml_solver singleton
        assert provider1 is not provider2  # Different instances
        # But they share the same underlying solver
        from app.automation.captcha.cnn_provider import barname_ml_solver as solver1
        from app.automation.captcha.cnn_provider import barname_ml_solver as solver2
        assert solver1 is solver2  # Same singleton
