from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from accounts.auth import AuthService
from database.database import Database
from settings.backup_manager import BackupManager
from settings.settings_manager import (
    DEFAULT_SETTINGS,
    SettingsError,
    SettingsManager,
)
from settings.theme_manager import ThemeManager, build_palette


class SettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.database = Database(self.root / "settings.sqlite3")
        self.database.initialize()
        self.auth = AuthService(self.database)
        self.user = self.auth.register("settings-user", "Settings User", "secure-pass-123")
        self.other = self.auth.register("other-settings", "Other", "secure-pass-456")
        self.manager = SettingsManager(self.database)
        self.addCleanup(self.temp_dir.cleanup)
        self.addCleanup(self.database.close)

    def test_settings_are_persisted_per_user_and_defaults_can_be_restored(self) -> None:
        saved = self.manager.save_settings(
            self.user.id, {"theme": "Jasny", "default_difficulty": 4}
        )

        self.assertEqual(saved["theme"], "Jasny")
        self.assertEqual(self.manager.get_settings(self.user.id)["default_difficulty"], 4)
        self.assertEqual(self.manager.get_settings(self.other.id), DEFAULT_SETTINGS)

        reset = self.manager.reset_settings(self.user.id)

        self.assertEqual(reset, DEFAULT_SETTINGS)
        self.assertEqual(self.manager.get_settings(self.user.id), DEFAULT_SETTINGS)

    def test_validation_rejects_invalid_colors_and_learning_values(self) -> None:
        with self.assertRaises(SettingsError):
            self.manager.save_settings(
                self.user.id,
                {"custom_colors": {**DEFAULT_SETTINGS["custom_colors"], "main": "purple"}},
            )
        with self.assertRaises(SettingsError):
            self.manager.save_settings(self.user.id, {"questions_per_session": 0})

    def test_user_json_export_omits_password_hash_and_other_accounts(self) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO exercise_history (user_id, topic, correct) VALUES (?, ?, 1)",
                (self.user.id, "addition"),
            )
            connection.execute(
                "INSERT INTO exercise_history (user_id, topic, correct) VALUES (?, ?, 1)",
                (self.other.id, "algebra"),
            )
        destination = self.root / "export.json"

        BackupManager(self.database, self.root / "backups").export_user_data(
            self.user.id, destination
        )
        export = json.loads(destination.read_text(encoding="utf-8"))

        self.assertNotIn("password_hash", export["tables"]["users"][0])
        self.assertEqual(len(export["tables"]["exercise_history"]), 1)
        self.assertEqual(export["tables"]["exercise_history"][0]["topic"], "addition")
        self.assertEqual(export["user_id"], self.user.id)

    def test_theme_palettes_and_live_widget_refresh(self) -> None:
        self.assertEqual(build_palette({**DEFAULT_SETTINGS, "theme": "Ciemny"})["background"], "#0B1020")
        self.assertEqual(build_palette({**DEFAULT_SETTINGS, "theme": "Jasny"})["background"], "#F4F6FC")
        self.assertEqual(
            build_palette({**DEFAULT_SETTINGS, "theme": "Systemowy"})["background"],
            ("#F4F6FC", "#0B1020"),
        )
        custom = {**DEFAULT_SETTINGS, "theme": "Niestandardowy"}
        custom["custom_colors"] = {**DEFAULT_SETTINGS["custom_colors"], "background": "#123456"}
        self.assertEqual(build_palette(custom)["background"], "#123456")

        class FakeWidget:
            def __init__(self) -> None:
                self.options = {"fg_color": "#8B5CF6"}
                self.updated: dict[str, object] = {}

            def configure(self, **kwargs: object) -> dict[str, object]:
                if kwargs:
                    self.updated.update(kwargs)
                    self.options.update(kwargs)
                return {"fg_color": ("", "", "", "", "", "")}

            def cget(self, key: str) -> object:
                return self.options[key]

            def winfo_children(self) -> list[object]:
                return []

            def winfo_manager(self) -> str:
                return ""

        class FakeRoot(FakeWidget):
            def __init__(self, child: FakeWidget) -> None:
                super().__init__()
                self.child = child

            def winfo_children(self) -> list[FakeWidget]:
                return [self.child]

        child = FakeWidget()
        root = FakeRoot(child)
        theme = ThemeManager(root)  # type: ignore[arg-type]
        with patch("settings.theme_manager.ctk.set_appearance_mode"):
            theme.apply({**DEFAULT_SETTINGS, "theme": "Jasny"})

        self.assertEqual(child.updated["fg_color"], "#6941C6")
        self.assertEqual(root.updated["fg_color"], "#F4F6FC")
