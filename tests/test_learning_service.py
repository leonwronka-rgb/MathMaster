from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from accounts.auth import AuthService
from database.database import Database
from learning.learning_service import LearningError, LearningService
from mathematics.engine import MathEngine
from mathematics.topic_library import LIBRARY_TOPICS
from mathematics.topics import Topic
from statistics.service import StatisticsService


class LearningServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "learning.sqlite3")
        self.database.initialize()
        self.auth = AuthService(self.database)
        self.user = self.auth.register("learner", "Learner", "secure-pass-123")
        self.other_user = self.auth.register("another", "Another", "secure-pass-456")
        self.service = LearningService(self.database, MathEngine(random.Random(81)))
        self.addCleanup(self.temp_dir.cleanup)
        self.addCleanup(self.database.close)

    def test_answers_are_saved_with_correct_user_and_session_summary(self) -> None:
        session = self.service.start_session(
            self.user.id, Topic.ADDITION, difficulty=2, question_count=2
        )
        first_answer = session.answer(session.current_exercise.answer_text)
        self.assertTrue(first_answer.correct)
        self.assertEqual(first_answer.progress, 0.5)
        session.next_question()
        second_answer = session.answer("incorrect")
        self.assertFalse(second_answer.correct)
        self.assertTrue(second_answer.session_finished)

        summary = session.summary()
        self.assertEqual(summary.correct_count, 1)
        self.assertEqual(summary.incorrect_count, 1)
        self.assertEqual(summary.accuracy_percent, 50)
        self.assertEqual(summary.answered_count, 2)

        history = self.service.get_recent_history(self.user.id)
        other_history = self.service.get_recent_history(self.other_user.id)
        self.assertEqual(len(history), 2)
        self.assertEqual(len(other_history), 0)
        self.assertEqual(history[0].submitted_answer, "incorrect")
        self.assertEqual(history[0].correct_answer, second_answer.correct_answer)
        self.assertIn("Odpowiedź:", history[0].solution)

    def test_adaptive_level_change_requires_explicit_user_approval(self) -> None:
        session = self.service.start_session(
            self.user.id, Topic.MULTIPLICATION, difficulty=2, question_count=5
        )
        for index in range(3):
            result = session.answer(session.current_exercise.answer_text)
            if index < 2:
                self.assertIsNone(result.suggested_difficulty)
                session.next_question()

        self.assertEqual(result.suggested_difficulty, 3)
        self.assertEqual(session.difficulty, 2)
        with self.assertRaises(LearningError):
            session.next_question()
        session.resolve_difficulty_change(accept=True)
        exercise = session.next_question()
        self.assertEqual(session.difficulty, 3)
        self.assertEqual(exercise.difficulty, 3)

    def test_adaptive_level_can_be_declined_and_errors_suggest_easier_tasks(self) -> None:
        session = self.service.start_session(
            self.user.id, Topic.ADDITION, difficulty=4, question_count=5
        )
        for index in range(3):
            result = session.answer("not a number")
            if index < 2:
                session.next_question()

        self.assertEqual(result.suggested_difficulty, 3)
        self.assertEqual(session.difficulty, 4)
        self.assertEqual(session.resolve_difficulty_change(accept=False), 4)
        self.assertEqual(session.next_question().difficulty, 4)

    def test_aborting_session_preserves_checked_history(self) -> None:
        session = self.service.start_session(
            self.user.id, Topic.FRACTION_ADDITION, difficulty=1, question_count=10
        )
        session.answer(session.current_exercise.answer_text)
        summary = session.finish(aborted=True)

        self.assertTrue(summary.aborted)
        self.assertEqual(summary.answered_count, 1)
        self.assertEqual(len(self.service.get_recent_history(self.user.id)), 1)
        self.assertTrue(session.finished)

    def test_requires_an_answer_before_advancing_or_completing(self) -> None:
        session = self.service.start_session(
            self.user.id, Topic.DIVISION, difficulty=1, question_count=1
        )
        with self.assertRaises(LearningError):
            session.next_question()
        with self.assertRaises(ValueError):
            session.answer(" ")

    def test_questions_are_not_repeated_within_the_last_30_across_sessions(self) -> None:
        repeated_question = MathEngine(random.Random(123)).generate(
            Topic.ADDITION, 2
        ).prompt
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO exercise_history (
                    user_id, topic, correct, difficulty, question
                ) VALUES (?, ?, 1, ?, ?)
                """,
                (self.user.id, Topic.ADDITION.value, 2, repeated_question),
            )

        service = LearningService(self.database, MathEngine(random.Random(123)))
        session = service.start_session(
            self.user.id, Topic.ADDITION, difficulty=2, question_count=1
        )

        self.assertNotEqual(session.current_exercise.prompt, repeated_question)

    def test_session_inputs_are_validated(self) -> None:
        for difficulty, count in ((0, 5), (6, 5), (2, 0), (2, 101)):
            with self.subTest(difficulty=difficulty, count=count):
                with self.assertRaises(ValueError):
                    self.service.start_session(
                        self.user.id, Topic.ADDITION, difficulty, count
                    )

    def test_library_exercises_keep_catalog_identity_in_history_and_statistics(self) -> None:
        catalog_topic = next(
            topic
            for topic in LIBRARY_TOPICS
            if topic.division == "Geometria płaska"
            and topic.subdivision == "Pola i obwody"
            and topic.exercise_topic == Topic.AREA
        )
        session = self.service.start_session(
            self.user.id,
            catalog_topic.exercise_topic,
            catalog_topic.difficulty,
            question_count=1,
            catalog_topic_id=catalog_topic.id,
        )
        session.answer(session.current_exercise.answer_text)

        with self.database.transaction() as connection:
            history = connection.execute(
                "SELECT catalog_topic_id FROM exercise_history WHERE user_id = ?",
                (self.user.id,),
            ).fetchone()
        self.assertEqual(history["catalog_topic_id"], catalog_topic.id)

        statistics = StatisticsService(self.database).get_statistics(self.user.id)
        progress = next(
            item for item in statistics.topic_progress if item.topic == catalog_topic.id
        )
        self.assertEqual(progress.topic_label, catalog_topic.title)
        self.assertEqual(progress.category, catalog_topic.division)


if __name__ == "__main__":
    unittest.main()
