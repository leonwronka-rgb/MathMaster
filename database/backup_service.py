from __future__ import annotations

from datetime import datetime
from pathlib import Path

from database.database import Database


class DatabaseBackupService:
    def __init__(self, database: Database, backup_directory: Path) -> None:
        self.database = database
        self.backup_directory = backup_directory

    def create_backup(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        destination = self.backup_directory / f"mathmaster-{stamp}.sqlite3"
        return self.database.backup_to(destination)

    def restore_backup(self, source: Path) -> Path:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        safety_backup = (
            self.backup_directory / f"before-restore-{stamp}.sqlite3"
        )
        return self.database.restore_from(source, safety_backup)
