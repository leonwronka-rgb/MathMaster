from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from core.paths import (
    default_user_data_dir,
    legacy_database_paths as find_legacy_database_paths,
    resource_path,
)


@dataclass(frozen=True, slots=True)
class AppConfig:
    app_name: str = "MathMaster"
    version: str = "0.1.0"
    data_dir: Path = default_user_data_dir()
    legacy_database_paths: tuple[Path, ...] = ()
    appearance_mode: str = "dark"
    color_theme: str = "blue"
    quiz_battle_url: str = ""
    quiz_battle_token: str = ""
    window_width: int = 1280
    window_height: int = 820

    @property
    def database_path(self) -> Path:
        return self.data_dir / "mathmaster.sqlite3"

    @property
    def log_path(self) -> Path:
        return self.data_dir / "mathmaster.log"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def content_dir(self) -> Path:
        return resource_path("data")

    @property
    def icon_path(self) -> Path:
        return resource_path("assets", "icons", "mathmaster.ico")

    @classmethod
    def from_environment(cls) -> AppConfig:
        configured_data_dir = os.environ.get("MATHMASTER_DATA_DIR")
        data_dir = (
            Path(configured_data_dir).expanduser()
            if configured_data_dir
            else default_user_data_dir()
        )
        legacy_database_paths = (
            find_legacy_database_paths()
            if configured_data_dir is None
            else ()
        )
        return cls(
            data_dir=data_dir,
            legacy_database_paths=legacy_database_paths,
            appearance_mode=os.environ.get("MATHMASTER_APPEARANCE", "dark"),
            quiz_battle_url=os.environ.get("MATHMASTER_QUIZ_BATTLE_URL", ""),
            quiz_battle_token=os.environ.get("MATHMASTER_QUIZ_BATTLE_TOKEN", ""),
        )