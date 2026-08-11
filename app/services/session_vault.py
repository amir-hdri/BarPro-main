import json
import logging
import os
import re
from pathlib import Path

from app.core.config import utcms_config
from app.core.redis import redis_manager
from app.core.utils import run_async

logger = logging.getLogger(__name__)


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z._-]+", "-", (value or "").strip())
    normalized = normalized.strip("-._")
    return normalized or "default"


class SessionVault:
    def __init__(self) -> None:
        self._base_path = Path(utcms_config.AUTH_STATE_PATH)

    def build_account_key(
        self,
        username: str | None = None,
        national_code: str | None = None,
        fallback: str | None = None,
    ) -> str:
        for candidate in (username, national_code, fallback):
            if candidate and str(candidate).strip():
                return _slugify(str(candidate))
        return "default"

    def auth_state_path_for_account(
        self,
        username: str | None = None,
        national_code: str | None = None,
        fallback: str | None = None,
        scope: str | None = None,
    ) -> str:
        account_key = self.build_account_key(username=username, national_code=national_code, fallback=fallback)
        if scope:
            account_key = f"{_slugify(scope)}-{account_key}"
        suffix = self._base_path.suffix or ".json"
        stem = self._base_path.stem or "utcms_state"
        directory = self._base_path.parent
        return str(directory / f"{stem}_{account_key}{suffix}")

    def auth_state_path_for_driver(
        self,
        client_id: int,
        driver_id: int,
        username: str | None = None,
        national_code: str | None = None,
        fallback: str | None = None,
    ) -> str:
        """Return the canonical auth-state path for a driver under a tenant.

        This must match the path used by the worker in waybill_worker.py so that
        reconciliation and other orchestrator tasks find the same session data.
        """
        scope = f"client-{client_id}-driver-{driver_id}"
        return self.auth_state_path_for_account(
            username=username,
            national_code=national_code,
            fallback=fallback,
            scope=scope,
        )

    def default_auth_state_path(self) -> str:
        return str(Path(utcms_config.AUTH_STATE_PATH))

    def _redis_key_from_path(self, path: str | None) -> str | None:
        if not path:
            return None
        filename = Path(path).stem
        return f"session:auth_state:{filename}"

    async def async_auth_state_exists(self, path: str | None) -> bool:
        if not path:
            return False
        redis_client = await redis_manager.get()
        if not redis_client:
            raise RuntimeError("Redis is not available (fail-closed)")

        key = self._redis_key_from_path(path)
        try:
            exists = await redis_client.exists(key)
            if not exists:
                return False

            raw = await redis_client.get(key)
            if not raw:
                return False

            data = json.loads(raw)
            playwright_state = data.get("playwright_state")
            if not playwright_state:
                return False

            return True
        except Exception as e:
            logger.error(f"Redis session vault check failed: {e}", exc_info=True)
            raise RuntimeError(f"Session vault access error (fail-closed): {e}") from e

    def auth_state_exists(self, path: str | None) -> bool:
        if not path:
            return False
        return run_async(self.async_auth_state_exists(path))

    async def restore_auth_state_to_file(self, path: str | None) -> bool:
        if not path:
            return False
        redis_client = await redis_manager.get()
        if not redis_client:
            raise RuntimeError("Redis is not available (fail-closed)")

        key = self._redis_key_from_path(path)
        try:
            raw = await redis_client.get(key)
            if not raw:
                return False

            data = json.loads(raw)
            playwright_state = data.get("playwright_state")
            if not playwright_state:
                return False

            self.ensure_parent_dir(path)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(playwright_state, f, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Redis session vault restore failed: {e}", exc_info=True)
            raise RuntimeError(f"Session vault access error (fail-closed): {e}") from e

    def restore_auth_state_to_file_sync(self, path: str | None) -> bool:
        if not path:
            return False
        return run_async(self.restore_auth_state_to_file(path))

    def ensure_parent_dir(self, path: str) -> None:
        directory = Path(path).parent
        directory.mkdir(parents=True, exist_ok=True)

    async def async_delete_auth_state(self, path: str | None) -> None:
        if not path:
            return
        redis_client = await redis_manager.get()
        if not redis_client:
            raise RuntimeError("Redis is not available (fail-closed)")

        key = self._redis_key_from_path(path)
        try:
            await redis_client.delete(key)
        except Exception as e:
            logger.error(f"Redis session vault delete failed: {e}", exc_info=True)
            raise RuntimeError(f"Session vault delete error (fail-closed): {e}") from e

        try:
            Path(path).unlink(missing_ok=True)
        except Exception as exc:
            logger.debug(
                "session_vault_legacy_file_cleanup_skipped",
                extra={"extra_fields": {"path": path, "error": str(exc)}},
            )

    def delete_auth_state(self, path: str | None) -> None:
        if not path:
            return
        run_async(self.async_delete_auth_state(path))

    async def store_auth_state_from_file(self, path: str, session_version: int = 0, ttl: int | None = None) -> None:
        if not os.path.exists(path):
            return

        redis_client = await redis_manager.get()
        if not redis_client:
            raise RuntimeError("Redis is not available (fail-closed)")

        key = self._redis_key_from_path(path)
        with open(path, encoding="utf-8") as f:
            content = f.read()

        try:
            playwright_state = json.loads(content)
        except Exception as e:
            logger.error(f"Invalid auth state JSON content: {e}")
            return

        wrapper = {"session_version": session_version, "playwright_state": playwright_state}

        ttl = ttl or utcms_config.RPA_SESSION_TTL_SECONDS
        try:
            await redis_client.set(key, json.dumps(wrapper, ensure_ascii=False), ex=ttl)
        except Exception as e:
            logger.error(f"Redis session vault store failed: {e}", exc_info=True)
            raise RuntimeError(f"Session vault store error (fail-closed): {e}") from e

    async def async_get_session_version(self, path: str | None) -> int | None:
        if not path:
            return None
        redis_client = await redis_manager.get()
        if not redis_client:
            raise RuntimeError("Redis is not available (fail-closed)")

        key = self._redis_key_from_path(path)
        try:
            raw = await redis_client.get(key)
            if not raw:
                return None
            data = json.loads(raw)
            if isinstance(data, dict) and "session_version" in data:
                return data["session_version"]
            return None
        except Exception as e:
            logger.error(f"Redis session vault version check failed: {e}", exc_info=True)
            raise RuntimeError(f"Session vault access error (fail-closed): {e}") from e

    def get_session_version(self, path: str | None) -> int | None:
        if not path:
            return None
        return run_async(self.async_get_session_version(path))


session_vault = SessionVault()
