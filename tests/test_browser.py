import tempfile
import unittest
from pathlib import Path

from huya_automation.browser import (
    BrowserError,
    cdp_browser_matches,
    select_browser_config,
)


class BrowserSelectionTest(unittest.TestCase):
    def test_prefers_edge_when_both_browsers_are_installed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            edge = root / "edge"
            chrome = root / "chrome"
            edge.touch()
            chrome.touch()

            config = select_browser_config(
                edge_executable=edge,
                chrome_executable=chrome,
                data_root=root / "profiles",
            )

            self.assertEqual(config.display_name, "Microsoft Edge")
            self.assertEqual(config.user_data_dir, root / "profiles" / "Edge")

    def test_falls_back_to_chrome_when_edge_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            chrome = root / "chrome"
            chrome.touch()

            config = select_browser_config(
                edge_executable=root / "missing-edge",
                chrome_executable=chrome,
                data_root=root / "profiles",
            )

            self.assertEqual(config.display_name, "Google Chrome")
            self.assertEqual(
                config.user_data_dir,
                root / "profiles" / "Chrome",
            )

    def test_fails_when_no_supported_browser_is_installed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(BrowserError):
                select_browser_config(
                    edge_executable=root / "missing-edge",
                    chrome_executable=root / "missing-chrome",
                    data_root=root / "profiles",
                )


class CdpBrowserIdentityTest(unittest.TestCase):
    def test_distinguishes_edge_from_chrome(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            edge = root / "edge"
            chrome = root / "chrome"
            edge.touch()
            chrome.touch()
            edge_config = select_browser_config(
                edge_executable=edge,
                chrome_executable=chrome,
                data_root=root / "profiles",
            )
            chrome_config = select_browser_config(
                edge_executable=root / "missing-edge",
                chrome_executable=chrome,
                data_root=root / "profiles",
            )
            edge_payload = {"Browser": "Edg/152.0.0.0"}
            chrome_payload = {"Browser": "Chrome/152.0.0.0"}

            self.assertTrue(cdp_browser_matches(edge_config, edge_payload))
            self.assertFalse(cdp_browser_matches(edge_config, chrome_payload))
            self.assertTrue(cdp_browser_matches(chrome_config, chrome_payload))
            self.assertFalse(cdp_browser_matches(chrome_config, edge_payload))


if __name__ == "__main__":
    unittest.main()
