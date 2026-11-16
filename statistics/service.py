from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

from database.database import Database
from mathematics.topic_library import LIBRARY_TOPICS
from mathematics.topics import TOPIC_CATEGORIES, Topic

_TOPIC_LABELS = {
    Topic.ADDITION: "Dodawanie",
    Topic.SUBTRACTION: "Odejmowanie",
    Topic.MULTIPLICATION: "Mnożenie",
    Topic.DIVISION: "Dzielenie",
    Topic.ORDER_OF_OPERATIONS: "Kolejność działań",
    Topic.FRACTION_SIMPLIFY: "Skracanie ułamków",
    Topic.FRACTION_EXPAND: "Rozszerzanie ułamków",
    Topic.FRACTION_ADDITION: "Dodawanie ułamków",
    Topic.FRACTION_SUBTRACTION: "Odejmowanie ułamków",
    Topic.FRACTION_MULTIPLICATION: "Mnożenie ułamków",
    Topic.FRACTION_DIVISION: "Dzielenie ułamków",
    Topic.PERCENT_OF: "Procent z liczby",
    Topic.PERCENT_INCREASE: "Podwyżki procentowe",
    Topic.PERCENT_DECREASE: "Obniżki procentowe",
    Topic.PERCENT_ORIGINAL: "Wartość początkowa",
    Topic.ALGEBRA_EXPRESSION: "Wyrażenia algebraiczne",
    Topic.LINEAR_EQUATION: "Równania liniowe",
    Topic.LINEAR_INEQUALITY: "Nierówności liniowe",
    Topic.LINEAR_SYSTEM: "Układy równań",
    Topic.QUADRATIC_EQUATION: "Równania kwadratowe",
    Topic.AREA: "Pola figur",
    Topic.PERIMETER: "Obwody figur",
    Topic.VOLUME: "Objętość brył",
    Topic.SURFACE_AREA: "Pole powierzchni brył",
    Topic.PYTHAGOREAN: "Twierdzenie Pitagorasa",
    Topic.ANALYTIC_GEOMETRY: "Geometria analityczna",
    Topic.POWERS: "Potęgi",
    Topic.SQUARE_ROOTS: "Pierwiastki",
    Topic.FUNCTION_VALUE: "Wartość funkcji",
    Topic.GRAPH_POINT: "Punkty na wykresie",
    Topic.SEQUENCES: "Ciągi",
    Topic.TRIGONOMETRY: "Trygonometria",
    Topic.LOGARITHMS: "Logarytmy",
    Topic.COMBINATORICS: "Kombinatoryka",
    Topic.PROBABILITY: "Prawdopodobieństwo",
    Topic.STATISTICS: "Statystyka",
    Topic.LIMITS: "Granice",
    Topic.DERIVATIVES: "Pochodne",
    Topic.INTEGRALS: "Całki",
}
_TOPIC_CATEGORIES = {
    topic.value: category
    for category, topics in TOPIC_CATEGORIES.items()
    for topic in topics
}


class StatisticsStorageError(Exception):
    """Could not load a user's statistics."""


@dataclass(frozen=True, slots=True)
class CategoryProgress:
    category: str
    attempts: int
    correct: int
    accuracy_percent: float


@dataclass(frozen=True, slots=True)
class TopicProgress:
    topic: str
    topic_label: str
    category: str
    attempts: int
    correct: int
    accuracy_percent: float


@dataclass(frozen=True, slots=True)
class MistakeGroup:
    category: str
    topic: str
    topic_label: str
    attempts: int
    incorrect: int
    accuracy_percent: float
    latest_mistake: str
    repeated: bool


@dataclass(frozen=True, slots=True)
class HistoryResult:
    topic_label: str
    question: str
    submitted_answer: str
    correct_answer: str
    correct: bool
    difficulty: int
    completed_at: str


@dataclass(frozen=True, slots=True)
class DifficultyPoint:
    completed_at: str
    difficulty: int


@dataclass(frozen=True, slots=True)
class StatisticsSnapshot:
    solved_tasks: int
    correct_answers: int
    accuracy_percent: float
    study_seconds: int
    category_progress: tuple[CategoryProgress, ...]
    best_categories: tuple[CategoryProgress, ...]
    hardest_categories: tuple[CategoryProgress, ...]
    topic_progress: tuple[TopicProgress, ...]
    mistakes: tuple[MistakeGroup, ...]
    recommendations: tuple[TopicProgress, ...]
    daily_progress: tuple[tuple[str, int], ...]
    weekly_progress: tuple[tuple[str, int], ...]
    difficulty_history: tuple[DifficultyPoint, ...]
    history: tuple[HistoryResult, ...]


