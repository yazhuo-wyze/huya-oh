"""Huya live room tab selection and theater mode handling."""

from __future__ import annotations

import logging
from urllib.parse import urlsplit, urlunsplit

from playwright.async_api import Browser, Page, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)


TARGET_ROOM_URL = "https://www.huya.com/660002"
THEATER_BUTTON_SELECTOR = "#player-fullpage-btn"
THEATER_BODY_CLASS = "mode-page-theater"
SOUND_BUTTON_SELECTOR = "#player-sound-btn"
SOUND_OFF_CLASS = "player-sound-off"
DANMU_BUTTON_SELECTOR = "#player-danmu-btn"
DANMU_OFF_CLASS = "player-ctrl-switch-hide"


class RoomError(RuntimeError):
    """Raised when the live room cannot reach a known safe state."""


def canonical_url(url: str) -> str:
    parts = urlsplit(url)
    normalized_path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), normalized_path, "", "")
    )


def is_target_room(url: str, target_url: str = TARGET_ROOM_URL) -> bool:
    return canonical_url(url) == canonical_url(target_url)


async def find_or_open_room(
    browser: Browser,
    target_url: str = TARGET_ROOM_URL,
) -> tuple[Page, bool]:
    if not browser.contexts:
        raise RoomError("Edge 没有可用的浏览器上下文。")

    context = browser.contexts[0]
    for page in context.pages:
        if is_target_room(page.url, target_url):
            logger.info("找到已打开的目标直播间标签页")
            await page.bring_to_front()
            return page, True

    logger.info("未找到目标直播间，正在新建标签页")
    page = await context.new_page()
    await page.goto(target_url, wait_until="domcontentloaded", timeout=45_000)
    await page.bring_to_front()
    return page, False


async def wait_for_room(page: Page) -> None:
    try:
        await page.locator(THEATER_BUTTON_SELECTOR).wait_for(
            state="attached", timeout=30_000
        )
    except PlaywrightTimeoutError as error:
        raise RoomError(
            "直播间已打开，但未找到剧场模式控件。页面可能尚未加载或结构已变化。"
        ) from error


async def is_theater_mode(page: Page) -> bool:
    body_classes = await page.locator("body").get_attribute("class") or ""
    if THEATER_BODY_CLASS in body_classes.split():
        return True
    title = await page.locator(THEATER_BUTTON_SELECTOR).get_attribute("title")
    return title == "退出剧场"


async def ensure_theater_mode(page: Page, *, dry_run: bool = False) -> bool:
    await wait_for_room(page)
    if await is_theater_mode(page):
        logger.info("剧场模式状态检查：已开启")
        return False
    if dry_run:
        logger.info("剧场模式状态检查：需要开启，dry-run 不点击")
        return True

    logger.info("正在进入剧场模式")
    button = page.locator(THEATER_BUTTON_SELECTOR)
    # Huya may place transient player controls over this button. Dispatching the
    # element's own click preserves site behavior without clicking by coordinates.
    await button.evaluate("(element) => element.click()")
    try:
        await page.wait_for_function(
            """className => document.body.classList.contains(className)
                || document.querySelector('#player-fullpage-btn')?.title === '退出剧场'""",
            arg=THEATER_BODY_CLASS,
            timeout=5_000,
        )
    except PlaywrightTimeoutError as error:
        raise RoomError("已点击剧场模式控件，但页面未进入剧场模式。") from error
    return True


async def is_room_muted(page: Page) -> bool:
    button_classes = (
        await page.locator(SOUND_BUTTON_SELECTOR).get_attribute("class") or ""
    )
    if SOUND_OFF_CLASS in button_classes.split():
        return True

    media = page.locator("video, audio")
    if await media.count() == 0:
        return False
    return await media.evaluate_all(
        "(elements) => elements.every((item) => item.muted || item.volume === 0)"
    )


async def ensure_room_muted(page: Page, *, dry_run: bool = False) -> bool:
    await wait_for_room(page)
    button = page.locator(SOUND_BUTTON_SELECTOR)
    try:
        await button.wait_for(state="attached", timeout=10_000)
    except PlaywrightTimeoutError as error:
        raise RoomError(
            "直播间已打开，但未找到音量控件。页面结构可能已变化。"
        ) from error

    if await is_room_muted(page):
        logger.info("直播声音状态检查：已静音")
        return False
    if dry_run:
        logger.info("直播声音状态检查：有声音，dry-run 不点击")
        return True

    logger.info("检测到直播声音，正在静音")
    await button.evaluate("(element) => element.click()")
    try:
        await page.wait_for_function(
            """([selector, offClass]) => {
                const button = document.querySelector(selector);
                const media = [...document.querySelectorAll('video, audio')];
                return button?.classList.contains(offClass)
                    || (media.length > 0
                        && media.every((item) => item.muted || item.volume === 0));
            }""",
            arg=[SOUND_BUTTON_SELECTOR, SOUND_OFF_CLASS],
            timeout=5_000,
        )
    except PlaywrightTimeoutError as error:
        raise RoomError("已点击音量控件，但直播间仍然有声音。") from error
    return True


async def is_player_danmu_disabled(page: Page) -> bool:
    button = page.locator(DANMU_BUTTON_SELECTOR)
    button_classes = await button.get_attribute("class") or ""
    if DANMU_OFF_CLASS in button_classes.split():
        return True
    return await button.get_attribute("title") == "开启弹幕"


async def ensure_player_danmu_disabled(
    page: Page,
    *,
    dry_run: bool = False,
) -> bool:
    await wait_for_room(page)
    button = page.locator(DANMU_BUTTON_SELECTOR)
    try:
        await button.wait_for(state="attached", timeout=10_000)
    except PlaywrightTimeoutError as error:
        raise RoomError(
            "直播间已打开，但未找到播放器弹幕开关。页面结构可能已变化。"
        ) from error

    if await is_player_danmu_disabled(page):
        logger.info("播放器弹幕状态检查：已关闭")
        return False
    if dry_run:
        logger.info("播放器弹幕状态检查：已开启，dry-run 不点击")
        return True

    logger.info("检测到播放器弹幕，正在关闭")
    await button.evaluate("(element) => element.click()")
    try:
        await page.wait_for_function(
            """([selector, offClass]) => {
                const button = document.querySelector(selector);
                return button?.classList.contains(offClass)
                    || button?.title === '开启弹幕';
            }""",
            arg=[DANMU_BUTTON_SELECTOR, DANMU_OFF_CLASS],
            timeout=5_000,
        )
    except PlaywrightTimeoutError as error:
        raise RoomError("已点击弹幕开关，但播放器弹幕仍然开启。") from error
    return True
