from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from database.database import Database, DatabaseBackupError


class DatabaseTests(unittest.TestCase):
    def test_initialize_applies_schema_and_transaction_persists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "test.sqlite3")
            database.initialize()
            try:
                with database.transaction() as connection:
                    connection.execute(
                        "INSERT INTO app_settings (key, value) VALUES (?, ?)",
                        ("theme", "dark"),
                    )
                with database.transaction() as connection:
                    setting = connection.execute(
                        "SELECT value FROM app_settings WHERE key = ?",
                        ("theme",),
                    ).fetchone()
                self.assertEqual(setting["value"], "dark")
            finally:
                database.close()

    def test_database_requires_initialization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "test.sqlite3")
            with self.assertRaises(RuntimeError):
                with database.transaction():
                    pass

    def test_newer_schema_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "newer.sqlite3"
            connection = sqlite3.connect(path)
            connection.execute("PRAGMA user_version = 99")
            connection.close()
            database = Database(path)
            with self.assertRaises(RuntimeError):
                database.initialize()
            database.close()

    def test_backup_creates_valid_snapshot_in_missing_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = Database(root / "test.sqlite3")
            database.initialize()
            try:
                with database.transaction() as connection:
                    connection.execute(
                        "INSERT INTO app_settings (key, value) VALUES (?, ?)",
                        ("saved", "yes"),
                    )

                backup_path = database.backup_to(root / "nested" / "snapshot.sqlite3")

                self.assertTrue(backup_path.is_file())
                backup = sqlite3.connect(backup_path)
                try:
                    self.assertEqual(
                        backup.execute("PRAGMA integrity_check").fetchone()[0], "ok"
                    )
                    self.assertEqual(
                        backup.execute(
                            "SELECT value FROM app_settings WHERE key = 'saved'"
                        ).fetchone()[0],
                        "yes",
                    )
                finally:
                    backup.close()
            finally:
                database.close()

    def test_restore_keeps_safety_backup_and_restores_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = Database(root / "active.sqlite3")
            source = Database(root / "source.sqlite3")
            database.initialize()
            source.initialize()
            try:
                with source.transaction() as connection:
                    connection.execute(
                        "INSERT INTO app_settings (key, value) VALUES (?, ?)",
                        ("selected", "backup"),
                    )
                restore_point = source.backup_to(root / "source-copy.sqlite3")
                with database.transaction() as connection:
                    connection.execute(
                        "INSERT INTO app_settings (key, value) VALUES (?, ?)",
                        ("selected", "current"),
                    )

                safety_path = database.restore_from(
                    restore_point, root / "backups" / "before-restore.sqlite3"
                )

                self.assertTrue(safety_path.is_file())
                with database.transaction() as connection:
                    value = connection.execute(
                        "SELECT value FROM app_settings WHERE key = ?",
                        ("selected",),
                    ).fetchone()["value"]
                self.assertEqual(value, "backup")
                safety = sqlite3.connect(safety_path)
                try:
                    self.assertEqual(
                        safety.execute(
                            "SELECT value FROM app_settings WHERE key = 'selected'"
                        ).fetchone()[0],
                        "current",
                    )
                finally:
                    safety.close()
            finally:
                database.close()
                source.close()

    def test_invalid_restore_does_not_change_active_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid_backup = root / "invalid.sqlite3"
            invalid_backup.write_text("not a SQLite database", encoding="utf-8")
            database = Database(root / "active.sqlite3")
            database.initialize()
            try:
                with database.transaction() as connection:
                    connection.execute(
                        "INSERT INTO app_settings (key, value) VALUES (?, ?)",
                        ("selected", "current"),
                    )

                with self.assertRaises(DatabaseBackupError):
                    database.restore_from(
                        invalid_backup, root / "backups" / "before-restore.sqlite3"
                    )

                with database.transaction() as connection:
                    value = connection.execute(
                        "SELECT value FROM app_settings WHERE key = ?",
                        ("selected",),
                    ).fetchone()["value"]
                self.assertEqual(value, "current")
                self.assertFalse((root / "backups" / "before-restore.sqlite3").exists())
            finally:
                database.close()

    def test_legacy_database_is_copied_without_removing_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "old" / "data" / "mathmaster.sqlite3"
            legacy.parent.mkdir(parents=True)
            old_database = Database(legacy)
            old_database.initialize()
            try:
                with old_database.transaction() as connection:
                    connection.execute(
                        "INSERT INTO app_settings (key, value) VALUES (?, ?)",
                        ("existing", "retained"),
                    )
            finally:
                old_database.close()

            database = Database(root / "new" / "mathmaster.sqlite3", (legacy,))
            database.initialize()
            try:
                self.assertTrue(legacy.is_file())
                with database.transaction() as connection:
                    value = connection.execute(
                        "SELECT value FROM app_settings WHERE key = ?",
                        ("existing",),
                    ).fetchone()["value"]
                self.assertEqual(value, "retained")
            finally:
                database.close()

    def test_older_schema_backup_directory_is_created_before_migration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "older.sqlite3"
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    "CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
                )
                connection.execute(
                    "INSERT INTO app_settings (key, value) VALUES ('old', 'preserved')"
                )
                connection.execute("PRAGMA user_version = 1")
                connection.commit()
            finally:
                connection.close()
            database = Database(path)
            database.initialize()
            try:
                backups = list((path.parent / "backups").glob("pre-migration-*.sqlite3"))
                self.assertEqual(len(backups), 1)
                backup = sqlite3.connect(backups[0])
                try:
                    self.assertEqual(
                        backup.execute(
                            "SELECT value FROM app_settings WHERE key = 'old'"
                        ).fetchone()[0],
                        "preserved",
                    )
                finally:
                    backup.close()
            finally:
                database.close()


if __name__ == "__main__":
    unittest.main()
