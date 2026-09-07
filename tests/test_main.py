import argparse
import asyncio
import unittest
from pathlib import Path
from unittest.mock import patch

from huya_automation.accounts import AccountConfig
from huya_automation.main import build_worker_command, run_all_accounts


class FakeWorker:
    def __init__(self, returncode: int | None = None) -> None:
        self.returncode = returncode
        self.terminated = False
        self.killed = False

    async def wait(self) -> int:
        while self.returncode is None:
            await asyncio.sleep(0)
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


class WorkerCommandTest(unittest.TestCase):
    @patch("huya_automation.main.sys.executable", "/python")
    def test_builds_isolated_account_worker_command(self) -> None:
        args = argparse.Namespace(
            config_file=Path("settings/config.toml"),
            dry_run=True,
            no_monitor=True,
        )
        account = AccountConfig("account-a")

        command = build_worker_command(args, account)

        self.assertEqual(
            command,
            [
                "/python",
                "-m",
                "huya_automation.main",
                "--account",
                "account-a",
                "--config-file",
                str(Path("settings/config.toml").resolve()),
                "--dry-run",
                "--no-monitor",
            ],
        )


class AccountSupervisorTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.args = argparse.Namespace(
            config_file=Path("config.toml"),
            dry_run=False,
            no_monitor=False,
        )
        self.accounts = [
            AccountConfig("account-a"),
            AccountConfig("account-b"),
        ]

    async def test_keeps_other_workers_running_when_one_exits(self) -> None:
        failed = FakeWorker()
        running = FakeWorker()
        workers = [failed, running]
        create_calls = 0

        async def create_worker(*command: str) -> FakeWorker:
            nonlocal create_calls
            worker = workers[create_calls]
            create_calls += 1
            return worker

        sleep_calls = 0

        async def fail_after_start(delay: float) -> None:
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls == 3:
                failed.returncode = 2
            elif sleep_calls == 4:
                running.returncode = 0

        with (
            patch(
                "huya_automation.main.asyncio.create_subprocess_exec",
                side_effect=create_worker,
            ),
            patch(
                "huya_automation.main.asyncio.sleep",
                side_effect=fail_after_start,
            ),
        ):
            result = await run_all_accounts(self.args, self.accounts)

        self.assertEqual(result, 2)
        self.assertFalse(running.terminated)

    async def test_no_monitor_returns_zero_when_all_workers_succeed(
        self,
    ) -> None:
        self.args.no_monitor = True
        workers = [FakeWorker(0), FakeWorker(0)]
        create_calls = 0

        async def create_in_order(*command: str) -> FakeWorker:
            nonlocal create_calls
            worker = workers[create_calls]
            create_calls += 1
            return worker

        with (
            patch(
                "huya_automation.main.asyncio.create_subprocess_exec",
                side_effect=create_in_order,
            ),
            patch(
                "huya_automation.main.asyncio.sleep",
                return_value=None,
            ),
        ):
            result = await run_all_accounts(self.args, self.accounts)

        self.assertEqual(result, 0)

    async def test_cancellation_stops_all_workers(self) -> None:
        workers = [FakeWorker(), FakeWorker()]

        create_calls = 0

        async def create_in_order(*command: str) -> FakeWorker:
            nonlocal create_calls
            worker = workers[create_calls]
            create_calls += 1
            return worker

        sleep_calls = 0

        async def cancel_after_start(delay: float) -> None:
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls >= 3:
                raise asyncio.CancelledError

        with (
            patch(
                "huya_automation.main.asyncio.create_subprocess_exec",
                side_effect=create_in_order,
            ),
            patch(
                "huya_automation.main.asyncio.sleep",
                side_effect=cancel_after_start,
            ),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await run_all_accounts(self.args, self.accounts)

        self.assertTrue(all(worker.terminated for worker in workers))


if __name__ == "__main__":
    unittest.main()
