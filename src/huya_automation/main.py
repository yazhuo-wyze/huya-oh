"""Command-line entry point for opening the Huya room in a local browser."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from playwright.async_api import async_playwright

from .accounts import (
    DEFAULT_CONFIG_FILE,
    AccountConfig,
    AccountConfigError,
    find_account,
    load_accounts,
)
from .auth import Credentials, LoginError, ensure_logged_in
from .browser import (
    BrowserError,
    connect_browser,
    ensure_debug_browser,
    resolve_debug_browser_config,
    select_browser_config,
)
from .lucky_event import LuckyEventError, monitor_lucky_event
from .instance_lock import InstanceLockError, acquire_instance_lock
from .logging_config import configure_logging
from .room import (
    RoomError,
    ensure_player_danmu_disabled,
    ensure_room_muted,
    ensure_theater_mode,
    find_or_open_room,
)

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="使用本机 Edge 或 Chrome 打开虎牙直播间并进入剧场模式。"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="检查并报告操作，但不切换剧场模式。",
    )
    parser.add_argument(
        "--no-monitor",
        action="store_true",
        help="完成直播间初始化后退出，不持续检测欧皇时刻活动。",
    )
    account_group = parser.add_mutually_exclusive_group()
    account_group.add_argument(
        "--account",
        help="运行 config.toml 中指定的账号 ID。",
    )
    account_group.add_argument(
        "--all-accounts",
        action="store_true",
        help="并行运行 config.toml 中所有 enabled=true 的账号。",
    )
    parser.add_argument(
        "--config-file",
        type=Path,
        default=DEFAULT_CONFIG_FILE,
        help="程序配置文件，默认 config.toml。",
    )
    return parser.parse_args()


def build_worker_command(
    args: argparse.Namespace,
    account: AccountConfig,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "huya_automation.main",
        "--account",
        account.account_id,
        "--config-file",
        str(args.config_file.resolve()),
    ]
    if args.dry_run:
        command.append("--dry-run")
    if args.no_monitor:
        command.append("--no-monitor")
    return command


async def stop_workers(workers: list[asyncio.subprocess.Process]) -> None:
    running = [worker for worker in workers if worker.returncode is None]
    for worker in running:
        worker.terminate()
    if not running:
        return
    try:
        await asyncio.wait_for(
            asyncio.gather(*(worker.wait() for worker in running)),
            timeout=5.0,
        )
    except asyncio.TimeoutError:
        for worker in running:
            if worker.returncode is None:
                worker.kill()
        await asyncio.gather(*(worker.wait() for worker in running))


async def run_all_accounts(
    args: argparse.Namespace,
    accounts: list[AccountConfig],
) -> int:
    enabled_accounts = [account for account in accounts if account.enabled]
    if not enabled_accounts:
        raise AccountConfigError("账号配置中没有 enabled=true 的账号。")

    workers: list[tuple[AccountConfig, asyncio.subprocess.Process]] = []
    failed_accounts: set[str] = set()
    logger.info("准备并行启动 %d 个账号", len(enabled_accounts))
    try:
        for account in enabled_accounts:
            logger.info(
                "启动账号 %s",
                account.account_id,
            )
            try:
                worker = await asyncio.create_subprocess_exec(
                    *build_worker_command(args, account)
                )
            except OSError as error:
                failed_accounts.add(account.account_id)
                logger.error(
                    "账号 %s 工作进程启动失败：%s",
                    account.account_id,
                    error,
                )
                continue
            workers.append((account, worker))
            await asyncio.sleep(0.5)
            if worker.returncode is not None:
                if worker.returncode != 0:
                    failed_accounts.add(account.account_id)
                    logger.error(
                        "账号 %s 工作进程启动后退出，退出码：%d",
                        account.account_id,
                        worker.returncode,
                    )

        if not workers:
            return 2

        if args.no_monitor:
            return_codes = await asyncio.gather(
                *(worker.wait() for _, worker in workers)
            )
            failed_accounts.update(
                account.account_id
                for (account, _), return_code in zip(
                    workers,
                    return_codes,
                    strict=True,
                )
                if return_code != 0
            )
        else:
            reported_accounts = set(failed_accounts)
            while any(worker.returncode is None for _, worker in workers):
                for account, worker in workers:
                    if (
                        worker.returncode is not None
                        and account.account_id not in reported_accounts
                    ):
                        reported_accounts.add(account.account_id)
                        if worker.returncode != 0:
                            failed_accounts.add(account.account_id)
                            logger.error(
                                "账号 %s 工作进程意外退出，退出码：%d；"
                                "其他账号继续运行",
                                account.account_id,
                                worker.returncode,
                            )
                await asyncio.sleep(0.5)
            for account, worker in workers:
                if (
                    worker.returncode != 0
                    and account.account_id not in reported_accounts
                ):
                    failed_accounts.add(account.account_id)
                    logger.error(
                        "账号 %s 工作进程意外退出，退出码：%d",
                        account.account_id,
                        worker.returncode,
                    )
    except asyncio.CancelledError:
        logger.info("正在停止所有账号工作进程")
        raise
    finally:
        await stop_workers([worker for _, worker in workers])

    if failed_accounts:
        logger.error(
            "以下账号运行失败：%s",
            ", ".join(sorted(failed_accounts)),
        )
        return 2
    return 0


async def run(
    args: argparse.Namespace,
    account: AccountConfig,
) -> int:
    config = select_browser_config(
        debug_port=0,
        account_id=account.storage_id,
    )
    config = resolve_debug_browser_config(config)
    logger.info("启动虎牙直播间自动化，dry_run=%s", args.dry_run)
    config = await ensure_debug_browser(config, allow_restart=False)
    logger.info(
        "已选择 %s，CDP 地址：%s",
        config.display_name,
        config.cdp_http_url,
    )
    async with async_playwright() as playwright:
        logger.info("正在连接 %s", config.display_name)
        browser = await connect_browser(playwright, config)
        page, reused = await find_or_open_room(browser)
        logger.info(
            "%s直播间标签页：%s",
            "复用" if reused else "新建",
            page.url,
        )
        credentials = (
            Credentials(
                username=account.username,
                password=account.password,
            )
            if account.username is not None and account.password is not None
            else None
        )
        login_needed = await ensure_logged_in(
            page,
            credentials,
            dry_run=args.dry_run,
        )
        muted = await ensure_room_muted(page, dry_run=args.dry_run)
        danmu_disabled = await ensure_player_danmu_disabled(
            page,
            dry_run=args.dry_run,
        )
        changed = await ensure_theater_mode(page, dry_run=args.dry_run)

        if args.dry_run and login_needed:
            logger.info("dry-run：当前未登录，正式运行时将打开登录框")
        elif login_needed:
            logger.info("账号密码登录成功")
        else:
            logger.info("当前已经登录")
        if muted is None:
            logger.warning("直播间静音状态未确认")
        elif args.dry_run and muted:
            logger.info("dry-run：当前直播间有声音，正式运行时将自动静音")
        elif muted:
            logger.info("已静音直播间")
        else:
            logger.info("当前直播间已经静音")
        if danmu_disabled is None:
            logger.warning("播放器弹幕关闭状态未确认")
        elif args.dry_run and danmu_disabled:
            logger.info("dry-run：播放器弹幕已开启，正式运行时将自动关闭")
        elif danmu_disabled:
            logger.info("已关闭播放器弹幕")
        else:
            logger.info("播放器弹幕已经关闭")
        if args.dry_run and changed:
            logger.info("dry-run：当前不是剧场模式，正式运行时将自动进入")
        elif changed:
            logger.info("已进入剧场模式")
        else:
            logger.info("当前已经是剧场模式")
        if args.no_monitor:
            logger.info("初始化完成，不启动活动监控，浏览器将保持打开")
        else:
            logger.info("开始每 5–10 秒检测欧皇时刻活动，按 Ctrl+C 停止")
            await monitor_lucky_event(page, dry_run=args.dry_run)
    return 0


def main() -> None:
    args = parse_args()
    log_account = (
        args.account
        if args.account is not None
        else "supervisor"
    )
    configure_logging(log_account)
    lock_file = None
    try:
        accounts = load_accounts(args.config_file)
        account = None
        if args.account is not None:
            account = find_account(accounts, args.account)

        lock_file = acquire_instance_lock(
            account_id=account.storage_id if account is not None else None,
            supervisor=account is None,
        )
        if account is None:
            exit_code = asyncio.run(run_all_accounts(args, accounts))
        else:
            exit_code = asyncio.run(run(args, account))
        raise SystemExit(exit_code)
    except (
        AccountConfigError,
        BrowserError,
        InstanceLockError,
        LoginError,
        LuckyEventError,
        RoomError,
    ) as error:
        logger.error("%s", error)
        raise SystemExit(2) from error
    except KeyboardInterrupt:
        logger.info("用户已停止程序")
        raise SystemExit(130)
    finally:
        if lock_file is not None:
            lock_file.close()


if __name__ == "__main__":
    main()
