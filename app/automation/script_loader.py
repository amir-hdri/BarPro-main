from functools import lru_cache
from pathlib import Path

class ScriptLoader:
    """Helper class to load JavaScript files."""

    BASE_DIR = Path(__file__).parent / "js"

    @classmethod
    @lru_cache(maxsize=None)
    def load(cls, script_name: str) -> str:
        """
        Loads a JavaScript file content by name (without extension).
        Results are cached for performance.
        """
        file_path = cls.BASE_DIR / f"{script_name}.js"
        if not file_path.exists():
            raise FileNotFoundError(f"Script {script_name}.js not found at {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

# Global instance for easy access
script_loader = ScriptLoader()
