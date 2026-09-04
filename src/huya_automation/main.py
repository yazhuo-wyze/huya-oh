"""Command-line entry point for opening the Huya room in Edge."""

from __future__ import annotations

import argparse
import asyncio
import sys

from dotenv import load_dotenv
from playwright.async_api import async_playwright

from .auth import Credentials, LoginError, ensure_logged_in, is_logged_in
from .edge import (
    EdgeConfig,
    EdgeError,
    connect_edge,
    ensure_debug_edge,
)
from .room import RoomError, ensure_theater_mode, find_or_open_room


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
        "--debug-port",
        type=int,
        default=9222,
        help="Edge CDP 远程调试端口，默认 9222。",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    config = EdgeConfig(debug_port=args.debug_port)
    await ensure_debug_edge(config, allow_restart=False)
    async with async_playwright() as playwright:
        browser = await connect_edge(playwright, config)
        page, reused = await find_or_open_room(browser)
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
        changed = await ensure_theater_mode(page, dry_run=args.dry_run)

        print(f"{'复用' if reused else '新建'}直播间标签页：{page.url}")
        if args.dry_run and login_needed:
            print("dry-run：当前未登录，正式运行时将打开账号密码登录框。")
        elif login_needed:
            print("账号密码登录成功。")
        else:
            print("当前已经登录。")
        if args.dry_run and changed:
            print("dry-run：当前不是剧场模式，正式运行时将自动进入。")
        elif changed:
            print("已进入剧场模式。")
        else:
            print("当前已经是剧场模式。")
        print("浏览器将保持打开。")
    return 0


def main() -> None:
    load_dotenv()
    args = parse_args()
    try:
        raise SystemExit(asyncio.run(run(args)))
    except (EdgeError, LoginError, RoomError) as error:
        print(f"错误：{error}", file=sys.stderr)
        raise SystemExit(2) from error
    except KeyboardInterrupt:
        print("\n已取消。", file=sys.stderr)
        raise SystemExit(130)


if __name__ == "__main__":
    main()
