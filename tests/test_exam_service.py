from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from accounts.auth import AuthService
from database.database import Database
from exams.exam_service import (
    ExamError,
    ExamGradingScale,
    ExamService,
)


class ExamServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "exams.sqlite3")
        self.database.initialize()
        auth = AuthService(self.database)
        self.user = auth.register("exam-user", "Exam User", "secure-pass-123")
        self.other_user = auth.register("exam-other", "Other User", "secure-pass-456")
        self.service = ExamService(self.database, rng=random.Random(301))
        self.addCleanup(self.temp_dir.cleanup)
        self.addCleanup(self.database.close)

    def test_completion_checks_answers_and_persists_summary_and_review_details(self) -> None:
        attempt = self.service.start_exam(
            user_id=self.user.id,
            subject="Matematyka",
            category="Arytmetyka",
            difficulty=2,
            question_count=3,
            time_limit_seconds=600,
            grading_scale=ExamGradingScale((25, 45, 65, 80, 95)),
        )
        attempt.set_answer(0, attempt.questions[0].exercise.answer_text)
        attempt.set_answer(1, "wrong")
        self.assertTrue(attempt.toggle_marked(1))

        completion = self.service.complete_exam(self.user.id, attempt)

        self.assertEqual(completion.result.correct_count, 1)
        self.assertAlmostEqual(completion.result.score_percent, 33.3)
        self.assertEqual(completion.result.grade, 2)
        self.assertEqual(completion.result.answers[2].submitted_answer, "")
        self.assertFalse(completion.result.answers[2].correct)
        self.assertTrue(completion.result.answers[1].marked_for_review)
        self.assertIsNone(completion.previous_result)
        self.assertEqual(completion.reward.xp_awarded, 145)

        with self.database.transaction() as connection:
            row = connection.execute(
                """
                SELECT subject, category, question_count, correct_count,
                       score, grade, passed, time_limit_seconds
                FROM exam_results WHERE user_id = ?
                """,
                (self.user.id,),
            ).fetchone()
            details = connection.execute(
                """
                SELECT question_number, submitted_answer, correct,
                       marked_for_review
                FROM exam_answer_details
                WHERE exam_id = ? ORDER BY question_number
                """,
                (completion.reward.exam_id,),
            ).fetchall()
        self.assertEqual(row["subject"], "Matematyka")
        self.assertEqual(row["category"], "Arytmetyka")
        self.assertEqual(row["question_count"], 3)
        self.assertEqual(row["correct_count"], 1)
        self.assertEqual(row["grade"], 2)
        self.assertEqual(row["passed"], 1)
        self.assertEqual(row["time_limit_seconds"], 600)
        self.assertEqual(len(details), 3)
        self.assertEqual(details[2]["submitted_answer"], "")
        self.assertEqual(details[2]["correct"], 0)
        self.assertEqual(details[1]["marked_for_review"], 1)

        repeated = self.service.complete_exam(self.user.id, attempt)
        self.assertTrue(repeated.reward.duplicate_attempt)
        self.assertEqual(repeated.reward.xp_awarded, 0)
        self.assertEqual(len(self.service.get_recent_results(self.user.id)), 1)

    def test_timer_expiry_ends_exam_and_unanswered_questions_get_no_points(self) -> None:
        now = [100.0]
        attempt = self.service.start_exam(
            user_id=self.user.id,
            subject="Matematyka",
            category="Procenty",
            difficulty=1,
            question_count=2,
            time_limit_seconds=60,
            clock=lambda: now[0],
        )
        attempt.set_answer(0, attempt.questions[0].exercise.answer_text)
        now[0] = 161.0
        self.assertTrue(attempt.expired)
        with self.assertRaises(ExamError):
            attempt.set_answer(1, attempt.questions[1].exercise.answer_text)

        completion = self.service.complete_exam(self.user.id, attempt)
        self.assertEqual(completion.result.duration_seconds, 60)
        self.assertEqual(completion.result.correct_count, 1)
        self.assertEqual(completion.result.question_count, 2)
        self.assertEqual(completion.result.score_percent, 50)
        self.assertEqual(completion.result.answers[1].submitted_answer, "")
        self.assertFalse(completion.result.answers[1].correct)

    def test_previous_exam_comparison_and_account_isolation(self) -> None:
        first = self.service.start_exam(
            user_id=self.user.id,
            subject="Matematyka",
            category="Geometria",
            difficulty=3,
            question_count=1,
            time_limit_seconds=600,
        )
        first.set_answer(0, first.questions[0].exercise.answer_text)
        self.service.complete_exam(self.user.id, first)

        second = self.service.start_exam(
            user_id=self.user.id,
            subject="Matematyka",
            category="Geometria",
            difficulty=3,
            question_count=1,
            time_limit_seconds=600,
        )
        second.set_answer(0, "wrong")
        completion = self.service.complete_exam(self.user.id, second)
        self.assertEqual(completion.previous_result.score_percent, 100)
        self.assertEqual(completion.score_difference, -100)

        other_history = self.service.get_recent_results(self.other_user.id)
        self.assertEqual(other_history, ())
        with self.assertRaises(ValueError):
            self.service.complete_exam(self.other_user.id, second)

    def test_invalid_grade_scale_and_exam_configuration_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ExamGradingScale((30, 50, 50, 80, 95))
        with self.assertRaises(ValueError):
            ExamGradingScale((0, 40, 60, 80, 95))
        with self.assertRaises(ValueError):
            self.service.start_exam(
                user_id=self.user.id,
                subject="Matematyka",
                category="Nieznana",
                difficulty=1,
                question_count=5,
                time_limit_seconds=600,
            )
        with self.assertRaises(ValueError):
            self.service.start_exam(
                user_id=self.user.id,
                subject="Matematyka",
                category="Arytmetyka",
                difficulty=1,
                question_count=5,
                time_limit_seconds=30,
            )


if __name__ == "__main__":
    unittest.main()
