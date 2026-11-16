from __future__ import annotations

import logging
import random
import sqlite3
import time
import uuid
from dataclasses import dataclass
from typing import Callable

from database.database import Database
from database.models import ExamAnswerRecord
from gamification.service import ExamReward, GamificationService
from mathematics.engine import MathEngine
from mathematics.solutions import Exercise
from mathematics.topics import DIFFICULTY_LEVELS, TOPIC_CATEGORIES
from educational_content.service import BankTask, ExamPack

SUBJECTS = ("Matematyka",)


class ExamError(Exception):
    """Expected exam-flow error."""


class ExamStorageError(ExamError):
    """Could not load or store exam results."""


@dataclass(frozen=True, slots=True)
class ExamGradingScale:
    thresholds: tuple[int, int, int, int, int] = (30, 50, 70, 85, 95)

    def __post_init__(self) -> None:
        if (
            len(self.thresholds) != 5
            or any(not 1 <= threshold <= 100 for threshold in self.thresholds)
            or tuple(sorted(set(self.thresholds))) != self.thresholds
        ):
            raise ValueError(
                "Progi ocen 2–6 muszą być pięcioma rosnącymi wartościami od 0 do 100."
            )

    def grade(self, score_percent: float) -> int:
        result = 1
        for grade, threshold in enumerate(self.thresholds, start=2):
            if score_percent >= threshold:
                result = grade
        return result

    def serialize(self) -> str:
        return ",".join(str(value) for value in self.thresholds)


@dataclass(slots=True)
class ExamQuestion:
    exercise: Exercise
    answer: str = ""
    marked_for_review: bool = False


@dataclass(frozen=True, slots=True)
class ExamResult:
    attempt_key: str
    subject: str
    category: str
    difficulty: int
    question_count: int
    correct_count: int
    score_percent: float
    grade: int
    duration_seconds: int
    time_limit_seconds: int
    passed: bool
    grade_scale: str
    answers: tuple[ExamAnswerRecord, ...]


@dataclass(frozen=True, slots=True)
class StoredExamResult:
    exam_name: str
    subject: str
    category: str
    score_percent: float
    difficulty: int
    question_count: int
    correct_count: int
    grade: int
    duration_seconds: int
    time_limit_seconds: int
    passed: bool
    completed_at: str


@dataclass(frozen=True, slots=True)
class ExamCompletion:
    result: ExamResult
    reward: ExamReward
    previous_result: StoredExamResult | None

    @property
    def score_difference(self) -> float | None:
        if self.previous_result is None:
            return None
        return self.result.score_percent - self.previous_result.score_percent


class ExamAttempt:
    def __init__(
        self,
        user_id: int,
        subject: str,
        category: str,
        difficulty: int,
        questions: tuple[Exercise, ...],
        time_limit_seconds: int,
        grading_scale: ExamGradingScale,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.user_id = user_id
        self.subject = subject
        self.category = category
        self.difficulty = difficulty
        self.questions = [ExamQuestion(exercise) for exercise in questions]
        self.time_limit_seconds = time_limit_seconds
        self.grading_scale = grading_scale
        self.attempt_key = str(uuid.uuid4())
        self._clock = clock
        self._started_at = clock()
        self._deadline = self._started_at + time_limit_seconds
        self._result: ExamResult | None = None

    @property
    def question_count(self) -> int:
        return len(self.questions)

    @property
    def finished(self) -> bool:
        return self._result is not None

    @property
    def expired(self) -> bool:
        return not self.finished and self.remaining_seconds <= 0

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self._deadline - self._clock())

    @property
    def result(self) -> ExamResult | None:
        return self._result

    def set_answer(self, question_index: int, answer: str) -> None:
        self._ensure_active()
        if not 0 <= question_index < self.question_count:
            raise IndexError("Numer zadania jest poza zakresem egzaminu.")
        if len(answer) > 500:
            raise ValueError("Odpowiedź może mieć maksymalnie 500 znaków.")
        self.questions[question_index].answer = answer

    def toggle_marked(self, question_index: int) -> bool:
        self._ensure_active()
        if not 0 <= question_index < self.question_count:
            raise IndexError("Numer zadania jest poza zakresem egzaminu.")
        question = self.questions[question_index]
        question.marked_for_review = not question.marked_for_review
        return question.marked_for_review

    def finish(self) -> ExamResult:
        if self._result is not None:
            return self._result
        elapsed = max(0, round(self._clock() - self._started_at))
        duration_seconds = min(self.time_limit_seconds, elapsed)
        details = tuple(
            ExamAnswerRecord(
                question_number=index,
                topic=question.exercise.topic.value,
                question=question.exercise.prompt,
                submitted_answer=question.answer,
                correct_answer=question.exercise.answer_text,
                solution=question.exercise.solution,
                correct=bool(
                    question.answer.strip()
                    and MathEngine.check_answer(question.exercise, question.answer)
                ),
                marked_for_review=question.marked_for_review,
            )
            for index, question in enumerate(self.questions, start=1)
        )
        correct_count = sum(item.correct for item in details)
        score_percent = round(correct_count * 100 / self.question_count, 1)
        grade = self.grading_scale.grade(score_percent)
        self._result = ExamResult(
            attempt_key=self.attempt_key,
            subject=self.subject,
            category=self.category,
            difficulty=self.difficulty,
            question_count=self.question_count,
            correct_count=correct_count,
            score_percent=score_percent,
            grade=grade,
            duration_seconds=duration_seconds,
            time_limit_seconds=self.time_limit_seconds,
            passed=grade >= 2,
            grade_scale=self.grading_scale.serialize(),
            answers=details,
        )
        return self._result

    def _ensure_active(self) -> None:
        if self.finished:
            raise ExamError("Egzamin jest już zakończony.")
        if self.expired:
            raise ExamError("Czas egzaminu upłynął. Egzamin należy zakończyć.")


