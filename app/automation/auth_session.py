"""Session management for UTCMS authentication.

Provides the SessionManager class responsible for persisting,
loading, validating, and cleaning up authentication session state.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from playwright.async_api import BrowserContext, Page

from app.automation.auth_utils import is_login_url
from app.core.config import utcms_config

logger = logging.getLogger(__name__)

AUTH_KEYWORDS = (
    "barname",
    "applicationtoken",
    "cookiesession1",
    "auth",
    "session",
    "sessionid",
    "aspxauth",
    "identity",
    "aspnet.applicationcookie",
    "aspnetcore.identity",
    "jwt",
)

SESSION_STATE_FILE = "utcms_state.json"


class SessionManager:
    """Manages UTCMS authentication session persistence and validation.

    Responsibilities:
      - Inspecting browser cookies for authentication tokens
      - Saving / loading session state to / from a JSON file on disk
      - Validating that a previously saved session is still usable
      - Cleaning up stale session files
    """

    def __init__(self, context: BrowserContext, page: Page):
        self.context = context
        self.page = page

    async def has_auth_cookie(self) -> bool:
        """Return True when any known authentication cookie exists in the browser context."""
        try:
            cookies = await self.context.cookies()
        except Exception:
            return False

        for cookie in cookies:
            name = str(cookie.get("name", "")).lower()
            if any(keyword in name for keyword in AUTH_KEYWORDS):
                return True
        return False

    async def save_session_state(self, state: dict | None = None) -> None:
        """Persist the current cookies and optional metadata to a JSON file."""
        try:
            cookies = await self.context.cookies()
            state_path = self._get_session_state_path()
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_data = {
                "saved_at": datetime.now(UTC).replace(tzinfo=None).isoformat() + "Z",
                "url": str(self.page.url) if hasattr(self.page, "url") else "",
                "cookies": cookies,
            }
            if state:
                state_data.update(state)
            state_path.write_text(json.dumps(state_data, ensure_ascii=False, indent=2, default=str))
            logger.info(
                "session_state_saved",
                extra={"extra_fields": {"path": str(state_path), "cookie_count": len(cookies)}},
            )
        except Exception:
            logger.warning("session_state_save_failed", exc_info=True)

    def load_session_state(self) -> dict | None:
        """Load a previously saved session state from the JSON file."""
        state_path = self._get_session_state_path()
        if not state_path.exists():
            return None
        try:
            return json.loads(state_path.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("session_state_load_failed", exc_info=True)
            return None

    async def validate_session(self) -> bool:
        """Check whether the current session is still considered active.

        Returns True when an auth cookie is present *and* the current page
        URL does not point to a login page.
        """
        if not await self.has_auth_cookie():
            return False
        current_url = str(self.page.url) if hasattr(self.page, "url") else ""
        if current_url and not is_login_url(current_url):
            return True
        return await self.has_auth_cookie()

    def clear_session_state(self) -> None:
        """Remove the saved session state file from disk."""
        state_path = self._get_session_state_path()
        if state_path.exists():
            state_path.unlink()
            logger.info("session_state_cleared", extra={"extra_fields": {"path": str(state_path)}})

    def _get_session_state_path(self) -> Path:
        debug_dir = Path(utcms_config.CAPTCHA_DEBUG_DIR)
        return debug_dir / SESSION_STATE_FILE
