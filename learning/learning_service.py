from __future__ import annotations

import logging
import sqlite3
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from collections.abc import Callable

from database.database import Database
from gamification.service import GamificationService, UnlockedAchievement
from mathematics.engine import MathEngine
from mathematics.solutions import Exercise
from mathematics.topics import DIFFICULTY_LEVELS, Topic


class LearningError(Exception):
    """Expected learning-flow error."""


class LearningStorageError(LearningError):
    """Could not store or load learning progress."""


@dataclass(frozen=True, slots=True)
class AnswerResult:
    correct: bool
    correct_answer: str
    solution: str
    correct_count: int
    incorrect_count: int
    answered_count: int
    total_questions: int
    suggested_difficulty: int | None
    session_finished: bool
    xp_awarded: int
    total_xp: int
    old_level: int
    level: int
    achievements: tuple[UnlockedAchievement, ...]

    @property
    def leveled_up(self) -> bool:
        return self.level > self.old_level

    @property
    def progress(self) -> float:
        return self.answered_count / self.total_questions


@dataclass(frozen=True, slots=True)
class SessionSummary:
    session_id: str
    topic: Topic
    initial_difficulty: int
    final_difficulty: int
    total_questions: int
    answered_count: int
    correct_count: int
    incorrect_count: int
    elapsed_seconds: int
    aborted: bool

    @property
    def accuracy_percent(self) -> int:
        if self.answered_count == 0:
            return 0
        return round(self.correct_count * 100 / self.answered_count)


@dataclass(frozen=True, slots=True)
class ExerciseHistoryEntry:
    topic: str
    difficulty: int
    question: str
    submitted_answer: str
    correct_answer: str
    correct: bool
    solution: str
    completed_at: str


