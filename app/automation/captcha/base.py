from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CaptchaResult:
    solved: bool
    provider: str
    value: str | None = None
    error: str | None = None


class CaptchaProvider(ABC):
    @abstractmethod
    async def solve_text_captcha(self, image_base64: str) -> CaptchaResult:
        raise NotImplementedError
