from __future__ import annotations

import logging
import math
import sqlite3
import base64
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from math import isqrt

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from database.database import Database
from database.models import ExamAnswerRecord
from gamification.catalog import ACHIEVEMENTS, CATEGORY_ACHIEVEMENT_KEYS
from mathematics.topics import TOPIC_CATEGORIES, Topic


class RankingSort(StrEnum):
    XP = "xp"
    LEVEL = "level"
    EXAMS = "exams"


@dataclass(frozen=True, slots=True)
class LevelProgress:
    xp: int
    level: int
    xp_in_level: int
    xp_for_next_level: int
    xp_to_next_level: int
    progress: float


@dataclass(frozen=True, slots=True)
class UnlockedAchievement:
    key: str
    title: str
    description: str
    xp_reward: int
    category: str = ""
    rarity: str = "Zwykłe"
    icon: str = "🏅"


@dataclass(frozen=True, slots=True)
class GamificationUpdate:
    xp_awarded: int
    total_xp: int
    old_level: int
    level: int
    achievements: tuple[UnlockedAchievement, ...]

    @property
    def leveled_up(self) -> bool:
        return self.level > self.old_level


@dataclass(frozen=True, slots=True)
class AchievementStatus:
    key: str
    title: str
    description: str
    xp_reward: int
    unlocked_at: str | None
    category: str = "Pierwsze kroki"
    rarity: str = "Zwykłe"
    icon: str = "🏅"
    progress: float = 0.0
    progress_text: str = ""
    badge_key: str = ""
    avatar_frame_key: str = ""
    available: bool = True

    @property
    def unlocked(self) -> bool:
        return self.unlocked_at is not None


@dataclass(frozen=True, slots=True)
class RankingEntry:
    place: int
    user_id: int
    username: str
    display_name: str
    xp: int
    level: int
    completed_exams: int
    is_current_user: bool


@dataclass(frozen=True, slots=True)
class ExamReward:
    exam_id: int
    duplicate_attempt: bool
    xp_awarded: int
    total_xp: int
    old_level: int
    level: int
    achievements: tuple[UnlockedAchievement, ...]


@dataclass(frozen=True, slots=True)
class BattleStanding:
    player_id: str
    display_name: str
    points: int
    correct_answers: int
    mistakes: int
    eliminated: bool
    place: int


@dataclass(frozen=True, slots=True)
class VerifiedBattleResult:
    battle_id: str
    player_id: str
    outcome: str
    mode: str
    difficulty: str
    room_code: str
    points: int
    correct_answers: int
    mistakes: int
    place: int
    player_count: int
    duration_seconds: int
    xp_awarded: int
    duplicate: bool
    standings: tuple[BattleStanding, ...]
    achievements: tuple[UnlockedAchievement, ...]


