from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.automation.captcha.advanced_preprocessor import AdvancedPreprocessor
from app.automation.captcha.advanced_segmentation import AdvancedSegmentation

try:
    import torch
    import torch.nn as nn
except Exception:  # pragma: no cover
    torch = None
    nn = None


MODEL_PATH = Path(__file__).with_name("assets") / "captcha_cnn.pth"
SUPPORTED_CLASSES = tuple(str(value) for value in range(10)) + ("plus",)
VALUE_MAP = {str(value): value for value in range(10)}
_DIGIT_TRANSLATION = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_PLUS_ALIASES = {"plus", "+", "＋", "add", "sum", "جمع"}


@dataclass(frozen=True)
class MlMathCaptchaCandidate:
    expression: str
    answer: str
    confidence: float
    characters: tuple[str, ...]
    confidences: tuple[float, ...]


def _normalize_class_name(class_name: object) -> str:
    normalized = str(class_name).strip()
    if not normalized:
        return ""
    lowered = normalized.lower()
    if lowered in _PLUS_ALIASES:
        return "plus"
    ascii_digits = lowered.translate(_DIGIT_TRANSLATION)
    if len(ascii_digits) == 1 and ascii_digits in VALUE_MAP:
        return ascii_digits
    return lowered


def _pad_and_resize(roi: np.ndarray, target_size: int = 28) -> np.ndarray:
    height, width = roi.shape[:2]
    max_dim = max(height, width)
    pad_top = (max_dim - height) // 2
    pad_bottom = max_dim - height - pad_top
    pad_left = (max_dim - width) // 2
    pad_right = max_dim - width - pad_left
    padded = cv2.copyMakeBorder(
        roi,
        pad_top,
        pad_bottom,
        pad_left,
        pad_right,
        cv2.BORDER_CONSTANT,
        value=0,
    )
    return cv2.resize(padded, (target_size, target_size), interpolation=cv2.INTER_AREA)


def _normalize_character(image: np.ndarray, target_size: int = 28) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    points = cv2.findNonZero(binary)
    if points is None:
        return cv2.resize(gray, (target_size, target_size), interpolation=cv2.INTER_AREA)

    x, y, width, height = cv2.boundingRect(points)
    roi = binary[y : y + height, x : x + width]
    return _pad_and_resize(roi, target_size=target_size)


