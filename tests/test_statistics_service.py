from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from accounts.auth import AuthService
from database.database import Database
from learning.learning_service import LearningService
from mathematics.engine import MathEngine
from mathematics.topics import Topic
from statistics.service import StatisticsService


class StatisticsServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "statistics.sqlite3")
        self.database.initialize()
        auth = AuthService(self.database)
        self.user = auth.register("stats-user", "Stats User", "secure-pass-123")
        self.other_user = auth.register("stats-other", "Other User", "secure-pass-456")
        self.learning = LearningService(self.database, MathEngine(random.Random(73)))
        self.statistics = StatisticsService(self.database)
        self.addCleanup(self.temp_dir.cleanup)
        self.addCleanup(self.database.close)

    def test_statistics_and_recommendations_use_only_the_selected_users_history(self) -> None:
        session = self.learning.start_session(
            self.user.id, Topic.ADDITION, difficulty=2, question_count=3
        )
        session.answer(session.current_exercise.answer_text)
        session.next_question()
        session.answer("not a mathematical answer")
        session.next_question()
        session.answer("not a mathematical answer")

        other_session = self.learning.start_session(
            self.other_user.id, Topic.DIVISION, difficulty=1, question_count=1
        )
        other_session.answer(other_session.current_exercise.answer_text)

        snapshot = self.statistics.get_statistics(self.user.id)

        self.assertEqual(snapshot.solved_tasks, 3)
        self.assertEqual(snapshot.correct_answers, 1)
        self.assertAlmostEqual(snapshot.accuracy_percent, 33.3)
        self.assertEqual(snapshot.category_progress[0].category, "Arytmetyka")
        self.assertEqual(snapshot.category_progress[0].attempts, 3)
        self.assertEqual(snapshot.mistakes[0].topic, Topic.ADDITION.value)
        self.assertEqual(snapshot.mistakes[0].incorrect, 2)
        self.assertTrue(snapshot.mistakes[0].repeated)
        self.assertEqual(snapshot.recommendations[0].topic, Topic.ADDITION.value)
        self.assertEqual(len(snapshot.history), 3)
        self.assertFalse(snapshot.history[0].correct)
        self.assertEqual(len(snapshot.daily_progress), 14)
        self.assertEqual(snapshot.daily_progress[-1][1], 3)
        self.assertEqual(len(snapshot.weekly_progress), 12)
        self.assertEqual(snapshot.weekly_progress[-1][1], 3)
        self.assertEqual(snapshot.difficulty_history[-1].difficulty, 2)

        other_snapshot = self.statistics.get_statistics(self.other_user.id)
        self.assertEqual(other_snapshot.solved_tasks, 1)
        self.assertEqual(other_snapshot.correct_answers, 1)
        self.assertEqual(other_snapshot.mistakes, ())

    def test_empty_history_returns_zeroed_metrics_and_empty_topic_data(self) -> None:
        snapshot = self.statistics.get_statistics(self.user.id)

        self.assertEqual(snapshot.solved_tasks, 0)
        self.assertEqual(snapshot.accuracy_percent, 0)
        self.assertEqual(snapshot.study_seconds, 0)
        self.assertEqual(snapshot.topic_progress, ())
        self.assertEqual(snapshot.history, ())
        self.assertEqual(snapshot.recommendations, ())


if __name__ == "__main__":
    unittest.main()
