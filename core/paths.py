from __future__ import annotations

import os
import sys
from pathlib import Path


def resource_root() -> Path:
    """Return the read-only directory containing bundled application resources."""
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        return Path(bundle_dir).resolve()
    return Path(__file__).resolve().parents[1]


def resource_path(*parts: str) -> Path:
    return resource_root().joinpath(*parts)


def default_user_data_dir() -> Path:
    if sys.platform == "win32":
        app_data = os.environ.get("APPDATA")
        if app_data:
            return Path(app_data).expanduser() / "MathMaster"
        local_app_data = os.environ.get("LOCALAPPDATA")
        root = Path(local_app_data).expanduser() if local_app_data else Path.home() / "AppData" / "Roaming"
        return root / "MathMaster"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "MathMaster"
    data_home = os.environ.get("XDG_DATA_HOME")
    root = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return root / "MathMaster"


def legacy_database_paths() -> tuple[Path, ...]:
    """Find pre-centralized database locations without using PyInstaller temp files."""
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
        candidates.extend(
            directory / "data" / "mathmaster.sqlite3"
            for directory in (executable_dir, executable_dir.parent)
        )
        if sys.platform == "win32":
            local_app_data = os.environ.get("LOCALAPPDATA")
            if local_app_data:
                candidates.append(
                    Path(local_app_data).expanduser()
                    / "MathMaster"
                    / "mathmaster.sqlite3"
                )
    else:
        candidates.append(resource_root() / "data" / "mathmaster.sqlite3")
    target = default_user_data_dir() / "mathmaster.sqlite3"
    target_resolved = target.resolve()
    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved != target_resolved and resolved not in seen:
            unique.append(candidate)
            seen.add(resolved)
    return tuple(unique)