class _SimpleCNN(nn.Module):
    def __init__(self, num_classes: int):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(1, 32, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(32, 64, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(64 * 7 * 7, 128),
            nn.ReLU(),
            nn.Dropout(0.5),
            nn.Linear(128, num_classes),
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        features = self.features(inputs)
        return self.classifier(features)


class BarnameMlCaptchaSolver:
    def __init__(self, model_path: Path | None = None) -> None:
        self.model_path = Path(model_path or MODEL_PATH)
        self._loaded = False
        self._available = False
        self._classes: list[str] = []
        self._device = None
        self._model = None

    @property
    def available(self) -> bool:
        self._ensure_loaded()
        return self._available

    def warmup(self) -> bool:
        self._ensure_loaded()
        return self._available

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if torch is None or nn is None or not self.model_path.exists():
            self._available = False
            return

        self._device = (
            torch.device("mps")
            if torch.backends.mps.is_available()
            else torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
        )
        try:
            checkpoint = torch.load(self.model_path, map_location=self._device)
        except Exception:
            self._available = False
            return

        if isinstance(checkpoint, dict) and "model_state" in checkpoint:
            state_dict = checkpoint["model_state"]
            classes = list(checkpoint.get("classes", SUPPORTED_CLASSES))
        else:
            self._available = False
            return

        output_keys = [key for key in state_dict if key.endswith("weight") and key.startswith("classifier.")]
        if not output_keys:
            self._available = False
            return
        num_classes = state_dict[sorted(output_keys)[-1]].shape[0]
        if len(classes) != num_classes:
            if num_classes > len(SUPPORTED_CLASSES):
                self._available = False
                return
            classes = list(SUPPORTED_CLASSES[:num_classes])

        normalized_classes = [_normalize_class_name(class_name) for class_name in classes]
        if len(normalized_classes) != num_classes:
            self._available = False
            return

        model = _SimpleCNN(num_classes).to(self._device)
        try:
            model.load_state_dict(state_dict)
        except Exception:
            self._available = False
            return
        model.eval()

        self._classes = normalized_classes
        self._model = model
        self._available = True

    def _segment(self, image: np.ndarray) -> list[np.ndarray]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        binary = cv2.morphologyEx(
            binary,
            cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2)),
        )

        height, width = binary.shape[:2]
        count, _, stats, _ = cv2.connectedComponentsWithStats(binary)
        components: list[tuple[int, np.ndarray]] = []
        for index in range(1, count):
            x, y, comp_width, comp_height, area = stats[index]
            if comp_height > height * 0.85 or comp_width > width * 0.85:
                continue
            if comp_height < 10 or comp_width < 5 or area < 100:
                continue
            aspect_ratio = comp_width / comp_height if comp_height else 0
            if aspect_ratio > 4.0 or aspect_ratio < 0.15:
                continue
            roi = binary[y : y + comp_height, x : x + comp_width]
            components.append((x, _pad_and_resize(roi)))

        components.sort(key=lambda item: item[0])
        if len(components) > 3:
            components = sorted(components, key=lambda item: int(np.count_nonzero(item[1])), reverse=True)[:3]
            components.sort(key=lambda item: item[0])
        return [roi for _, roi in components]

    def _segment_variants(self, image: np.ndarray) -> list[list[np.ndarray]]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
        candidates: list[list[np.ndarray]] = []

        basic = self._segment(gray)
        if basic:
            candidates.append(basic)

        for enhanced in AdvancedPreprocessor.enhance_image(gray):
            for binary in AdvancedPreprocessor.binarize_advanced(enhanced):
                cleaned = AdvancedPreprocessor.morphological_cleanup(binary)
                segmented = AdvancedSegmentation.segment_characters(cleaned)
                if segmented:
                    candidates.append(segmented)

        unique: list[list[np.ndarray]] = []
        seen: set[tuple[tuple[int, int], ...]] = set()
        for candidate in candidates:
            normalized = self._normalize_candidate_length(candidate)
            if not normalized:
                continue
            signature = tuple(bitmap.shape for bitmap in normalized)
            if signature in seen:
                continue
            seen.add(signature)
            unique.append(normalized)
        return unique

    @staticmethod
    def _normalize_candidate_length(symbols: list[np.ndarray]) -> list[np.ndarray]:
        if len(symbols) == 3:
            return symbols
        if len(symbols) < 3:
            return []

        windows: list[list[np.ndarray]] = []
        for start in range(0, len(symbols) - 2):
            windows.append(symbols[start : start + 3])
        if not windows:
            return []
        return max(windows, key=lambda triplet: sum(int(np.count_nonzero(item)) for item in triplet))

    def _predict_scores(self, image: np.ndarray) -> dict[str, float]:
        self._ensure_loaded()
        if not self._available or self._model is None:
            return {}

        normalized = _normalize_character(image, 28)
        tensor = torch.from_numpy(normalized).float().div(255.0).unsqueeze(0).unsqueeze(0).to(self._device)
        with torch.no_grad():
            logits = self._model(tensor)
            probabilities = torch.softmax(logits, dim=1)[0]

        scores: dict[str, float] = {}
        for index, class_name in enumerate(self._classes):
            normalized_name = _normalize_class_name(class_name)
            if not normalized_name:
                continue
            scores[normalized_name] = max(float(probabilities[index]), scores.get(normalized_name, 0.0))
        return scores

    def _predict_with_constraints(
        self, image: np.ndarray, allowed_classes: tuple[str, ...] | None
    ) -> tuple[str, float]:
        scores = self._predict_scores(image)
        if not scores:
            return "", 0.0
        if allowed_classes:
            scores = {label: score for label, score in scores.items() if label in allowed_classes}
        if not scores:
            return "", 0.0
        label = max(scores, key=scores.get)
        return label, float(scores[label])

    def solve_image(self, image: np.ndarray) -> MlMathCaptchaCandidate | None:
        self._ensure_loaded()
        if not self._available:
            return None

        best_candidate: MlMathCaptchaCandidate | None = None
        allowed_by_position = (tuple(VALUE_MAP.keys()), ("plus",), tuple(VALUE_MAP.keys()))

        for symbols in self._segment_variants(image):
            if len(symbols) != 3:
                continue

            labels: list[str] = []
            confidences: list[float] = []
            for index, symbol in enumerate(symbols):
                label, confidence = self._predict_with_constraints(symbol, allowed_by_position[index])
                if not label:
                    labels = []
                    break
                labels.append(label)
                confidences.append(confidence)

            if len(labels) != 3:
                continue
            if labels[1] != "plus" or labels[0] not in VALUE_MAP or labels[2] not in VALUE_MAP:
                continue

            candidate = MlMathCaptchaCandidate(
                expression="".join("+" if label == "plus" else label for label in labels),
                answer=str(VALUE_MAP[labels[0]] + VALUE_MAP[labels[2]]),
                confidence=float(sum(confidences) / len(confidences)),
                characters=tuple(labels),
                confidences=tuple(confidences),
            )
            if best_candidate is None or candidate.confidence > best_candidate.confidence:
                best_candidate = candidate

        return best_candidate

    def solve_base64(self, image_base64: str) -> MlMathCaptchaCandidate | None:
        if not image_base64 or not str(image_base64).strip():
            return None
        try:
            image_bytes = base64.b64decode(image_base64, validate=True)
        except (ValueError, binascii.Error):
            return None
        buffer = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(buffer, cv2.IMREAD_GRAYSCALE)
        if image is None or image.size == 0:
            return None
        return self.solve_image(image)


barname_ml_solver = BarnameMlCaptchaSolver()
