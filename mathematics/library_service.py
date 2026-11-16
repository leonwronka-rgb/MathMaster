from __future__ import annotations

import json
import sqlite3
import uuid

from database.database import Database
from mathematics.engine import MathEngine
from mathematics.solutions import Exercise
from mathematics.topic_library import (
    LIBRARY_TOPICS,
    STATUS_VALUES,
    LibraryTopic,
)
from mathematics.topics import DIFFICULTY_LEVELS, Topic

_MAX_TEXT_LENGTH = 2_000


class TopicLibraryError(ValueError):
    """Invalid topic catalog operation."""


class TopicLibraryStorageError(RuntimeError):
    """A topic catalog database operation failed."""


class TopicLibraryService:
    def __init__(
        self, database: Database, engine: MathEngine | None = None
    ) -> None:
        self.database = database
        self.engine = engine or MathEngine()

    def search(
        self,
        user_id: int,
        query: str = "",
        *,
        division: str | None = None,
        difficulty: int | None = None,
        status: str | None = None,
    ) -> tuple[LibraryTopic, ...]:
        if difficulty is not None and difficulty not in DIFFICULTY_LEVELS:
            raise TopicLibraryError("Poziom musi należeć do zakresu 1–5.")
        if status is not None and status not in STATUS_VALUES:
            raise TopicLibraryError("Nieznany status opanowania tematu.")
        normalized_query = query.casefold().strip()
        custom_topics = self._custom_topics(user_id)
        candidates = (*LIBRARY_TOPICS, *custom_topics)
        statuses = self.get_statuses(user_id)
        return tuple(
            topic
            for topic in candidates
            if (division is None or topic.division == division)
            and (difficulty is None or topic.difficulty == difficulty)
            and (status is None or statuses.get(topic.id, "unmastered") == status)
            and (
                not normalized_query
                or normalized_query in topic.title.casefold()
                or normalized_query in topic.division.casefold()
                or normalized_query in topic.subdivision.casefold()
                or normalized_query in topic.description.casefold()
                or any(normalized_query in item.casefold() for item in topic.subtopics)
            )
        )

    def get_topic(self, user_id: int, topic_id: str) -> LibraryTopic:
        for topic in self._custom_topics(user_id):
            if topic.id == topic_id:
                return topic
        for topic in LIBRARY_TOPICS:
            if topic.id == topic_id:
                return topic
        raise TopicLibraryError(f"Nie znaleziono tematu o identyfikatorze {topic_id!r}.")

    def get_statuses(self, user_id: int) -> dict[str, str]:
        try:
            with self.database.transaction() as connection:
                rows = connection.execute(
                    "SELECT topic_id, status FROM learning_topic_status WHERE user_id = ?",
                    (user_id,),
                ).fetchall()
            return {str(row["topic_id"]): str(row["status"]) for row in rows}
        except sqlite3.Error as error:
            raise TopicLibraryStorageError("Nie udało się odczytać postępu tematów.") from error

    def set_status(self, user_id: int, topic_id: str, status: str) -> None:
        if status not in STATUS_VALUES:
            raise TopicLibraryError("Nieznany status opanowania tematu.")
        self.get_topic(user_id, topic_id)
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO learning_topic_status (user_id, topic_id, status)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id, topic_id) DO UPDATE SET
                        status = excluded.status,
                        updated_at = datetime('now')
                    """,
                    (user_id, topic_id, status),
                )
        except sqlite3.Error as error:
            raise TopicLibraryStorageError("Nie udało się zapisać statusu tematu.") from error

    def add_topic(
        self,
        user_id: int,
        *,
        division: str,
        subdivision: str,
        title: str,
        description: str,
        difficulty: int,
        theory: tuple[str, ...],
        examples: tuple[str, ...],
        subtopics: tuple[str, ...],
        exercise_topic: Topic | str,
    ) -> str:
        division = self._required_text("Dział", division, 80)
        subdivision = self._required_text("Poddział", subdivision, 100)
        title = self._required_text("Temat", title, 120)
        description = self._required_text("Opis", description, _MAX_TEXT_LENGTH)
        if difficulty not in DIFFICULTY_LEVELS:
            raise TopicLibraryError("Poziom musi należeć do zakresu 1–5.")
        try:
            generator_topic = Topic(exercise_topic)
        except ValueError as error:
            raise TopicLibraryError("Wybierz obsługiwany typ generatora zadań.") from error
        if not theory or not examples or not subtopics:
            raise TopicLibraryError(
                "Dodaj co najmniej jedną pozycję teorii, przykładu i podtematu."
            )
        topic_id = f"custom.{uuid.uuid4().hex}"
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO custom_learning_topics (
                        topic_id, owner_id, division, subdivision, title,
                        description, difficulty, theory_json, examples_json,
                        subtopics_json, exercise_topic
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        topic_id,
                        user_id,
                        division,
                        subdivision,
                        title,
                        description,
                        difficulty,
                        self._dump_texts(theory),
                        self._dump_texts(examples),
                        self._dump_texts(subtopics),
                        generator_topic.value,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise TopicLibraryStorageError("Nie udało się dodać tematu.") from error
        except sqlite3.Error as error:
            raise TopicLibraryStorageError("Nie udało się zapisać nowego tematu.") from error
        return topic_id

    def generate_exercises(
        self, user_id: int, topic_id: str, count: int = 3
    ) -> tuple[Exercise, ...]:
        if not 1 <= count <= 20:
            raise TopicLibraryError("Liczba ćwiczeń musi należeć do zakresu 1–20.")
        topic = self.get_topic(user_id, topic_id)
        return tuple(
            self.engine.generate(topic.exercise_topic, topic.difficulty)
            for _ in range(count)
        )

    def _custom_topics(self, user_id: int) -> tuple[LibraryTopic, ...]:
        try:
            with self.database.transaction() as connection:
                rows = connection.execute(
                    """
                    SELECT topic_id, division, subdivision, title, description,
                           difficulty, theory_json, examples_json, subtopics_json,
                           exercise_topic
                    FROM custom_learning_topics
                    WHERE owner_id = ?
                    ORDER BY division COLLATE NOCASE, subdivision COLLATE NOCASE,
                             title COLLATE NOCASE
                    """,
                    (user_id,),
                ).fetchall()
        except sqlite3.Error as error:
            raise TopicLibraryStorageError("Nie udało się odczytać własnych tematów.") from error
        try:
            return tuple(
                LibraryTopic(
                    id=str(row["topic_id"]),
                    division=str(row["division"]),
                    subdivision=str(row["subdivision"]),
                    title=str(row["title"]),
                    description=str(row["description"]),
                    difficulty=int(row["difficulty"]),
                    theory=self._load_texts(row["theory_json"]),
                    examples=self._load_texts(row["examples_json"]),
                    subtopics=self._load_texts(row["subtopics_json"]),
                    exercise_topic=Topic(row["exercise_topic"]),
                    custom=True,
                )
                for row in rows
            )
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            raise TopicLibraryStorageError("Dane własnego tematu są uszkodzone.") from error

    @staticmethod
    def _required_text(label: str, value: str, limit: int) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > limit:
            raise TopicLibraryError(f"{label}: wymagane 1–{limit} znaków.")
        return normalized

    @classmethod
    def _dump_texts(cls, values: tuple[str, ...]) -> str:
        cleaned = tuple(
            cls._required_text("Element treści", value, _MAX_TEXT_LENGTH)
            for value in values
        )
        if len(cleaned) > 30:
            raise TopicLibraryError("Każda lista treści może zawierać najwyżej 30 pozycji.")
        return json.dumps(cleaned, ensure_ascii=False)

    @staticmethod
    def _load_texts(value: str) -> tuple[str, ...]:
        decoded = json.loads(value)
        if not isinstance(decoded, list) or not all(
            isinstance(item, str) for item in decoded
        ):
            raise ValueError("Oczekiwano listy tekstów.")
        return tuple(decoded)

