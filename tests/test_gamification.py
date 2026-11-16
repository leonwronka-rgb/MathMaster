from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from accounts.auth import AuthService
from database.database import Database
from gamification.service import GamificationService, RankingSort
from learning.learning_service import LearningService
from mathematics.topics import Topic
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


class GamificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "game.sqlite3")
        self.database.initialize()
        self.auth = AuthService(self.database)
        self.user = self.auth.register("player", "Player", "secure-pass-123")
        self.other_user = self.auth.register("rival", "Rival", "secure-pass-456")
        self.gamification = GamificationService(self.database)
        self.learning = LearningService(self.database)
        self.addCleanup(self.temp_dir.cleanup)
        self.addCleanup(self.database.close)

    def test_correct_answer_xp_topic_completion_and_level_progress(self) -> None:
        session = self.learning.start_session(
            self.user.id, Topic.ADDITION, difficulty=1, question_count=2
        )
        first = session.answer(session.current_exercise.answer_text)
        self.assertEqual(first.xp_awarded, 35)  # Task XP and two first-answer awards.
        self.assertEqual(first.total_xp, 35)
        self.assertEqual(first.level, 1)

        session.next_question()
        second = session.answer(session.current_exercise.answer_text)
        self.assertEqual(second.xp_awarded, 70)  # Task XP and one-time topic rewards.
        self.assertEqual(second.total_xp, 105)
        progress = self.gamification.get_level_progress(self.user.id)
        self.assertEqual(progress.level, 2)
        self.assertEqual(progress.xp_to_next_level, 195)
        self.assertEqual(progress.level, 2)
        self.assertEqual(progress.progress, 0.025)

        repeat = self.learning.start_session(
            self.user.id, Topic.ADDITION, difficulty=1, question_count=1
        )
        repeated = repeat.answer(repeat.current_exercise.answer_text)
        self.assertEqual(repeated.xp_awarded, 5)
        self.assertEqual(repeated.total_xp, 110)

    def test_difficulty_xp_rates_and_level_thresholds(self) -> None:
        expected = ((1, 5), (3, 10), (5, 20))
        total = 0
        for index, (difficulty, points) in enumerate(expected):
            session = self.learning.start_session(
                self.user.id,
                (Topic.ADDITION, Topic.SUBTRACTION, Topic.MULTIPLICATION)[index],
                difficulty=difficulty,
                question_count=2,
            )
            result = session.answer(session.current_exercise.answer_text)
            if index == 0:
                # First-task achievement is independent of task-difficulty XP.
                self.assertEqual(result.xp_awarded - 30, points)
            else:
                self.assertEqual(result.xp_awarded, points)
            total += points
        self.assertEqual(total, 35)
        self.assertEqual(self.gamification.level_for_xp(99), 1)
        self.assertEqual(self.gamification.level_for_xp(100), 2)
        self.assertEqual(self.gamification.level_for_xp(299), 2)
        self.assertEqual(self.gamification.level_for_xp(300), 3)

    def test_achievements_are_unlocked_and_rewarded_only_once(self) -> None:
        session = self.learning.start_session(
            self.user.id, Topic.ADDITION, difficulty=1, question_count=1
        )
        result = session.answer(session.current_exercise.answer_text)
        self.assertEqual(
            [achievement.key for achievement in result.achievements],
            ["first_exercise", "first_correct", "first_topic"],
        )
        entries = self.gamification.get_achievements(self.user.id)
        unlocked = [entry for entry in entries if entry.unlocked]
        self.assertEqual(
            [entry.key for entry in unlocked],
            ["first_exercise", "first_correct", "first_topic"],
        )

        another = self.learning.start_session(
            self.user.id, Topic.SUBTRACTION, difficulty=1, question_count=1
        )
        repeat_result = another.answer(another.current_exercise.answer_text)
        self.assertNotIn(
            "first_exercise",
            [achievement.key for achievement in repeat_result.achievements],
        )

    def test_exam_rewards_are_idempotent_and_rankings_are_local(self) -> None:
        first = self.gamification.record_exam_result(
            user_id=self.user.id,
            exam_name="Algebra final",
            score=90,
            difficulty=5,
            passed=True,
            attempt_key="attempt-001",
        )
        self.assertEqual(first.xp_awarded, 245)
        self.assertIn("difficult_exam", [item.key for item in first.achievements])
        repeated_attempt = self.gamification.record_exam_result(
            user_id=self.user.id,
            exam_name="Algebra final",
            score=90,
            difficulty=5,
            passed=True,
            attempt_key="attempt-001",
        )
        self.assertTrue(repeated_attempt.duplicate_attempt)
        self.assertEqual(repeated_attempt.xp_awarded, 0)
        repeated_exam = self.gamification.record_exam_result(
            user_id=self.user.id,
            exam_name="Algebra final",
            score=95,
            difficulty=5,
            passed=True,
            attempt_key="attempt-002",
        )
        self.assertEqual(repeated_exam.xp_awarded, 0)

        xp_ranking = self.gamification.get_ranking(self.user.id, RankingSort.XP)
        exam_ranking = self.gamification.get_ranking(
            self.user.id, RankingSort.EXAMS
        )
        self.assertEqual(xp_ranking[0].user_id, self.user.id)
        self.assertEqual(exam_ranking[0].completed_exams, 2)
        self.assertEqual(
            self.gamification.get_ranking(self.other_user.id)[0].user_id,
            self.user.id,
        )

    def test_failed_exam_does_not_award_exam_xp_or_completed_exam_credit(self) -> None:
        result = self.gamification.record_exam_result(
            user_id=self.user.id,
            exam_name="Trial",
            score=39,
            difficulty=5,
            passed=False,
            attempt_key="failed-attempt",
        )
        self.assertEqual(result.xp_awarded, 15)  # Completed-exam achievement only.
        ranking = self.gamification.get_ranking(self.user.id, RankingSort.EXAMS)
        self.assertEqual(ranking[0].completed_exams, 0)
        achievements = self.gamification.get_achievements(self.user.id)
        self.assertTrue(next(item for item in achievements if item.key == "first_exam").unlocked)
        self.assertFalse(
            next(
                item for item in achievements if item.key == "first_passed_exam"
            ).unlocked
        )

    def test_activity_unlocks_streak_daily_and_category_achievements_once(self) -> None:
        with self.database.transaction() as connection:
            for days_ago in range(10):
                study_day = date.today() - timedelta(days=days_ago)
                connection.execute(
                    """
                    INSERT INTO exercise_history
                        (user_id, topic, correct, difficulty, completed_at)
                    VALUES (?, ?, 1, 1, ?)
                    """,
                    (self.user.id, Topic.ADDITION.value, f"{study_day.isoformat()} 12:00:00"),
                )
            update = self.gamification.award_exercise(
                connection,
                user_id=self.user.id,
                source_key="achievement-check",
                topic=Topic.ADDITION,
                difficulty=1,
                correct=False,
                topic_completed=False,
            )

        unlocked = {achievement.key for achievement in update.achievements}
        self.assertEqual(
            unlocked,
            {
                "first_exercise",
                "first_correct",
                "ten_correct",
                "ten_streak",
                "study_3",
                "seven_day_study",
                "master_arithmetic",
            },
        )
        self.assertEqual(update.xp_awarded, 220)

    def test_ranking_validates_sort_mode_and_level_progress_is_monotonic(self) -> None:
        with self.assertRaises(ValueError):
            self.gamification.get_ranking(self.user.id, "invalid")
        progress = [
            self.gamification.progress_for_xp(xp)
            for xp in (0, 50, 99, 100, 150, 300, 10_000)
        ]
        self.assertEqual([item.level for item in progress], [1, 1, 1, 2, 2, 3, 14])
        self.assertTrue(all(0 <= item.progress < 1 for item in progress))

    def test_achievement_gallery_progress_notifications_and_cosmetics(self) -> None:
        session = self.learning.start_session(
            self.user.id, Topic.ADDITION, difficulty=1, question_count=1
        )
        session.answer(session.current_exercise.answer_text)
        statuses = self.gamification.get_achievements(self.user.id)
        first = next(item for item in statuses if item.key == "first_exercise")
        self.assertEqual((first.category, first.rarity, first.icon), ("Pierwsze kroki", "Zwykłe", "🏅"))
        battle = next(item for item in statuses if item.key == "battle_first_win")
        self.assertFalse(battle.available)
        self.assertEqual(
            {
                item.key
                for item in self.gamification.get_achievements(
                    self.user.id, category="Pierwsze kroki", rarity="Zwykłe"
                )
            },
            {
                "first_exercise", "first_correct", "first_topic",
                "first_exam", "first_flashcard",
            },
        )

        with self.database.transaction() as connection:
            connection.executemany(
                """
                INSERT INTO exercise_history (user_id, topic, correct, difficulty)
                VALUES (?, ?, 1, 1)
                """,
                [(self.user.id, Topic.LIMITS.value)] * 10,
            )
        self.gamification.get_achievements(self.user.id)
        cosmetics = self.gamification.get_cosmetics(self.user.id)
        self.assertIn(("badge", "badge_first_exercise", False), cosmetics)
        self.gamification.equip_cosmetic(self.user.id, "badge", "badge_first_exercise")
        self.gamification.equip_cosmetic(self.user.id, "avatar_frame", "frame_calculus")
        with self.assertRaises(ValueError):
            self.gamification.equip_cosmetic(self.user.id, "avatar_frame", "not-owned")
        equipped = self.gamification.get_cosmetics(self.user.id)
        self.assertIn(("badge", "badge_first_exercise", True), equipped)
        self.assertIn(("avatar_frame", "frame_calculus", True), equipped)

        notices = self.gamification.claim_pending_achievement_notifications(self.user.id)
        self.assertEqual(
            {item.key for item in notices},
            {
                "first_exercise", "first_correct", "first_topic",
                "ten_correct", "ten_streak", "master_calculus",
            },
        )
        self.assertEqual(
            self.gamification.claim_pending_achievement_notifications(self.user.id), ()
        )

    def test_exam_achievement_milestones_use_saved_results(self) -> None:
        for index in range(3):
            self.gamification.record_exam_result(
                user_id=self.user.id,
                exam_name=f"Exam {index}",
                score=95,
                difficulty=3,
                passed=True,
                attempt_key=f"high-score-{index}",
            )
        statuses = {
            item.key: item for item in self.gamification.get_achievements(self.user.id)
        }
        self.assertTrue(statuses["first_exam"].unlocked)
        self.assertTrue(statuses["first_passed_exam"].unlocked)
        self.assertTrue(statuses["three_exams_90"].unlocked)
        self.assertFalse(statuses["difficult_exam"].unlocked)

    def test_quiz_battle_requires_valid_server_signature_and_is_idempotent(self) -> None:
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        service = GamificationService(self.database, public_key)
        payload = {
            "battle_id": "battle-001",
            "player_id": "server-player-1",
            "winner_player_id": "server-player-1",
            "mode": "race",
            "difficulty": "expert",
            "completed_at": "2026-03-01T12:00:00+00:00",
            "duration_seconds": 60,
            "room_code": "",
            "standings": [
                {
                    "player_id": "server-player-1",
                    "display_name": "Player",
                    "points": 120,
                    "correct_answers": 3,
                    "mistakes": 1,
                    "eliminated": False,
                    "place": 1,
                },
                {
                    "player_id": "server-player-2",
                    "display_name": "Rival",
                    "points": 80,
                    "correct_answers": 2,
                    "mistakes": 0,
                    "eliminated": False,
                    "place": 2,
                },
            ],
        }
        signed = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
        signature = private_key.sign(signed)

        unlocked = service.record_verified_battle_result(
            signed,
            signature,
            user_id=self.user.id,
            expected_player_id="server-player-1",
        )

        self.assertEqual(
            {item.key for item in unlocked.achievements},
            {"battle_first_win", "battle_one_mistake", "battle_expert_win"},
        )
        self.assertEqual(
            service.record_verified_battle_result(
                signed, signature, user_id=self.user.id,
                expected_player_id="server-player-1",
            ).duplicate,
            True,
        )
        with self.assertRaises(ValueError):
            service.record_verified_battle_result(
                signed.replace(b'"race"', b'"survival"'),
                signature,
                user_id=self.user.id,
                expected_player_id="server-player-1",
            )
        with self.assertRaises(ValueError):
            self.gamification.record_verified_battle_result(
                signed, signature, user_id=self.user.id,
                expected_player_id="server-player-1",
            )
        statuses = {item.key: item for item in service.get_achievements(self.user.id)}
        self.assertTrue(statuses["battle_expert_win"].unlocked)
        self.assertEqual(service.get_level_progress(self.user.id).xp, 255)


if __name__ == "__main__":
    unittest.main()