class StatisticsService:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.logger = logging.getLogger(__name__)
        self._catalog_metadata = {
            topic.id: (topic.title, topic.division) for topic in LIBRARY_TOPICS
        }

    def get_statistics(self, user_id: int) -> StatisticsSnapshot:
        if user_id < 1:
            raise ValueError("Id użytkownika musi być dodatni.")
        today = date.today()
        daily_start = today - timedelta(days=13)
        weekly_start = today - timedelta(days=today.weekday(), weeks=11)
        try:
            with self.database.transaction() as connection:
                if connection.execute(
                    "SELECT 1 FROM users WHERE id = ?", (user_id,)
                ).fetchone() is None:
                    raise ValueError("Nie znaleziono użytkownika.")

                totals = connection.execute(
                    """
                    SELECT COUNT(*) AS solved,
                           COALESCE(SUM(correct), 0) AS correct,
                           COALESCE(SUM(duration_seconds), 0) AS study_seconds
                    FROM exercise_history
                    WHERE user_id = ?
                    """,
                    (user_id,),
                ).fetchone()
                topic_rows = connection.execute(
                    """
                    SELECT COALESCE(NULLIF(catalog_topic_id, ''), topic) AS topic,
                           COUNT(*) AS attempts,
                           COALESCE(SUM(correct), 0) AS correct
                    FROM exercise_history
                    WHERE user_id = ?
                    GROUP BY COALESCE(NULLIF(catalog_topic_id, ''), topic)
                    """,
                    (user_id,),
                ).fetchall()
                mistake_rows = connection.execute(
                    """
                    SELECT COALESCE(NULLIF(h.catalog_topic_id, ''), h.topic) AS topic,
                           COUNT(*) AS attempts,
                           COALESCE(SUM(correct), 0) AS correct,
                           SUM(CASE WHEN correct = 0 THEN 1 ELSE 0 END) AS incorrect,
                           (SELECT previous.submitted_answer
                            FROM exercise_history AS previous
                            WHERE previous.user_id = h.user_id
                              AND COALESCE(
                                  NULLIF(previous.catalog_topic_id, ''), previous.topic
                              ) = COALESCE(NULLIF(h.catalog_topic_id, ''), h.topic)
                              AND previous.correct = 0
                            ORDER BY previous.id DESC
                            LIMIT 1) AS latest_mistake
                    FROM exercise_history AS h
                    WHERE h.user_id = ?
                    GROUP BY COALESCE(NULLIF(h.catalog_topic_id, ''), h.topic)
                    HAVING SUM(CASE WHEN h.correct = 0 THEN 1 ELSE 0 END) > 0
                    """,
                    (user_id,),
                ).fetchall()
                daily_rows = connection.execute(
                    """
                    SELECT date(completed_at) AS day, COUNT(*) AS solved
                    FROM exercise_history
                    WHERE user_id = ? AND date(completed_at) BETWEEN ? AND ?
                    GROUP BY date(completed_at)
                    """,
                    (user_id, daily_start.isoformat(), today.isoformat()),
                ).fetchall()
                weekly_rows = connection.execute(
                    """
                    SELECT date(completed_at) AS day, COUNT(*) AS solved
                    FROM exercise_history
                    WHERE user_id = ? AND date(completed_at) BETWEEN ? AND ?
                    GROUP BY date(completed_at)
                    """,
                    (user_id, weekly_start.isoformat(), today.isoformat()),
                ).fetchall()
                difficulty_rows = connection.execute(
                    """
                    SELECT completed_at, difficulty
                    FROM exercise_history
                    WHERE user_id = ?
                    ORDER BY id DESC
                    LIMIT 100
                    """,
                    (user_id,),
                ).fetchall()
                history_rows = connection.execute(
                    """
                    SELECT COALESCE(NULLIF(catalog_topic_id, ''), topic) AS topic,
                           question, submitted_answer, correct_answer,
                           correct, difficulty, completed_at
                    FROM exercise_history
                    WHERE user_id = ?
                    ORDER BY id DESC
                    LIMIT 30
                    """,
                    (user_id,),
                ).fetchall()
                custom_topic_rows = connection.execute(
                    """
                    SELECT topic_id, title, division
                    FROM custom_learning_topics
                    WHERE owner_id = ?
                    """,
                    (user_id,),
                ).fetchall()
        except ValueError:
            raise
        except sqlite3.Error as error:
            self.logger.exception("Database failure while loading user statistics")
            raise StatisticsStorageError(
                "Nie udało się wczytać statystyk. Spróbuj ponownie."
            ) from error

        catalog_metadata = self._catalog_metadata.copy()
        catalog_metadata.update(
            {
                str(row["topic_id"]): (str(row["title"]), str(row["division"]))
                for row in custom_topic_rows
            }
        )
        solved = int(totals["solved"])
        correct = int(totals["correct"])
        topic_progress = tuple(
            sorted(
                (
                    TopicProgress(
                        topic=str(row["topic"]),
                        topic_label=self._topic_label(
                            str(row["topic"]), catalog_metadata
                        ),
                        category=self._category(str(row["topic"]), catalog_metadata),
                        attempts=int(row["attempts"]),
                        correct=int(row["correct"]),
                        accuracy_percent=self._accuracy(
                            int(row["correct"]), int(row["attempts"])
                        ),
                    )
                    for row in topic_rows
                ),
                key=lambda item: (item.category, item.topic_label),
            )
        )
        category_totals: dict[str, list[int]] = {}
        for item in topic_progress:
            values = category_totals.setdefault(item.category, [0, 0])
            values[0] += item.attempts
            values[1] += item.correct
        category_progress = tuple(
            sorted(
                (
                    CategoryProgress(
                        category=category,
                        attempts=attempts,
                        correct=category_correct,
                        accuracy_percent=self._accuracy(category_correct, attempts),
                    )
                    for category, (attempts, category_correct) in category_totals.items()
                ),
                key=lambda item: item.category,
            )
        )
        category_by_topic = {item.topic: item.category for item in topic_progress}
        mistakes = tuple(
            sorted(
                (
                    MistakeGroup(
                        category=category_by_topic.get(
                            str(row["topic"]),
                            self._category(str(row["topic"]), catalog_metadata),
                        ),
                        topic=str(row["topic"]),
                        topic_label=self._topic_label(
                            str(row["topic"]), catalog_metadata
                        ),
                        attempts=int(row["attempts"]),
                        incorrect=int(row["incorrect"]),
                        accuracy_percent=self._accuracy(
                            int(row["correct"]), int(row["attempts"])
                        ),
                        latest_mistake=str(row["latest_mistake"] or ""),
                        repeated=int(row["incorrect"]) >= 2,
                    )
                    for row in mistake_rows
                ),
                key=lambda item: (-item.incorrect, item.accuracy_percent, item.topic_label),
            )
        )
        recommendations = tuple(
            sorted(
                (
                    item
                    for item in topic_progress
                    if any(mistake.topic == item.topic for mistake in mistakes)
                ),
                key=lambda item: (
                    item.accuracy_percent,
                    -next(
                        mistake.incorrect
                        for mistake in mistakes
                        if mistake.topic == item.topic
                    ),
                    item.topic_label,
                ),
            )[:5]
        )
        daily_counts = {str(row["day"]): int(row["solved"]) for row in daily_rows}
        daily_progress = tuple(
            ((daily_start + timedelta(days=index)).isoformat(),
             daily_counts.get((daily_start + timedelta(days=index)).isoformat(), 0))
            for index in range(14)
        )
        weekly_counts: dict[str, int] = {}
        for row in weekly_rows:
            day = date.fromisoformat(str(row["day"]))
            week_start = day - timedelta(days=day.weekday())
            key = week_start.isoformat()
            weekly_counts[key] = weekly_counts.get(key, 0) + int(row["solved"])
        current_week_start = today - timedelta(days=today.weekday())
        weekly_progress = tuple(
            (
                (current_week_start - timedelta(weeks=index)).isoformat(),
                weekly_counts.get(
                    (current_week_start - timedelta(weeks=index)).isoformat(), 0
                ),
            )
            for index in reversed(range(12))
        )
        return StatisticsSnapshot(
            solved_tasks=solved,
            correct_answers=correct,
            accuracy_percent=self._accuracy(correct, solved),
            study_seconds=int(totals["study_seconds"]),
            category_progress=category_progress,
            best_categories=tuple(
                sorted(
                    category_progress,
                    key=lambda item: (-item.accuracy_percent, -item.attempts),
                )[:3]
            ),
            hardest_categories=tuple(
                sorted(
                    category_progress,
                    key=lambda item: (item.accuracy_percent, -item.attempts),
                )[:3]
            ),
            topic_progress=topic_progress,
            mistakes=mistakes,
            recommendations=recommendations,
            daily_progress=daily_progress,
            weekly_progress=weekly_progress,
            difficulty_history=tuple(
                DifficultyPoint(
                    completed_at=str(row["completed_at"]),
                    difficulty=int(row["difficulty"]),
                )
                for row in reversed(difficulty_rows)
            ),
            history=tuple(
                HistoryResult(
                    topic_label=self._topic_label(
                        str(row["topic"]), catalog_metadata
                    ),
                    question=str(row["question"]),
                    submitted_answer=str(row["submitted_answer"]),
                    correct_answer=str(row["correct_answer"]),
                    correct=bool(row["correct"]),
                    difficulty=int(row["difficulty"]),
                    completed_at=str(row["completed_at"]),
                )
                for row in history_rows
            ),
        )

    @staticmethod
    def _accuracy(correct: int, attempts: int) -> float:
        return round(correct * 100 / attempts, 1) if attempts else 0.0

    def _category(
        self, topic: str, catalog_metadata: dict[str, tuple[str, str]]
    ) -> str:
        return catalog_metadata.get(
            topic, ("", _TOPIC_CATEGORIES.get(topic, "Pozostałe"))
        )[1]

    def _topic_label(
        self, topic: str, catalog_metadata: dict[str, tuple[str, str]]
    ) -> str:
        if topic in catalog_metadata:
            return catalog_metadata[topic][0]
        try:
            return _TOPIC_LABELS[Topic(topic)]
        except (ValueError, KeyError):
            return topic.replace("_", " ").capitalize()
