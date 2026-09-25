from __future__ import annotations

import base64
import binascii
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np

try:
    import torch
    import torch.nn as nn
except ImportError:  # pragma: no cover
    torch = None
    nn = None

if TYPE_CHECKING:
    from app.automation.captcha.barname_ml_solver import MlMathCaptchaCandidate

logger = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).parent / "assets" / "math_captcha_crnn.pth"
VOCAB = list("0123456789+-")
BLANK_IDX = len(VOCAB)
IMG_W = 160
IMG_H = 48


class MathCRNN(nn.Module if nn else object):  # type: ignore[misc]
    def __init__(self, num_classes: int) -> None:
        super().__init__()
        self.cnn = nn.Sequential(
            nn.Conv2d(1, 32, 3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2, 2),
            nn.Conv2d(32, 64, 3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2, 2),
            nn.Conv2d(64, 128, 3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.MaxPool2d((2, 1)),
            nn.Conv2d(128, 128, 3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.MaxPool2d((2, 1)),
            nn.Conv2d(128, 128, (3, 1), padding=0),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
        )
        self.rnn = nn.GRU(
            input_size=128,
            hidden_size=96,
            num_layers=2,
            bidirectional=True,
            batch_first=True,
            dropout=0.2,
        )
        self.fc = nn.Linear(96 * 2, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        conv = self.cnn(x)
        conv = conv.squeeze(2)
        conv = conv.permute(0, 2, 1)
        recurrent, _ = self.rnn(conv)
        logits = self.fc(recurrent)
        return logits.permute(1, 0, 2)


def decode_ctc(logits: torch.Tensor, vocab: list[str]) -> tuple[str, float]:
    probs = logits.permute(1, 0, 2).softmax(dim=-1)[0]  # (W_seq, num_classes)
    max_probs, max_indices = probs.max(dim=-1)
    max_indices_np = max_indices.cpu().numpy()
    max_probs_np = max_probs.cpu().numpy()

    blank = len(vocab)
    chars = []
    char_confs = []
    prev = -1
    for idx, p in zip(max_indices_np, max_probs_np, strict=False):
        if idx != blank and idx != prev:
            chars.append(vocab[idx])
            char_confs.append(float(p))
        prev = idx

    text = "".join(chars)
    avg_conf = float(sum(char_confs) / max(1, len(char_confs))) if char_confs else 0.0
    return text, avg_conf


class MathCrnnSolver:
    def __init__(self, model_path: Path | None = None) -> None:
        self.model_path = model_path or MODEL_PATH
        self._model = None
        self._device = None
        self._loaded = False
        self._available = False

    @property
    def available(self) -> bool:
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
            checkpoint = torch.load(self.model_path, map_location=self._device)
            state_dict = checkpoint["model_state"] if isinstance(checkpoint, dict) and "model_state" in checkpoint else checkpoint
            model = MathCRNN(num_classes=len(VOCAB) + 1).to(self._device)
            model.load_state_dict(state_dict)
            model.eval()
            self._model = model
            self._available = True
            logger.info("MathCRNN solver loaded successfully on %s from %s", self._device, self.model_path)
        except Exception as e:
            logger.warning("Failed to load MathCRNN model: %s", e)
            self._available = False

    def solve_image(self, image: np.ndarray) -> MlMathCaptchaCandidate | None:
        self._ensure_loaded()
        if not self._available or self._model is None:
            return None

        from app.automation.captcha.barname_ml_solver import MlMathCaptchaCandidate

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
        resized = cv2.resize(gray, (IMG_W, IMG_H), interpolation=cv2.INTER_AREA)
        norm = (255.0 - resized.astype(np.float32)) / 255.0
        tensor_img = torch.from_numpy(norm).unsqueeze(0).unsqueeze(0).to(self._device)

        with torch.no_grad():
            logits = self._model(tensor_img)
            pred_text, confidence = decode_ctc(logits, VOCAB)

        logger.debug("MathCRNN decoded sequence: %r (conf: %.3f)", pred_text, confidence)
        if not pred_text:
            return None

        # Parse arithmetic expression (e.g. 54-9, 10+6)
        op = None
        if "+" in pred_text:
            op = "+"
        elif "-" in pred_text:
            op = "-"

        if not op:
            return None

        parts = pred_text.split(op)
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            return None

        left = int(parts[0])
        right = int(parts[1])
        ans = left + right if op == "+" else left - right

        chars = list(pred_text)
        confs = [confidence] * len(chars)

        return MlMathCaptchaCandidate(
            expression=f"{left}{op}{right}",
            answer=str(ans),
            confidence=confidence,
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


math_crnn_solver = MathCrnnSolver()
