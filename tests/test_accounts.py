import tempfile
import unittest
from pathlib import Path

from huya_automation.accounts import (
    AccountConfig,
    AccountConfigError,
    find_account,
    load_accounts,
)


class AccountIdTest(unittest.TestCase):
    def test_uses_username_as_id_and_safe_hash_for_storage(self) -> None:
        account = AccountConfig("user@example.com")

        self.assertEqual(account.account_id, "user@example.com")
        self.assertRegex(account.storage_id, r"^account-[0-9a-f]{16}$")
        self.assertNotIn("@", account.storage_id)


class AccountFileTest(unittest.TestCase):
    def write_config(self, directory: str, content: str) -> Path:
        path = Path(directory) / "config.toml"
        path.write_text(content, encoding="utf-8")
        return path

    def test_loads_accounts_and_enabled_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(
                directory,
                """
[[accounts]]
username = "account-a"

[[accounts]]
username = "account-b"
enabled = false
""",
            )

            accounts = load_accounts(path)

            self.assertFalse(accounts[1].enabled)
            self.assertEqual(find_account(accounts, "account-b"), accounts[1])

    def test_rejects_duplicate_usernames(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(
                directory,
                """
[[accounts]]
username = "same"
[[accounts]]
username = "same"
""",
            )

            with self.assertRaises(AccountConfigError):
                load_accounts(path)

    def test_loads_account_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(
                directory,
                """
[[accounts]]
username = " account-user "
password = "account-secret"
""",
            )

            account = load_accounts(path)[0]

            self.assertEqual(account.username, "account-user")
            self.assertEqual(account.password, "account-secret")

    def test_allows_omitting_password_for_existing_login(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(
                directory,
                """
[[accounts]]
username = "user"
""",
            )

            account = load_accounts(path)[0]

            self.assertIsNone(account.password)

    def test_rejects_missing_username(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(
                directory,
                """
[[accounts]]
enabled = true
""",
            )

            with self.assertRaises(AccountConfigError):
                load_accounts(path)

    def test_rejects_unknown_account_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(
                directory,
                """
[[accounts]]
username = "user"
debug_port = 9222
""",
            )

            with self.assertRaises(AccountConfigError):
                load_accounts(path)

    def test_rejects_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(AccountConfigError):
                load_accounts(Path(directory) / "missing.toml")


if __name__ == "__main__":
    unittest.main()
