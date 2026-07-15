import asyncio
import base64
import json
import logging
from pathlib import Path

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


# Recreate the model architecture inside the solver class
class CRNN(nn.Module):
    def __init__(self, num_classes, img_channel=1):
        super().__init__()
        self.cnn = nn.Sequential(
            nn.Conv2d(img_channel, 32, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=2, stride=2),
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
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
            nn.Conv2d(256, 256, kernel_size=3, padding=1),
            nn.BatchNorm2d(256),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=(2, 1)),
        )

        self.rnn = nn.GRU(
            input_size=256, hidden_size=128, num_layers=2, bidirectional=True, batch_first=True, dropout=0.3
        )

        self.fc = nn.Linear(128 * 2, num_classes)

    def forward(self, x):
        features = self.cnn(x)
        features = features.squeeze(2)
        features = features.permute(0, 2, 1)

        rnn_out, _ = self.rnn(features)
        output = self.fc(rnn_out)
        output = output.permute(1, 0, 2)
        return output


class PyTorchFuelCaptchaProvider(CaptchaProvider):
    """
    Solves word-based Persian captchas using a locally trained
    PyTorch CRNN (CNN+GRU+CTC) model running in-process.
    """

    def __init__(self):
        self.model_path = Path(__file__).resolve().parent / "assets" / "fuel_captcha_crnn.pth"
        self.vocab_path = Path(__file__).resolve().parent / "assets" / "fuel_captcha_vocab.json"
        self._model = None
        self._vocab = []
        self._initialized = False
        self._lock: asyncio.Lock | None = None
        self._lock_loop: asyncio.AbstractEventLoop | None = None

    @property
    def _safe_lock(self) -> asyncio.Lock:
        """Recreate lock if event loop changed (Celery workers reuse loop per process)."""
        current = asyncio.get_event_loop()
        if self._lock is None or self._lock_loop != current:
            self._lock = asyncio.Lock()
            self._lock_loop = current
        return self._lock

    async def solve_text_captcha(self, image_base64: str) -> CaptchaResult:
        if not image_base64 or not str(image_base64).strip():
            return CaptchaResult(solved=False, provider="pytorch_fuel", error="missing_image")

        if torch is None or nn is None:
            return CaptchaResult(solved=False, provider="pytorch_fuel", error="torch_not_installed")

        # Lazy load model
        if not self._initialized:
            async with self._safe_lock:
                if not self._initialized:
                    success = self._load_model()
                    if not success:
                        return CaptchaResult(solved=False, provider="pytorch_fuel", error="model_init_failed")

        return await asyncio.to_thread(self._solve_sync, image_base64)

    def _load_model(self) -> bool:
        try:
            if not self.model_path.exists():
                logger.error(f"PyTorch fuel captcha model file not found: {self.model_path}")
                return False

            if not self.vocab_path.exists():
                logger.error(f"PyTorch fuel captcha vocab file not found: {self.vocab_path}")
                return False

            with open(self.vocab_path, encoding="utf-8") as f:
                self._vocab = json.load(f)

            num_classes = len(self._vocab) + 1
            self._model = CRNN(num_classes)

            # Use CPU to avoid MPS GRU inference inconsistencies on Mac
            self._device = torch.device("cpu")

            checkpoint = torch.load(self.model_path, map_location=self._device)  # nosec B614
            self._model.load_state_dict(checkpoint)
            self._model.to(self._device)
            self._model.eval()

            self._initialized = True
            logger.info("PyTorch fuel captcha solver successfully loaded!")
            return True
        except Exception as e:
            logger.exception(f"Error loading PyTorch fuel captcha solver: {e}")
            return False

    def _solve_sync(self, image_base64: str) -> CaptchaResult:
        try:
            # Decode base64 to image
            if "," in image_base64:
                image_base64 = image_base64.split(",", 1)[1]
            image_bytes = base64.b64decode(image_base64)
            from io import BytesIO

            try:
                img = Image.open(BytesIO(image_bytes)).convert("L")
            except Exception as e:
                logger.error(f"Failed to open image via PIL: {e}")
                return CaptchaResult(solved=False, provider="pytorch_fuel", error="invalid_image_data")

            # Preprocess: center text to prevent edge cutoff of right-aligned RTL text
            arr = np.array(img)
            col_mins = np.min(arr, axis=0)
            non_white_cols = np.where(col_mins < 240)[0]
            if len(non_white_cols) > 0:
                left_bound = non_white_cols[0]
                right_bound = non_white_cols[-1]
                bbox_w = right_bound - left_bound + 1
                cropped = img.crop((left_bound, 0, right_bound + 1, img.height))
                if bbox_w < 300:
                    pad_left = (300 - bbox_w) // 2
                    centered = Image.new(img.mode, (300, img.height), 255)
                    centered.paste(cropped, (pad_left, 0))
                    img = centered
                else:
                    img = cropped.resize((300, img.height), Image.Resampling.BILINEAR)

            # resize to W=300, H=32 (identical to PIL bilinear resize during training)
            img_resized = img.resize((300, 32), Image.Resampling.BILINEAR)
            img_normalized = np.array(img_resized, dtype=np.float32) / 255.0

            # Prepare tensor: shape (1, 1, 32, 300)
            tensor = torch.tensor(img_normalized, dtype=torch.float32).unsqueeze(0).unsqueeze(0).to(self._device)

            with torch.no_grad():
                outputs = self._model(tensor)  # (SeqLen, 1, Classes)

            # Decode using Greedy CTC Decoder
            outputs = outputs.permute(1, 0, 2)  # (1, SeqLen, Classes)
            preds = torch.softmax(outputs, dim=-1)
            max_idx = torch.argmax(preds, dim=-1)[0]  # (SeqLen,)

            chars = []
            prev = -1
            for idx in max_idx:
                val = idx.item()
                if val != len(self._vocab) and val != prev:
                    chars.append(self._vocab[val])
                prev = val

            words_predicted = "".join(chars).strip()

            if not words_predicted:
                return CaptchaResult(solved=False, provider="pytorch_fuel", error="decoding_empty")

            # Convert Persian words to digits
            digits_solved = persian_words_to_number(words_predicted)

            if not digits_solved or digits_solved == "0":
                logger.warning(f"Failed to parse predicted Persian words: '{words_predicted}'")
                return CaptchaResult(solved=False, provider="pytorch_fuel", error="parsing_failed")

            logger.info(f"PyTorch fuel solver successfully solved captcha: '{words_predicted}' -> {digits_solved}")
            return CaptchaResult(solved=True, provider="pytorch_fuel", value=digits_solved)

        except Exception as e:
            logger.exception(f"Exception in PyTorch fuel solver: {e}")
            return CaptchaResult(solved=False, provider="pytorch_fuel", error=f"exception: {e}")
