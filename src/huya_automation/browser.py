"""Cross-platform Chromium browser selection, lifecycle, and CDP connection."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from playwright.async_api import Browser, Playwright

logger = logging.getLogger(__name__)


class BrowserError(RuntimeError):
    """Raised when no supported browser can be safely started or connected."""


@dataclass(frozen=True)
class BrowserConfig:
    display_name: str
    product_marker: str
    executable: Path
    user_data_dir: Path
    log_file: Path
    platform_name: str
    debug_host: str = "127.0.0.1"
    debug_port: int = 9222
    startup_timeout_seconds: float = 20.0

    @property
    def cdp_http_url(self) -> str:
        return f"http://{self.debug_host}:{self.debug_port}"


def default_automation_data_root(
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    system = platform_name or platform.system()
    environment = os.environ if environ is None else environ
    if system == "Darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Huya Automation"
        )
    if system == "Windows":
        local_app_data = environment.get("LOCALAPPDATA")
        if not local_app_data:
            local_app_data = str(Path.home() / "AppData" / "Local")
        return Path(local_app_data) / "Huya Automation"
    raise BrowserError(f"不支持的操作系统：{system}。目前仅支持 macOS 和 Windows。")


def default_browser_executables(
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    system = platform_name or platform.system()
    environment = os.environ if environ is None else environ
    if system == "Darwin":
        return (
            (
                Path(
                    "/Applications/Microsoft Edge.app/Contents/MacOS/"
                    "Microsoft Edge"
                ),
            ),
            (
                Path(
                    "/Applications/Google Chrome.app/Contents/MacOS/"
                    "Google Chrome"
                ),
            ),
        )
    if system == "Windows":
        program_files = environment.get("PROGRAMFILES")
        program_files_x86 = environment.get("PROGRAMFILES(X86)")
        program_files_64 = environment.get("PROGRAMW6432")
        local_app_data = environment.get("LOCALAPPDATA")
        edge_roots = (
            program_files_x86,
            program_files_64,
            program_files,
            local_app_data,
        )
        chrome_roots = (
            program_files_64,
            program_files,
            program_files_x86,
            local_app_data,
        )
        edge = tuple(
            Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            for root in edge_roots
            if root
        )
        chrome = tuple(
            Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe"
            for root in chrome_roots
            if root
        )
        return edge, chrome
    raise BrowserError(f"不支持的操作系统：{system}。目前仅支持 macOS 和 Windows。")


def first_installed(paths: Sequence[Path]) -> Path | None:
    return next((path for path in paths if path.is_file()), None)


def select_browser_config(
    *,
    debug_port: int = 9222,
    edge_executable: Path | None = None,
    chrome_executable: Path | None = None,
    data_root: Path | None = None,
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> BrowserConfig:
    system = platform_name or platform.system()
    default_edge, default_chrome = default_browser_executables(
        system,
        environ,
    )
    edge_paths = (edge_executable,) if edge_executable else default_edge
    chrome_paths = (chrome_executable,) if chrome_executable else default_chrome
    root = data_root or default_automation_data_root(system, environ)
    candidates = (
        (
            "Microsoft Edge",
            "Edg/",
            first_installed(edge_paths),
            root / "Edge",
            root / "edge-debug.log",
        ),
        (
            "Google Chrome",
            "Chrome/",
            first_installed(chrome_paths),
            root / "Chrome",
            root / "chrome-debug.log",
        ),
    )
    for display_name, marker, executable, profile, log_file in candidates:
        if executable is not None:
            return BrowserConfig(
                display_name=display_name,
                product_marker=marker,
                executable=executable,
                user_data_dir=profile,
                log_file=log_file,
                platform_name=system,
                debug_port=debug_port,
            )
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


def read_process_commands(platform_name: str) -> list[str]:
    if platform_name == "Darwin":
        command = ["ps", "-ax", "-o", "command="]
    elif platform_name == "Windows":
        command = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
            "Get-CimInstance Win32_Process | "
            "ForEach-Object { $_.CommandLine }",
        ]
    else:
        raise BrowserError(f"不支持的操作系统：{platform_name}")
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise BrowserError(f"无法读取浏览器进程列表：{error}") from error
    return result.stdout.splitlines()


def process_commands_include_browser(
    config: BrowserConfig,
    commands: Sequence[str],
) -> bool:
    executable = str(config.executable).casefold()
    profile_argument = f"--user-data-dir={config.user_data_dir}".casefold()
    return any(
        executable in command.casefold()
        and profile_argument in command.casefold()
        for command in commands
    )


def is_browser_running(config: BrowserConfig) -> bool:
    """Detect the selected browser process that owns this automation profile."""
    return process_commands_include_browser(
        config,
        read_process_commands(config.platform_name),
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


def launch_debug_browser(config: BrowserConfig) -> None:
    if not config.executable.is_file():
        raise BrowserError(f"未找到 {config.display_name}：{config.executable}")
    config.user_data_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "启动自动化 %s，用户目录：%s",
        config.display_name,
        config.user_data_dir,
    )

    process_options: dict[str, object]
    if config.platform_name == "Windows":
        process_options = {
            "creationflags": (
                getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            ),
        }
    else:
        process_options = {"start_new_session": True}

    try:
        log_file = config.log_file.open("a", encoding="utf-8")
    except OSError as error:
        raise BrowserError(
            f"无法打开浏览器日志文件 {config.log_file}：{error}"
        ) from error
    try:
        try:
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
                **process_options,
            )
        except OSError as error:
            raise BrowserError(
                f"无法启动 {config.display_name}：{error}"
            ) from error
    finally:
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
