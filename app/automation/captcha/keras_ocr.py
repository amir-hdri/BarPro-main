import asyncio
import base64
import logging
import os
import threading
from pathlib import Path

from app.automation.captcha.base import CaptchaProvider, CaptchaResult
from app.core.config import utcms_config

logger = logging.getLogger(__name__)

CHARS = [str(d) for d in range(10)]
BLANK_INDEX = len(CHARS)  # 10


def _strip_data_header(b64: str) -> str:
    if "," in b64:
        return b64.split(",", 1)[1]
    return b64


def _decode_predictions(pred, chars):
    import tensorflow as tf

    pred_time_major = tf.transpose(pred, perm=[1, 0, 2])
    input_len = [pred.shape[1]] * pred.shape[0]
    decoded, _ = tf.nn.ctc_greedy_decoder(
        pred_time_major,
        sequence_length=tf.constant(input_len, dtype=tf.int32),
        blank_index=BLANK_INDEX,
    )
    dense = tf.sparse.to_dense(decoded[0], default_value=-1).numpy()
    output_numbers = []
    for res in dense:
        digits = [chars[int(c)] for c in res if c != -1]
        reversed_str = "".join(digits)
        normal_str = reversed_str[::-1]
        output_numbers.append(normal_str if normal_str != "" else "?")
    return output_numbers


def _solve_image_data(img_bytes: bytes, model) -> str:
    import numpy as np
    import tensorflow as tf

    image_decoded = tf.io.decode_image(img_bytes, channels=3)
    image_resized = tf.image.resize(image_decoded, [25, 180])
    image_normalized = tf.cast(image_resized, tf.float32) / 255.0
    input_tensor = np.expand_dims(image_normalized.numpy(), axis=0)
    pred = model.predict(input_tensor, verbose=0)
    decoded = _decode_predictions(pred, CHARS)
    return decoded[0]


class KerasOcrCaptchaProvider(CaptchaProvider):
    """
    Solves digit-based Persian captchas using a Keras model loaded in-process.

    The model is loaded lazily once per worker process (thread-safe) and reused
    across calls, eliminating the per-captcha subprocess cold start and the
    unbounded TensorFlow subprocess RAM that previously risked OOM on the
    2.5 GB worker cgroup.
    """

    _model = None
    _model_lock = threading.Lock()
    _model_error = False

    def _get_model(self):
        if self._model is not None:
            return self._model
        if self._model_error:
            return None
        with self._model_lock:
            if self._model is not None:
                return self._model
            model_path = utcms_config.KERAS_MODEL_PATH
            if not os.path.isabs(model_path):
                model_path = str(Path(os.getcwd()) / model_path)
            if not os.path.exists(model_path):
                logger.error(f"Keras model path not found: {model_path}")
                self._model_error = True
                return None
            try:
                import os as _os

                _os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
                _os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
                _os.environ.setdefault("OMP_NUM_THREADS", "1")
                _os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "1")
                _os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")
                import keras

                self._model = keras.models.load_model(model_path, compile=False)
                logger.info(f"Keras OCR model loaded in-process from {model_path}")
                return self._model
            except Exception as e:
                logger.error(f"Failed to load Keras OCR model: {e}")
                self._model_error = True
                return None

    async def solve_text_captcha(self, image_base64: str) -> CaptchaResult:
        if not image_base64 or not str(image_base64).strip():
            return CaptchaResult(solved=False, provider="keras_ocr", error="missing_image")

        return await asyncio.to_thread(self._solve_sync, image_base64)

    def _solve_sync(self, image_base64: str) -> CaptchaResult:
        model = self._get_model()
        if model is None:
            return CaptchaResult(solved=False, provider="keras_ocr", error="model_load_failed")

        try:
            raw = _strip_data_header(image_base64.strip())
            img_bytes = base64.b64decode(raw)
        except Exception as e:
            logger.warning(f"Keras OCR failed to decode image: {e}")
            return CaptchaResult(solved=False, provider="keras_ocr", error="image_decode_failed")

        try:
            prediction = _solve_image_data(img_bytes, model)
        except Exception as e:
            logger.warning(f"Keras OCR prediction error: {e}")
            return CaptchaResult(solved=False, provider="keras_ocr", error="prediction_error")

        if not prediction or prediction == "?":
            logger.warning("Keras OCR model could not decode the captcha digits")
            return CaptchaResult(solved=False, provider="keras_ocr", error="model_decoding_failed")

        logger.info("Keras OCR captcha solved successfully")
        return CaptchaResult(solved=True, provider="keras_ocr", value=prediction)
