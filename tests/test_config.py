from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import AppConfig


class AppConfigTests(unittest.TestCase):
    def test_paths_are_created_under_configured_data_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"MATHMASTER_DATA_DIR": directory}):
                config = AppConfig.from_environment()

        self.assertEqual(config.database_path, Path(directory) / "mathmaster.sqlite3")
        self.assertEqual(config.log_path, Path(directory) / "mathmaster.log")

    def test_appearance_can_be_configured(self) -> None:
        with patch.dict(os.environ, {"MATHMASTER_APPEARANCE": "dark"}):
            config = AppConfig.from_environment()

        self.assertEqual(config.appearance_mode, "dark")

    def test_frozen_app_uses_persistent_user_data_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            local_app_data = Path(directory) / "LocalAppData"
            with (
                patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}, clear=True),
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "_MEIPASS", str(Path(directory) / "bundle"), create=True),
            ):
                config = AppConfig.from_environment()

        self.assertEqual(config.data_dir, local_app_data / "MathMaster")
        self.assertEqual(config.database_path.parent, local_app_data / "MathMaster")
        self.assertEqual(len(config.legacy_database_paths), 2)

    def test_windows_prefers_appdata_for_user_data(self) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    "APPDATA": r"C:\Users\Tester\AppData\Roaming",
                    "LOCALAPPDATA": r"C:\Users\Tester\AppData\Local",
                },
                clear=True,
            ),
            patch("core.paths.sys.platform", "win32"),
        ):
            config = AppConfig.from_environment()

        self.assertEqual(
            config.data_dir,
            Path(r"C:\Users\Tester\AppData\Roaming") / "MathMaster",
        )

    def test_bundled_resources_use_meipass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "bundle"
            with patch.object(sys, "_MEIPASS", str(bundle), create=True):
                config = AppConfig()
                self.assertEqual(config.content_dir, bundle / "data")
                self.assertEqual(
                    config.icon_path, bundle / "assets" / "icons" / "mathmaster.ico"
                )

    def test_explicit_data_directory_disables_legacy_auto_migration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.dict(
                    os.environ,
                    {"MATHMASTER_DATA_DIR": directory},
                    clear=True,
                ),
                patch.object(sys, "frozen", True, create=True),
            ):
                config = AppConfig.from_environment()

        self.assertEqual(config.data_dir, Path(directory))
        self.assertEqual(config.legacy_database_paths, ())


if __name__ == "__main__":
    unittest.main()
