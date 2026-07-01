import asyncio
import logging
import os
import subprocess
from pathlib import Path

from app.automation.captcha.base import CaptchaProvider, CaptchaResult
from app.core.config import utcms_config

logger = logging.getLogger(__name__)

class KerasOcrCaptchaProvider(CaptchaProvider):
    """
    Solves digit-based Persian captchas using a Keras model executed
    in an external Python virtual environment containing tensorflow/keras.
    """

    async def solve_text_captcha(self, image_base64: str) -> CaptchaResult:
        if not image_base64 or not str(image_base64).strip():
            return CaptchaResult(solved=False, provider="keras_ocr", error="missing_image")

        return await asyncio.to_thread(self._solve_sync, image_base64)

    def _solve_sync(self, image_base64: str) -> CaptchaResult:
        python_path = utcms_config.KERAS_PYTHON_PATH
        model_path = utcms_config.KERAS_MODEL_PATH

        # Resolve model path to absolute path if relative
        if not os.path.isabs(model_path):
            model_path = str(Path(os.getcwd()) / model_path)

        script_path = str(Path(__file__).parent / "solve_keras.py")

        if not os.path.exists(python_path):
            logger.error(f"Keras Python path not found: {python_path}")
            return CaptchaResult(
                solved=False,
                provider="keras_ocr",
                error="python_env_not_found"
            )

        if not os.path.exists(model_path):
            logger.error(f"Keras model path not found: {model_path}")
            return CaptchaResult(
                solved=False,
                provider="keras_ocr",
                error="model_file_not_found"
            )

        try:
            logger.info("Invoking external Keras model prediction script...")
            env = os.environ.copy()
            env["TF_CPP_MIN_LOG_LEVEL"] = "3"
            env["CUDA_VISIBLE_DEVICES"] = ""
            env["OMP_NUM_THREADS"] = "1"
            env["TF_NUM_INTRAOP_THREADS"] = "1"
            env["TF_NUM_INTEROP_THREADS"] = "1"

            # Run the solve_keras.py script with subprocess
            process = subprocess.Popen(
                [python_path, script_path, model_path, "-"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env
            )

            stdout, stderr = process.communicate(input=image_base64, timeout=15)

            if process.returncode != 0:
                logger.error(f"Keras solver script failed with exit code {process.returncode}: {stderr.strip()}")
                return CaptchaResult(
                    solved=False,
                    provider="keras_ocr",
                    error="script_execution_error"
                )

            # Get last non-empty line of stdout to avoid TF/Keras startup logs
            stdout_lines = [line.strip() for line in stdout.splitlines() if line.strip()]
            prediction = stdout_lines[-1] if stdout_lines else ""
            if not prediction or prediction == "?":
                logger.warning("Keras OCR model could not decode the captcha digits")
                return CaptchaResult(
                    solved=False,
                    provider="keras_ocr",
                    error="model_decoding_failed"
                )

            logger.info(f"Keras OCR model successfully solved captcha: {prediction}")
            return CaptchaResult(
                solved=True,
                provider="keras_ocr",
                value=prediction
            )

        except subprocess.TimeoutExpired:
            logger.error("Keras solver script timed out after 15 seconds")
            try:
                process.kill()
                process.communicate()
            except Exception as e:
                logger.error(f"Failed to kill Keras solver subprocess: {e}")
            return CaptchaResult(
                solved=False,
                provider="keras_ocr",
                error="timeout"
            )
        except Exception as e:
            logger.exception(f"Unexpected error executing Keras OCR solver: {e}")
            return CaptchaResult(
                solved=False,
                provider="keras_ocr",
                error=f"internal_error: {e}"
            )
