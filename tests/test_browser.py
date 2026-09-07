import tempfile
import unittest
from pathlib import Path

from huya_automation.browser import (
    BrowserError,
    cdp_browser_matches,
    default_automation_data_root,
    default_browser_executables,
    process_commands_include_browser,
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
                platform_name="Darwin",
            )

            self.assertEqual(config.display_name, "Microsoft Edge")
            self.assertEqual(config.user_data_dir, root / "profiles" / "Edge")
            self.assertEqual(
                config.log_file,
                root / "profiles" / "edge-debug.log",
            )

    def test_falls_back_to_chrome_when_edge_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            chrome = root / "chrome"
            chrome.touch()

            config = select_browser_config(
                edge_executable=root / "missing-edge",
                chrome_executable=chrome,
                data_root=root / "profiles",
                platform_name="Windows",
            )

            self.assertEqual(config.display_name, "Google Chrome")
            self.assertEqual(config.platform_name, "Windows")
            self.assertEqual(
                config.user_data_dir,
                root / "profiles" / "Chrome",
            )
            self.assertEqual(
                config.log_file,
                root / "profiles" / "chrome-debug.log",
            )

    def test_fails_when_no_supported_browser_is_installed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(BrowserError):
                select_browser_config(
                    edge_executable=root / "missing-edge",
                    chrome_executable=root / "missing-chrome",
                    data_root=root / "profiles",
                    platform_name="Darwin",
                )

    def test_rejects_unsupported_operating_system(self) -> None:
        with self.assertRaises(BrowserError):
            select_browser_config(platform_name="Linux", environ={})


class PlatformPathTest(unittest.TestCase):
    def test_macos_browser_and_profile_paths(self) -> None:
        edge, chrome = default_browser_executables("Darwin", {})

        self.assertIn("Microsoft Edge.app", str(edge[0]))
        self.assertIn("Google Chrome.app", str(chrome[0]))
        self.assertEqual(
            default_automation_data_root("Darwin", {}).parts[-3:],
            ("Library", "Application Support", "Huya Automation"),
        )

    def test_windows_browser_and_profile_paths(self) -> None:
        environment = {
            "PROGRAMFILES": "C:/Program Files",
            "PROGRAMFILES(X86)": "C:/Program Files (x86)",
            "PROGRAMW6432": "C:/Program Files",
            "LOCALAPPDATA": "C:/Users/test/AppData/Local",
        }

        edge, chrome = default_browser_executables("Windows", environment)

        self.assertTrue(str(edge[0]).endswith("msedge.exe"))
        self.assertTrue(str(chrome[0]).endswith("chrome.exe"))
        self.assertEqual(
            default_automation_data_root("Windows", environment),
            Path("C:/Users/test/AppData/Local") / "Huya Automation",
        )


class BrowserProcessTest(unittest.TestCase):
    def test_matches_browser_and_profile_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            edge = root / "MSedge.exe"
            edge.touch()
            config = select_browser_config(
                edge_executable=edge,
                chrome_executable=root / "missing-chrome",
                data_root=root / "Profiles",
                platform_name="Windows",
            )
            command = (
                f'"{str(edge).upper()}" '
                f'"--user-data-dir={str(config.user_data_dir).upper()}"'
            )

            self.assertTrue(
                process_commands_include_browser(config, [command])
            )
            self.assertFalse(
                process_commands_include_browser(config, ["other.exe"])
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
                platform_name="Darwin",
            )
            chrome_config = select_browser_config(
                edge_executable=root / "missing-edge",
                chrome_executable=chrome,
                data_root=root / "profiles",
                platform_name="Windows",
            )
            edge_payload = {"Browser": "Edg/152.0.0.0"}
            chrome_payload = {"Browser": "Chrome/152.0.0.0"}

            self.assertTrue(cdp_browser_matches(edge_config, edge_payload))
            self.assertFalse(cdp_browser_matches(edge_config, chrome_payload))
            self.assertTrue(cdp_browser_matches(chrome_config, chrome_payload))
            self.assertFalse(cdp_browser_matches(chrome_config, edge_payload))


if __name__ == "__main__":
    unittest.main()
