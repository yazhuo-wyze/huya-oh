"""Microsoft Edge lifecycle and CDP connection management for macOS."""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from playwright.async_api import Browser, Playwright

logger = logging.getLogger(__name__)


DEFAULT_EDGE_EXECUTABLE = Path(
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
)
DEFAULT_EDGE_DATA_DIR = (
    Path.home()
    / "Library"
    / "Application Support"
    / "Huya Automation"
    / "Edge"
)


class EdgeError(RuntimeError):
    """Raised when Edge cannot be safely started or connected."""


@dataclass(frozen=True)
class EdgeConfig:
    executable: Path = DEFAULT_EDGE_EXECUTABLE
    user_data_dir: Path = DEFAULT_EDGE_DATA_DIR
    debug_host: str = "127.0.0.1"
    debug_port: int = 9222
    startup_timeout_seconds: float = 20.0
    shutdown_timeout_seconds: float = 15.0

    @property
    def cdp_http_url(self) -> str:
        return f"http://{self.debug_host}:{self.debug_port}"


def is_cdp_ready(config: EdgeConfig) -> bool:
    """Return whether a browser exposes a valid local CDP endpoint."""
    try:
        with urllib.request.urlopen(
            f"{config.cdp_http_url}/json/version", timeout=1
        ) as response:
            payload = json.load(response)
        return bool(payload.get("webSocketDebuggerUrl"))
    except (OSError, ValueError, urllib.error.URLError):
        return False


def is_edge_running(config: EdgeConfig) -> bool:
    """Detect the Edge process that owns this automation profile."""
    result = subprocess.run(
        ["ps", "-ax", "-o", "command="],
        check=True,
        capture_output=True,
        text=True,
    )
    executable = str(config.executable)
    profile_argument = f"--user-data-dir={config.user_data_dir}"
    return any(
        line.strip().startswith(f"{executable} ") and profile_argument in line
        for line in result.stdout.splitlines()
    )


def request_edge_quit() -> None:
    """Ask Edge to quit normally so the profile is not damaged."""
    subprocess.run(
        ["osascript", "-e", 'tell application "Microsoft Edge" to quit'],
        check=True,
        capture_output=True,
        text=True,
    )


async def wait_until(
    predicate: Callable[[], bool],
    expected: bool,
    timeout_seconds: float,
    interval_seconds: float = 0.25,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate() is expected:
            return True
        await asyncio.sleep(interval_seconds)
    return predicate() is expected


async def stop_regular_edge(config: EdgeConfig) -> None:
    request_edge_quit()
    stopped = await wait_until(
        lambda: is_edge_running(config),
        expected=False,
        timeout_seconds=config.shutdown_timeout_seconds,
    )
    if not stopped:
        raise EdgeError(
            "Edge 未能在规定时间内退出。请手动关闭 Edge 后重新运行。"
        )


def launch_debug_edge(config: EdgeConfig) -> None:
    if not config.executable.is_file():
        raise EdgeError(f"未找到 Microsoft Edge：{config.executable}")
    config.user_data_dir.mkdir(parents=True, exist_ok=True)
    logger.info("启动自动化 Edge，用户目录：%s", config.user_data_dir)

    log_file = Path("edge-debug.log").open("a", encoding="utf-8")
    subprocess.Popen(
        [
            str(config.executable),
            f"--remote-debugging-address={config.debug_host}",
            f"--remote-debugging-port={config.debug_port}",
            f"--user-data-dir={config.user_data_dir}",
            "--no-first-run",
        ],
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    log_file.close()


async def ensure_debug_edge(
    config: EdgeConfig,
    *,
    allow_restart: bool,
) -> None:
    if is_cdp_ready(config):
        logger.info("检测到可用的 Edge CDP 服务")
        return

    if is_edge_running(config):
        if not allow_restart:
            raise EdgeError(
                "自动化专用 Edge 正在运行，但未开放远程调试端口。"
            )
        raise EdgeError(
            "自动化专用 Edge 状态异常。请关闭该窗口后重新运行。"
        )

    launch_debug_edge(config)
    logger.info("等待 Edge CDP 服务就绪")
    ready = await wait_until(
        lambda: is_cdp_ready(config),
        expected=True,
        timeout_seconds=config.startup_timeout_seconds,
    )
    if not ready:
        raise EdgeError(
            "Edge 已启动，但远程调试端口不可用。新版 Edge 可能禁止默认用户"
            "目录启用远程调试。程序不会复制或修改用户数据；详情见 edge-debug.log。"
        )
    logger.info("Edge CDP 服务已就绪")


async def connect_edge(playwright: Playwright, config: EdgeConfig) -> Browser:
    try:
        browser = await playwright.chromium.connect_over_cdp(
            config.cdp_http_url
        )
        logger.info("已连接 Edge，共发现 %d 个浏览器上下文", len(browser.contexts))
        return browser
    except Exception as error:
        raise EdgeError(f"无法通过 CDP 连接 Edge：{error}") from error
