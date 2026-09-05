"""Command-line entry point for opening the Huya room in Edge."""

from __future__ import annotations

import argparse
import asyncio
import logging

from dotenv import load_dotenv
from playwright.async_api import async_playwright

from .auth import Credentials, LoginError, ensure_logged_in, is_logged_in
from .edge import (
    EdgeConfig,
    EdgeError,
    connect_edge,
    ensure_debug_edge,
)
from .lucky_event import LuckyEventError, monitor_lucky_event
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
        description="使用本机 Microsoft Edge 打开虎牙直播间并进入剧场模式。"
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
    parser.add_argument(
        "--debug-port",
        type=int,
        default=9222,
        help="Edge CDP 远程调试端口，默认 9222。",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    config = EdgeConfig(debug_port=args.debug_port)
    logger.info("启动虎牙直播间自动化，dry_run=%s", args.dry_run)
    logger.info("检查自动化 Edge，CDP 地址：%s", config.cdp_http_url)
    await ensure_debug_edge(config, allow_restart=False)
    async with async_playwright() as playwright:
        logger.info("正在连接 Microsoft Edge")
        browser = await connect_edge(playwright, config)
        page, reused = await find_or_open_room(browser)
        logger.info(
            "%s直播间标签页：%s",
            "复用" if reused else "新建",
            page.url,
        )
        credentials = Credentials.from_environment()
        if (
            credentials is None
            and not args.dry_run
            and not await is_logged_in(page)
        ):
            credentials = await asyncio.to_thread(Credentials.prompt)
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
        if args.dry_run and muted:
            logger.info("dry-run：当前直播间有声音，正式运行时将自动静音")
        elif muted:
            logger.info("已静音直播间")
        else:
            logger.info("当前直播间已经静音")
        if args.dry_run and danmu_disabled:
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
    configure_logging()
    load_dotenv()
    args = parse_args()
    try:
        raise SystemExit(asyncio.run(run(args)))
    except (EdgeError, LoginError, LuckyEventError, RoomError) as error:
        logger.error("%s", error)
        raise SystemExit(2) from error
    except KeyboardInterrupt:
        logger.info("用户已停止程序")
        raise SystemExit(130)


if __name__ == "__main__":
    main()
