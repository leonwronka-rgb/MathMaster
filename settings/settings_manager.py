from __future__ import annotations

import json
import logging
import sqlite3
from copy import deepcopy
from typing import Any

from database.database import Database
from mathematics.topics import TOPIC_CATEGORIES

DEFAULT_SETTINGS: dict[str, Any] = {
    "theme": "Ciemny",
    "font_size": "Normalny",
    "font_family": "Segoe UI",
    "bold_text": False,
    "spacing": "Normalne",
    "high_contrast": False,
    "custom_colors": {
        "main": "#8B5CF6", "secondary": "#60A5FA", "background": "#0B1020",
        "card": "#151F35", "text": "#F1F4FC", "button": "#8B5CF6",
        "selection": "#282044",
    },
    "default_difficulty": 3,
    "questions_per_session": 10,
    "session_duration_minutes": 25,
    "auto_next_question": False,
    "show_hints": True,
    "show_solution_after_error": True,
    "adaptive_difficulty": True,
    "default_category": "Arytmetyka",
    "notifications_enabled": True,
    "study_reminders": False,
    "reminder_time": "18:00",
    "daily_goal_reminders": True,
    "flashcard_reminders": True,
    "reminder_days": [0, 1, 2, 3, 4, 5, 6],
    "sound_enabled": False,
    "sound_volume": 50,
    "animations_enabled": True,
    "reduce_animations": False,
}
_THEMES = {"Ciemny", "Jasny", "Systemowy", "Niestandardowy"}
_FONT_SIZES = {"Mały", "Normalny", "Duży", "Bardzo duży"}
_SPACINGS = {"Zwarte", "Normalne", "Przestronne"}
_CUSTOM_COLOR_KEYS = frozenset(DEFAULT_SETTINGS["custom_colors"])


class SettingsError(ValueError):
    """Invalid or unavailable user settings."""


class SettingsStorageError(RuntimeError):
    """Could not load or store user settings."""


