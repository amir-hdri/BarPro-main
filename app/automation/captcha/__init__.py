import asyncio
from threading import Lock
from typing import Optional

from app.automation.captcha.barname_ml_solver import BarnameMlCaptchaSolver, barname_ml_solver
from app.automation.captcha.base import CaptchaProvider, CaptchaResult
from app.automation.captcha.cnn_provider import CnnCaptchaProvider
from app.automation.captcha.dnt_captcha_solver import DntCaptchaProvider
from app.automation.captcha.engine import CaptchaEngine, captcha_engine
from app.automation.captcha.enhanced_ocr import EnhancedOcrProvider
from app.automation.captcha.fuel_captcha_solver import PyTorchFuelCaptchaProvider
from app.automation.captcha.keras_ocr import KerasOcrCaptchaProvider
from app.automation.captcha.local_ocr import LocalOcrCaptchaProvider
from app.core.config import utcms_config

_provider_lock = Lock()
_cached_provider: CaptchaProvider | None = None
_cached_signature: tuple | None = None


def _close_provider_async(provider: CaptchaProvider | None) -> None:
    if not provider:
        return
    close = getattr(provider, "aclose", None)
    if not callable(close):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(close())


class CompositeCaptchaProvider(CaptchaProvider):
    def __init__(self, providers: list[CaptchaProvider]) -> None:
        self.providers = providers

    async def solve_text_captcha(self, image_base64: str) -> CaptchaResult:
        last_result = CaptchaResult(solved=False, provider="composite", error="no_provider")
        for provider in self.providers:
            result = await provider.solve_text_captcha(image_base64)
            if result.solved and result.value:
                return result
            last_result = result
        return last_result


def _build_provider(provider_name: str) -> CaptchaProvider | None:
    if provider_name == "dnt_crnn":
        return DntCaptchaProvider()
    if provider_name == "keras_ocr":
        return KerasOcrCaptchaProvider()
    if provider_name == "pytorch_fuel":
        return PyTorchFuelCaptchaProvider()
    if provider_name == "cnn":
        return CnnCaptchaProvider()
    if provider_name == "local_ocr":
        return LocalOcrCaptchaProvider()
    if provider_name == "enhanced_ocr":
        return EnhancedOcrProvider()
    if provider_name in ("auto", "ensemble", "composite"):
        return CompositeCaptchaProvider(
            [
                DntCaptchaProvider(),
                CnnCaptchaProvider(),
                PyTorchFuelCaptchaProvider(),
                KerasOcrCaptchaProvider(),
                EnhancedOcrProvider(),
                LocalOcrCaptchaProvider(),
            ]
        )
    return None


def get_captcha_provider() -> CaptchaProvider | None:
    global _cached_provider, _cached_signature
    provider = utcms_config.CAPTCHA_PROVIDER
    if provider in ("off", "none", "disabled", ""):
        with _provider_lock:
            previous = _cached_provider
            _cached_provider = None
            _cached_signature = None
        _close_provider_async(previous)
        return None

    signature = (provider, str(barname_ml_solver.model_path), barname_ml_solver.available)
    with _provider_lock:
        if _cached_provider is not None and _cached_signature == signature:
            return _cached_provider

        previous = _cached_provider
        _cached_provider = _build_provider(provider)
        _cached_signature = signature

    _close_provider_async(previous)
    return _cached_provider


__all__ = [
    "CaptchaProvider",
    "BarnameMlCaptchaSolver",
    "CnnCaptchaProvider",
    "CompositeCaptchaProvider",
    "CaptchaEngine",
    "EnhancedOcrProvider",
    "LocalOcrCaptchaProvider",
    "KerasOcrCaptchaProvider",
    "get_captcha_provider",
    "barname_ml_solver",
    "captcha_engine",
]
