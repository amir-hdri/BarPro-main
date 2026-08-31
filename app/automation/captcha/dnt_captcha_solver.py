"""
PyTorch CRNN Solver for DNT Captcha (Persian Number Words).
Decodes wave-distorted Persian numbers into exact digit strings.
"""

import asyncio
import base64
import json
import logging
from io import BytesIO
from pathlib import Path
from threading import Lock

import numpy as np
from PIL import Image

from app.automation.captcha.base import CaptchaProvider, CaptchaResult
from app.automation.captcha.persian_number_parser import persian_words_to_number

try:
    import torch
    import torch.nn as nn
except ImportError:
    torch = None
    nn = None

logger = logging.getLogger(__name__)


class CRNN(nn.Module):
    def __init__(self, num_classes: int, img_channel: int = 1):
        super().__init__()
        self.cnn = nn.Sequential(
            nn.Conv2d(img_channel, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=2, stride=2),

            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=2, stride=2),

            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=(2, 1)),

            nn.Conv2d(128, 256, kernel_size=3, padding=1),
            nn.BatchNorm2d(256),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=(2, 1)),

            nn.Conv2d(256, 256, kernel_size=(2, 1)),
            nn.BatchNorm2d(256),
            nn.ReLU(),
        )

        self.rnn = nn.GRU(
            input_size=256,
            hidden_size=128,
            num_layers=2,
            bidirectional=True,
            batch_first=True,
            dropout=0.25,
        )

        self.fc = nn.Linear(128 * 2, num_classes)

    def forward(self, x):
        features = self.cnn(x)
        features = features.squeeze(2)
        features = features.permute(0, 2, 1)

        rnn_out, _ = self.rnn(features)
        output = self.fc(rnn_out)
        return output


class DntCaptchaProvider(CaptchaProvider):
    """
    Solves word-based DNT Persian captchas using a locally trained
    PyTorch CRNN (CNN + GRU + CTC) model running in-process.
    """

    def __init__(self):
        self.model_path = Path(__file__).resolve().parent / "assets" / "dnt_captcha_crnn.pth"
        self.vocab_path = Path(__file__).resolve().parent / "assets" / "dnt_captcha_vocab.json"
        self._model = None
        self._vocab = []
        self._initialized = False
        self._init_lock = Lock()
        self.img_w = 240
        self.img_h = 36

    async def solve_text_captcha(self, image_base64: str) -> CaptchaResult:
        if not image_base64 or not str(image_base64).strip():
            return CaptchaResult(solved=False, provider="dnt_crnn", error="missing_image")

        if torch is None or nn is None:
            return CaptchaResult(solved=False, provider="dnt_crnn", error="torch_not_installed")

        if not self._initialized:
            with self._init_lock:
                if not self._initialized:
                    success = self._load_model()
                    if not success:
                        return CaptchaResult(solved=False, provider="dnt_crnn", error="model_init_failed")

        return await asyncio.to_thread(self._solve_sync, image_base64)

    def _load_model(self) -> bool:
        try:
            if not self.model_path.exists():
                logger.warning(f"DNT captcha model file not found: {self.model_path}")
                return False

            if not self.vocab_path.exists():
                logger.warning(f"DNT captcha vocab file not found: {self.vocab_path}")
                return False

            with open(self.vocab_path, encoding="utf-8") as f:
                self._vocab = json.load(f)

            num_classes = len(self._vocab) + 1  # 0 is CTC blank
            self._model = CRNN(num_classes)
            self._device = torch.device("cpu")

            checkpoint = torch.load(self.model_path, map_location=self._device)
            self._model.load_state_dict(checkpoint)
            self._model.eval()
            self._initialized = True
            logger.info("DNT captcha PyTorch CRNN model loaded successfully.")
            return True
        except Exception as exc:
            logger.error(f"Failed to load DNT captcha model: {exc}")
            return False

    def _solve_sync(self, image_base64: str) -> CaptchaResult:
        try:
            raw_bytes = base64.b64decode(image_base64)
            img = Image.open(BytesIO(raw_bytes)).convert("L")
            img = img.resize((self.img_w, self.img_h), Image.Resampling.BILINEAR)

            arr = np.array(img, dtype=np.float32) / 255.0
            arr = (arr - 0.5) / 0.5
            tensor = torch.tensor(arr, dtype=torch.float32).unsqueeze(0).unsqueeze(0).to(self._device)

            with torch.no_grad():
                preds = self._model(tensor)  # [1, W_seq, num_classes]
                argmax_preds = torch.argmax(preds, dim=2)[0].cpu().numpy()

            decoded_chars = []
            prev_idx = 0
            for idx in argmax_preds:
                if idx != 0 and idx != prev_idx:
                    if idx - 1 < len(self._vocab):
                        decoded_chars.append(self._vocab[idx - 1])
                prev_idx = idx

            predicted_text = "".join(decoded_chars).strip()
            digits = persian_words_to_number(predicted_text)

            if digits and digits.isdigit() and len(digits) >= 4:
                return CaptchaResult(
                    solved=True,
                    provider="dnt_crnn",
                    value=digits,
                )

            return CaptchaResult(
                solved=False,
                provider="dnt_crnn",
                error=f"parse_failed: '{predicted_text}' -> '{digits}'",
            )
        except Exception as exc:
            logger.warning(f"DntCaptchaProvider inference error: {exc}")
            return CaptchaResult(solved=False, provider="dnt_crnn", error=str(exc))
