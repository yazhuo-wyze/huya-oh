"""Chromium browser selection, lifecycle, and CDP connection for macOS."""

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
DEFAULT_CHROME_EXECUTABLE = Path(
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
)
DEFAULT_AUTOMATION_DATA_ROOT = (
    Path.home() / "Library" / "Application Support" / "Huya Automation"
)


class BrowserError(RuntimeError):
    """Raised when no supported browser can be safely started or connected."""


@dataclass(frozen=True)
class BrowserConfig:
    display_name: str
    application_name: str
    product_marker: str
    executable: Path
    user_data_dir: Path
    log_file: Path
    debug_host: str = "127.0.0.1"
    debug_port: int = 9222
    startup_timeout_seconds: float = 20.0
    shutdown_timeout_seconds: float = 15.0

    @property
    def cdp_http_url(self) -> str:
        return f"http://{self.debug_host}:{self.debug_port}"


def select_browser_config(
    *,
    debug_port: int = 9222,
    edge_executable: Path = DEFAULT_EDGE_EXECUTABLE,
    chrome_executable: Path = DEFAULT_CHROME_EXECUTABLE,
    data_root: Path = DEFAULT_AUTOMATION_DATA_ROOT,
) -> BrowserConfig:
    candidates = (
        BrowserConfig(
            display_name="Microsoft Edge",
            application_name="Microsoft Edge",
            product_marker="Edg/",
            executable=edge_executable,
            user_data_dir=data_root / "Edge",
            log_file=Path("edge-debug.log"),
            debug_port=debug_port,
        ),
        BrowserConfig(
            display_name="Google Chrome",
            application_name="Google Chrome",
            product_marker="Chrome/",
            executable=chrome_executable,
            user_data_dir=data_root / "Chrome",
            log_file=Path("chrome-debug.log"),
            debug_port=debug_port,
        ),
    )
    for config in candidates:
        if config.executable.is_file():
            return config
    raise BrowserError(
        "未找到受支持的浏览器。请安装 Microsoft Edge 或 Google Chrome。"
    )


def read_cdp_version(config: BrowserConfig) -> dict[str, object] | None:
    try:
        with urllib.request.urlopen(
            f"{config.cdp_http_url}/json/version", timeout=1
        ) as response:
            payload = json.load(response)
        return payload if isinstance(payload, dict) else None
    except (OSError, ValueError, urllib.error.URLError):
        return None


def cdp_browser_matches(
    config: BrowserConfig,
    payload: dict[str, object],
) -> bool:
    identity = " ".join(
        str(payload.get(field, "")) for field in ("Browser", "User-Agent")
    )
    if config.product_marker == "Chrome/":
        return "Chrome/" in identity and "Edg/" not in identity
    return config.product_marker in identity


def is_cdp_ready(config: BrowserConfig) -> bool:
    """Return whether the selected browser exposes a valid local CDP endpoint."""
    payload = read_cdp_version(config)
    return bool(
        payload
        and payload.get("webSocketDebuggerUrl")
        and cdp_browser_matches(config, payload)
    )


def is_browser_running(config: BrowserConfig) -> bool:
    """Detect the selected browser process that owns this automation profile."""
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


def request_browser_quit(config: BrowserConfig) -> None:
    """Ask the selected browser to quit normally."""
    subprocess.run(
        [
            "osascript",
            "-e",
            f'tell application "{config.application_name}" to quit',
        ],
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


async def stop_regular_browser(config: BrowserConfig) -> None:
    request_browser_quit(config)
    stopped = await wait_until(
        lambda: is_browser_running(config),
        expected=False,
        timeout_seconds=config.shutdown_timeout_seconds,
    )
    if not stopped:
        raise BrowserError(
            f"{config.display_name} 未能在规定时间内退出，请手动关闭后重新运行。"
        )


def launch_debug_browser(config: BrowserConfig) -> None:
    if not config.executable.is_file():
        raise BrowserError(f"未找到 {config.display_name}：{config.executable}")
    config.user_data_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "启动自动化 %s，用户目录：%s",
        config.display_name,
        config.user_data_dir,
    )

    log_file = config.log_file.open("a", encoding="utf-8")
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


async def ensure_debug_browser(
    config: BrowserConfig,
    *,
    allow_restart: bool,
) -> None:
    payload = read_cdp_version(config)
    if payload and payload.get("webSocketDebuggerUrl"):
        if cdp_browser_matches(config, payload):
            logger.info("检测到可用的 %s CDP 服务", config.display_name)
            return
        occupied_by = payload.get("Browser", "其他浏览器")
        raise BrowserError(
            f"CDP 端口 {config.debug_port} 已被 {occupied_by} 占用，"
            "请关闭对应自动化浏览器或改用 --debug-port。"
        )

    if is_browser_running(config):
        if not allow_restart:
            raise BrowserError(
                f"自动化专用 {config.display_name} 正在运行，"
                "但未开放远程调试端口。"
            )
        raise BrowserError(
            f"自动化专用 {config.display_name} 状态异常，"
            "请关闭该窗口后重新运行。"
        )

    launch_debug_browser(config)
    logger.info("等待 %s CDP 服务就绪", config.display_name)
    ready = await wait_until(
        lambda: is_cdp_ready(config),
        expected=True,
        timeout_seconds=config.startup_timeout_seconds,
    )
    if not ready:
        raise BrowserError(
            f"{config.display_name} 已启动，但远程调试端口不可用。"
            f"程序不会复制或修改用户数据；详情见 {config.log_file}。"
        )
    logger.info("%s CDP 服务已就绪", config.display_name)


async def connect_browser(
    playwright: Playwright,
    config: BrowserConfig,
) -> Browser:
    try:
        browser = await playwright.chromium.connect_over_cdp(
            config.cdp_http_url
        )
        logger.info(
            "已连接 %s，共发现 %d 个浏览器上下文",
            config.display_name,
            len(browser.contexts),
        )
        return browser
    except Exception as error:
        raise BrowserError(
            f"无法通过 CDP 连接 {config.display_name}：{error}"
        ) from error
