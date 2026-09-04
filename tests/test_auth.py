import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from huya_automation.auth import Credentials, LoginError, ensure_logged_in


class CredentialsTest(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_returns_none_without_environment_variables(self) -> None:
        self.assertIsNone(Credentials.from_environment())

    @patch.dict(os.environ, {"HUYA_USERNAME": "user"}, clear=True)
    def test_rejects_partial_credentials(self) -> None:
        with self.assertRaises(LoginError):
            Credentials.from_environment()

    @patch("huya_automation.auth.getpass.getpass", return_value="secret")
    @patch("builtins.input", return_value="user")
    def test_prompts_without_exposing_password(
        self,
        _input: unittest.mock.Mock,
        _getpass: unittest.mock.Mock,
    ) -> None:
        credentials = Credentials.prompt()

        self.assertEqual(credentials.username, "user")
        self.assertEqual(credentials.password, "secret")


class LoginStateTest(unittest.IsolatedAsyncioTestCase):
    async def test_logged_in_does_not_require_credentials(self) -> None:
        login_link = MagicMock()
        login_link.is_visible = AsyncMock(return_value=False)
        page = MagicMock()
        page.get_by_role.return_value = login_link

        changed = await ensure_logged_in(page, credentials=None)

        self.assertFalse(changed)

    async def test_dry_run_reports_login_without_opening_dialog(self) -> None:
        login_link = MagicMock()
        login_link.is_visible = AsyncMock(return_value=True)
        page = MagicMock()
        page.get_by_role.return_value = login_link

        changed = await ensure_logged_in(page, credentials=None, dry_run=True)

        self.assertTrue(changed)
        login_link.click.assert_not_called()


if __name__ == "__main__":
    unittest.main()