class LearningService:
    def __init__(
        self,
        database: Database,
        engine: MathEngine | None = None,
        exercise_provider: Callable[[Topic, int], Exercise] | None = None,
    ) -> None:
        self.database = database
        self.engine = engine or MathEngine()
        self.exercise_provider = exercise_provider
        self.gamification = GamificationService(database)
        self.logger = logging.getLogger(__name__)

    def start_session(
        self,
        user_id: int,
        topic: Topic | str,
        difficulty: int,
        question_count: int = 10,
        catalog_topic_id: str | None = None,
    ) -> LearningSession:
        try:
            selected_topic = Topic(topic)
        except ValueError as error:
            raise ValueError(f"Nieznany temat: {topic!r}.") from error
        if difficulty not in DIFFICULTY_LEVELS:
            raise ValueError("Poziom trudności musi być liczbą od 1 do 5.")
        if not 1 <= question_count <= 100:
            raise ValueError("Liczba zadań musi należeć do zakresu 1–100.")
        try:
            with self.database.transaction() as connection:
                user = connection.execute(
                    "SELECT 1 FROM users WHERE id = ?", (user_id,)
                ).fetchone()
            if user is None:
                raise ValueError("Nie znaleziono zalogowanego użytkownika.")
        except sqlite3.Error as error:
            self.logger.exception("Database failure while starting learning session")
            raise LearningStorageError("Nie udało się rozpocząć sesji nauki.") from error
        return LearningSession(
            user_id, selected_topic, difficulty, question_count,
            self.database, self.engine,
            self.gamification,
            catalog_topic_id,
            self.exercise_provider,
        )

    def get_recent_history(
        self, user_id: int, limit: int = 20
    ) -> tuple[ExerciseHistoryEntry, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("Limit historii musi należeć do zakresu 1–100.")
        try:
            with self.database.transaction() as connection:
                rows = connection.execute(
                    """
                    SELECT topic, difficulty, question, submitted_answer,
                           correct_answer, correct, solution, completed_at
                    FROM exercise_history
                    WHERE user_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (user_id, limit),
                ).fetchall()
            return tuple(
                ExerciseHistoryEntry(
                    topic=str(row["topic"]),
                    difficulty=int(row["difficulty"]),
                    question=str(row["question"]),
                    submitted_answer=str(row["submitted_answer"]),
                    correct_answer=str(row["correct_answer"]),
                    correct=bool(row["correct"]),
                    solution=str(row["solution"]),
                    completed_at=str(row["completed_at"]),
                )
                for row in rows
            )
        except sqlite3.Error as error:
            self.logger.exception("Database failure while loading exercise history")
            raise LearningStorageError("Nie udało się wczytać historii ćwiczeń.") from error


class LearningSession:
    def __init__(
        self,
        user_id: int,
        topic: Topic,
        difficulty: int,
        question_count: int,
        database: Database,
        engine: MathEngine,
        gamification: GamificationService,
        catalog_topic_id: str | None = None,
        exercise_provider: Callable[[Topic, int], Exercise] | None = None,
    ) -> None:
        self.user_id = user_id
        self.topic = topic
        self.initial_difficulty = difficulty
        self.difficulty = difficulty
        self.total_questions = question_count
        self.session_id = str(uuid.uuid4())
        self.database = database
        self.engine = engine
        self.gamification = gamification
        self.catalog_topic_id = catalog_topic_id or ""
        self.exercise_provider = exercise_provider
        self.logger = logging.getLogger(__name__)
        self.started_at = time.monotonic()
        self.correct_count = 0
        self.incorrect_count = 0
        self._answered_count = 0
        self._correct_streak = 0
        self._incorrect_streak = 0
        self._pending_difficulty: int | None = None
        self._finished = False
        self._aborted = False
        self._question_started_at = time.monotonic()
        try:
            with self.database.transaction() as connection:
                recent_questions = connection.execute(
                    """
                    SELECT question FROM exercise_history
                    WHERE user_id = ? AND question != ''
                    ORDER BY id DESC
                    LIMIT 30
                    """,
                    (self.user_id,),
                ).fetchall()
        except sqlite3.Error as error:
            self.logger.exception("Could not load recent questions")
            raise LearningStorageError(
                "Nie udało się wczytać ostatnich pytań."
            ) from error
        self._recent_questions: deque[str] = deque(
            (str(row["question"]) for row in reversed(recent_questions)),
            maxlen=30,
        )
        self.current_exercise = self._generate()
        self._answered_current = False

    @property
    def answered_count(self) -> int:
        return self._answered_count

    @property
    def pending_difficulty(self) -> int | None:
        return self._pending_difficulty

    @property
    def progress(self) -> float:
        return self._answered_count / self.total_questions

    @property
    def finished(self) -> bool:
        return self._finished

    @property
    def aborted(self) -> bool:
        return self._aborted

    def answer(self, submitted_answer: str) -> AnswerResult:
        if self._finished:
            raise LearningError("Sesja jest już zakończona.")
        if self._answered_current:
            raise LearningError("Przejdź do następnego zadania.")
        if not submitted_answer.strip():
            raise ValueError("Wpisz odpowiedź przed jej sprawdzeniem.")
        if len(submitted_answer) > 500:
            raise ValueError("Odpowiedź może mieć maksymalnie 500 znaków.")

        exercise = self.current_exercise
        correct = self.engine.check_answer(exercise, submitted_answer)
        elapsed = max(0, round(time.monotonic() - self._question_started_at))
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO exercise_history (
                        user_id, topic, correct, duration_seconds, difficulty,
                        question, submitted_answer, correct_answer, solution,
                        session_id, catalog_topic_id, bank_task_id, generator_id,
                        generator_parameters_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.user_id,
                        exercise.topic.value,
                        int(correct),
                        elapsed,
                        exercise.difficulty,
                        exercise.prompt,
                        submitted_answer,
                        exercise.answer_text,
                        exercise.solution,
                        self.session_id,
                        self.catalog_topic_id,
                        exercise.bank_task_id,
                        exercise.generator_id or "",
                        exercise.generator_parameters_json,
                    ),
                )
                gamification = self.gamification.award_exercise(
                    connection,
                    user_id=self.user_id,
                    source_key=f"{self.session_id}:{self._answered_count + 1}",
                    topic=exercise.topic,
                    difficulty=exercise.difficulty,
                    correct=correct,
                    topic_completed=self._answered_count + 1 == self.total_questions,
                )
        except sqlite3.Error as error:
            self.logger.exception("Database failure while saving exercise answer")
            raise LearningStorageError(
                "Nie udało się zapisać odpowiedzi. Spróbuj ponownie."
            ) from error

        self._answered_current = True
        self._answered_count += 1
        if correct:
            self.correct_count += 1
            self._correct_streak += 1
            self._incorrect_streak = 0
        else:
            self.incorrect_count += 1
            self._incorrect_streak += 1
            self._correct_streak = 0

        if self._answered_count >= self.total_questions:
            self._finished = True
        elif self._correct_streak >= 3 and self.difficulty < max(DIFFICULTY_LEVELS):
            self._pending_difficulty = self.difficulty + 1
        elif self._incorrect_streak >= 3 and self.difficulty > min(DIFFICULTY_LEVELS):
            self._pending_difficulty = self.difficulty - 1

        return AnswerResult(
            correct=correct,
            correct_answer=exercise.answer_text,
            solution=exercise.solution,
            correct_count=self.correct_count,
            incorrect_count=self.incorrect_count,
            answered_count=self._answered_count,
            total_questions=self.total_questions,
            suggested_difficulty=self._pending_difficulty,
            session_finished=self._finished,
            xp_awarded=gamification.xp_awarded,
            total_xp=gamification.total_xp,
            old_level=gamification.old_level,
            level=gamification.level,
            achievements=gamification.achievements,
        )

    def resolve_difficulty_change(self, accept: bool) -> int:
        if self._pending_difficulty is None:
            raise LearningError("Nie ma oczekującej propozycji zmiany poziomu.")
        if accept:
            self.difficulty = self._pending_difficulty
        self._pending_difficulty = None
        self._correct_streak = 0
        self._incorrect_streak = 0
        return self.difficulty

    def next_question(self) -> Exercise | None:
        if self._finished:
            return None
        if not self._answered_current:
            raise LearningError("Najpierw sprawdź odpowiedź na bieżące zadanie.")
        if self._pending_difficulty is not None:
            raise LearningError("Najpierw zdecyduj, czy zmienić poziom trudności.")
        self.current_exercise = self._generate()
        self._answered_current = False
        self._question_started_at = time.monotonic()
        return self.current_exercise

    def finish(self, *, aborted: bool = True) -> SessionSummary:
        if not self._finished:
            self._finished = True
            self._aborted = aborted
            self._pending_difficulty = None
        return self.summary()

    def summary(self) -> SessionSummary:
        return SessionSummary(
            session_id=self.session_id,
            topic=self.topic,
            initial_difficulty=self.initial_difficulty,
            final_difficulty=self.difficulty,
            total_questions=self.total_questions,
            answered_count=self._answered_count,
            correct_count=self.correct_count,
            incorrect_count=self.incorrect_count,
            elapsed_seconds=max(0, round(time.monotonic() - self.started_at)),
            aborted=self._aborted,
        )

    def _generate(self) -> Exercise:
        for _ in range(100):
            exercise = (
                self.exercise_provider(self.topic, self.difficulty)
                if self.exercise_provider is not None
                else self.engine.generate(self.topic, self.difficulty)
            )
            if exercise.prompt not in self._recent_questions:
                self._recent_questions.append(exercise.prompt)
                return exercise
        raise LearningError(
            "Nie udało się znaleźć nowego pytania w ostatnich 30 zadaniach. "
            "Wybierz inny temat lub poziom trudności."
        )
