from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from database.backup_service import DatabaseBackupService
from database.database import Database

_OWNED_TABLES = {
    "exercise_history": "user_id", "user_progress": "user_id",
    "user_achievements": "user_id", "study_plans": "user_id",
    "flashcards": "user_id", "flashcard_decks": "user_id",
    "flashcard_reviews": "user_id", "flashcard_settings": "user_id",
    "exam_results": "user_id", "learning_topic_status": "user_id",
    "custom_learning_topics": "owner_id", "custom_task_sets": "user_id",
    "user_custom_tasks": "user_id", "custom_task_attempts": "user_id",
    "achievement_progress": "user_id", "user_cosmetics": "user_id",
    "user_equipped_cosmetics": "user_id", "quiz_battle_results": "user_id",
    "user_settings": "user_id",
}


class BackupManager:
    def __init__(self, database: Database, backup_directory: Path) -> None:
        self.database = database
        self.backups = DatabaseBackupService(database, backup_directory)

    def create_database_backup(self) -> Path:
        return self.backups.create_backup()

    def restore_database_backup(self, source: Path) -> Path:
        if not source.is_file():
            raise ValueError("Wybrany plik kopii zapasowej nie istnieje.")
        if source.resolve() == self.database.path.resolve():
            raise ValueError("Wybierz kopię zapasową, a nie aktywny plik bazy danych.")
        return self.backups.restore_backup(source)

    def export_user_data(self, user_id: int, destination: Path) -> Path:
        tables: dict[str, list[dict[str, Any]]] = {}
        with self.database.transaction() as connection:
            user = connection.execute(
                "SELECT id, username, display_name, created_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if user is None:
                raise ValueError("Nie znaleziono użytkownika do eksportu.")
            tables["users"] = [dict(user)]
            for table, owner_column in _OWNED_TABLES.items():
                columns = {
                    str(row["name"])
                    for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
                }
                if owner_column not in columns:
                    continue
                rows = connection.execute(
                    f'SELECT * FROM "{table}" WHERE "{owner_column}" = ?', (user_id,)
                ).fetchall()
                tables[table] = [dict(row) for row in rows]
            existing = {
                str(row["name"]) for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            if "exam_answer_details" in existing and tables.get("exam_results"):
                exam_ids = [row["id"] for row in tables["exam_results"] if "id" in row]
                if exam_ids:
                    placeholders = ",".join("?" for _ in exam_ids)
                    rows = connection.execute(
                        f"SELECT * FROM exam_answer_details WHERE exam_id IN ({placeholders})",
                        exam_ids,
                    ).fetchall()
                    tables["exam_answer_details"] = [dict(row) for row in rows]
            if "flashcards" in tables:
                card_ids = [row["id"] for row in tables["flashcards"] if "id" in row]
                if card_ids:
                    placeholders = ",".join("?" for _ in card_ids)
                    rows = connection.execute(
                        f"""
                        SELECT * FROM flashcard_reviews
                        WHERE user_id = ? AND flashcard_id IN ({placeholders})
                        """,
                        [user_id, *card_ids],
                    ).fetchall()
                    tables["flashcard_reviews"] = [dict(row) for row in rows]
        payload = {
            "format_version": 1,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "tables": tables,
        }
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return destination
