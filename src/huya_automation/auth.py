"""Huya authentication detection and account-password login."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from playwright.async_api import (
    Locator,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

logger = logging.getLogger(__name__)


LOGIN_IFRAME_SELECTOR = "#UDBSdkLgn_iframe"
USERNAME_SELECTOR = "#username"
PASSWORD_SELECTOR = "#password"
SUBMIT_SELECTOR = "#login-btn"


class LoginError(RuntimeError):
    """Raised when authentication requires manual intervention."""


@dataclass(frozen=True)
class Credentials:
    username: str
    password: str


async def any_locator_visible(locator: Locator) -> bool:
    """Check all matching elements without triggering Playwright strict mode."""
    for index in range(await locator.count()):
        if await locator.nth(index).is_visible():
            return True
    return False


async def is_logged_in(page: Page) -> bool:
    login_link = page.get_by_role("link", name="登录", exact=True)
    return not await login_link.is_visible()


async def open_login_dialog(page: Page) -> None:
    login_link = page.get_by_role("link", name="登录", exact=True)
    try:
        logger.info("当前未登录，正在打开账号密码登录框")
        await login_link.click(timeout=10_000)
        await page.frame_locator(LOGIN_IFRAME_SELECTOR).locator(
            USERNAME_SELECTOR
        ).wait_for(state="visible", timeout=15_000)
    except PlaywrightTimeoutError as error:
        raise LoginError("无法打开虎牙账号密码登录框，页面结构可能已变化。") from error


async def wait_for_login_result(page: Page, timeout_seconds: float = 20.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    login_frame = page.frame_locator(LOGIN_IFRAME_SELECTOR)
    captcha = login_frame.locator('input[placeholder="请输入验证码"]')

    while time.monotonic() < deadline:
        if await is_logged_in(page):
            logger.info("虎牙登录状态验证成功")
            return
        if await any_locator_visible(captcha):
            logger.warning("登录流程出现验证码，需要人工处理")
            raise LoginError(
                "登录需要验证码。登录框已保留，请人工完成验证后重新运行。"
            )
        await asyncio.sleep(0.5)

    raise LoginError(
        "账号密码已提交，但登录未完成。请在浏览器中检查提示或完成安全验证。"
    )


async def ensure_logged_in(
    page: Page,
    credentials: Credentials | None,
    *,
    dry_run: bool = False,
) -> bool:
    """Ensure the room is authenticated and return whether login was needed."""
    if await is_logged_in(page):
        logger.info("检测到已登录状态")
        return False

    if dry_run:
        logger.info("dry-run：检测到当前未登录")
        return True
    if credentials is None:
        raise LoginError(
            "当前未登录。请在 config.toml 中配置 username 和 password，"
            "或直接在自动化浏览器中手动登录。"
        )

    await open_login_dialog(page)
    logger.info("正在提交账号密码，日志不会记录凭据内容")
    login_frame = page.frame_locator(LOGIN_IFRAME_SELECTOR)
    await login_frame.locator(USERNAME_SELECTOR).fill(credentials.username)
    await login_frame.locator(PASSWORD_SELECTOR).fill(credentials.password)
    await login_frame.locator(SUBMIT_SELECTOR).click()
    await wait_for_login_result(page)
    return True
