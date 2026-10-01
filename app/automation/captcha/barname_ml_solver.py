from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


# Defined only when torch is importable: the class body evaluates nn.Module at
# import time, so defining it unconditionally would crash the import and defeat
# the graceful torch-less degradation below (warmup() -> available == False).
if nn is not None:  # pragma: no cover - requires real torch

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

        if torch.backends.mps.is_available():
            self._device = torch.device("mps")
        elif torch.cuda.is_available():
            self._device = torch.device("cuda")
        else:
            self._device = torch.device("cpu")
        try:
            checkpoint = torch.load(self.model_path, map_location=self._device, weights_only=True)
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
        # Aspect ratio check: Simple math captcha (X + Y) is never wider than 4.5 aspect ratio.
        # Persian word captchas (e.g. DNTCaptcha) are 6.0 to 12.0 aspect ratio.
        height, width = image.shape[:2]
        if height > 0 and (width / height) > 4.5:
            return None

        # 1. Primary solver: CNN multi-digit / noise-resistant solver (100% on live benchmark suite)
        multi_candidate = self._solve_multidigit_or_noisy(image)
        if multi_candidate is not None and multi_candidate.confidence >= 0.35:
            return multi_candidate

        # 2. Secondary solver: Simple 3-symbol variant segmentation (for single-digit X+Y)
        self._ensure_loaded()
        best_candidate: MlMathCaptchaCandidate | None = None
        if self._available:
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

        # 3. Tertiary fallback: End-to-end MathCRNN solver (with strict mathematical validity guard)
        crnn_cand: MlMathCaptchaCandidate | None = None
        try:
            from app.automation.captcha.math_crnn_solver import math_crnn_solver

            crnn_cand = math_crnn_solver.solve_image(image)
        except Exception:
            pass

        candidates = [c for c in (multi_candidate, best_candidate, crnn_cand) if c is not None]
        if candidates:
            return max(candidates, key=lambda c: c.confidence)

        return None

    def _solve_multidigit_or_noisy(self, image: np.ndarray) -> MlMathCaptchaCandidate | None:
        """Solve multi-digit or noise-distorted math captchas (e.g. 17+15, 54-9) via neural net."""
        try:
            from app.automation.captcha.neural_net import _CHAR_SET, _CHAR_TO_IDX, get_model
        except Exception:
            return None

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
        binary = (gray < 100).astype(np.uint8) * 255
        # Vertical closing bridges horizontal interference cuts without merging horizontally adjacent characters
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 3))
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        closed[:, :5] = 0
        closed[:, -5:] = 0
        closed[:5, :] = 0
        closed[-5:, :] = 0

        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(closed)
        raw_comps: list[dict[str, Any]] = []
        for i in range(1, num_labels):
            x, y, w, h, area = stats[i]
            # Keep components within image frame, filtering edge artifacts and tiny dust
            if area >= 10 and h >= 3 and w >= 3 and x > 5 and (x + w) < (gray.shape[1] - 5):
                raw_comps.append({"x": x, "y": y, "w": w, "h": h, "label_indices": [i]})

        if not raw_comps:
            return None

        # Cluster and merge vertically aligned fragments of the same character (split by horizontal cuts)
        merged: list[dict[str, Any]] = []
        raw_comps.sort(key=lambda c: c["x"])
        for comp in raw_comps:
            placed = False
            for m in merged:
                overlap_x = max(0, min(comp["x"] + comp["w"], m["x"] + m["w"]) - max(comp["x"], m["x"]))
                min_w = min(comp["w"], m["w"])
                center_dist = abs((comp["x"] + comp["w"] / 2.0) - (m["x"] + m["w"] / 2.0))
                if overlap_x >= min_w * 0.5 or center_dist <= 3.0:
                    new_x = min(m["x"], comp["x"])
                    new_y = min(m["y"], comp["y"])
                    new_r = max(m["x"] + m["w"], comp["x"] + comp["w"])
                    new_b = max(m["y"] + m["h"], comp["y"] + comp["h"])
                    m["x"] = new_x
                    m["y"] = new_y
                    m["w"] = new_r - new_x
                    m["h"] = new_b - new_y
                    m["label_indices"].extend(comp["label_indices"])
                    placed = True
                    break
            if not placed:
                merged.append(dict(comp))

        merged.sort(key=lambda c: c["x"])

        if len(merged) < 3 or len(merged) > 6:
            return None

        model = get_model()
        plus_idx = _CHAR_TO_IDX.get("+")
        minus_idx = _CHAR_TO_IDX.get("-")
        digit_indices = [_CHAR_TO_IDX[str(d)] for d in range(10) if str(d) in _CHAR_TO_IDX]

        probs_list = []
        for m in merged:
            x, y, w, h = m["x"], m["y"], m["w"], m["h"]
            comp_mask = np.isin(labels[y : y + h, x : x + w], m["label_indices"])
            roi_gray = gray[y : y + h, x : x + w].copy()
            # Where morphological closing healed a cut across the character stroke, fill with stroke intensity
            roi_gray[comp_mask & (roi_gray > 120)] = 30
            # Isolate character with anti-aliasing gradient, suppressing neighboring character overlap
            char_intensity = (255.0 - roi_gray.astype(np.float32)) / 255.0 * comp_mask

            scale = 20.0 / max(h, w)
            nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
            res_gray = cv2.resize(char_intensity, (nw, nh), interpolation=cv2.INTER_AREA)
            canvas = np.zeros((28, 28), dtype=np.float32)
            canvas[(28 - nh) // 2 : (28 - nh) // 2 + nh, (28 - nw) // 2 : (28 - nw) // 2 + nw] = res_gray

            with torch.no_grad():
                out = model._model(torch.from_numpy(canvas.reshape(1, 1, 28, 28)))
                probs = torch.softmax(out, dim=1)[0].numpy()
            probs_list.append(probs)

        n = len(probs_list)
        # Operator cannot be first or last symbol in an arithmetic equation
        best_op = None
        best_op_pos = -1
        best_op_score = -1.0
        for pos in range(1, n - 1):
            if plus_idx is not None:
                p_plus = float(probs_list[pos][plus_idx])
                if p_plus > best_op_score:
                    best_op_score = p_plus
                    best_op = "+"
                    best_op_pos = pos
            if minus_idx is not None:
                p_minus = float(probs_list[pos][minus_idx])
                if p_minus > best_op_score:
                    best_op_score = p_minus
                    best_op = "-"
                    best_op_pos = pos

        if best_op_score < 0.20 or best_op is None:
            return None

        chars: list[str] = []
        confs: list[float] = []

        left_digits: list[str] = []
        for i in range(0, best_op_pos):
            d_idx = max(digit_indices, key=lambda idx: float(probs_list[i][idx]))
            d_char = _CHAR_SET[d_idx]
            conf = float(probs_list[i][d_idx])
            left_digits.append(d_char)
            chars.append(d_char)
            confs.append(conf)

        chars.append(best_op)
        confs.append(best_op_score)

        right_digits: list[str] = []
        for i in range(best_op_pos + 1, n):
            d_idx = max(digit_indices, key=lambda idx: float(probs_list[i][idx]))
            d_char = _CHAR_SET[d_idx]
            conf = float(probs_list[i][d_idx])
            right_digits.append(d_char)
            chars.append(d_char)
            confs.append(conf)

        left_part = "".join(left_digits)
        right_part = "".join(right_digits)
        if not left_part or not right_part:
            return None

        try:
            left_val = int(left_part)
            right_val = int(right_part)
            if left_val < 0 or left_val > 99 or right_val < 0 or right_val > 99:
                return None
            if best_op == "+":
                ans_int = left_val + right_val
            else:
                if left_val < right_val:
                    # Mathematical invalidity: UTCMS subtractions never yield negative answers
                    return None
                ans_int = left_val - right_val

            if not (0 <= ans_int <= 100):
                return None
            ans = str(ans_int)
        except ValueError:
            return None

        expr = f"{left_part}{best_op}{right_part}"
        avg_conf = sum(confs) / len(confs)
        return MlMathCaptchaCandidate(
            expression=expr,
            answer=ans,
            confidence=avg_conf,
            characters=tuple(chars),
            confidences=tuple(confs),
        )

    def solve_base64(self, image_base64: str) -> MlMathCaptchaCandidate | None:
        if not image_base64 or not str(image_base64).strip():
            return None
        cleaned = str(image_base64).strip()
        if "," in cleaned:
            cleaned = cleaned.split(",", 1)[1]
        pad = len(cleaned) % 4
        if pad:
            cleaned += "=" * (4 - pad)
        try:
            image_bytes = base64.b64decode(cleaned)
        except (ValueError, binascii.Error):
            return None
        buffer = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(buffer, cv2.IMREAD_GRAYSCALE)
        if image is None or image.size == 0:
            return None
        return self.solve_image(image)


barname_ml_solver = BarnameMlCaptchaSolver()
