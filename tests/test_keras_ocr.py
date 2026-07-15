import base64
from pathlib import Path

import pytest

from app.automation.captcha.keras_ocr import KerasOcrCaptchaProvider
from app.core.config import utcms_config

# Keras OCR requires the `keras`/`tensorflow` stack, which is expected to live in a
# separate Python 3.12 environment (KERAS_PYTHON_PATH) rather than the main venv.
# Skip this test when that stack is unavailable in the current interpreter.
keras_available = False
try:
    import keras  # noqa: F401
    import tensorflow  # noqa: F401

    keras_available = True
except Exception:
    keras_available = False


@pytest.mark.asyncio
async def test_keras_ocr_solver():
    if not keras_available:
        pytest.skip("keras/tensorflow not installed in this interpreter (expected in KERAS_PYTHON_PATH env). Skipping.")

    provider = KerasOcrCaptchaProvider()

    # Path to sample image in dataset
    sample_image_path = Path("/Users/amirheidari/Documents/captcha_OCR/dataset/test/images/000000.png")

    if not sample_image_path.exists():
        pytest.skip("Sample image 000000.png does not exist at the expected path (OCR dataset missing). Skipping.")

    model_path = utcms_config.KERAS_MODEL_PATH
    if not model_path or not Path(model_path).exists():
        pytest.skip(f"Keras model not found at {model_path}. Skipping.")

    # Read the image and base64-encode it
    image_bytes = sample_image_path.read_bytes()
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    # Call the solver
    result = await provider.solve_text_captcha(image_base64)

    # Assertions
    assert result.solved is True, f"OCR Solver failed to solve captcha: {result.error}"
    assert result.value == "48146", f"Expected '48146', but got '{result.value}'"
    assert result.provider == "keras_ocr"