class ExamService:
    def __init__(
        self,
        database: Database,
        engine: MathEngine | None = None,
        gamification: GamificationService | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.database = database
        self.engine = engine or MathEngine(rng)
        self.gamification = gamification or GamificationService(database)
        self.rng = rng or random.Random()
        self.logger = logging.getLogger(__name__)

    def start_exam(
        self,
        *,
        user_id: int,
        subject: str,
        category: str,
        difficulty: int,
        question_count: int,
        time_limit_seconds: int,
        grading_scale: ExamGradingScale | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> ExamAttempt:
        if subject not in SUBJECTS:
            raise ValueError("Wybrany przedmiot nie jest obsługiwany.")
        if category not in TOPIC_CATEGORIES:
            raise ValueError("Wybierz prawidłową kategorię egzaminu.")
        if difficulty not in DIFFICULTY_LEVELS:
            raise ValueError("Poziom trudności musi być liczbą od 1 do 5.")
        if not 1 <= question_count <= 50:
            raise ValueError("Liczba zadań musi należeć do zakresu 1–50.")
        if not 60 <= time_limit_seconds <= 10_800:
            raise ValueError("Czas egzaminu musi należeć do zakresu 1–180 minut.")
        try:
            with self.database.transaction() as connection:
                user_exists = connection.execute(
                    "SELECT 1 FROM users WHERE id = ?", (user_id,)
                ).fetchone()
            if user_exists is None:
                raise ValueError("Nie znaleziono zalogowanego użytkownika.")
        except sqlite3.Error as error:
            self.logger.exception("Database failure while starting exam")
            raise ExamStorageError("Nie udało się rozpocząć egzaminu.") from error

        topics = TOPIC_CATEGORIES[category]
        generated = tuple(
            self.engine.generate(self.rng.choice(topics), difficulty)
            for _ in range(question_count)
        )
        return ExamAttempt(
            user_id,
            subject,
            category,
            difficulty,
            generated,
            time_limit_seconds,
            grading_scale or ExamGradingScale(),
            clock=clock,
        )

    def start_catalog_exam(
        self,
        user_id: int,
        exam: ExamPack,
        tasks: tuple[BankTask, ...],
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> ExamAttempt:
        if not tasks or len(tasks) != len(exam.task_ids):
            raise ValueError("Zestaw egzaminacyjny zawiera niekompletną listę zadań.")
        if any(task.id not in exam.task_ids for task in tasks):
            raise ValueError("Zadanie nie należy do wybranego egzaminu.")
        if exam.category not in TOPIC_CATEGORIES:
            raise ValueError("Egzamin ma nieobsługiwaną kategorię matematyczną.")
        if not 60 <= exam.time_limit_seconds <= 10_800:
            raise ValueError("Limit czasu egzaminu musi wynosić od 1 do 180 minut.")
        difficulty = max(task.difficulty for task in tasks)
        thresholds = _exam_thresholds(exam.pass_percent)
        try:
            with self.database.transaction() as connection:
                exists = connection.execute(
                    "SELECT 1 FROM users WHERE id = ?", (user_id,)
                ).fetchone()
            if exists is None:
                raise ValueError("Nie znaleziono zalogowanego użytkownika.")
        except sqlite3.Error as error:
            self.logger.exception("Database failure while starting catalog exam")
            raise ExamStorageError("Nie udało się rozpocząć egzaminu z biblioteki.") from error
        return ExamAttempt(
            user_id,
            "Matematyka",
            exam.category,
            difficulty,
            tuple(task.exercise for task in tasks),
            exam.time_limit_seconds,
            ExamGradingScale(thresholds),
            clock=clock,
        )

    def complete_exam(
        self, user_id: int, attempt: ExamAttempt
    ) -> ExamCompletion:
        if attempt.user_id != user_id:
            raise ValueError("Nie można zapisać egzaminu innego użytkownika.")
        result = attempt.finish()
        previous = self.get_previous_result(
            user_id, result.subject, result.category, result.attempt_key
        )
        exam_name = f"{result.subject} — {result.category}"
        try:
            reward = self.gamification.record_exam_result(
                user_id=user_id,
                exam_name=exam_name,
                score=result.score_percent,
                difficulty=result.difficulty,
                passed=result.passed,
                attempt_key=result.attempt_key,
                subject=result.subject,
                category=result.category,
                question_count=result.question_count,
                correct_count=result.correct_count,
                duration_seconds=result.duration_seconds,
                time_limit_seconds=result.time_limit_seconds,
                grade=result.grade,
                grade_scale=result.grade_scale,
                answer_details=result.answers,
            )
        except RuntimeError as error:
            self.logger.exception("Could not persist exam result")
            raise ExamStorageError("Nie udało się zapisać wyniku egzaminu.") from error
        return ExamCompletion(result, reward, previous)

    def get_previous_result(
        self,
        user_id: int,
        subject: str,
        category: str,
        exclude_attempt_key: str = "",
    ) -> StoredExamResult | None:
        try:
            with self.database.transaction() as connection:
                row = connection.execute(
                    """
                    SELECT exam_name, subject, category, score, difficulty,
                           question_count, correct_count, grade, duration_seconds,
                           time_limit_seconds, passed, completed_at
                    FROM exam_results
                    WHERE user_id = ? AND subject = ? AND category = ?
                      AND attempt_key <> ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (user_id, subject, category, exclude_attempt_key),
                ).fetchone()
            return self._stored_result(row) if row is not None else None
        except sqlite3.Error as error:
            self.logger.exception("Database failure while loading previous exam")
            raise ExamStorageError(
                "Nie udało się wczytać poprzedniego wyniku egzaminu."
            ) from error

    def get_recent_results(
        self, user_id: int, limit: int = 10
    ) -> tuple[StoredExamResult, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("Limit historii musi należeć do zakresu 1–100.")
        try:
            with self.database.transaction() as connection:
                rows = connection.execute(
                    """
                    SELECT exam_name, subject, category, score, difficulty,
                           question_count, correct_count, grade, duration_seconds,
                           time_limit_seconds, passed, completed_at
                    FROM exam_results
                    WHERE user_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (user_id, limit),
                ).fetchall()
            return tuple(self._stored_result(row) for row in rows)
        except sqlite3.Error as error:
            self.logger.exception("Database failure while loading exam history")
            raise ExamStorageError("Nie udało się wczytać historii egzaminów.") from error

    @staticmethod
    def _stored_result(row: sqlite3.Row) -> StoredExamResult:
        return StoredExamResult(
            exam_name=str(row["exam_name"]),
            subject=str(row["subject"]),
            category=str(row["category"]),
            score_percent=float(row["score"]),
            difficulty=int(row["difficulty"]),
            question_count=int(row["question_count"]),
            correct_count=int(row["correct_count"]),
            grade=int(row["grade"]),
            duration_seconds=int(row["duration_seconds"]),
            time_limit_seconds=int(row["time_limit_seconds"]),
            passed=bool(row["passed"]),
            completed_at=str(row["completed_at"]),
        )


def _exam_thresholds(pass_percent: int) -> tuple[int, int, int, int, int]:
    if not 1 <= pass_percent <= 80:
        raise ValueError("Progi egzaminu muszą umożliwiać pięć rosnących ocen.")
    return (
        pass_percent,
        pass_percent + 5,
        pass_percent + 10,
        pass_percent + 15,
        pass_percent + 20,
    )
