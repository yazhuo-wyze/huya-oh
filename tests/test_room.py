import unittest
from unittest.mock import AsyncMock, MagicMock

from huya_automation.room import (
    TARGET_ROOM_URL,
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


if __name__ == "__main__":
    unittest.main()
