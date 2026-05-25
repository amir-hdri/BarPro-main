from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class CaptchaResult:
    solved: bool
    provider: str
    value: Optional[str] = None
    error: Optional[str] = None


class CaptchaProvider(ABC):
    @abstractmethod
    async def solve_text_captcha(self, image_base64: str) -> CaptchaResult:
        raise NotImplementedError
