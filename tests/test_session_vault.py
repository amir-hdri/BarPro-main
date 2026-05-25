import unittest
from unittest.mock import patch

from app.services.session_vault import SessionVault


class TestSessionVault(unittest.TestCase):
    def test_auth_state_path_for_account_uses_username(self):
        with patch("app.core.config.utcms_config.AUTH_STATE_PATH", ".auth/utcms_state.json"):
            vault = SessionVault()
            path = vault.auth_state_path_for_account(username="09121234567")

        self.assertTrue(path.endswith("utcms_state_09121234567.json"))

    def test_auth_state_path_falls_back_to_national_code(self):
        with patch("app.core.config.utcms_config.AUTH_STATE_PATH", ".auth/utcms_state.json"):
            vault = SessionVault()
            path = vault.auth_state_path_for_account(national_code="1234567890")

        self.assertTrue(path.endswith("utcms_state_1234567890.json"))

    def test_build_account_key_sanitizes_value(self):
        vault = SessionVault()
        self.assertEqual(vault.build_account_key(username=" test user "), "test-user")
