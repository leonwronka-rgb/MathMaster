from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass

from accounts.auth import AccountDatabaseError
from database.database import Database


@dataclass(frozen=True, slots=True)
class UserProfile:
    user_id: int
    username: str
    display_name: str
    created_at: str
    xp: int
    level: int
    daily_goal_minutes: int


class ProfileService:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.logger = logging.getLogger(__name__)

    def get_profile(self, user_id: int) -> UserProfile:
        try:
            with self.database.transaction() as connection:
                row = connection.execute(
                    """
                    SELECT users.id, users.username, users.display_name, users.created_at,
                           user_progress.xp, user_progress.level,
                           user_progress.daily_goal_minutes
                    FROM users
                    JOIN user_progress ON user_progress.user_id = users.id
                    WHERE users.id = ?
                    """,
                    (user_id,),
                ).fetchone()
            if row is None:
                raise AccountDatabaseError("Nie znaleziono profilu użytkownika.")
            return UserProfile(
                user_id=int(row["id"]),
                username=str(row["username"]),
                display_name=str(row["display_name"]),
                created_at=str(row["created_at"]),
                xp=int(row["xp"]),
                level=int(row["level"]),
                daily_goal_minutes=int(row["daily_goal_minutes"]),
            )
        except sqlite3.Error as error:
            self.logger.exception("Database failure while reading user profile")
            raise AccountDatabaseError("Nie udało się odczytać profilu.") from error

    def update_display_name(self, user_id: int, display_name: str) -> str:
        display_name = display_name.strip()
        if not display_name or len(display_name) > 60:
            raise ValueError("Nazwa profilu musi mieć od 1 do 60 znaków.")
        try:
            with self.database.transaction() as connection:
                cursor = connection.execute(
                    "UPDATE users SET display_name = ? WHERE id = ?",
                    (display_name, user_id),
                )
                if cursor.rowcount != 1:
                    raise AccountDatabaseError("Nie znaleziono profilu użytkownika.")
            return display_name
        except sqlite3.Error as error:
            self.logger.exception("Database failure while updating user profile")
            raise AccountDatabaseError("Nie udało się zaktualizować profilu.") from error

    def update_username(self, user_id: int, username: str) -> str:
        from accounts.auth import AuthService

        username = username.strip()
        AuthService._validate_username(username)
        try:
            with self.database.transaction() as connection:
                cursor = connection.execute(
                    "UPDATE users SET username = ? WHERE id = ?",
                    (username, user_id),
                )
                if cursor.rowcount != 1:
                    raise AccountDatabaseError("Nie znaleziono profilu użytkownika.")
            return username
        except sqlite3.IntegrityError as error:
            raise ValueError("Ta nazwa użytkownika jest już zajęta.") from error
        except sqlite3.Error as error:
            self.logger.exception("Database failure while updating username")
            raise AccountDatabaseError("Nie udało się zmienić nazwy użytkownika.") from error