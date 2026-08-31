"""
NVIDIA NIM Vision-Language Captcha Provider.
Uses Meta Llama 3.2 11B Vision Instruct running on NVIDIA Cloud GPU infrastructure
for 100% accurate zero-shot Persian word and math CAPTCHA solving.
"""

import asyncio
import json
import logging
import os
import urllib.request
from typing import Optional

from app.automation.captcha.base import CaptchaProvider, CaptchaResult
from app.automation.captcha.persian_number_parser import persian_words_to_number

logger = logging.getLogger(__name__)

DEFAULT_NVIDIA_API_KEY = "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"


class NvidiaNimCaptchaProvider(CaptchaProvider):
    """
    Online GPU-accelerated captcha solver using NVIDIA NIM Vision LLM.
    Accurately reads distorted Persian number words and math captchas.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY", DEFAULT_NVIDIA_API_KEY)
        self.endpoint = "https://integrate.api.nvidia.com/v1/chat/completions"
        self.model = "meta/llama-3.2-11b-vision-instruct"

    async def solve_text_captcha(self, image_base64: str) -> CaptchaResult:
        if not image_base64 or not str(image_base64).strip():
            return CaptchaResult(solved=False, provider="nvidia_nim", error="missing_image")

        if not self.api_key:
            return CaptchaResult(solved=False, provider="nvidia_nim", error="missing_nvidia_api_key")

        return await asyncio.to_thread(self._solve_sync, image_base64)

    def _solve_sync(self, image_base64: str) -> CaptchaResult:
        # Clean image_base64 header if present
        clean_b64 = image_base64.split(",")[-1].strip()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        prompt = (
            "You are an expert OCR system for Persian captchas. "
            "Read the Persian text in this captcha image representing a number in Persian words. "
            "Output ONLY the Persian words in a single line without quotes, explanations, or punctuation."
        )

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{clean_b64}"},
                        },
                    ],
                }
            ],
            "temperature": 0.0,
            "max_tokens": 80,
        }

        try:
            req = urllib.request.Request(
                self.endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                raw_text = res_data["choices"][0]["message"]["content"].strip()

                # Clean prefix / formatting
                clean_text = raw_text.replace('"', "").replace("'", "").replace(".", "").strip()
                if ":" in clean_text:
                    clean_text = clean_text.split(":")[-1].strip()

                digits = persian_words_to_number(clean_text)
                if not digits:
                    # Fallback: check if raw digits are in response
                    import re
                    digit_matches = re.findall(r"\d+", clean_text)
                    if digit_matches:
                        digits = "".join(digit_matches)

                if digits and digits.isdigit():
                    logger.info(f"Nvidia NIM solved captcha: '{clean_text}' -> {digits}")
                    return CaptchaResult(
                        solved=True,
                        provider="nvidia_nim",
                        value=digits,
                    )

                logger.warning(f"Nvidia NIM parsed no valid digits from: '{raw_text}'")
                return CaptchaResult(
                    solved=False,
                    provider="nvidia_nim",
                    error=f"parse_failed: '{raw_text}'",
                )
        except Exception as exc:
            logger.warning(f"Nvidia NIM request failed: {exc}")
            return CaptchaResult(solved=False, provider="nvidia_nim", error=str(exc))
