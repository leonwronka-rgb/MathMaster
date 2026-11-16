from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from accounts.auth import (
    AccountValidationError,
    AuthenticationError,
    AuthService,
)
from accounts.profile import ProfileService
from database.database import Database


class AuthServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "accounts.sqlite3")
        self.database.initialize()
        self.auth = AuthService(self.database)
        self.addCleanup(self.temp_dir.cleanup)
        self.addCleanup(self.database.close)

    def test_registration_creates_user_and_isolated_progress(self) -> None:
        user = self.auth.register("alice", "Alice", "secure-pass-123")
        profile = ProfileService(self.database).get_profile(user.id)

        self.assertEqual(user.username, "alice")
        self.assertEqual(profile.display_name, "Alice")
        self.assertEqual(profile.xp, 0)
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT password_hash FROM users WHERE id = ?", (user.id,)
            ).fetchone()
        self.assertNotEqual(row["password_hash"], "secure-pass-123")
        self.assertTrue(row["password_hash"].startswith("$2"))

    def test_login_accepts_correct_password_and_rejects_wrong_password(self) -> None:
        created = self.auth.register("alice", "Alice", "secure-pass-123")

        authenticated = self.auth.authenticate("ALICE", "secure-pass-123")

        self.assertEqual(authenticated, created)
        with self.assertRaises(AuthenticationError):
            self.auth.authenticate("alice", "incorrect-pass")

    def test_duplicate_and_invalid_registration_are_rejected(self) -> None:
        self.auth.register("alice", "Alice", "secure-pass-123")
        with self.assertRaises(AccountValidationError):
            self.auth.register("ALICE", "Another Alice", "secure-pass-456")
        with self.assertRaises(AccountValidationError):
            self.auth.register("x", "Invalid", "short")

    def test_password_change_and_remembered_account(self) -> None:
        user = self.auth.register("alice", "Alice", "secure-pass-123")
        self.auth.remember_account(user.username)

        self.assertEqual(self.auth.get_remembered_username(), "alice")
        self.auth.change_password(user.id, "secure-pass-123", "new-secure-pass")
        with self.assertRaises(AuthenticationError):
            self.auth.authenticate("alice", "secure-pass-123")
        self.assertEqual(
            self.auth.authenticate("alice", "new-secure-pass").id, user.id
        )
        self.auth.remember_account(None)
        self.assertEqual(self.auth.get_remembered_username(), "")

    @patch("accounts.auth.keyring.set_password")
    @patch("accounts.auth.keyring.get_password", return_value="secure-pass-123")
    def test_remembered_password_uses_system_credential_store(
        self, get_password, set_password
    ) -> None:
        self.auth.register("alice", "Alice", "secure-pass-123")

        self.auth.remember_account("alice", "secure-pass-123")

        self.assertEqual(self.auth.get_remembered_password(), "secure-pass-123")
        set_password.assert_called_once_with(
            "MathMaster", "alice", "secure-pass-123"
        )
        get_password.assert_called_once_with(
            "MathMaster", "alice"
        )

    def test_deleting_account_cascades_data_without_affecting_other_users(self) -> None:
        first = self.auth.register("alice", "Alice", "secure-pass-123")
        second = self.auth.register("bob", "Bob", "secure-pass-456")
        self.auth.remember_account(first.username)
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO exercise_history (user_id, topic, correct) "
                "VALUES (?, ?, ?)",
                (first.id, "algebra", 1),
            )
            connection.execute(
                "INSERT INTO flashcards (user_id, front, back) VALUES (?, ?, ?)",
                (first.id, "1+1", "2"),
            )

        self.auth.delete_account(first.id, "secure-pass-123")

        with self.database.transaction() as connection:
            exercise_count = connection.execute(
                "SELECT COUNT(*) FROM exercise_history WHERE user_id = ?",
                (first.id,),
            ).fetchone()[0]
            card_count = connection.execute(
                "SELECT COUNT(*) FROM flashcards WHERE user_id = ?", (first.id,)
            ).fetchone()[0]
            remaining_users = connection.execute(
                "SELECT COUNT(*) FROM users"
            ).fetchone()[0]
        self.assertEqual(exercise_count, 0)
        self.assertEqual(card_count, 0)
        self.assertEqual(remaining_users, 1)
        self.assertEqual(self.auth.authenticate("bob", "secure-pass-456").id, second.id)
        self.assertEqual(self.auth.get_remembered_username(), "")


if __name__ == "__main__":
    unittest.main()
