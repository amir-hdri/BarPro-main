from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CaptchaResult:
    solved: bool
    provider: str
    value: str | None = None
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class CaptchaProvider(ABC):
    @abstractmethod
    async def solve_text_captcha(self, image_base64: str) -> CaptchaResult:
        raise NotImplementedError
