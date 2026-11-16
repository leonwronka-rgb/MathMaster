from __future__ import annotations

import json
import random
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from accounts.auth import AuthService
from database.database import Database
from flashcards.service import FlashcardError, FlashcardService
from gamification.service import GamificationService
from mathematics.engine import MathEngine
from mathematics.topic_library import LIBRARY_TOPICS
from mathematics.topics import Topic


class FlashcardServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "flashcards.sqlite3")
        self.database.initialize()
        auth = AuthService(self.database)
        self.user = auth.register("cards_user", "Cards User", "secure-pass-123")
        self.other_user = auth.register("cards_other", "Other User", "secure-pass-456")
        self.now = datetime(2026, 2, 10, 12, 0, tzinfo=timezone.utc)
        self.service = FlashcardService(
            self.database,
            MathEngine(random.Random(41)),
            clock=lambda: self.now,
            rng=random.Random(41),
        )
        self.addCleanup(self.temp_dir.cleanup)
        self.addCleanup(self.database.close)

    def test_cards_decks_and_favorites_are_isolated_by_user(self) -> None:
        deck = self.service.create_deck(self.user.id, "Algebra")
        card = self.service.create_card(
            self.user.id, "2 + 2", "4", deck_id=deck.id
        )
        self.assertEqual(self.service.list_cards(self.user.id), (card,))
        self.assertEqual(self.service.list_cards(self.other_user.id), ())

        self.assertTrue(self.service.toggle_favorite(self.user.id, card.id))
        self.assertEqual(
            self.service.list_cards(self.user.id, favorites_only=True)[0].id,
            card.id,
        )
        with self.assertRaises(FlashcardError):
            self.service.get_card(self.other_user.id, card.id)

    def test_review_scheduling_history_and_daily_stats(self) -> None:
        card = self.service.create_card(self.user.id, "Pytanie", "Odpowiedź")

        first = self.service.review(self.user.id, card.id, "know")

        self.assertEqual(first.mastery, 1)
        self.assertEqual(first.next_review_at, "2026-02-11 12:00:00")
        self.assertEqual(
            self.service.get_review_history(self.user.id, card.id)[0].next_review_at,
            first.next_review_at,
        )
        stats = self.service.get_stats(self.user.id)
        self.assertEqual(stats.studied_today, 1)
        self.assertEqual(stats.accuracy_percent, 100)
        self.assertEqual(stats.streak_days, 1)
        self.assertEqual(self.service.get_due_cards(self.user.id), ())
        self.assertEqual(
            len(self.service.get_all_cards_for_study(self.user.id)), 1
        )

        self.now = datetime(2026, 2, 11, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(len(self.service.get_due_cards(self.user.id)), 1)

    def test_again_schedules_short_repeat_and_records_incorrect_result(self) -> None:
        card = self.service.create_card(self.user.id, "Pytanie", "Odpowiedź")

        review = self.service.review(self.user.id, card.id, "again")

        self.assertFalse(review.correct)
        self.assertEqual(review.mastery, 0)
        self.assertEqual(review.next_review_at, "2026-02-10 12:10:00")
        stats = self.service.get_stats(self.user.id)
        self.assertEqual(stats.correct_today, 0)
        self.assertEqual(stats.accuracy_percent, 0)

    def test_test_mode_records_deck_session_accuracy_for_achievement(self) -> None:
        deck = self.service.create_deck(self.user.id, "Algebra")
        first = self.service.create_card(self.user.id, "2 + 2", "4", deck_id=deck.id)
        second = self.service.create_card(self.user.id, "3 + 3", "6", deck_id=deck.id)
        self.service.review(
            self.user.id,
            first.id,
            "again",
            test_correct=False,
            test_session_id="failed-test",
        )
        self.service.review(
            self.user.id,
            first.id,
            "know",
            test_correct=True,
            test_session_id="perfect-test",
        )
        self.service.review(
            self.user.id,
            second.id,
            "know",
            test_correct=True,
            test_session_id="perfect-test",
        )

        statuses = {
            item.key: item
            for item in GamificationService(self.database).get_achievements(
                self.user.id
            )
        }

        self.assertTrue(statuses["deck_perfect"].unlocked)
        with self.database.transaction() as connection:
            incorrect_test_count = connection.execute(
                """
                SELECT COUNT(*) FROM flashcard_reviews
                WHERE user_id = ? AND tested = 1 AND correct = 0
                """,
                (self.user.id,),
            ).fetchone()[0]
        self.assertEqual(incorrect_test_count, 1)

    def test_json_round_trip_and_invalid_data(self) -> None:
        deck = self.service.create_deck(self.user.id, "Ułamki")
        card = self.service.create_card(
            self.user.id, "1/2 + 1/2", "1", deck_id=deck.id, division="Ułamki"
        )
        self.service.toggle_favorite(self.user.id, card.id)

        exported = self.service.export_json(self.user.id, deck_id=deck.id)
        self.assertEqual(json.loads(exported)["format"], "MathMaster.flashcards")
        imported = self.service.import_json(self.other_user.id, exported)

        self.assertEqual(imported, 1)
        copied = self.service.list_cards(self.other_user.id)[0]
        self.assertEqual((copied.front, copied.back, copied.division), ("1/2 + 1/2", "1", "Ułamki"))
        self.assertTrue(copied.favorite)
        with self.assertRaises(FlashcardError):
            self.service.import_json(self.user.id, '{"format":"invalid"}')

    def test_topic_generation_creates_answer_and_solution_cards(self) -> None:
        topic = next(
            item for item in LIBRARY_TOPICS if item.exercise_topic == Topic.ADDITION
        )

        generated = self.service.create_from_topic(
            self.user.id, topic, count=2
        )

        self.assertEqual(len(generated), 2)
        self.assertTrue(all(card.front and card.back for card in generated))
        self.assertTrue(all(card.topic_id == topic.id for card in generated))
        self.assertTrue(all(card.back.splitlines()[0] for card in generated))

    def test_daily_goal_validation(self) -> None:
        self.service.set_daily_goal(self.user.id, 12)
        self.assertEqual(self.service.get_stats(self.user.id).daily_goal, 12)
        with self.assertRaises(FlashcardError):
            self.service.set_daily_goal(self.user.id, 0)

    def test_migration_preserves_legacy_flashcards_and_assigns_default_deck(self) -> None:
        legacy_path = Path(self.temp_dir.name) / "legacy.sqlite3"
        connection = sqlite3.connect(legacy_path)
        try:
            connection.executescript(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL
                );
                INSERT INTO users VALUES (1, 'legacy', 'Legacy', 'hash');
                CREATE TABLE flashcards (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    front TEXT NOT NULL,
                    back TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE exercise_history (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    topic TEXT NOT NULL
                );
                INSERT INTO flashcards (user_id, front, back)
                VALUES (1, 'Stare pytanie', 'Stara odpowiedź');
                PRAGMA user_version = 7;
                """
            )
        finally:
            connection.close()

        migrated = Database(legacy_path)
        migrated.initialize()
        try:
            cards = FlashcardService(migrated).list_cards(1)
            self.assertEqual(len(cards), 1)
            self.assertEqual(
                (cards[0].front, cards[0].back, cards[0].deck_name),
                ("Stare pytanie", "Stara odpowiedź", "Moje fiszki"),
            )
            self.assertIsNotNone(cards[0].next_review_at)
        finally:
            migrated.close()


if __name__ == "__main__":
    unittest.main()
