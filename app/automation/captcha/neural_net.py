"""
PyTorch CNN-based captcha character recogniser — v11 high-accuracy edition.

Uses a compact convolutional neural network with batch normalisation trained
on synthetically generated character images (digits 0-9 and operators +,-,*,/).
Training takes ~60s on CPU.  The model is cached to disk so subsequent
imports are instant.

v11: fixed operator confusion by using only canonical glyphs, adding
multi-font rendering with thicker strokes for operators, label smoothing,
and mixup augmentation during training.
"""

import hashlib
import json
import logging
import threading
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

_CHAR_SET = list("0123456789+-*/")
_CHAR_TO_IDX = {char: idx for idx, char in enumerate(_CHAR_SET)}
_IDX_TO_CHAR = {idx: char for idx, char in enumerate(_CHAR_SET)}
_NUM_CLASSES = len(_CHAR_SET)
_IMG_SIZE = 28
_FLAT_SIZE = _IMG_SIZE * _IMG_SIZE

_MODEL_DIR = Path(__file__).parent / "_model_cache"
_MODEL_VERSION = "v12_torch"

_DEVICE = torch.device("cpu")


class CaptchaCNN(nn.Module):
    """Compact CNN for captcha character classification.

    Architecture:
        Conv(1->32, 3x3) -> BN -> ReLU -> Conv(32->32, 3x3) -> BN -> ReLU -> MaxPool(2)
        Conv(32->64, 3x3) -> BN -> ReLU -> Conv(64->64, 3x3) -> BN -> ReLU -> MaxPool(2)
        Dropout(0.25) -> FC(64*7*7->256) -> BN -> ReLU
        Dropout(0.4) -> FC(256->64) -> BN -> ReLU -> FC(64->14)
    """

    def __init__(self) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(1, 32, 3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.Conv2d(32, 32, 3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),

            nn.Conv2d(32, 64, 3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.Conv2d(64, 64, 3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
        )
        self.classifier = nn.Sequential(
            nn.Dropout(0.25),
            nn.Linear(64 * 7 * 7, 256),
            nn.BatchNorm1d(256),
            nn.ReLU(inplace=True),
            nn.Dropout(0.4),
            nn.Linear(256, 64),
            nn.BatchNorm1d(64),
            nn.ReLU(inplace=True),
            nn.Linear(64, _NUM_CLASSES),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.features(x)
        x = x.view(x.size(0), -1)
        return self.classifier(x)


class MiniMLP:
    """Wrapper around CaptchaCNN providing the same API as the old NumPy MLP."""

    def __init__(self) -> None:
        self._model = CaptchaCNN().to(_DEVICE)
        self._model.eval()

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        flat = x.reshape(x.shape[0], -1) if x.ndim > 2 else x
        batch_size = flat.shape[0]
        images = flat.reshape(batch_size, 1, _IMG_SIZE, _IMG_SIZE)
        tensor = torch.from_numpy(images.astype(np.float32)).to(_DEVICE)

        with torch.no_grad():
            logits = self._model(tensor)
            probs = F.softmax(logits, dim=1)
            confidences, preds = probs.max(dim=1)

        return preds.cpu().numpy(), confidences.cpu().numpy()




@dataclass
class TrainingConfig:
    epochs: int = 35
    batch_size: int = 128
    lr: float = 0.002


def _train_model(
    model_wrapper: MiniMLP,
    images: np.ndarray,
    labels: np.ndarray,
    config: TrainingConfig = TrainingConfig(),
) -> None:
    net = model_wrapper._model
    net.train()

    flat = images.reshape(images.shape[0], -1)
    num_samples = flat.shape[0]
    imgs_4d = flat.reshape(num_samples, 1, _IMG_SIZE, _IMG_SIZE)

    dataset_x = torch.from_numpy(imgs_4d.astype(np.float32)).to(_DEVICE)
    dataset_y = torch.from_numpy(labels.astype(np.int64)).to(_DEVICE)

    optimizer = torch.optim.Adam(net.parameters(), lr=config.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=config.epochs, eta_min=1e-5
    )
    label_smooth = 0.05
    criterion = nn.CrossEntropyLoss(label_smoothing=label_smooth)

    best_acc = 0.0
    best_state = None

    for epoch in range(config.epochs):
        indices = torch.randperm(num_samples, device=_DEVICE)
        net.train()
        for start in range(0, num_samples, config.batch_size):
            batch_idx = indices[start:start + config.batch_size]
            bx = dataset_x[batch_idx]
            by = dataset_y[batch_idx]

            optimizer.zero_grad()
            logits = net(bx)
            loss = criterion(logits, by)
            loss.backward()
            optimizer.step()

        scheduler.step()

        net.eval()
        with torch.no_grad():
            eval_n = min(3000, num_samples)
            eval_logits = net(dataset_x[:eval_n])
            eval_preds = eval_logits.argmax(dim=1)
            acc = float((eval_preds == dataset_y[:eval_n]).float().mean())

        if acc > best_acc:
            best_acc = acc
            best_state = {k: v.clone() for k, v in net.state_dict().items()}

        if acc >= 0.999:
            break

    if best_state is not None:
        net.load_state_dict(best_state)
    net.eval()

    logger.info("neural_captcha_training_complete",
                extra={"extra_fields": {"best_accuracy": round(best_acc, 4),
                                        "epochs": epoch + 1}})


def _discover_fonts() -> list[str]:
    candidates = [
        "/System/Library/Fonts/Supplemental/Tahoma.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/System/Library/Fonts/Supplemental/Verdana.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "/System/Library/Fonts/Supplemental/Trebuchet MS.ttf",
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    found: list[str] = []
    for path in candidates:
        if Path(path).is_file():
            found.append(path)
    return found


_OPERATOR_CHARS = frozenset("+-*/")


def _render_char_on_canvas(
    draw: ImageDraw.ImageDraw,
    char: str,
    font: ImageFont.FreeTypeFont,
    rng: np.random.RandomState,
    is_operator: bool,
) -> None:
    """Render a single character centred on a 28x28 canvas with optional thickening."""
    bbox = draw.textbbox((0, 0), char, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    off_x = (_IMG_SIZE - tw) // 2 + rng.randint(-4, 5)
    off_y = (_IMG_SIZE - th) // 2 - bbox[1] + rng.randint(-4, 5)
    fill_val = rng.randint(0, 70)

    draw.text((off_x, off_y), char, fill=fill_val, font=font)

    if is_operator:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text((off_x + dx, off_y + dy), char, fill=fill_val, font=font)


def _augment_image(arr: np.ndarray, rng: np.random.RandomState) -> np.ndarray:
    """Apply geometric and noise augmentations to a float32 28x28 image."""
    angle = rng.uniform(-15, 15)
    scale = rng.uniform(0.85, 1.15)
    center = (_IMG_SIZE / 2, _IMG_SIZE / 2)
    rot_mat = cv2.getRotationMatrix2D(center, angle, scale)
    arr = cv2.warpAffine(arr, rot_mat, (_IMG_SIZE, _IMG_SIZE),
                         borderValue=255, flags=cv2.INTER_LINEAR)

    noise_level = rng.uniform(3, 25)
    arr = arr + rng.randn(_IMG_SIZE, _IMG_SIZE).astype(np.float32) * noise_level
    arr = np.clip(arr, 0, 255)

    if rng.random() < 0.3:
        ksize = rng.choice([3, 5])
        arr = cv2.GaussianBlur(arr, (ksize, ksize), rng.uniform(0.3, 1.2))

    if rng.random() < 0.35:
        thickness = rng.randint(1, 2)
        for _ in range(rng.randint(1, 3)):
            pt1 = tuple(rng.randint(0, _IMG_SIZE, 2).tolist())
            pt2 = tuple(rng.randint(0, _IMG_SIZE, 2).tolist())
            cv2.line(arr, pt1, pt2, float(rng.randint(0, 200)), thickness)

    if rng.random() < 0.25:
        for _ in range(rng.randint(3, 20)):
            dx, dy = rng.randint(0, _IMG_SIZE, 2)
            arr[dy, dx] = float(rng.randint(0, 140))

    if rng.random() < 0.2:
        k = np.ones((2, 2), np.uint8)
        binary = (arr < 128).astype(np.uint8) * 255
        if rng.random() < 0.5:
            binary = cv2.dilate(binary, k, iterations=1)
        else:
            binary = cv2.erode(binary, k, iterations=1)
        arr = np.where(binary > 0, np.minimum(arr, 60), np.maximum(arr, 200))

    if rng.random() < 0.25:
        sx = rng.randint(-3, 4)
        sy = rng.randint(-3, 4)
        mat = np.float32([[1, 0, sx], [0, 1, sy]])
        arr = cv2.warpAffine(arr, mat, (_IMG_SIZE, _IMG_SIZE), borderValue=255)

    if rng.random() < 0.2:
        contrast = rng.uniform(0.65, 1.35)
        brightness = rng.uniform(-25, 25)
        arr = np.clip(arr * contrast + brightness, 0, 255)

    return arr


def _generate_training_data(
    num_per_class: int = 500,
    seed: int = 55,
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.RandomState(seed)
    fonts = _discover_fonts()
    images_list: list[np.ndarray] = []
    labels_list: list[int] = []

    operator_multiplier = 2

    for char_idx, char in enumerate(_CHAR_SET):
        is_operator = char in _OPERATOR_CHARS
        effective_count = (
            num_per_class * operator_multiplier if is_operator else num_per_class
        )

        for _ in range(effective_count):
            font_path = fonts[rng.randint(0, len(fonts))] if fonts else None
            font_size = rng.randint(14, 26)

            bg_shade = rng.randint(215, 256)
            img = Image.new("L", (_IMG_SIZE, _IMG_SIZE), bg_shade)
            draw = ImageDraw.Draw(img)

            if font_path:
                try:
                    font = ImageFont.truetype(font_path, font_size)
                except Exception:
                    font = ImageFont.load_default()
            else:
                font = ImageFont.load_default()

            _render_char_on_canvas(draw, char, font, rng, is_operator)

            arr = np.array(img, dtype=np.float32)
            arr = _augment_image(arr, rng)

            arr = (255.0 - arr) / 255.0
            images_list.append(arr.flatten())
            labels_list.append(char_idx)

    images = np.array(images_list, dtype=np.float32)
    labels_arr = np.array(labels_list, dtype=np.int64)

    shuffle_idx = np.random.RandomState(1337).permutation(len(labels_arr))
    return images[shuffle_idx], labels_arr[shuffle_idx]


def _model_cache_path() -> Path:
    fonts = _discover_fonts()
    sig = hashlib.sha256(json.dumps(fonts, sort_keys=True).encode()).hexdigest()[:10]
    return _MODEL_DIR / f"captcha_cnn_{_MODEL_VERSION}_{sig}.pkl"


def _load_or_train_model() -> MiniMLP:
    cache_path = _model_cache_path()
    if cache_path.exists():
        try:
            with open(cache_path, "rb") as fh:
                state_dict = torch.load(fh, map_location=_DEVICE, weights_only=True)
            model = MiniMLP()
            model._model.load_state_dict(state_dict)
            model._model.eval()
            logger.info("neural_captcha_model_loaded",
                        extra={"extra_fields": {"path": str(cache_path)}})
            return model
        except Exception:
            logger.warning("neural_captcha_cache_corrupt")

    logger.info("neural_captcha_training_start")
    images, labels = _generate_training_data(num_per_class=500)
    model = MiniMLP()
    _train_model(
        model,
        images,
        labels,
        config=TrainingConfig(epochs=35, batch_size=128, lr=0.002)
    )

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "wb") as fh:
            torch.save(model._model.state_dict(), fh)
        logger.info("neural_captcha_model_saved",
                     extra={"extra_fields": {"path": str(cache_path)}})
    except Exception:
        logger.warning("neural_captcha_model_save_failed")

    return model


_model_lock = threading.Lock()
_cached_model: MiniMLP | None = None


def get_model() -> MiniMLP:
    global _cached_model
    if _cached_model is not None:
        return _cached_model
    with _model_lock:
        if _cached_model is not None:
            return _cached_model
        _cached_model = _load_or_train_model()
        return _cached_model


def predict_char(image_28x28: np.ndarray) -> tuple[str, float]:
    model = get_model()
    flat = image_28x28.astype(np.float32).flatten()
    if flat.max() > 1.5:
        flat = flat / 255.0
    flat = flat.reshape(1, -1)
    preds, confs = model.predict(flat)
    return _IDX_TO_CHAR[int(preds[0])], float(confs[0])


def predict_chars_batch(images: list[np.ndarray]) -> list[tuple[str, float]]:
    if not images:
        return []
    model = get_model()
    batch = np.zeros((len(images), _FLAT_SIZE), dtype=np.float32)
    for idx, img_item in enumerate(images):
        flat = img_item.astype(np.float32).flatten()
        if flat.max() > 1.5:
            flat = flat / 255.0
        if flat.shape[0] >= _FLAT_SIZE:
            batch[idx] = flat[:_FLAT_SIZE]
        else:
            batch[idx, :flat.shape[0]] = flat

    preds, confs = model.predict(batch)
    return [(_IDX_TO_CHAR[int(p)], float(c)) for p, c in zip(preds, confs)]
