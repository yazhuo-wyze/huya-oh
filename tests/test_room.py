import unittest
from unittest.mock import AsyncMock, MagicMock

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from huya_automation.room import (
    TARGET_ROOM_URL,
    ensure_player_danmu_disabled,
    ensure_room_muted,
    ensure_theater_mode,
    is_target_room,
)


class TargetRoomUrlTest(unittest.TestCase):
    def test_accepts_query_fragment_and_trailing_slash(self) -> None:
        self.assertTrue(is_target_room(f"{TARGET_ROOM_URL}/?from=test#player"))

    def test_rejects_another_room(self) -> None:
        self.assertFalse(is_target_room("https://www.huya.com/660003"))


class TheaterModeTest(unittest.IsolatedAsyncioTestCase):
    async def test_dry_run_does_not_click(self) -> None:
        button = MagicMock()
        button.wait_for = AsyncMock()
        button.get_attribute = AsyncMock(return_value="剧场模式")
        button.evaluate = AsyncMock()
        body = MagicMock()
        body.get_attribute = AsyncMock(return_value="liveStatus-on")
        page = MagicMock()
        page.locator.side_effect = lambda selector: (
            body if selector == "body" else button
        )

        changed = await ensure_theater_mode(page, dry_run=True)

        self.assertTrue(changed)
        button.evaluate.assert_not_awaited()

    async def test_already_in_theater_mode_does_not_click(self) -> None:
        button = MagicMock()
        button.wait_for = AsyncMock()
        button.get_attribute = AsyncMock(return_value="退出剧场")
        button.evaluate = AsyncMock()
        body = MagicMock()
        body.get_attribute = AsyncMock(return_value="mode-page-theater")
        page = MagicMock()
        page.locator.side_effect = lambda selector: (
            body if selector == "body" else button
        )

        changed = await ensure_theater_mode(page)

        self.assertFalse(changed)
        button.evaluate.assert_not_awaited()


class RoomMuteTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def build_page(button_class: str, media_muted: bool) -> tuple:
        sound_button = MagicMock()
        sound_button.wait_for = AsyncMock()
        sound_button.get_attribute = AsyncMock(return_value=button_class)
        sound_button.evaluate = AsyncMock()
        theater_button = MagicMock()
        theater_button.wait_for = AsyncMock()
        media = MagicMock()
        media.count = AsyncMock(return_value=1)
        media.evaluate_all = AsyncMock(return_value=media_muted)
        page = MagicMock()

        def locator(selector: str) -> MagicMock:
            if selector == "#player-sound-btn":
                return sound_button
            if selector == "video, audio":
                return media
            return theater_button

        page.locator.side_effect = locator
        return page, sound_button

    async def test_already_muted_does_not_click(self) -> None:
        page, button = self.build_page("player-sound-off", True)

        changed = await ensure_room_muted(page)

        self.assertFalse(changed)
        button.evaluate.assert_not_awaited()

    async def test_dry_run_does_not_click_audible_room(self) -> None:
        page, button = self.build_page("player-sound-on", False)

        changed = await ensure_room_muted(page, dry_run=True)

        self.assertTrue(changed)
        button.evaluate.assert_not_awaited()

    async def test_continues_when_muted_state_cannot_be_confirmed(
        self,
    ) -> None:
        page, button = self.build_page("player-sound-on", False)
        page.wait_for_function = AsyncMock(
            side_effect=PlaywrightTimeoutError("not updated")
        )
        page.wait_for_timeout = AsyncMock()

        changed = await ensure_room_muted(page)

        self.assertIsNone(changed)
        self.assertEqual(button.evaluate.await_count, 2)
        page.wait_for_timeout.assert_awaited_once_with(1_000)


class PlayerDanmuTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def build_page(button_class: str, title: str) -> tuple:
        danmu_button = MagicMock()
        danmu_button.wait_for = AsyncMock()
        danmu_button.get_attribute = AsyncMock(
            side_effect=lambda name: button_class if name == "class" else title
        )
        danmu_button.evaluate = AsyncMock()
        theater_button = MagicMock()
        theater_button.wait_for = AsyncMock()
        page = MagicMock()
        page.locator.side_effect = lambda selector: (
            danmu_button
            if selector == "#player-danmu-btn"
            else theater_button
        )
        return page, danmu_button

    async def test_already_disabled_does_not_click(self) -> None:
        page, button = self.build_page(
            "player-ctrl-switch player-ctrl-switch-hide",
            "开启弹幕",
        )

        changed = await ensure_player_danmu_disabled(page)

        self.assertFalse(changed)
        button.evaluate.assert_not_awaited()

    async def test_dry_run_does_not_click_enabled_danmu(self) -> None:
        page, button = self.build_page(
            "player-ctrl-switch player-ctrl-switch-show",
            "关闭弹幕",
        )

        changed = await ensure_player_danmu_disabled(page, dry_run=True)

        self.assertTrue(changed)
        button.evaluate.assert_not_awaited()

    async def test_continues_when_disabled_state_cannot_be_confirmed(
        self,
    ) -> None:
        page, button = self.build_page(
            "player-ctrl-switch player-ctrl-switch-show",
            "关闭弹幕",
        )
        page.wait_for_function = AsyncMock(
            side_effect=PlaywrightTimeoutError("not updated")
        )
        page.wait_for_timeout = AsyncMock()

        changed = await ensure_player_danmu_disabled(page)

        self.assertIsNone(changed)
        self.assertEqual(button.evaluate.await_count, 2)
        page.wait_for_timeout.assert_awaited_once_with(1_000)


if __name__ == "__main__":
    unittest.main()
