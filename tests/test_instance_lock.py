import tempfile
import unittest
from pathlib import Path

from huya_automation.accounts import AccountConfig
from huya_automation.instance_lock import (
    InstanceLockError,
    acquire_instance_lock,
    default_lock_file,
)


class InstanceLockPathTest(unittest.TestCase):
    def test_macos_lock_path(self) -> None:
        self.assertEqual(
            default_lock_file("Darwin", {}).parts[-4:],
            (
                "Library",
                "Application Support",
                "Huya Automation",
                "automation.lock",
            ),
        )

    def test_windows_lock_path(self) -> None:
        environment = {"LOCALAPPDATA": "C:/Users/test/AppData/Local"}

        self.assertEqual(
            default_lock_file("Windows", environment),
            Path("C:/Users/test/AppData/Local")
            / "Huya Automation"
            / "automation.lock",
        )

    def test_account_lock_path(self) -> None:
        account = AccountConfig("user@example.com")

        self.assertEqual(
            default_lock_file(
                "Darwin",
                {},
                account_id=account.storage_id,
            ).parts[-2:],
            ("locks", f"{account.storage_id}.lock"),
        )

    def test_supervisor_lock_does_not_collide_with_account(self) -> None:
        supervisor = default_lock_file("Darwin", {}, supervisor=True)
        account = default_lock_file(
            "Darwin",
            {},
            account_id="supervisor",
        )

        self.assertEqual(supervisor.name, "supervisor.lock")
        self.assertEqual(account.parts[-2:], ("locks", "supervisor.lock"))
        self.assertNotEqual(supervisor, account)


class InstanceLockBehaviorTest(unittest.TestCase):
    def test_rejects_second_process_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "automation.lock"
            first = acquire_instance_lock(lock_path)
            try:
                with self.assertRaises(InstanceLockError):
                    acquire_instance_lock(lock_path)
            finally:
                first.close()


if __name__ == "__main__":
    unittest.main()