class SettingsManager:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.logger = logging.getLogger(__name__)

    def get_settings(self, user_id: int) -> dict[str, Any]:
        try:
            with self.database.transaction() as connection:
                row = connection.execute(
                    "SELECT settings_json FROM user_settings WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
            if row is None:
                return deepcopy(DEFAULT_SETTINGS)
            stored = json.loads(str(row["settings_json"]))
            if not isinstance(stored, dict):
                raise ValueError("settings_json must contain a JSON object")
            supported = {key: value for key, value in stored.items() if key in DEFAULT_SETTINGS}
            custom_colors = supported.get("custom_colors", {})
            if not isinstance(custom_colors, dict):
                raise ValueError("custom_colors must contain a JSON object")
            return self.validate({
                **DEFAULT_SETTINGS,
                **supported,
                "custom_colors": {**DEFAULT_SETTINGS["custom_colors"], **custom_colors},
            })
        except (sqlite3.Error, json.JSONDecodeError, TypeError, ValueError) as error:
            self.logger.exception("Could not load settings for user %s", user_id)
            raise SettingsStorageError("Nie udało się wczytać ustawień użytkownika.") from error

    def save_settings(self, user_id: int, values: dict[str, Any]) -> dict[str, Any]:
        current = self.get_settings(user_id)
        merged = {**current, **values}
        if "custom_colors" in values:
            if not isinstance(values["custom_colors"], dict):
                raise SettingsError("Zestaw własnych kolorów jest nieprawidłowy.")
            merged["custom_colors"] = {**current["custom_colors"], **values["custom_colors"]}
        validated = self.validate(merged)
        try:
            with self.database.transaction() as connection:
                exists = connection.execute(
                    "SELECT 1 FROM users WHERE id = ?", (user_id,)
                ).fetchone()
                if exists is None:
                    raise SettingsError("Nie znaleziono zalogowanego użytkownika.")
                connection.execute(
                    """
                    INSERT INTO user_settings (user_id, settings_json)
                    VALUES (?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        settings_json = excluded.settings_json,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (user_id, json.dumps(validated, ensure_ascii=False)),
                )
            return deepcopy(validated)
        except SettingsError:
            raise
        except sqlite3.Error as error:
            self.logger.exception("Could not save settings for user %s", user_id)
            raise SettingsStorageError("Nie udało się zapisać ustawień użytkownika.") from error

    def reset_settings(self, user_id: int) -> dict[str, Any]:
        try:
            with self.database.transaction() as connection:
                exists = connection.execute(
                    "SELECT 1 FROM users WHERE id = ?", (user_id,)
                ).fetchone()
                if exists is None:
                    raise SettingsError("Nie znaleziono zalogowanego użytkownika.")
                connection.execute("DELETE FROM user_settings WHERE user_id = ?", (user_id,))
            return deepcopy(DEFAULT_SETTINGS)
        except SettingsError:
            raise
        except sqlite3.Error as error:
            self.logger.exception("Could not reset settings for user %s", user_id)
            raise SettingsStorageError("Nie udało się przywrócić ustawień domyślnych.") from error

    @staticmethod
    def validate(values: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(values, dict) or set(values) - set(DEFAULT_SETTINGS):
            raise SettingsError("Zestaw ustawień zawiera nieznane pola.")
        result = deepcopy(DEFAULT_SETTINGS)
        result.update(values)
        colors = values.get("custom_colors", result["custom_colors"])
        if not isinstance(colors, dict) or set(colors) != _CUSTOM_COLOR_KEYS:
            raise SettingsError("Zestaw własnych kolorów jest niekompletny.")
        for color in colors.values():
            if not isinstance(color, str) or len(color) != 7 or color[0] != "#":
                raise SettingsError("Kolor musi być zapisany w formacie #RRGGBB.")
            try:
                int(color[1:], 16)
            except ValueError as error:
                raise SettingsError("Kolor musi być zapisany w formacie #RRGGBB.") from error
        result["custom_colors"] = dict(colors)
        if not isinstance(result["theme"], str) or result["theme"] not in _THEMES:
            raise SettingsError("Wybrany motyw jest nieprawidłowy.")
        if not isinstance(result["font_size"], str) or result["font_size"] not in _FONT_SIZES:
            raise SettingsError("Wybrany rozmiar tekstu jest nieprawidłowy.")
        if not isinstance(result["spacing"], str) or result["spacing"] not in _SPACINGS:
            raise SettingsError("Wybrane odstępy są nieprawidłowe.")
        if (
            not isinstance(result["default_category"], str)
            or result["default_category"] not in TOPIC_CATEGORIES
        ):
            raise SettingsError("Wybrany domyślny dział matematyki jest nieprawidłowy.")
        for key in (
            "bold_text", "high_contrast", "auto_next_question", "show_hints",
            "show_solution_after_error", "adaptive_difficulty",
            "notifications_enabled", "study_reminders", "daily_goal_reminders",
            "flashcard_reminders", "sound_enabled", "animations_enabled",
            "reduce_animations",
        ):
            if not isinstance(result[key], bool):
                raise SettingsError(f"Ustawienie „{key}” musi być wartością logiczną.")
        for key, low, high in (
            ("default_difficulty", 1, 5),
            ("questions_per_session", 1, 100),
            ("session_duration_minutes", 1, 240),
            ("sound_volume", 0, 100),
        ):
            value = result[key]
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                raise SettingsError(f"Ustawienie „{key}” jest poza dozwolonym zakresem.")
        time_value = result["reminder_time"]
        if not isinstance(time_value, str) or len(time_value) != 5:
            raise SettingsError("Godzina przypomnienia musi mieć format HH:MM.")
        try:
            hour, minute = (int(part) for part in time_value.split(":"))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
        except ValueError as error:
            raise SettingsError("Godzina przypomnienia musi mieć format HH:MM.") from error
        if not isinstance(result["font_family"], str) or not result["font_family"].strip():
            raise SettingsError("Nazwa czcionki nie może być pusta.")
        days = result["reminder_days"]
        if not isinstance(days, list) or any(type(day) is not int or day not in range(7) for day in days):
            raise SettingsError("Dni przypomnień muszą być liczbami od 0 do 6.")
        result["reminder_days"] = sorted(set(days))
        return result
