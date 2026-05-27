import asyncio
import base64
import binascii
import logging

import cv2
import numpy as np

from app.automation.captcha.base import CaptchaProvider, CaptchaResult
from app.automation.captcha.engine import captcha_engine
from app.automation.captcha.neural_net import _IMG_SIZE, predict_chars_batch

logger = logging.getLogger(__name__)


class LocalOcrCaptchaProvider(CaptchaProvider):

    def __init__(
        self,
        min_char_score: float = 0.35,
        min_expression_score: float = 0.45,
    ) -> None:
        self.min_char_score = float(min_char_score)
        self.min_expression_score = float(min_expression_score)

    async def solve_text_captcha(self, image_base64: str) -> CaptchaResult:
        if not image_base64 or not str(image_base64).strip():
            return CaptchaResult(solved=False, provider="local_ocr", error="missing_image")

        return await asyncio.to_thread(self._solve_sync, image_base64)

    def _solve_sync(self, image_base64: str) -> CaptchaResult:
        image = self._decode_image(image_base64)
        if image is None:
            return CaptchaResult(solved=False, provider="local_ocr", error="invalid_image")

        best_text: str | None = None
        best_score = -1.0
        best_answer: str | None = None

        for binary_variant in self._binarize_variants(image):
            for components in self._segment_variants(binary_variant):
                if len(components) < 1:
                    continue
                predictions = predict_chars_batch(components)
                if not predictions:
                    continue

                text = "".join(char for char, _ in predictions).strip()
                if not text:
                    continue

                if len(predictions) < 2:
                    continue

                avg_conf = sum(conf for _, conf in predictions) / len(predictions)
                min_conf = min(conf for _, conf in predictions)

                if min_conf < self.min_char_score:
                    continue

                score = avg_conf * 0.7 + min_conf * 0.3

                if self._looks_like_math_expression(text):
                    decision = captcha_engine.solve_text_with_confidence(text)
                    if decision.value:
                        boost = min(0.35, max(0.0, float(decision.confidence)) * 0.35)
                        score += boost
                        if score > best_score:
                            best_score = score
                            best_text = text
                            best_answer = decision.value
                elif text.replace(" ", "").isdigit():
                    if score > best_score:
                        best_score = score
                        best_text = text
                        best_answer = text.replace(" ", "")

        if not best_text or not best_answer:
            return CaptchaResult(solved=False, provider="local_ocr", error="ocr_unsolved")

        if best_score < self.min_expression_score:
            return CaptchaResult(
                solved=False,
                provider="local_ocr",
                value=best_answer,
                error="low_confidence",
            )

        return CaptchaResult(
            solved=True,
            provider="local_ocr",
            value=best_answer,
        )

    @staticmethod
    def _decode_image(image_base64: str) -> np.ndarray | None:
        try:
            image_bytes = base64.b64decode(image_base64, validate=True)
        except (ValueError, binascii.Error):
            return None

        buffer = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(buffer, cv2.IMREAD_GRAYSCALE)
        if image is None or image.size == 0:
            return None
        return image

    @classmethod
    def _binarize_variants(cls, image: np.ndarray) -> list[np.ndarray]:
        results = []
        for scale in (2, 3, 4):
            enlarged = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            blurred = cv2.GaussianBlur(enlarged, (3, 3), 0)

            _, fixed = cv2.threshold(blurred, 200, 255, cv2.THRESH_BINARY_INV)
            _, otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            adaptive = cv2.adaptiveThreshold(
                enlarged, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV, 31, 11,
            )
            adaptive2 = cv2.adaptiveThreshold(
                enlarged, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                cv2.THRESH_BINARY_INV, 21, 8,
            )

            for variant in (fixed, otsu, adaptive, adaptive2):
                results.append(cls._cleanup_binary(variant))

        return results

    @staticmethod
    def _cleanup_binary(binary: np.ndarray) -> np.ndarray:
        kernel = np.ones((2, 2), dtype=np.uint8)
        cleaned = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        return cleaned

    @classmethod
    def _segment_variants(cls, binary: np.ndarray) -> list[list[np.ndarray]]:
        results = []
        min_areas = [12, 18, 30, 50]
        for min_area_mult in min_areas:
            components = cls._segment_components(binary, min_area_multiplier=min_area_mult)
            if components and len(components) >= 2:
                results.append(components)
        if not results:
            components = cls._segment_components(binary, min_area_multiplier=8)
            if components:
                results.append(components)
        return results

    @classmethod
    def _segment_components(cls, binary: np.ndarray, min_area_multiplier: int = 18) -> list[np.ndarray]:
        num_labels, _labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
        components: list[tuple[int, np.ndarray]] = []
        total_pixels = binary.shape[0] * binary.shape[1]
        min_area = max(min_area_multiplier, int(total_pixels * 0.002))
        max_area = int(total_pixels * 0.5)

        for index in range(1, num_labels):
            x, y, width, height, area = stats[index]
            if area < min_area or area > max_area or width <= 0 or height <= 0:
                continue
            aspect_ratio = width / max(1, height)
            if aspect_ratio > 6 or aspect_ratio < 0.08:
                continue
            roi = binary[y : y + height, x : x + width]
            components.append((x, cls._normalize_bitmap(roi)))

        components.sort(key=lambda item: item[0])
        return [bitmap for _x, bitmap in components]

    @classmethod
    def _normalize_bitmap(cls, bitmap: np.ndarray) -> np.ndarray:
        ys, xs = np.where(bitmap > 0)
        if len(xs) == 0 or len(ys) == 0:
            return np.zeros((_IMG_SIZE, _IMG_SIZE), dtype=np.uint8)

        x1, x2 = xs.min(), xs.max() + 1
        y1, y2 = ys.min(), ys.max() + 1
        roi = bitmap[y1:y2, x1:x2]

        scale = min(
            (_IMG_SIZE - 4) / max(1, roi.shape[1]),
            (_IMG_SIZE - 4) / max(1, roi.shape[0]),
        )
        new_width = max(1, int(round(roi.shape[1] * scale)))
        new_height = max(1, int(round(roi.shape[0] * scale)))
        resized = cv2.resize(
            roi,
            (new_width, new_height),
            interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC,
        )

        canvas = np.zeros((_IMG_SIZE, _IMG_SIZE), dtype=np.uint8)
        offset_x = (_IMG_SIZE - new_width) // 2
        offset_y = (_IMG_SIZE - new_height) // 2
        canvas[offset_y : offset_y + new_height, offset_x : offset_x + new_width] = resized
        return canvas

    @staticmethod
    def _looks_like_math_expression(text: str) -> bool:
        return any(operator in text for operator in ("+", "-", "*", "/", "x", "×"))