class GamificationService:
    _EXERCISE_XP = {1: 5, 2: 5, 3: 10, 4: 20, 5: 20}
    _LEVEL_SORTS = {
        RankingSort.XP: "p.xp DESC, p.level DESC, completed_exams DESC, u.username COLLATE NOCASE",
        RankingSort.LEVEL: "p.level DESC, p.xp DESC, completed_exams DESC, u.username COLLATE NOCASE",
        RankingSort.EXAMS: "completed_exams DESC, p.level DESC, p.xp DESC, u.username COLLATE NOCASE",
    }

    def __init__(
        self, database: Database, quiz_battle_public_key: bytes | str | None = None
    ) -> None:
        self.database = database
        self.logger = logging.getLogger(__name__)
        self.quiz_battle_public_key = self._load_battle_public_key(
            quiz_battle_public_key
        )

    @staticmethod
    def _load_battle_public_key(
        configured: bytes | str | None,
    ) -> Ed25519PublicKey | None:
        configured = configured or os.environ.get("MATHMASTER_QUIZ_BATTLE_PUBLIC_KEY")
        if configured is None:
            return None
        try:
            raw = (
                configured
                if isinstance(configured, bytes)
                else base64.b64decode(configured, validate=True)
            )
            return Ed25519PublicKey.from_public_bytes(raw)
        except (ValueError, TypeError) as error:
            raise ValueError("Nieprawidłowy klucz publiczny Quiz Battle.") from error

    @staticmethod
    def level_for_xp(xp: int) -> int:
        if xp < 0:
            raise ValueError("XP nie może być ujemne.")
        return (1 + isqrt(1 + 2 * xp // 25)) // 2

    @staticmethod
    def xp_threshold(level: int) -> int:
        if level < 1:
            raise ValueError("Poziom musi być dodatni.")
        return 50 * level * (level - 1)

    @classmethod
    def progress_for_xp(cls, xp: int) -> LevelProgress:
        level = cls.level_for_xp(xp)
        current_threshold = cls.xp_threshold(level)
        next_threshold = cls.xp_threshold(level + 1)
        xp_in_level = xp - current_threshold
        xp_for_next_level = next_threshold - current_threshold
        return LevelProgress(
            xp=xp,
            level=level,
            xp_in_level=xp_in_level,
            xp_for_next_level=xp_for_next_level,
            xp_to_next_level=next_threshold - xp,
            progress=xp_in_level / xp_for_next_level,
        )

    def award_exercise(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: int,
        source_key: str,
        topic: Topic,
        difficulty: int,
        correct: bool,
        topic_completed: bool,
    ) -> GamificationUpdate:
        progress = connection.execute(
            "SELECT xp, level FROM user_progress WHERE user_id = ?", (user_id,)
        ).fetchone()
        if progress is None:
            raise ValueError("Nie znaleziono postępów użytkownika.")
        old_level = int(progress["level"])
        xp_before = int(progress["xp"])
        xp_awarded = 0
        unlocked: list[UnlockedAchievement] = []

        if correct:
            xp_awarded += self._award_xp(
                connection,
                user_id,
                source_key=f"exercise:{source_key}",
                amount=self._EXERCISE_XP[difficulty],
                reason="Poprawna odpowiedź",
            )
        if topic_completed:
            completion = connection.execute(
                """
                INSERT OR IGNORE INTO topic_completions (user_id, topic)
                VALUES (?, ?)
                """,
                (user_id, topic.value),
            )
            if completion.rowcount:
                xp_awarded += self._award_xp(
                    connection,
                    user_id,
                    source_key=f"topic:{topic.value}",
                    amount=50,
                    reason="Pierwsze ukończenie tematu",
                )

        unlocked.extend(self._evaluate_exercise_achievements(connection, user_id))
        xp_awarded += sum(item.xp_reward for item in unlocked)

        xp_after = int(
            connection.execute(
                "SELECT xp FROM user_progress WHERE user_id = ?", (user_id,)
            ).fetchone()["xp"]
        )
        level = self.level_for_xp(xp_after)
        connection.execute(
            "UPDATE user_progress SET level = ?, updated_at = datetime('now') "
            "WHERE user_id = ?",
            (level, user_id),
        )
        return GamificationUpdate(
            xp_awarded=xp_after - xp_before,
            total_xp=xp_after,
            old_level=old_level,
            level=level,
            achievements=tuple(unlocked),
        )

    def award_custom_exercise(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: int,
        source_key: str,
        xp_points: int,
    ) -> GamificationUpdate:
        if not source_key.strip():
            raise ValueError("Klucz źródła nagrody nie może być pusty.")
        if isinstance(xp_points, bool) or not 0 <= xp_points <= 1_000:
            raise ValueError("Punkty XP muszą należeć do zakresu 0–1000.")
        progress = connection.execute(
            "SELECT xp, level FROM user_progress WHERE user_id = ?", (user_id,)
        ).fetchone()
        if progress is None:
            raise ValueError("Nie znaleziono postępów użytkownika.")
        old_level = int(progress["level"])
        xp_before = int(progress["xp"])
        self._award_xp(
            connection,
            user_id,
            source_key=f"custom-exercise:{source_key}",
            amount=xp_points,
            reason="Poprawne rozwiązanie własnego zadania",
        )
        unlocked = self._evaluate_exercise_achievements(connection, user_id)
        xp_after = int(
            connection.execute(
                "SELECT xp FROM user_progress WHERE user_id = ?", (user_id,)
            ).fetchone()["xp"]
        )
        level = self.level_for_xp(xp_after)
        connection.execute(
            "UPDATE user_progress SET level = ?, updated_at = datetime('now') "
            "WHERE user_id = ?",
            (level, user_id),
        )
        return GamificationUpdate(
            xp_awarded=xp_after - xp_before,
            total_xp=xp_after,
            old_level=old_level,
            level=level,
            achievements=tuple(unlocked),
        )

    def record_exam_result(
        self,
        *,
        user_id: int,
        exam_name: str,
        score: float,
        difficulty: int,
        passed: bool,
        attempt_key: str,
        subject: str = "Matematyka",
        category: str = "",
        question_count: int = 0,
        correct_count: int = 0,
        duration_seconds: int = 0,
        time_limit_seconds: int = 0,
        grade: int = 1,
        grade_scale: str = "",
        answer_details: tuple[ExamAnswerRecord, ...] = (),
    ) -> ExamReward:
        exam_name = exam_name.strip()
        attempt_key = attempt_key.strip()
        if not exam_name or len(exam_name) > 120:
            raise ValueError("Nazwa egzaminu musi mieć od 1 do 120 znaków.")
        if not math.isfinite(score) or not 0 <= score <= 100:
            raise ValueError("Wynik egzaminu musi należeć do zakresu 0–100.")
        if difficulty not in self._EXERCISE_XP:
            raise ValueError("Poziom egzaminu musi należeć do zakresu 1–5.")
        if not isinstance(passed, bool):
            raise ValueError("Status zdania egzaminu musi być wartością logiczną.")
        if not attempt_key or len(attempt_key) > 120:
            raise ValueError("Wymagany jest unikatowy identyfikator podejścia.")
        subject = subject.strip()
        category = category.strip()
        if not subject or len(subject) > 120 or len(category) > 120:
            raise ValueError("Nieprawidłowy przedmiot lub kategoria egzaminu.")
        if (
            not 0 <= question_count <= 100
            or not 0 <= correct_count <= question_count
            or duration_seconds < 0
            or time_limit_seconds < 0
            or grade not in range(1, 7)
            or len(grade_scale) > 200
        ):
            raise ValueError("Nieprawidłowe szczegóły wyniku egzaminu.")
        if time_limit_seconds and duration_seconds > time_limit_seconds:
            raise ValueError("Czas trwania przekracza limit egzaminu.")
        if question_count and len(answer_details) != question_count:
            raise ValueError("Liczba zapisanych odpowiedzi nie zgadza się z egzaminem.")
        if question_count and score != round(correct_count * 100 / question_count, 1):
            raise ValueError("Procent wyniku nie zgadza się z liczbą punktów.")
        if answer_details and sum(item.correct for item in answer_details) != correct_count:
            raise ValueError("Liczba poprawnych odpowiedzi nie zgadza się z wynikiem.")
        if any(
            detail.question_number != index
            for index, detail in enumerate(answer_details, start=1)
        ):
            raise ValueError("Nieprawidłowa kolejność odpowiedzi egzaminacyjnych.")

        try:
            with self.database.transaction() as connection:
                inserted_attempt = connection.execute(
                    """
                    INSERT OR IGNORE INTO exam_results
                        (user_id, exam_name, score, difficulty, passed, attempt_key,
                         subject, category, question_count, correct_count,
                         duration_seconds, time_limit_seconds, grade, grade_scale)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id, exam_name, score, difficulty, int(passed), attempt_key,
                        subject, category, question_count, correct_count,
                        duration_seconds, time_limit_seconds, grade, grade_scale,
                    ),
                )
                exam = connection.execute(
                    """
                    SELECT id, exam_name, score, difficulty, passed, user_id,
                           subject, category, question_count, correct_count,
                           duration_seconds, time_limit_seconds, grade, grade_scale
                    FROM exam_results WHERE user_id = ? AND attempt_key = ?
                    """,
                    (user_id, attempt_key),
                ).fetchone()
                if exam is None:
                    raise ValueError("Nie udało się zapisać wyniku egzaminu.")
                if (
                    exam["exam_name"] != exam_name
                    or float(exam["score"]) != float(score)
                    or int(exam["difficulty"]) != difficulty
                    or bool(exam["passed"]) != passed
                    or str(exam["subject"]) != subject
                    or str(exam["category"]) != category
                    or int(exam["question_count"]) != question_count
                    or int(exam["correct_count"]) != correct_count
                    or int(exam["duration_seconds"]) != duration_seconds
                    or int(exam["time_limit_seconds"]) != time_limit_seconds
                    or int(exam["grade"]) != grade
                    or str(exam["grade_scale"]) != grade_scale
                ):
                    raise ValueError("Identyfikator podejścia został już użyty.")
                duplicate = not inserted_attempt.rowcount
                if duplicate:
                    stored_details = connection.execute(
                        """
                        SELECT question_number, topic, question, submitted_answer,
                               correct_answer, solution, correct, marked_for_review
                        FROM exam_answer_details
                        WHERE exam_id = ? ORDER BY question_number
                        """,
                        (int(exam["id"]),),
                    ).fetchall()
                    if tuple(
                        (
                            int(row["question_number"]), str(row["topic"]),
                            str(row["question"]), str(row["submitted_answer"]),
                            str(row["correct_answer"]), str(row["solution"]),
                            bool(row["correct"]), bool(row["marked_for_review"]),
                        )
                        for row in stored_details
                    ) != tuple(
                        (
                            item.question_number, item.topic, item.question,
                            item.submitted_answer, item.correct_answer, item.solution,
                            item.correct, item.marked_for_review,
                        )
                        for item in answer_details
                    ):
                        raise ValueError("Zapisane odpowiedzi egzaminu są niezgodne.")
                elif answer_details:
                    connection.executemany(
                        """
                        INSERT INTO exam_answer_details (
                            exam_id, question_number, topic, question,
                            submitted_answer, correct_answer, solution,
                            correct, marked_for_review
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            (
                                int(exam["id"]), item.question_number, item.topic,
                                item.question, item.submitted_answer,
                                item.correct_answer, item.solution, int(item.correct),
                                int(item.marked_for_review),
                            )
                            for item in answer_details
                        ),
                    )
                # The unique key means an already saved attempt is returned unchanged.
                prior = connection.execute(
                    "SELECT xp, level FROM user_progress WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
                if prior is None:
                    raise ValueError("Nie znaleziono postępów użytkownika.")
                old_level = int(prior["level"])
                xp_before = int(prior["xp"])
                unlocked: list[UnlockedAchievement] = []
                if passed:
                    self._award_xp(
                        connection,
                        user_id,
                        source_key=f"exam-pass:{exam_name.casefold()}",
                        amount=100,
                        reason=f"Zdany egzamin: {exam_name}",
                    )
                unlocked.extend(self._evaluate_exam_achievements(connection, user_id))
                achievements = tuple(unlocked)
                xp_after = int(
                    connection.execute(
                        "SELECT xp FROM user_progress WHERE user_id = ?", (user_id,)
                    ).fetchone()["xp"]
                )
                level = self.level_for_xp(xp_after)
                connection.execute(
                    "UPDATE user_progress SET level = ?, updated_at = datetime('now') "
                    "WHERE user_id = ?",
                    (level, user_id),
                )
            return ExamReward(
                exam_id=int(exam["id"]),
                duplicate_attempt=duplicate,
                xp_awarded=xp_after - xp_before,
                total_xp=xp_after,
                old_level=old_level,
                level=level,
                achievements=achievements,
            )
        except sqlite3.Error as error:
            self.logger.exception("Database failure while recording exam result")
            raise RuntimeError("Nie udało się zapisać wyniku egzaminu.") from error

    def get_achievements(
        self,
        user_id: int,
        *,
        category: str | None = None,
        rarity: str | None = None,
    ) -> tuple[AchievementStatus, ...]:
        try:
            with self.database.transaction() as connection:
                self._evaluate_all_achievements(connection, user_id)
                progress = connection.execute(
                    "SELECT xp FROM user_progress WHERE user_id = ?", (user_id,)
                ).fetchone()
                if progress is None:
                    raise ValueError("Nie znaleziono postępów użytkownika.")
                connection.execute(
                    "UPDATE user_progress SET level = ? WHERE user_id = ?",
                    (self.level_for_xp(int(progress["xp"])), user_id),
                )
                rows = connection.execute(
                    """
                    SELECT a.name, a.description, a.reward_xp, a.category, a.rarity,
                           a.icon, a.badge_key, a.avatar_frame_key, ua.unlocked_at,
                           COALESCE(ap.progress_value, 0) AS progress_value,
                           COALESCE(ap.progress_target, 1) AS progress_target,
                           COALESCE(ap.progress_text, '') AS progress_text
                    FROM achievements AS a
                    LEFT JOIN user_achievements AS ua
                        ON ua.achievement_id = a.id AND ua.user_id = ?
                    LEFT JOIN achievement_progress AS ap
                        ON ap.achievement_id = a.id AND ap.user_id = ?
                    ORDER BY a.id
                    """,
                    (user_id, user_id),
                ).fetchall()
            definitions = {item.key: item for item in ACHIEVEMENTS}
            return tuple(
                AchievementStatus(
                    key=str(row["name"]),
                    title=definitions[str(row["name"])].title,
                    description=str(row["description"]),
                    xp_reward=int(row["reward_xp"]),
                    unlocked_at=str(row["unlocked_at"]) if row["unlocked_at"] else None,
                    category=str(row["category"]),
                    rarity=str(row["rarity"]),
                    icon=str(row["icon"]),
                    progress=min(
                        1.0,
                        float(row["progress_value"])
                        / max(1.0, float(row["progress_target"])),
                    ),
                    progress_text=str(row["progress_text"]),
                    badge_key=str(row["badge_key"]),
                    avatar_frame_key=str(row["avatar_frame_key"]),
                    available=not definitions[str(row["name"])].server_only
                    or self.quiz_battle_public_key is not None,
                )
                for row in rows
                if (category is None or str(row["category"]) == category)
                and (rarity is None or str(row["rarity"]) == rarity)
            )
        except sqlite3.Error as error:
            self.logger.exception("Database failure while loading achievements")
            raise RuntimeError("Nie udało się wczytać osiągnięć.") from error

    def claim_pending_achievement_notifications(
        self, user_id: int
    ) -> tuple[UnlockedAchievement, ...]:
        try:
            with self.database.transaction() as connection:
                self._evaluate_all_achievements(connection, user_id)
                rows = connection.execute(
                    """
                    SELECT a.name, a.description, a.reward_xp, a.category, a.rarity, a.icon
                    FROM user_achievements AS ua
                    JOIN achievements AS a ON a.id = ua.achievement_id
                    WHERE ua.user_id = ? AND ua.notified_at IS NULL
                    ORDER BY ua.unlocked_at, a.id
                    """,
                    (user_id,),
                ).fetchall()
                connection.execute(
                    """
                    UPDATE user_achievements SET notified_at = datetime('now')
                    WHERE user_id = ? AND notified_at IS NULL
                    """,
                    (user_id,),
                )
                progress = connection.execute(
                    "SELECT xp FROM user_progress WHERE user_id = ?", (user_id,)
                ).fetchone()
                if progress is not None:
                    connection.execute(
                        "UPDATE user_progress SET level = ? WHERE user_id = ?",
                        (self.level_for_xp(int(progress["xp"])), user_id),
                    )
            return tuple(
                UnlockedAchievement(
                    key=str(row["name"]),
                    title=self._achievement_title(str(row["name"])),
                    description=str(row["description"]),
                    xp_reward=int(row["reward_xp"]),
                    category=str(row["category"]),
                    rarity=str(row["rarity"]),
                    icon=str(row["icon"]),
                )
                for row in rows
            )
        except sqlite3.Error as error:
            self.logger.exception("Database failure while claiming achievement notifications")
            raise RuntimeError("Nie udało się odczytać powiadomień o osiągnięciach.") from error

    def get_cosmetics(self, user_id: int) -> tuple[tuple[str, str, bool], ...]:
        try:
            with self.database.transaction() as connection:
                rows = connection.execute(
                    """
                    SELECT c.cosmetic_type, c.cosmetic_key,
                           (e.cosmetic_key IS NOT NULL) AS equipped
                    FROM user_cosmetics AS c
                    LEFT JOIN user_equipped_cosmetics AS e
                        ON e.user_id = c.user_id AND e.cosmetic_type = c.cosmetic_type
                        AND e.cosmetic_key = c.cosmetic_key
                    WHERE c.user_id = ?
                    ORDER BY c.cosmetic_type, c.unlocked_at, c.cosmetic_key
                    """,
                    (user_id,),
                ).fetchall()
            return tuple(
                (str(row["cosmetic_type"]), str(row["cosmetic_key"]), bool(row["equipped"]))
                for row in rows
            )
        except sqlite3.Error as error:
            self.logger.exception("Database failure while loading user cosmetics")
            raise RuntimeError("Nie udało się wczytać kosmetyków profilu.") from error

    def equip_cosmetic(
        self, user_id: int, cosmetic_type: str, cosmetic_key: str | None
    ) -> None:
        if cosmetic_type not in {"badge", "avatar_frame"}:
            raise ValueError("Nieznany rodzaj elementu profilu.")
        if cosmetic_key is not None and (
            not cosmetic_key.strip() or len(cosmetic_key) > 100
        ):
            raise ValueError("Nieprawidłowy identyfikator kosmetyczny.")
        try:
            with self.database.transaction() as connection:
                if cosmetic_key is None:
                    connection.execute(
                        """
                        DELETE FROM user_equipped_cosmetics
                        WHERE user_id = ? AND cosmetic_type = ?
                        """,
                        (user_id, cosmetic_type),
                    )
                    return
                owned = connection.execute(
                    """
                    SELECT 1 FROM user_cosmetics
                    WHERE user_id = ? AND cosmetic_type = ? AND cosmetic_key = ?
                    """,
                    (user_id, cosmetic_type, cosmetic_key),
                ).fetchone()
                if owned is None:
                    raise ValueError("Ten element nie został odblokowany przez konto.")
                connection.execute(
                    """
                    INSERT INTO user_equipped_cosmetics (user_id, cosmetic_type, cosmetic_key)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id, cosmetic_type) DO UPDATE SET
                        cosmetic_key = excluded.cosmetic_key,
                        equipped_at = datetime('now')
                    """,
                    (user_id, cosmetic_type, cosmetic_key),
                )
        except sqlite3.Error as error:
            self.logger.exception("Database failure while equipping user cosmetic")
            raise RuntimeError("Nie udało się zmienić elementu profilu.") from error

    def record_verified_battle_result(
        self,
        signed_payload: bytes,
        signature: bytes | str,
        *,
        user_id: int,
        expected_player_id: str,
    ) -> VerifiedBattleResult:
        if self.quiz_battle_public_key is None:
            raise ValueError("Osiągnięcia Quiz Battle wymagają zaufanego klucza serwera.")
        if not isinstance(signed_payload, bytes) or len(signed_payload) > 8_192:
            raise ValueError("Nieprawidłowy lub zbyt duży wynik Quiz Battle.")
        try:
            payload = json.loads(signed_payload)
            if not isinstance(payload, dict) or set(payload) != {
                "battle_id", "player_id", "winner_player_id", "mode", "difficulty",
                "completed_at", "duration_seconds", "room_code", "standings",
            }:
                raise ValueError("Nieprawidłowe pola wyniku Quiz Battle.")
            if (
                not isinstance(payload["battle_id"], str)
                or not payload["battle_id"].strip()
                or len(payload["battle_id"]) > 120
                or not isinstance(payload["player_id"], str)
                or payload["player_id"] != expected_player_id
                or not isinstance(payload["winner_player_id"], str)
                or payload["mode"] not in {"race", "survival"}
                or payload["difficulty"] not in {"easy", "medium", "hard", "expert"}
                or not isinstance(payload["completed_at"], str)
                or isinstance(payload["duration_seconds"], bool)
                or not isinstance(payload["duration_seconds"], int)
                or not 0 <= payload["duration_seconds"] <= 3_600
                or not isinstance(payload["room_code"], str)
                or len(payload["room_code"]) > 24
                or not isinstance(payload["standings"], list)
                or not 2 <= len(payload["standings"]) <= 8
            ):
                raise ValueError("Nieprawidłowe dane wyniku Quiz Battle.")
            if not isinstance(expected_player_id, str) or not expected_player_id.strip():
                raise ValueError("Brak uwierzytelnionej tożsamości gracza.")
            standings: list[BattleStanding] = []
            player_ids: set[str] = set()
            places: set[int] = set()
            for entry in payload["standings"]:
                if not isinstance(entry, dict) or set(entry) != {
                    "player_id", "display_name", "points", "correct_answers",
                    "mistakes", "eliminated", "place",
                }:
                    raise ValueError("Nieprawidłowy wynik uczestnika pojedynku.")
                player_id = entry["player_id"]
                display_name = entry["display_name"]
                points = entry["points"]
                correct_answers = entry["correct_answers"]
                mistakes = entry["mistakes"]
                place = entry["place"]
                if (
                    not isinstance(player_id, str)
                    or not player_id.strip()
                    or len(player_id) > 120
                    or not isinstance(display_name, str)
                    or not display_name.strip()
                    or len(display_name) > 80
                    or any(isinstance(value, bool) or not isinstance(value, int)
                           for value in (points, correct_answers, mistakes, place))
                    or points < 0
                    or correct_answers < 0
                    or not 0 <= mistakes <= 100
                    or not 1 <= place <= len(payload["standings"])
                    or not isinstance(entry["eliminated"], bool)
                    or player_id in player_ids
                    or place in places
                ):
                    raise ValueError("Nieprawidłowe dane uczestnika pojedynku.")
                player_ids.add(player_id)
                places.add(place)
                standings.append(
                    BattleStanding(
                        player_id, display_name.strip(), points,
                        correct_answers, mistakes, entry["eliminated"], place,
                    )
                )
            if places != set(range(1, len(standings) + 1)):
                raise ValueError("Miejsca w wynikach pojedynku są niekompletne.")
            standings.sort(key=lambda item: item.place)
            winner = next(
                (item for item in standings if item.player_id == payload["winner_player_id"]),
                None,
            )
            current = next(
                (item for item in standings if item.player_id == expected_player_id),
                None,
            )
            if winner is None or winner.place != 1 or current is None:
                raise ValueError("Wynik nie zawiera zwycięzcy lub bieżącego gracza.")
            completed = datetime.fromisoformat(payload["completed_at"].replace("Z", "+00:00"))
            if completed.tzinfo is None:
                raise ValueError("Wynik Quiz Battle nie zawiera strefy czasowej.")
            canonical = json.dumps(
                payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            raw_signature = (
                base64.b64decode(signature, validate=True)
                if isinstance(signature, str)
                else signature
            )
            self.quiz_battle_public_key.verify(raw_signature, canonical)
        except InvalidSignature as error:
            raise ValueError("Podpis wyniku Quiz Battle jest nieprawidłowy.") from error
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError, KeyError) as error:
            raise ValueError("Nie udało się odczytać wyniku Quiz Battle.") from error
        digest = hashlib.sha256(canonical).hexdigest()
        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("Nieprawidłowe lokalne konto użytkownika.")
        outcome = "win" if current.player_id == winner.player_id else "loss"
        xp_awarded = min(
            300, 10 + min(current.correct_answers, 48) * 5 + (50 if outcome == "win" else 0)
        )
        try:
            with self.database.transaction() as connection:
                inserted = connection.execute(
                    """
                    INSERT OR IGNORE INTO quiz_battle_results (
                        battle_id, user_id, outcome, mistakes, difficulty, completed_at,
                        payload_hash, player_id, mode, room_code, points, correct_answers,
                        place, player_count, duration_seconds, standings_json, xp_awarded
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["battle_id"], user_id, outcome, current.mistakes,
                        payload["difficulty"], completed.isoformat(), digest,
                        expected_player_id, payload["mode"], payload["room_code"],
                        current.points, current.correct_answers, current.place,
                        len(standings), payload["duration_seconds"],
                        json.dumps(
                            [
                                {
                                    "player_id": item.player_id,
                                    "display_name": item.display_name,
                                    "points": item.points,
                                    "correct_answers": item.correct_answers,
                                    "mistakes": item.mistakes,
                                    "eliminated": item.eliminated,
                                    "place": item.place,
                                }
                                for item in standings
                            ],
                            ensure_ascii=False,
                        ),
                        xp_awarded,
                    ),
                )
                stored = connection.execute(
                    "SELECT user_id, payload_hash, xp_awarded FROM quiz_battle_results "
                    "WHERE battle_id = ?",
                    (payload["battle_id"],),
                ).fetchone()
                if (
                    stored is None
                    or int(stored["user_id"]) != user_id
                    or stored["payload_hash"] != digest
                ):
                    raise ValueError("Identyfikator pojedynku został użyty dla innego wyniku.")
                if inserted.rowcount:
                    self._award_xp(
                        connection,
                        user_id,
                        source_key=f"quiz-battle:{payload['battle_id']}",
                        amount=xp_awarded,
                        reason="Ukończony pojedynek Quiz Battle",
                    )
                    unlocked = self._evaluate_battle_achievements(connection, user_id)
                else:
                    unlocked = []
                progress = connection.execute(
                    "SELECT xp FROM user_progress WHERE user_id = ?", (user_id,)
                ).fetchone()
                if progress is None:
                    raise ValueError("Nie znaleziono postępów użytkownika.")
                connection.execute(
                    "UPDATE user_progress SET level = ? WHERE user_id = ?",
                    (self.level_for_xp(int(progress["xp"])), user_id),
                )
            return VerifiedBattleResult(
                battle_id=str(payload["battle_id"]),
                player_id=expected_player_id,
                outcome=outcome,
                mode=str(payload["mode"]),
                difficulty=str(payload["difficulty"]),
                room_code=str(payload["room_code"]),
                points=current.points,
                correct_answers=current.correct_answers,
                mistakes=current.mistakes,
                place=current.place,
                player_count=len(standings),
                duration_seconds=int(payload["duration_seconds"]),
                xp_awarded=int(stored["xp_awarded"]) if inserted.rowcount else 0,
                duplicate=not bool(inserted.rowcount),
                standings=tuple(standings),
                achievements=tuple(unlocked),
            )
        except sqlite3.Error as error:
            self.logger.exception("Database failure while saving verified battle result")
            raise RuntimeError("Nie udało się zapisać zweryfikowanego wyniku pojedynku.") from error

    def get_level_progress(self, user_id: int) -> LevelProgress:
        try:
            with self.database.transaction() as connection:
                row = connection.execute(
                    "SELECT xp FROM user_progress WHERE user_id = ?", (user_id,)
                ).fetchone()
            if row is None:
                raise ValueError("Nie znaleziono postępów użytkownika.")
            return self.progress_for_xp(int(row["xp"]))
        except sqlite3.Error as error:
            self.logger.exception("Database failure while loading XP progress")
            raise RuntimeError("Nie udało się wczytać postępu XP.") from error

    def get_ranking(
        self,
        current_user_id: int,
        sort_by: RankingSort | str = RankingSort.XP,
        limit: int = 100,
    ) -> tuple[RankingEntry, ...]:
        try:
            selected_sort = RankingSort(sort_by)
        except ValueError as error:
            raise ValueError("Nieznany sposób sortowania rankingu.") from error
        if not 1 <= limit <= 500:
            raise ValueError("Limit rankingu musi należeć do zakresu 1–500.")
        order_clause = self._LEVEL_SORTS[selected_sort]
        try:
            with self.database.transaction() as connection:
                rows = connection.execute(
                    f"""
                    SELECT u.id, u.username, u.display_name, p.xp, p.level,
                           COALESCE(exams.completed_exams, 0) AS completed_exams
                    FROM users AS u
                    JOIN user_progress AS p ON p.user_id = u.id
                    LEFT JOIN (
                        SELECT user_id, COUNT(*) AS completed_exams
                        FROM exam_results WHERE passed = 1 GROUP BY user_id
                    ) AS exams ON exams.user_id = u.id
                    ORDER BY {order_clause}
                    """
                ).fetchall()
            entries = tuple(
                RankingEntry(
                    place=index,
                    user_id=int(row["id"]),
                    username=str(row["username"]),
                    display_name=str(row["display_name"]),
                    xp=int(row["xp"]),
                    level=int(row["level"]),
                    completed_exams=int(row["completed_exams"]),
                    is_current_user=int(row["id"]) == current_user_id,
                )
                for index, row in enumerate(rows, start=1)
            )
            visible = list(entries[:limit])
            if not any(row.is_current_user for row in visible):
                current = next(
                    (row for row in entries if row.is_current_user), None
                )
                if current is not None:
                    visible.append(current)
            return tuple(visible)
        except sqlite3.Error as error:
            self.logger.exception("Database failure while loading local ranking")
            raise RuntimeError("Nie udało się wczytać lokalnego rankingu.") from error

    def _evaluate_exercise_achievements(
        self, connection: sqlite3.Connection, user_id: int
    ) -> list[UnlockedAchievement]:
        unlocked: list[UnlockedAchievement] = []
        history = connection.execute(
            """
            SELECT correct, completed_at, source, id FROM (
                SELECT correct, completed_at, 0 AS source, id
                FROM exercise_history WHERE user_id = ?
                UNION ALL
                SELECT correct, completed_at, 1 AS source, id
                FROM custom_task_attempts WHERE user_id = ?
            )
            ORDER BY completed_at, source, id
            """,
            (user_id, user_id),
        ).fetchall()
        total = len(history)
        correct_total = sum(bool(row["correct"]) for row in history)
        self._track(
            connection, user_id, "first_exercise", total, 1, f"{min(total, 1)}/1",
            total > 0, unlocked,
        )
        self._track(
            connection, user_id, "first_correct", correct_total, 1,
            f"{min(correct_total, 1)}/1", correct_total > 0, unlocked,
        )
        topic_count = int(connection.execute(
            "SELECT COUNT(*) FROM topic_completions WHERE user_id = ?", (user_id,)
        ).fetchone()[0])
        self._track(
            connection, user_id, "first_topic", topic_count, 1,
            f"{min(topic_count, 1)}/1", topic_count > 0, unlocked,
        )
        self._track(connection, user_id, "ten_correct", correct_total, 10,
                    f"{min(correct_total, 10)}/10", correct_total >= 10, unlocked)
        self._track(connection, user_id, "hundred_correct", correct_total, 100,
                    f"{min(correct_total, 100)}/100", correct_total >= 100, unlocked)

        longest_streak = current_streak = 0
        for row in history:
            current_streak = current_streak + 1 if bool(row["correct"]) else 0
            longest_streak = max(longest_streak, current_streak)
        for key, target in (("ten_streak", 10), ("streak_25", 25), ("hundred_streak", 100)):
            self._track(
                connection, user_id, key, longest_streak, target,
                f"{min(longest_streak, target)}/{target}",
                longest_streak >= target, unlocked,
            )

        dates = connection.execute(
            """
            SELECT DISTINCT date(study_date) AS study_day
            FROM (
                SELECT completed_at AS study_date FROM exercise_history WHERE user_id = ?
                UNION ALL
                SELECT completed_at FROM custom_task_attempts WHERE user_id = ?
                UNION ALL
                SELECT reviewed_at FROM flashcard_reviews WHERE user_id = ?
            )
            ORDER BY study_day DESC LIMIT 365
            """,
            (user_id, user_id, user_id),
        ).fetchall()
        study_days = tuple(str(row["study_day"]) for row in dates)
        day_streak = self._consecutive_day_count(study_days)
        for key, target in (
            ("study_3", 3), ("seven_day_study", 7), ("study_30", 30),
            ("study_100", 100), ("study_365", 365),
        ):
            self._track(
                connection, user_id, key, day_streak, target,
                f"{min(day_streak, target)}/{target} dni z rzędu",
                day_streak >= target, unlocked,
            )

        for category, topics in TOPIC_CATEGORIES.items():
            placeholders = ",".join("?" for _ in topics)
            row = connection.execute(
                f"""
                SELECT COUNT(*) AS attempts, COALESCE(SUM(correct), 0) AS correct
                FROM exercise_history
                WHERE user_id = ? AND topic IN ({placeholders})
                """,
                (user_id, *(topic.value for topic in topics)),
            ).fetchone()
            attempts, successes = int(row["attempts"]), int(row["correct"])
            category_aliases = tuple(
                name for name, key in CATEGORY_ACHIEVEMENT_KEYS.items()
                if key == CATEGORY_ACHIEVEMENT_KEYS.get(category)
            )
            if category_aliases:
                placeholders_category = ",".join("?" for _ in category_aliases)
                custom = connection.execute(
                    f"""
                    SELECT COUNT(*) AS attempts, COALESCE(SUM(correct), 0) AS correct
                    FROM custom_task_attempts
                    WHERE user_id = ? AND category IN ({placeholders_category})
                    """,
                    (user_id, *category_aliases),
                ).fetchone()
                attempts += int(custom["attempts"])
                successes += int(custom["correct"])
            key = CATEGORY_ACHIEVEMENT_KEYS.get(category)
            if key is not None:
                accuracy = successes / attempts if attempts else 0.0
                progress = min(1.0, attempts / 10) * min(
                    1.0, accuracy / 0.8 if accuracy else 0.0
                )
                self._save_progress(
                    connection, user_id, key, progress, 1,
                    f"{attempts}/10 zadań · {accuracy:.0%} skuteczności (cel 80%)",
                )
                if attempts >= 10 and successes * 100 >= attempts * 80:
                    self._collect(connection, user_id, key, unlocked)
        return unlocked

    @staticmethod
    def _consecutive_day_count(days: tuple[str, ...]) -> int:
        if not days:
            return 0
        parsed = tuple(date.fromisoformat(day) for day in days)
        count = 1
        for index in range(1, len(parsed)):
            difference = (parsed[index - 1] - parsed[index]).days
            if difference != 1:
                break
            count += 1
        return count

    def _track(
        self,
        connection: sqlite3.Connection,
        user_id: int,
        key: str,
        value: int,
        target: int,
        text: str,
        achieved: bool,
        unlocked: list[UnlockedAchievement],
    ) -> None:
        self._save_progress(connection, user_id, key, value, target, text)
        if achieved:
            self._collect(connection, user_id, key, unlocked)

    @staticmethod
    def _save_progress(
        connection: sqlite3.Connection,
        user_id: int,
        key: str,
        value: int | float,
        target: int | float,
        text: str,
    ) -> None:
        row = connection.execute(
            "SELECT id FROM achievements WHERE name = ?", (key,)
        ).fetchone()
        if row is None:
            return
        connection.execute(
            """
            INSERT INTO achievement_progress (
                user_id, achievement_id, progress_value, progress_target, progress_text
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, achievement_id) DO UPDATE SET
                progress_value = excluded.progress_value,
                progress_target = excluded.progress_target,
                progress_text = excluded.progress_text,
                updated_at = datetime('now')
            """,
            (user_id, int(row["id"]), max(0, value), max(1, target), text),
        )

    def _evaluate_all_achievements(
        self, connection: sqlite3.Connection, user_id: int
    ) -> list[UnlockedAchievement]:
        unlocked = self._evaluate_exercise_achievements(connection, user_id)
        unlocked.extend(self._evaluate_exam_achievements(connection, user_id))
        unlocked.extend(self._evaluate_flashcard_achievements(connection, user_id))
        if self.quiz_battle_public_key is not None:
            unlocked.extend(self._evaluate_battle_achievements(connection, user_id))
        return unlocked

    def _evaluate_exam_achievements(
        self, connection: sqlite3.Connection, user_id: int
    ) -> list[UnlockedAchievement]:
        rows = connection.execute(
            """
            SELECT score, difficulty, passed FROM exam_results WHERE user_id = ?
            ORDER BY id
            """,
            (user_id,),
        ).fetchall()
        unlocked: list[UnlockedAchievement] = []
        total = len(rows)
        passed = sum(bool(row["passed"]) for row in rows)
        advanced = sum(bool(row["passed"]) and int(row["difficulty"]) == 5 for row in rows)
        high_scores = sum(bool(row["passed"]) and float(row["score"]) > 90 for row in rows)
        perfect = any(bool(row["passed"]) and float(row["score"]) == 100 for row in rows)
        metrics = (
            ("first_exam", total, 1, "ukończonych egzaminów"),
            ("first_passed_exam", passed, 1, "zdanych egzaminów"),
            ("five_passed_exams", passed, 5, "zdanych egzaminów"),
            ("ten_passed_exams", passed, 10, "zdanych egzaminów"),
            ("three_exams_90", high_scores, 3, "egzaminów powyżej 90%"),
            ("difficult_exam", advanced, 1, "zdanych egzaminów eksperckich"),
            ("perfect_exam", int(perfect), 1, "egzaminów z wynikiem 100%"),
        )
        for key, value, target, unit in metrics:
            self._track(
                connection, user_id, key, value, target,
                f"{min(value, target)}/{target} {unit}",
                value >= target, unlocked,
            )
        return unlocked

    def _evaluate_flashcard_achievements(
        self, connection: sqlite3.Connection, user_id: int
    ) -> list[UnlockedAchievement]:
        unlocked: list[UnlockedAchievement] = []
        total = int(connection.execute(
            "SELECT COUNT(*) FROM flashcards WHERE user_id = ?", (user_id,)
        ).fetchone()[0])
        mastered = int(connection.execute(
            "SELECT COUNT(*) FROM flashcards WHERE user_id = ? AND mastery >= 4",
            (user_id,),
        ).fetchone()[0])
        reviews = int(connection.execute(
            "SELECT COUNT(*) FROM flashcard_reviews WHERE user_id = ?", (user_id,)
        ).fetchone()[0])
        self._track(connection, user_id, "first_flashcard", total, 1,
                    f"{min(total, 1)}/1 fiszek", total > 0, unlocked)
        for key, target in (("flashcards_10", 10), ("flashcards_100", 100), ("flashcards_500", 500)):
            self._track(
                connection, user_id, key, mastered, target,
                f"{min(mastered, target)}/{target} opanowanych fiszek",
                mastered >= target, unlocked,
            )
        review_days = connection.execute(
            """
            SELECT DISTINCT date(reviewed_at) AS study_day FROM flashcard_reviews
            WHERE user_id = ? ORDER BY study_day DESC LIMIT 30
            """,
            (user_id,),
        ).fetchall()
        review_streak = self._consecutive_day_count(
            tuple(str(row["study_day"]) for row in review_days)
        )
        self._track(
            connection, user_id, "review_streak_30", review_streak, 30,
            f"{min(review_streak, 30)}/30 dni z rzędu",
            review_streak >= 30, unlocked,
        )

        decks = connection.execute(
            """
            SELECT d.id, d.name, COUNT(f.id) AS card_count
            FROM flashcard_decks AS d
            JOIN flashcards AS f ON f.deck_id = d.id AND f.user_id = d.user_id
            WHERE d.user_id = ?
            GROUP BY d.id, d.name
            """,
            (user_id,),
        ).fetchall()
        best_coverage = 0.0
        perfect = False
        best_label = "Brak kompletnego testu zestawu"
        for deck in decks:
            sessions = connection.execute(
                """
                SELECT test_session_id,
                       COUNT(DISTINCT CASE WHEN correct = 1 THEN flashcard_id END) AS seen,
                       SUM(CASE WHEN correct = 0 THEN 1 ELSE 0 END) AS errors
                FROM flashcard_reviews
                WHERE user_id = ? AND deck_id = ? AND deck_name = ?
                    AND tested = 1 AND test_session_id <> ''
                GROUP BY test_session_id
                """,
                (user_id, int(deck["id"]), str(deck["name"])),
            ).fetchall()
            card_count = int(deck["card_count"])
            for session in sessions:
                seen = int(session["seen"])
                coverage = seen / card_count if card_count else 0.0
                if coverage > best_coverage:
                    best_coverage = coverage
                    best_label = f"{seen}/{card_count} fiszek w teście zestawu"
                if seen == card_count and int(session["errors"] or 0) == 0:
                    perfect = True
        self._track(
            connection, user_id, "deck_perfect", int(perfect), 1,
            "Wszystkie fiszki poprawne" if perfect else best_label,
            perfect, unlocked,
        )
        return unlocked

    def _evaluate_battle_achievements(
        self, connection: sqlite3.Connection, user_id: int
    ) -> list[UnlockedAchievement]:
        results = connection.execute(
            """
            SELECT outcome, mistakes, difficulty FROM quiz_battle_results
            WHERE user_id = ? ORDER BY completed_at, battle_id
            """,
            (user_id,),
        ).fetchall()
        wins = sum(row["outcome"] == "win" for row in results)
        win_streak = best_streak = 0
        for row in results:
            win_streak = win_streak + 1 if row["outcome"] == "win" else 0
            best_streak = max(best_streak, win_streak)
        one_mistake = any(
            row["outcome"] == "win" and int(row["mistakes"]) <= 1 for row in results
        )
        expert_win = any(
            row["outcome"] == "win" and row["difficulty"] == "expert"
            for row in results
        )
        unlocked: list[UnlockedAchievement] = []
        for key, value, target, label, achieved in (
            ("battle_first_win", wins, 1, "zwycięstw", wins >= 1),
            ("battle_5_wins", wins, 5, "zwycięstw", wins >= 5),
            ("battle_25_wins", wins, 25, "zwycięstw", wins >= 25),
            ("battle_10_streak", best_streak, 10, "zwycięstw z rzędu", best_streak >= 10),
            ("battle_one_mistake", int(one_mistake), 1, "wygranych z maks. 1 pomyłką", one_mistake),
            ("battle_expert_win", int(expert_win), 1, "wygranych eksperckich", expert_win),
        ):
            self._track(
                connection, user_id, key, value, target,
                f"{min(value, target)}/{target} {label}", achieved, unlocked,
            )
        return unlocked

    def _collect(
        self,
        connection: sqlite3.Connection,
        user_id: int,
        key: str,
        unlocked: list[UnlockedAchievement],
    ) -> None:
        achievement = self._unlock_achievement(connection, user_id, key)
        if achievement is not None:
            unlocked.append(achievement)

    def _unlock_achievement(
        self, connection: sqlite3.Connection, user_id: int, key: str
    ) -> UnlockedAchievement | None:
        row = connection.execute(
            """
            SELECT id, name, description, reward_xp, category, rarity, icon,
                   badge_key, avatar_frame_key
            FROM achievements WHERE name = ?
            """,
            (key,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Nieznane osiągnięcie: {key}.")
        inserted = connection.execute(
            """
            INSERT OR IGNORE INTO user_achievements (user_id, achievement_id)
            VALUES (?, ?)
            """,
            (user_id, row["id"]),
        )
        if not inserted.rowcount:
            return None
        if row["badge_key"]:
            connection.execute(
                """
                INSERT OR IGNORE INTO user_cosmetics (user_id, cosmetic_type, cosmetic_key)
                VALUES (?, 'badge', ?)
                """,
                (user_id, str(row["badge_key"])),
            )
        if row["avatar_frame_key"]:
            connection.execute(
                """
                INSERT OR IGNORE INTO user_cosmetics (user_id, cosmetic_type, cosmetic_key)
                VALUES (?, 'avatar_frame', ?)
                """,
                (user_id, str(row["avatar_frame_key"])),
            )
        reward = int(row["reward_xp"])
        if reward:
            self._award_xp(
                connection,
                user_id,
                source_key=f"achievement:{key}",
                amount=reward,
                reason=f"Osiągnięcie: {row['name']}",
            )
        return UnlockedAchievement(
            key=str(row["name"]),
            title=self._achievement_title(str(row["name"])),
            description=str(row["description"]),
            xp_reward=reward,
            category=str(row["category"]),
            rarity=str(row["rarity"]),
            icon=str(row["icon"]),
        )

    def _award_xp(
        self,
        connection: sqlite3.Connection,
        user_id: int,
        *,
        source_key: str,
        amount: int,
        reason: str,
    ) -> int:
        if amount <= 0:
            return 0
        inserted = connection.execute(
            """
            INSERT OR IGNORE INTO xp_transactions (user_id, source_key, amount, reason)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, source_key, amount, reason),
        )
        if not inserted.rowcount:
            return 0
        connection.execute(
            "UPDATE user_progress SET xp = xp + ? WHERE user_id = ?",
            (amount, user_id),
        )
        return amount

    @staticmethod
    def _achievement_title(key: str) -> str:
        return next(
            (achievement.title for achievement in ACHIEVEMENTS if achievement.key == key),
            key,
        )
