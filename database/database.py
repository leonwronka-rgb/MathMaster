from __future__ import annotations

import sqlite3
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from database.migrations import CURRENT_SCHEMA_VERSION, apply_migrations


class DatabaseBackupError(RuntimeError):
    """A database snapshot or restore could not be completed safely."""


class Database:
    def __init__(
        self,
        path: Path,
        legacy_database_paths: tuple[Path, ...] = (),
    ) -> None:
        self.path = path
        self.legacy_database_paths = legacy_database_paths
        self._connection: sqlite3.Connection | None = None

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_database()
        existed_before_initialize = self.path.exists()
        connection = self._connect()
        try:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if existed_before_initialize and version < CURRENT_SCHEMA_VERSION:
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                self._backup_connection(
                    connection,
                    self.path.parent / "backups"
                    / f"pre-migration-v{version}-{stamp}.sqlite3",
                )
            apply_migrations(connection)
        except Exception:
            connection.close()
            self._connection = None
            raise
        self._connection = connection

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        if self._connection is None:
            raise RuntimeError("Baza danych nie została zainicjalizowana.")
        with self._connection:
            yield self._connection

    def backup_to(self, destination: Path) -> Path:
        if self._connection is None:
            raise RuntimeError("Baza danych nie została zainicjalizowana.")
        destination = Path(destination).expanduser().resolve()
        if destination == self.path.expanduser().resolve():
            raise ValueError("Kopia zapasowa nie może nadpisać aktywnej bazy danych.")
        if self._connection.in_transaction:
            raise RuntimeError("Nie można wykonać kopii w trakcie transakcji.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._backup_connection(self._connection, destination)
        return destination

    def restore_from(self, source: Path, safety_backup: Path) -> Path:
        if self._connection is None:
            raise RuntimeError("Baza danych nie została zainicjalizowana.")
        source = Path(source).expanduser().resolve()
        if source == self.path.expanduser().resolve():
            raise ValueError("Nie można przywrócić bazy z jej własnego pliku.")
        if not source.is_file():
            raise FileNotFoundError(f"Nie znaleziono kopii zapasowej: {source}")
        if self._connection.in_transaction:
            raise RuntimeError("Nie można przywrócić bazy w trakcie transakcji.")

        try:
            check = sqlite3.connect(source)
            try:
                check.execute("PRAGMA query_only = ON")
                version = int(check.execute("PRAGMA user_version").fetchone()[0])
                integrity = str(check.execute("PRAGMA integrity_check").fetchone()[0])
            finally:
                check.close()
            if integrity != "ok":
                raise DatabaseBackupError("Kopia zapasowa jest uszkodzona.")
            if version > CURRENT_SCHEMA_VERSION:
                raise DatabaseBackupError(
                    "Kopia pochodzi z nowszej wersji aplikacji i nie może zostać przywrócona."
                )
            safety_path = self.backup_to(safety_backup)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{self.path.name}.restore-",
                suffix=".tmp",
                dir=self.path.parent,
            )
            os.close(descriptor)
            temporary_path = Path(temporary_name)
            try:
                source_connection = sqlite3.connect(source)
                restored_connection = sqlite3.connect(temporary_path)
                try:
                    source_connection.backup(restored_connection)
                    apply_migrations(restored_connection)
                    restored_connection.execute("PRAGMA foreign_keys = ON")
                    integrity = str(
                        restored_connection.execute(
                            "PRAGMA integrity_check"
                        ).fetchone()[0]
                    )
                    if integrity != "ok":
                        raise DatabaseBackupError(
                            "Przywrócona baza nie przeszła kontroli integralności."
                        )
                finally:
                    source_connection.close()
                    restored_connection.close()

                self._connection.close()
                self._connection = None
                os.replace(temporary_path, self.path)
                self._connection = self._connect()
                return safety_path
            finally:
                if temporary_path.exists():
                    temporary_path.unlink()
        except (sqlite3.Error, OSError) as error:
            if self._connection is None and self.path.exists():
                self._connection = self._connect()
            raise DatabaseBackupError(
                "Nie udało się bezpiecznie przywrócić kopii zapasowej."
            ) from error

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _migrate_legacy_database(self) -> None:
        if self.path.exists():
            return
        for legacy_path in self.legacy_database_paths:
            source = Path(legacy_path).expanduser().resolve()
            if source == self.path.expanduser().resolve() or not source.is_file():
                continue
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{self.path.name}.migration-",
                suffix=".tmp",
                dir=self.path.parent,
            )
            os.close(descriptor)
            temporary_path = Path(temporary_name)
            try:
                self._copy_database_file(source, temporary_path)
                os.replace(temporary_path, self.path)
                return
            except (sqlite3.Error, OSError) as error:
                raise DatabaseBackupError(
                    f"Nie udało się przenieść istniejącej bazy z {source}."
                ) from error
            finally:
                if temporary_path.exists():
                    temporary_path.unlink()

    @staticmethod
    def _backup_connection(
        source: sqlite3.Connection, destination: Path
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        try:
            target = sqlite3.connect(temporary_path)
            try:
                source.backup(target)
                integrity = str(target.execute("PRAGMA integrity_check").fetchone()[0])
                if integrity != "ok":
                    raise DatabaseBackupError(
                        "Kopia zapasowa nie przeszła kontroli integralności."
                    )
            finally:
                target.close()
            os.replace(temporary_path, destination)
        except (sqlite3.Error, OSError) as error:
            raise DatabaseBackupError(
                f"Nie udało się utworzyć kopii zapasowej: {destination}"
            ) from error
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    @staticmethod
    def _copy_database_file(source: Path, destination: Path) -> None:
        source_connection = sqlite3.connect(source)
        target_connection = sqlite3.connect(destination)
        try:
            source_connection.backup(target_connection)
            integrity = str(
                target_connection.execute("PRAGMA integrity_check").fetchone()[0]
            )
            if integrity != "ok":
                raise DatabaseBackupError(
                    f"Niepoprawna kopia starszej bazy: {source}"
                )
        finally:
            source_connection.close()
            target_connection.close()