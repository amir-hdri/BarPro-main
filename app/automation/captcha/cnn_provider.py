import asyncio
import logging

from app.automation.captcha.barname_ml_solver import barname_ml_solver
from app.automation.captcha.base import CaptchaProvider, CaptchaResult

logger = logging.getLogger(__name__)


class CnnCaptchaProvider(CaptchaProvider):
    async def solve_text_captcha(self, image_base64: str) -> CaptchaResult:
        if not image_base64 or not str(image_base64).strip():
            return CaptchaResult(solved=False, provider="cnn", error="missing_image")

        candidate = await asyncio.to_thread(barname_ml_solver.solve_base64, image_base64)
        if candidate is None:
            return CaptchaResult(solved=False, provider="cnn", error="cnn_unsolved")

        meta = {
            "expression": candidate.expression,
            "answer": candidate.answer,
            "confidence": float(candidate.confidence),
            "characters": list(candidate.characters),
        }
        logger.info(
            "cnn_prediction expression=%r answer=%r confidence=%.3f",
            candidate.expression,
            candidate.answer,
            candidate.confidence,
        )
        return CaptchaResult(
            solved=True,
            provider="cnn",
            value=candidate.answer,
            meta=meta,
        )
