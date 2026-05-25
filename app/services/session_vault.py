import os
import re
from pathlib import Path
from typing import Optional

from app.core.config import utcms_config


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z._-]+", "-", (value or "").strip())
    normalized = normalized.strip("-._")
    return normalized or "default"


class SessionVault:
    def __init__(self) -> None:
        self._base_path = Path(utcms_config.AUTH_STATE_PATH)

    def build_account_key(
        self,
        username: Optional[str] = None,
        national_code: Optional[str] = None,
        fallback: Optional[str] = None,
    ) -> str:
        for candidate in (username, national_code, fallback):
            if candidate and str(candidate).strip():
                return _slugify(str(candidate))
        return "default"

    def auth_state_path_for_account(
        self,
        username: Optional[str] = None,
        national_code: Optional[str] = None,
        fallback: Optional[str] = None,
    ) -> str:
        account_key = self.build_account_key(username=username, national_code=national_code, fallback=fallback)
        suffix = self._base_path.suffix or ".json"
        stem = self._base_path.stem or "utcms_state"
        directory = self._base_path.parent
        return str(directory / f"{stem}_{account_key}{suffix}")

    def default_auth_state_path(self) -> str:
        return str(Path(utcms_config.AUTH_STATE_PATH))

    def auth_state_exists(self, path: Optional[str]) -> bool:
        if not path:
            return False
        return os.path.exists(path)

    def ensure_parent_dir(self, path: str) -> None:
        directory = Path(path).parent
        directory.mkdir(parents=True, exist_ok=True)

    def delete_auth_state(self, path: Optional[str]) -> None:
        if not path:
            return
        try:
            Path(path).unlink(missing_ok=True)
        except Exception:
            return


session_vault = SessionVault()
