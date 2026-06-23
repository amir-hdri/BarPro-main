import base64
from pathlib import Path
import pytest
from app.automation.captcha.keras_ocr import KerasOcrCaptchaProvider
from app.core.config import utcms_config

@pytest.mark.asyncio
async def test_keras_ocr_solver():
    provider = KerasOcrCaptchaProvider()
    
    # Path to sample image in dataset
    sample_image_path = Path("/Users/amirheidari/Documents/captcha_OCR/dataset/test/images/000000.png")
    
    assert sample_image_path.exists(), "Sample image 000000.png does not exist at the expected path"
    
    # Read the image and base64-encode it
    image_bytes = sample_image_path.read_bytes()
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")
    
    # Call the solver
    result = await provider.solve_text_captcha(image_base64)
    
    # Assertions
    assert result.solved is True, f"OCR Solver failed to solve captcha: {result.error}"
    assert result.value == "48146", f"Expected '48146', but got '{result.value}'"
    assert result.provider == "keras_ocr"
