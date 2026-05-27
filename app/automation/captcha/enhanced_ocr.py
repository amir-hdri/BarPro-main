"""
Enhanced OCR with advanced preprocessing and ensemble methods.
"""
import asyncio
import base64
import logging

import cv2
import numpy as np

from app.automation.captcha.advanced_preprocessor import AdvancedPreprocessor
from app.automation.captcha.advanced_segmentation import AdvancedSegmentation
from app.automation.captcha.base import CaptchaProvider, CaptchaResult
from app.automation.captcha.engine import captcha_engine
from app.automation.captcha.ensemble_solver import EnsembleSolver, SolveCandidate
from app.automation.captcha.neural_net import predict_chars_batch
from app.automation.captcha.validator import CaptchaValidator

logger = logging.getLogger(__name__)


class EnhancedOcrProvider(CaptchaProvider):
    """Enhanced OCR with high accuracy."""

    def __init__(self, min_confidence: float = 0.75):
        self.min_confidence = float(min_confidence)
        self.preprocessor = AdvancedPreprocessor()
        self.segmenter = AdvancedSegmentation()
        self.ensemble = EnsembleSolver()
        self.validator = CaptchaValidator()

    async def solve_text_captcha(self, image_base64: str) -> CaptchaResult:
        if not image_base64:
            return CaptchaResult(solved=False, provider="enhanced_ocr", error="missing_image")

        return await asyncio.to_thread(self._solve_sync, image_base64)

    def _solve_sync(self, image_base64: str) -> CaptchaResult:
        image = self._decode_image(image_base64)
        if image is None:
            return CaptchaResult(solved=False, provider="enhanced_ocr", error="invalid_image")

        candidates: list[SolveCandidate] = []

        enhanced_images = self.preprocessor.enhance_image(image)

        for enhanced in enhanced_images:
            binaries = self.preprocessor.binarize_advanced(enhanced)

            for binary in binaries:
                cleaned = self.preprocessor.morphological_cleanup(binary)
                chars = self.segmenter.segment_characters(cleaned)

                if len(chars) < 2:
                    continue

                predictions = predict_chars_batch(chars)
                if not predictions:
                    continue

                text = "".join(c for c, _ in predictions)
                avg_conf = sum(conf for _, conf in predictions) / len(predictions)
                min_conf = min(conf for _, conf in predictions)

                if min_conf < 0.5:
                    continue

                confidence = avg_conf * 0.6 + min_conf * 0.4

                if self._is_math(text):
                    decision = captcha_engine.solve_text_with_confidence(text)
                    if decision.value:
                        boost = decision.confidence * 0.3
                        candidates.append(SolveCandidate(
                            value=decision.value,
                            confidence=confidence + boost,
                            source=f"math_{text}"
                        ))
                elif text.replace(" ", "").replace("-", "").isdigit():
                    candidates.append(SolveCandidate(
                        value=text.replace(" ", ""),
                        confidence=confidence,
                        source="digit"
                    ))

        best = self.ensemble.vote_best_solution(candidates, self.min_confidence)

        if not best or not self.validator.validate_solution(best):
            return CaptchaResult(solved=False, provider="enhanced_ocr", error="no_solution")

        normalized = self.validator.normalize_solution(best)
        return CaptchaResult(solved=True, provider="enhanced_ocr", value=normalized)

    @staticmethod
    def _decode_image(image_base64: str) -> np.ndarray | None:
        try:
            image_bytes = base64.b64decode(image_base64, validate=True)
            buffer = np.frombuffer(image_bytes, dtype=np.uint8)
            image = cv2.imdecode(buffer, cv2.IMREAD_GRAYSCALE)
            return image if image is not None and image.size > 0 else None
        except Exception:
            return None

    @staticmethod
    def _is_math(text: str) -> bool:
        return any(op in text for op in ("+", "-", "*", "/", "×", "÷"))
