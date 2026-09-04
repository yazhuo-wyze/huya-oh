"""Automation for Huya's free-ad lucky event flow."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Frame, Locator, Page


LUCKY_ENTRY_SELECTOR = ".player-lucky-burst-icon"
ROUND_COUNTDOWN_PATTERN = re.compile(r"^\d{1,2}:\d{2}$")
LUCKY_VALUE_PATTERN = re.compile(r"累计幸运值\s*[^\d]*(\d+)")
ACTIVITY_TEXT = "欧皇时刻"
FREE_DRAW_TEXT = "免费抽"
FREE_PARTICIPATE_TEXT = "看视频免费参与"
AD_COMPLETE_TEXT = "恭喜完成任务"


class LuckyEventError(RuntimeError):
    """Raised when an active lucky event reaches an unknown state."""


@dataclass(frozen=True)
class LuckyEventConfig:
    poll_seconds: float = 15.0
    ad_poll_seconds: float = 1.0
    target_lucky_value: int = 200
    panel_timeout_seconds: float = 10.0
    ad_timeout_seconds: float = 180.0


async def is_lucky_round_active(page: Page) -> bool:
    entry = page.locator(LUCKY_ENTRY_SELECTOR)
    if not await entry.is_visible():
        return False
    return is_active_round_text(await entry.inner_text())


def is_active_round_text(text: str) -> bool:
    return bool(ROUND_COUNTDOWN_PATTERN.fullmatch(text.strip()))


async def open_lucky_event(page: Page) -> bool:
    if not await is_lucky_round_active(page):
        return False
    await page.locator(LUCKY_ENTRY_SELECTOR).evaluate(
        "(element) => element.click()"
    )
    return True


async def find_activity_frame(page: Page) -> Frame | None:
    for frame in page.frames:
        try:
            body_text = await frame.locator("body").inner_text(timeout=500)
        except PlaywrightError:
            continue
        if ACTIVITY_TEXT in body_text and (
            "累计幸运值" in body_text or FREE_PARTICIPATE_TEXT in body_text
        ):
            return frame
    return None


def parse_lucky_value(text: str) -> int | None:
    match = LUCKY_VALUE_PATTERN.search(text)
    return int(match.group(1)) if match else None


async def read_lucky_value(frame: Frame) -> int:
    body_text = await frame.locator("body").inner_text()
    value = parse_lucky_value(body_text)
    if value is None:
        raise LuckyEventError("活动面板中未找到累计幸运值。")
    return value


async def first_visible_text(
    page: Page,
    text: str,
) -> tuple[Frame, Locator] | None:
    for frame in page.frames:
        locator = frame.get_by_text(text, exact=False)
        for index in range(await locator.count()):
            candidate = locator.nth(index)
            if await candidate.is_visible():
                return frame, candidate
    return None


async def select_free_draw(frame: Frame) -> None:
    locator = frame.get_by_text(FREE_DRAW_TEXT, exact=False)
    for index in range(await locator.count()):
        candidate = locator.nth(index)
        if await candidate.is_visible():
            await candidate.click()
            return
    raise LuckyEventError("本轮活动没有可用的“免费抽”入口。")


async def start_free_ad(frame: Frame) -> None:
    locator = frame.get_by_text(FREE_PARTICIPATE_TEXT, exact=False)
    for index in range(await locator.count()):
        candidate = locator.nth(index)
        if await candidate.is_visible() and await candidate.is_enabled():
            await candidate.click()
            return
    raise LuckyEventError("本轮活动无法继续通过广告免费参与。")


async def wait_for_ad_completion(
    page: Page,
    config: LuckyEventConfig,
) -> bool:
    elapsed = 0.0
    while elapsed < config.ad_timeout_seconds:
        completed = await first_visible_text(page, AD_COMPLETE_TEXT)
        if completed is not None:
            _, button = completed
            await button.click()
            return True
        if not await is_lucky_round_active(page):
            return False
        await asyncio.sleep(config.ad_poll_seconds)
        elapsed += config.ad_poll_seconds
    raise LuckyEventError("等待广告完成超时，已停止本轮自动操作。")


async def wait_for_activity_frame(
    page: Page,
    config: LuckyEventConfig,
) -> Frame | None:
    elapsed = 0.0
    while elapsed < config.panel_timeout_seconds:
        frame = await find_activity_frame(page)
        if frame is not None:
            return frame
        if not await is_lucky_round_active(page):
            return None
        await asyncio.sleep(0.5)
        elapsed += 0.5
    raise LuckyEventError("活动入口已开启，但活动面板未能加载。")


async def participate_current_round(
    page: Page,
    config: LuckyEventConfig,
    *,
    dry_run: bool = False,
) -> int | None:
    if not await is_lucky_round_active(page):
        return None
    if dry_run:
        return None
    if not await open_lucky_event(page):
        return None

    frame = await wait_for_activity_frame(page, config)
    while frame is not None and await is_lucky_round_active(page):
        lucky_value = await read_lucky_value(frame)
        print(f"当前累计幸运值：{lucky_value}/{config.target_lucky_value}")
        if lucky_value >= config.target_lucky_value:
            return lucky_value

        await select_free_draw(frame)
        await start_free_ad(frame)
        if not await wait_for_ad_completion(page, config):
            return lucky_value

        frame = await wait_for_activity_frame(page, config)
    return None


async def monitor_lucky_event(
    page: Page,
    config: LuckyEventConfig | None = None,
    *,
    dry_run: bool = False,
) -> None:
    config = config or LuckyEventConfig()
    previous_active = False
    while True:
        active = await is_lucky_round_active(page)
        if active and not previous_active:
            if dry_run:
                print("dry-run：检测到欧皇时刻活动，不执行点击。")
            else:
                print("检测到欧皇时刻活动，开始免费广告累计幸运值。")
                await participate_current_round(page, config)
                print("本轮免费广告流程结束，继续等待下一轮。")
        previous_active = active
        if not active:
            previous_active = False
        await asyncio.sleep(config.poll_seconds)
