import re
from dataclasses import dataclass
from typing import Optional


_DIGIT_TRANSLATION = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_WORD_OPERATORS = {
    "بعلاوه": "+",
    "به علاوه": "+",
    "جمع": "+",
    "منهای": "-",
    "تفریق": "-",
    "ضربدر": "*",
    "ضرب در": "*",
    "ضرب": "*",
    "تقسیم": "/",
}


@dataclass(frozen=True)
class CaptchaSolveDecision:
    value: Optional[str]
    confidence: float
    strategy: Optional[str] = None


class CaptchaEngine:
    """Parses math-like captcha hints extracted from the login page."""

    def solve_text(self, captcha_hint: str) -> Optional[str]:
        decision = self.solve_text_with_confidence(captcha_hint)
        if decision.value is not None:
            return decision.value
        return None

    def solve_text_with_confidence(self, captcha_hint: str) -> CaptchaSolveDecision:
        if not captcha_hint or not str(captcha_hint).strip():
            return CaptchaSolveDecision(value=None, confidence=0.0, strategy=None)

        normalized = self._normalize_hint(str(captcha_hint))
        expression = self._extract_expression(normalized)
        if not expression:
            digits = re.findall(r"-?\d+", normalized)
            if len(digits) == 1:
                return CaptchaSolveDecision(value=digits[0], confidence=0.55, strategy="single_number_hint")
            return CaptchaSolveDecision(value=None, confidence=0.0, strategy=None)

        left, operator, right = expression
        try:
            left_num = int(left)
            right_num = int(right)
        except ValueError:
            return CaptchaSolveDecision(value=None, confidence=0.0, strategy=None)

        if operator == "+":
            result = left_num + right_num
        elif operator == "-":
            result = left_num - right_num
        elif operator in ("*", "x"):
            result = left_num * right_num
        elif operator == "/":
            if right_num == 0:
                return CaptchaSolveDecision(value=None, confidence=0.0, strategy=None)
            result = left_num // right_num if left_num % right_num == 0 else left_num / right_num
        else:
            return CaptchaSolveDecision(value=None, confidence=0.0, strategy=None)

        confidence = 0.98 if any(op in normalized for op in "+-*/×÷x") else 0.9
        return CaptchaSolveDecision(value=str(int(result) if isinstance(result, float) and result.is_integer() else result), confidence=confidence, strategy="parsed_hint")

    @staticmethod
    def _normalize_hint(raw: str) -> str:
        normalized = raw.translate(_DIGIT_TRANSLATION)
        normalized = normalized.replace("×", "*").replace("÷", "/").replace("=", " ")
        normalized = normalized.replace("؟", " ").replace("?", " ").replace(":", " ")
        normalized = " ".join(normalized.split())
        for word, operator in _WORD_OPERATORS.items():
            normalized = normalized.replace(word, f" {operator} ")
        return " ".join(normalized.split())

    @staticmethod
    def _extract_expression(normalized: str) -> Optional[tuple[str, str, str]]:
        match = re.search(r"(-?\d+)\s*([+\-*/x])\s*(-?\d+)", normalized)
        if not match:
            return None
        return match.group(1), match.group(2), match.group(3)


captcha_engine = CaptchaEngine()
