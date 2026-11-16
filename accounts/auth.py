from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass

import bcrypt
import keyring

from database.database import Database

_USERNAME = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
_MAX_PASSWORD_BYTES = 72
_CREDENTIAL_SERVICE = "MathMaster"


class AccountError(Exception):
    """Expected account operation failure safe to display to the user."""


class AccountValidationError(AccountError):
    pass


class AuthenticationError(AccountError):
    pass


class AccountDatabaseError(AccountError):
    pass


@dataclass(frozen=True, slots=True)
class User:
    id: int
    username: str
    display_name: str


class AuthService:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.logger = logging.getLogger(__name__)

    def register(self, username: str, display_name: str, password: str) -> User:
        username = username.strip()
        display_name = display_name.strip()
        self._validate_username(username)
        if not display_name or len(display_name) > 60:
            raise AccountValidationError("Nazwa profilu musi mieć od 1 do 60 znaków.")
        password_bytes = self._validate_password(password)
        password_hash = bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("ascii")
        try:
            with self.database.transaction() as connection:
                cursor = connection.execute(
                    "INSERT INTO users (username, display_name, password_hash) "
                    "VALUES (?, ?, ?)",
                    (username, display_name, password_hash),
                )
                user_id = int(cursor.lastrowid)
                connection.execute(
                    "INSERT INTO user_progress (user_id) VALUES (?)", (user_id,)
                )
            return User(user_id, username, display_name)
        except sqlite3.IntegrityError as error:
            if "users.username" in str(error):
                raise AccountValidationError(
                    "Ta nazwa użytkownika jest już zajęta."
                ) from error
            self.logger.exception("Database constraint failure while registering user")
            raise AccountDatabaseError("Nie udało się utworzyć konta.") from error
        except sqlite3.Error as error:
            self.logger.exception("Database failure while registering user")
            raise AccountDatabaseError("Nie udało się utworzyć konta.") from error

    def authenticate(self, username: str, password: str) -> User:
        username = username.strip()
        if not _USERNAME.fullmatch(username):
            raise AuthenticationError("Nieprawidłowa nazwa użytkownika lub hasło.")
        password_bytes = password.encode("utf-8")
        if not password_bytes or len(password_bytes) > _MAX_PASSWORD_BYTES:
            raise AuthenticationError("Nieprawidłowa nazwa użytkownika lub hasło.")
        try:
            with self.database.transaction() as connection:
                row = connection.execute(
                    "SELECT id, username, display_name, password_hash "
                    "FROM users WHERE username = ?",
                    (username,),
                ).fetchone()
            if row is None or not bcrypt.checkpw(
                password_bytes, row["password_hash"].encode("ascii")
            ):
                raise AuthenticationError(
                    "Nieprawidłowa nazwa użytkownika lub hasło."
                )
            return User(int(row["id"]), row["username"], row["display_name"])
        except AuthenticationError:
            raise
        except sqlite3.Error as error:
            self.logger.exception("Database failure while authenticating user")
            raise AccountDatabaseError("Nie udało się zalogować. Spróbuj ponownie.") from error

    def change_password(
        self, user_id: int, current_password: str, new_password: str
    ) -> None:
        current_bytes = current_password.encode("utf-8")
        if not current_bytes or len(current_bytes) > _MAX_PASSWORD_BYTES:
            raise AuthenticationError("Obecne hasło jest nieprawidłowe.")
        new_bytes = self._validate_password(new_password)
        new_hash = bcrypt.hashpw(new_bytes, bcrypt.gensalt()).decode("ascii")
        try:
            with self.database.transaction() as connection:
                row = connection.execute(
                    "SELECT password_hash, username FROM users WHERE id = ?", (user_id,)
                ).fetchone()
                if row is None or not bcrypt.checkpw(
                    current_bytes, row["password_hash"].encode("ascii")
                ):
                    raise AuthenticationError("Obecne hasło jest nieprawidłowe.")
                connection.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (new_hash, user_id),
                )
            if self.get_remembered_username() == row["username"]:
                try:
                    keyring.set_password(
                        _CREDENTIAL_SERVICE, row["username"], new_password
                    )
                except keyring.errors.KeyringError as error:
                    self.logger.exception(
                        "Could not update remembered account password"
                    )
                    raise AccountDatabaseError(
                        "Hasło zmieniono, ale nie udało się zaktualizować "
                        "zapamiętanego hasła na tym urządzeniu."
                    ) from error
        except AuthenticationError:
            raise
        except sqlite3.Error as error:
            self.logger.exception("Database failure while changing password")
            raise AccountDatabaseError("Nie udało się zmienić hasła.") from error

    def delete_account(self, user_id: int, password: str) -> None:
        password_bytes = password.encode("utf-8")
        if not password_bytes or len(password_bytes) > _MAX_PASSWORD_BYTES:
            raise AuthenticationError("Hasło jest nieprawidłowe.")
        try:
            with self.database.transaction() as connection:
                row = connection.execute(
                    "SELECT password_hash, username FROM users WHERE id = ?", (user_id,)
                ).fetchone()
                if row is None or not bcrypt.checkpw(
                    password_bytes, row["password_hash"].encode("ascii")
                ):
                    raise AuthenticationError("Hasło jest nieprawidłowe.")
                connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
                connection.execute(
                    "DELETE FROM app_settings WHERE key = 'remembered_username' "
                    "AND value = ?",
                    (row["username"],),
                )
            try:
                keyring.delete_password(_CREDENTIAL_SERVICE, row["username"])
            except keyring.errors.PasswordDeleteError:
                pass
            except keyring.errors.KeyringError as error:
                self.logger.exception("Could not remove deleted account password")
                raise AccountDatabaseError(
                    "Konto usunięto, ale nie udało się usunąć zapamiętanego hasła."
                ) from error
        except AuthenticationError:
            raise
        except sqlite3.Error as error:
            self.logger.exception("Database failure while deleting account")
            raise AccountDatabaseError("Nie udało się usunąć konta.") from error

    def get_remembered_username(self) -> str:
        try:
            with self.database.transaction() as connection:
                row = connection.execute(
                    "SELECT value FROM app_settings WHERE key = ?",
                    ("remembered_username",),
                ).fetchone()
            return str(row["value"]) if row else ""
        except sqlite3.Error as error:
            self.logger.exception("Database failure while reading remembered account")
            raise AccountDatabaseError(
                "Nie udało się odczytać zapamiętanego konta."
            ) from error

    def get_remembered_password(self) -> str:
        try:
            return keyring.get_password(
                _CREDENTIAL_SERVICE, self.get_remembered_username()
            ) or ""
        except keyring.errors.KeyringError as error:
            self.logger.exception("Could not read remembered account password")
            raise AccountDatabaseError(
                "Nie udało się odczytać zapamiętanego hasła."
            ) from error

    def remember_account(self, username: str | None, password: str | None = None) -> None:
        previous_username = self.get_remembered_username()
        try:
            with self.database.transaction() as connection:
                if username is None:
                    connection.execute(
                        "DELETE FROM app_settings WHERE key = ?",
                        ("remembered_username",),
                    )
                else:
                    connection.execute(
                        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        ("remembered_username", username),
                    )
        except sqlite3.Error as error:
            self.logger.exception("Database failure while saving remembered account")
            raise AccountDatabaseError(
                "Nie udało się zapisać ustawienia zapamiętanego konta."
            ) from error
        try:
            if previous_username and previous_username != username:
                try:
                    keyring.delete_password(_CREDENTIAL_SERVICE, previous_username)
                except keyring.errors.PasswordDeleteError:
                    pass
            if username is None or not password:
                if previous_username:
                    keyring.delete_password(_CREDENTIAL_SERVICE, previous_username)
            else:
                keyring.set_password(_CREDENTIAL_SERVICE, username, password)
        except keyring.errors.PasswordDeleteError:
            pass
        except keyring.errors.KeyringError as error:
            self.logger.exception("Could not save remembered account password")
            raise AccountDatabaseError(
                "Nie udało się bezpiecznie zapisać hasła na tym urządzeniu."
            ) from error

    @staticmethod
    def _validate_username(username: str) -> None:
        if not _USERNAME.fullmatch(username):
            raise AccountValidationError(
                "Nazwa użytkownika musi mieć 3–32 znaki: litery, cyfry, kropka, "
                "myślnik lub podkreślenie."
            )

    @staticmethod
    def _validate_password(password: str) -> bytes:
        password_bytes = password.encode("utf-8")
        if len(password_bytes) < 8:
            raise AccountValidationError("Hasło musi mieć co najmniej 8 znaków.")
        if len(password_bytes) > _MAX_PASSWORD_BYTES:
            raise AccountValidationError(
                "Hasło może mieć maksymalnie 72 bajty UTF-8."
            )
        return password_bytes
