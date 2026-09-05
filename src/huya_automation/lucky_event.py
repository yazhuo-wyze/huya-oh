"""Automation for Huya's free-ad lucky event flow."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Frame, Page

logger = logging.getLogger(__name__)


LUCKY_ENTRY_SELECTOR = ".player-lucky-burst-icon"
ACTIVITY_FRAME_PATH = "/hyfe/super_lucky_time/index.html"
LUCKY_VALUE_SELECTOR = ".luck-value"
FREE_DRAW_CARD_SELECTOR = ".list-item"
FREE_DRAW_TAG_SELECTOR = ".tag"
SELECTED_CARD_CLASS = "select-list-item"
PARTICIPATE_BUTTON_SELECTOR = ".btn"
AD_COMPLETE_SELECTOR = "#ext-ab-time"
BASE_COIN_BUTTON_SELECTOR = "button.return-gold"
BONUS_COIN_BUTTON_SELECTOR = "button.not-enough"
COIN_REWARD_SELECTOR = ".reward-container"
COIN_REWARD_VALUE_SELECTOR = ".reward-container .value"
COIN_CONFIRM_BUTTON_SELECTOR = ".reward-container button.btn"
ROUND_COUNTDOWN_PATTERN = re.compile(r"^\d{1,2}:\d{2}$")
LUCKY_VALUE_PATTERN = re.compile(r"累计幸运值\s*[^\d]*(\d+)")
BASE_COIN_PATTERN = re.compile(r"^只领(\d+)金币$")
BONUS_COIN_PATTERN = re.compile(r"^不够！再领(\d+)金币$")
FREE_DRAW_TEXT = "免费抽"
FREE_PARTICIPATE_TEXT = "看视频免费参与"
AD_COMPLETE_TEXT = "恭喜完成任务"
COIN_CONFIRM_TEXT = "开心收下"
COIN_TEXT = "金币"


class LuckyEventError(RuntimeError):
    """Raised when an active lucky event reaches an unknown state."""


@dataclass(frozen=True)
class LuckyEventConfig:
    poll_seconds: float = 15.0
    ad_poll_seconds: float = 1.0
    target_lucky_value: int = 200
    min_participation_seconds: int = 60
    panel_timeout_seconds: float = 10.0
    ad_timeout_seconds: float = 180.0


async def is_lucky_round_active(page: Page) -> bool:
    entry = page.locator(LUCKY_ENTRY_SELECTOR)
    if not await entry.is_visible():
        return False
    return is_active_round_text(await entry.inner_text())


def is_active_round_text(text: str) -> bool:
    return bool(ROUND_COUNTDOWN_PATTERN.fullmatch(text.strip()))


def parse_countdown_seconds(text: str) -> int | None:
    normalized = text.strip()
    if not ROUND_COUNTDOWN_PATTERN.fullmatch(normalized):
        return None
    minutes, seconds = (int(part) for part in normalized.split(":"))
    if seconds >= 60:
        return None
    return minutes * 60 + seconds


async def can_start_free_ad(page: Page, minimum_seconds: int) -> bool:
    entry = page.locator(LUCKY_ENTRY_SELECTOR)
    if not await entry.is_visible():
        return False
    remaining = parse_countdown_seconds(await entry.inner_text())
    return remaining is not None and remaining >= minimum_seconds


async def open_lucky_event(page: Page) -> bool:
    if not await is_lucky_round_active(page):
        return False
    if await find_activity_frame(page) is not None:
        return True
    await page.locator(LUCKY_ENTRY_SELECTOR).evaluate(
        "(element) => element.click()"
    )
    return True


async def find_activity_frame(page: Page) -> Frame | None:
    for frame in page.frames:
        if ACTIVITY_FRAME_PATH in frame.url:
            return frame
        try:
            body_text = await frame.locator("body").inner_text(timeout=500)
        except PlaywrightError:
            continue
        if "累计幸运值" in body_text and FREE_DRAW_TEXT in body_text:
            return frame
    return None


def parse_lucky_value(text: str) -> int | None:
    match = LUCKY_VALUE_PATTERN.search(text)
    return int(match.group(1)) if match else None


def is_safe_free_draw_card(card_text: str, tag_text: str) -> bool:
    normalized_card = " ".join(card_text.split())
    return (
        normalized_card.endswith(FREE_DRAW_TEXT)
        and tag_text.strip() == FREE_DRAW_TEXT
        and COIN_TEXT not in normalized_card
    )


def is_free_participate_button(text: str) -> bool:
    return " ".join(text.split()) == FREE_PARTICIPATE_TEXT


def parse_base_coin_amount(text: str) -> int | None:
    match = BASE_COIN_PATTERN.fullmatch(" ".join(text.split()))
    return int(match.group(1)) if match else None


def parse_bonus_coin_amount(text: str) -> int | None:
    match = BONUS_COIN_PATTERN.fullmatch(" ".join(text.split()))
    return int(match.group(1)) if match else None


async def read_lucky_value(frame: Frame) -> int:
    value_locator = frame.locator(LUCKY_VALUE_SELECTOR)
    if await value_locator.count():
        value_text = (await value_locator.first.inner_text()).strip()
        if value_text.isdigit():
            return int(value_text)

    value = parse_lucky_value(await frame.locator("body").inner_text())
    if value is None:
        raise LuckyEventError("活动面板中未找到累计幸运值。")
    return value


async def select_free_draw(frame: Frame) -> bool:
    cards = frame.locator(FREE_DRAW_CARD_SELECTOR).filter(has_text=FREE_DRAW_TEXT)
    for index in range(await cards.count()):
        card = cards.nth(index)
        if not await card.is_visible():
            continue
        text = " ".join((await card.inner_text()).split())
        tag = card.locator(FREE_DRAW_TAG_SELECTOR)
        if (
            await tag.count()
            and is_safe_free_draw_card(
                text,
                await tag.first.inner_text(),
            )
        ):
            logger.info("已定位安全的“免费抽”档位，正在选择")
            await card.click()
            classes = (await card.get_attribute("class") or "").split()
            selected = SELECTED_CARD_CLASS in classes
            if selected:
                logger.info("“免费抽”档位选择成功")
            return selected
    return False


async def start_free_ad(frame: Frame) -> bool:
    buttons = frame.locator(PARTICIPATE_BUTTON_SELECTOR)
    for index in range(await buttons.count()):
        button = buttons.nth(index)
        if not await button.is_visible():
            continue
        text = " ".join((await button.inner_text()).split())
        if is_free_participate_button(text) and await button.is_enabled():
            logger.info("正在点击“看视频免费参与”")
            await button.click()
            return True
        if COIN_TEXT in text:
            continue
    return False


async def wait_for_ad_completion(
    page: Page,
    config: LuckyEventConfig,
    *,
    stop_when_round_ends: bool = True,
) -> bool:
    elapsed = 0.0
    logger.info("等待广告播放完成，最长等待 %.0f 秒", config.ad_timeout_seconds)
    while elapsed < config.ad_timeout_seconds:
        for frame in page.frames:
            button = frame.locator(AD_COMPLETE_SELECTOR)
            if (
                await button.count()
                and await button.first.is_visible()
                and (await button.first.inner_text()).strip() == AD_COMPLETE_TEXT
            ):
                await button.first.click()
                logger.info("检测到“恭喜完成任务”，已点击完成")
                return True
        if stop_when_round_ends and not await is_lucky_round_active(page):
            return False
        await asyncio.sleep(config.ad_poll_seconds)
        elapsed += config.ad_poll_seconds
        if int(elapsed) > 0 and int(elapsed) % 5 == 0:
            logger.info("广告播放中，已等待 %.0f 秒", elapsed)
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


async def wait_for_lucky_value_increase(
    page: Page,
    previous_value: int,
    config: LuckyEventConfig,
) -> tuple[Frame | None, int]:
    elapsed = 0.0
    while elapsed < config.panel_timeout_seconds:
        if not await is_lucky_round_active(page):
            return None, previous_value
        frame = await find_activity_frame(page)
        if frame is not None:
            value = await read_lucky_value(frame)
            if value > previous_value:
                logger.info(
                    "幸运值已到账：%d -> %d",
                    previous_value,
                    value,
                )
                return frame, value
        await asyncio.sleep(config.ad_poll_seconds)
        elapsed += config.ad_poll_seconds
    raise LuckyEventError("广告任务已完成，但累计幸运值未在预期时间内增加。")


async def accept_coin_reward(
    page: Page,
    config: LuckyEventConfig,
    *,
    dry_run: bool = False,
) -> int | None:
    elapsed = 0.0
    while elapsed < config.panel_timeout_seconds:
        frame = await find_activity_frame(page)
        if frame is None:
            return None
        reward = frame.locator(COIN_REWARD_SELECTOR)
        confirm = frame.locator(COIN_CONFIRM_BUTTON_SELECTOR)
        if (
            await reward.count()
            and await reward.first.is_visible()
            and await confirm.count()
            and await confirm.first.is_visible()
            and (await confirm.first.inner_text()).strip() == COIN_CONFIRM_TEXT
        ):
            value_text = (
                await frame.locator(COIN_REWARD_VALUE_SELECTOR).first.inner_text()
            ).strip()
            if not value_text.isdigit():
                raise LuckyEventError("金币奖励弹层中的数量无法识别。")
            if not dry_run:
                logger.info("金币奖励为 %s，正在点击“开心收下”", value_text)
                await confirm.first.click()
            return int(value_text)
        await asyncio.sleep(0.5)
        elapsed += 0.5
    return None


async def claim_base_coins(
    page: Page,
    config: LuckyEventConfig,
    *,
    dry_run: bool = False,
) -> int | None:
    frame = await find_activity_frame(page)
    if frame is None:
        return None
    buttons = frame.locator(BASE_COIN_BUTTON_SELECTOR)
    for index in range(await buttons.count()):
        button = buttons.nth(index)
        if not await button.is_visible() or not await button.is_enabled():
            continue
        amount = parse_base_coin_amount(await button.inner_text())
        if amount is None:
            continue
        if dry_run:
            return amount
        logger.info("正在领取基础金币，按钮金额：%d", amount)
        await button.click()
        received = await accept_coin_reward(page, config)
        if received is None:
            raise LuckyEventError("基础金币已点击，但未出现“开心收下”确认。")
        return received
    return None


async def claim_bonus_coins(
    page: Page,
    config: LuckyEventConfig,
    *,
    dry_run: bool = False,
) -> tuple[int, int] | None:
    frame = await find_activity_frame(page)
    if frame is None:
        return None
    button = frame.locator(BONUS_COIN_BUTTON_SELECTOR)
    if not await button.count() or not await button.first.is_visible():
        return None
    advertised_amount = parse_bonus_coin_amount(await button.first.inner_text())
    if advertised_amount is None or not await button.first.is_enabled():
        return None
    if dry_run:
        return advertised_amount, advertised_amount

    logger.info("正在追加金币，按钮标注上限：%d", advertised_amount)
    await button.first.click()
    if not await wait_for_ad_completion(
        page,
        config,
        stop_when_round_ends=False,
    ):
        return None
    received = await accept_coin_reward(page, config)
    if received is None:
        logger.info("追加广告完成后未出现金币奖励，停止本轮追加领取")
        return None
    return received, advertised_amount


async def has_coin_result_panel(page: Page) -> bool:
    frame = await find_activity_frame(page)
    if frame is None:
        return False
    base = frame.locator(BASE_COIN_BUTTON_SELECTOR)
    bonus = frame.locator(BONUS_COIN_BUTTON_SELECTOR)
    return (
        (await base.count() and await base.first.is_visible())
        or (await bonus.count() and await bonus.first.is_visible())
    )


async def claim_result_coins(
    page: Page,
    config: LuckyEventConfig,
    *,
    dry_run: bool = False,
) -> int:
    total = 0
    bonus_total = 0
    pending = await accept_coin_reward(page, config, dry_run=dry_run)
    if pending is not None:
        total += pending
        logger.info("已确认待领取金币奖励：%d", pending)

    base = await claim_base_coins(page, config, dry_run=dry_run)
    if base is not None:
        total += base
        action = "可领取" if dry_run else "已领取"
        logger.info("开奖完成，%s基础金币：%d", action, base)

    while True:
        bonus_result = await claim_bonus_coins(page, config, dry_run=dry_run)
        if bonus_result is None:
            return total
        bonus, bonus_limit = bonus_result
        if pending is not None and base is None and bonus_total == 0:
            if pending <= bonus_limit:
                bonus_total = pending
        total += bonus
        bonus_total += bonus
        action = "可追加" if dry_run else "已追加"
        logger.info(
            "%s金币：%d，追加累计：%d/%d",
            action,
            bonus,
            bonus_total,
            bonus_limit,
        )
        if dry_run or bonus_total >= bonus_limit:
            logger.info("追加金币流程达到本轮上限，停止追加")
            return total


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
        logger.info(
            "当前累计幸运值：%d/%d",
            lucky_value,
            config.target_lucky_value,
        )
        if lucky_value >= config.target_lucky_value:
            logger.info("幸运值已达到目标，停止本轮免费广告")
            return lucky_value

        if not await can_start_free_ad(
            page,
            config.min_participation_seconds,
        ):
            logger.info("活动剩余不足 1 分钟，不再发起新的免费广告")
            return lucky_value
        if not await select_free_draw(frame):
            logger.info("本轮“免费抽”入口不可用，停止本轮操作")
            return lucky_value
        if not await start_free_ad(frame):
            logger.warning(
                "未出现“看视频免费参与”，为避免误点金币已停止本轮操作"
            )
            return lucky_value
        if not await wait_for_ad_completion(page, config):
            return lucky_value

        frame, lucky_value = await wait_for_lucky_value_increase(
            page,
            lucky_value,
            config,
        )
        if frame is not None:
            logger.info(
                "广告奖励到账，当前累计幸运值：%d/%d",
                lucky_value,
                config.target_lucky_value,
            )
    return None


async def monitor_lucky_event(
    page: Page,
    config: LuckyEventConfig | None = None,
    *,
    dry_run: bool = False,
) -> None:
    config = config or LuckyEventConfig()
    previous_active = False
    result_processed = False
    while True:
        entry = page.locator(LUCKY_ENTRY_SELECTOR)
        entry_text = (
            (await entry.inner_text()).strip()
            if await entry.is_visible()
            else "入口不可见"
        )
        active = is_active_round_text(entry_text)
        logger.info("活动巡检：入口状态=%s", entry_text)
        if active and not previous_active:
            result_processed = False
            if dry_run:
                logger.info("dry-run：检测到欧皇时刻活动，不执行点击")
            else:
                logger.info("检测到欧皇时刻活动，开始免费广告累计幸运值")
                try:
                    await participate_current_round(page, config)
                except (LuckyEventError, PlaywrightError) as error:
                    logger.warning("本轮活动已停止：%s", error)
                logger.info("本轮免费广告流程结束，继续等待下一轮")
        previous_active = active
        if not active:
            previous_active = False
            if not result_processed and await has_coin_result_panel(page):
                try:
                    await claim_result_coins(page, config, dry_run=dry_run)
                except (LuckyEventError, PlaywrightError) as error:
                    logger.warning("金币领取流程已停止：%s", error)
                result_processed = True
        await asyncio.sleep(config.poll_seconds)
