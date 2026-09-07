import unittest
from unittest.mock import AsyncMock, MagicMock

from huya_automation.auth import any_locator_visible, ensure_logged_in


class LocatorVisibilityTest(unittest.IsolatedAsyncioTestCase):
    async def test_checks_each_match_without_strict_mode(self) -> None:
        hidden = MagicMock()
        hidden.is_visible = AsyncMock(return_value=False)
        visible = MagicMock()
        visible.is_visible = AsyncMock(return_value=True)
        locator = MagicMock()
        locator.count = AsyncMock(return_value=3)
        locator.nth.side_effect = [hidden, visible, hidden]

        self.assertTrue(await any_locator_visible(locator))
        locator.nth.assert_any_call(0)
        locator.nth.assert_any_call(1)


class LoginStateTest(unittest.IsolatedAsyncioTestCase):
    async def test_logged_in_does_not_require_credentials(self) -> None:
        state = MagicMock()
        state.json_value = AsyncMock(return_value="logged-in")
        page = MagicMock()
        page.wait_for_function = AsyncMock(return_value=state)

        changed = await ensure_logged_in(page, credentials=None)

        self.assertFalse(changed)

    async def test_dry_run_reports_login_without_opening_dialog(self) -> None:
        login_link = MagicMock()
        state = MagicMock()
        state.json_value = AsyncMock(return_value="logged-out")
        page = MagicMock()
        page.get_by_role.return_value = login_link
        page.wait_for_function = AsyncMock(return_value=state)

        changed = await ensure_logged_in(page, credentials=None, dry_run=True)

        self.assertTrue(changed)
        page.wait_for_function.assert_awaited_once()
        login_link.click.assert_not_called()


if __name__ == "__main__":
    unittest.main()
