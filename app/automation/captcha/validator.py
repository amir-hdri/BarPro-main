"""
Captcha solution validator.
"""
import re
from typing import Optional


class CaptchaValidator:
    """Validate captcha solutions."""
    
    @staticmethod
    def validate_solution(solution: str) -> bool:
        """Check if solution is valid."""
        if not solution:
            return False

        # Must be numeric or simple math result
        if not re.match(r'^-?\d+$', solution.strip()):
            return False

        # Reasonable range
        try:
            val = int(solution)
            return -9999 <= val <= 9999
        except Exception:
            return False
    
    @staticmethod
    def normalize_solution(solution: Optional[str]) -> Optional[str]:
        """Normalize solution format."""
        if not solution:
            return None
        
        # Remove spaces and normalize
        normalized = solution.strip().replace(" ", "")
        
        # Persian/Arabic to English digits
        digit_map = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        normalized = normalized.translate(digit_map)
        
        if CaptchaValidator.validate_solution(normalized):
            return normalized
        
        return None
