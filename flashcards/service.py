from __future__ import annotations

import json
import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from database.database import Database
from mathematics.engine import MathEngine
from mathematics.topic_library import LibraryTopic
from mathematics.topics import Topic

_RATINGS = frozenset({"again", "hard", "know", "easy"})
_MAX_TEXT_LENGTH = 4_000
_MAX_IMPORTED_CARDS = 500
_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


class FlashcardError(ValueError):
    """Invalid flashcard request or content."""


class FlashcardStorageError(RuntimeError):
    """A flashcard database operation failed."""


@dataclass(frozen=True, slots=True)
class FlashcardDeck:
    id: int
    name: str
    card_count: int


@dataclass(frozen=True, slots=True)
class Flashcard:
    id: int
    deck_id: int | None
    deck_name: str
    front: str
    back: str
    division: str
    topic_id: str
    favorite: bool
    repetitions: int
    last_reviewed_at: str | None
    next_review_at: str | None
    mastery: int
    interval_days: float
    ease_factor: float


@dataclass(frozen=True, slots=True)
class FlashcardReview:
    rating: str
    correct: bool
    reviewed_at: str
    next_review_at: str
    mastery: int


@dataclass(frozen=True, slots=True)
class FlashcardStats:
    total_cards: int
    mastered_cards: int
    due_cards: int
    studied_today: int
    daily_goal: int
    correct_today: int
    accuracy_percent: float
    streak_days: int

    @property
    def goal_progress(self) -> float:
        return min(1.0, self.studied_today / self.daily_goal) if self.daily_goal else 0


class FlashcardService:
    def __init__(
        self,
        database: Database,
        engine: MathEngine | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.database = database
        self.engine = engine or MathEngine(rng)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.rng = rng or random.Random()

    def create_deck(self, user_id: int, name: str) -> FlashcardDeck:
        name = self._text(name, "Nazwa zestawu", 80)
        try:
            with self.database.transaction() as connection:
                cursor = connection.execute(
                    "INSERT INTO flashcard_decks (user_id, name) VALUES (?, ?)",
                    (user_id, name),
                )
                deck_id = int(cursor.lastrowid)
            return FlashcardDeck(deck_id, name, 0)
        except sqlite3.IntegrityError as error:
            raise FlashcardError("Zestaw o tej nazwie już istnieje.") from error
        except sqlite3.Error as error:
            raise FlashcardStorageError("Nie udało się utworzyć zestawu.") from error

    def rename_deck(self, user_id: int, deck_id: int, name: str) -> None:
        name = self._text(name, "Nazwa zestawu", 80)
        try:
            with self.database.transaction() as connection:
                cursor = connection.execute(
                    "UPDATE flashcard_decks SET name = ? WHERE id = ? AND user_id = ?",
                    (name, deck_id, user_id),
                )
                if cursor.rowcount == 0:
                    raise FlashcardError("Nie znaleziono zestawu.")
        except sqlite3.IntegrityError as error:
            raise FlashcardError("Zestaw o tej nazwie już istnieje.") from error
        except sqlite3.Error as error:
            raise FlashcardStorageError("Nie udało się zmienić nazwy zestawu.") from error

    def delete_deck(self, user_id: int, deck_id: int) -> None:
        try:
            with self.database.transaction() as connection:
                cursor = connection.execute(
                    "DELETE FROM flashcard_decks WHERE id = ? AND user_id = ?",
                    (deck_id, user_id),
                )
                if cursor.rowcount == 0:
                    raise FlashcardError("Nie znaleziono zestawu.")
        except sqlite3.Error as error:
            raise FlashcardStorageError("Nie udało się usunąć zestawu.") from error

    def get_decks(self, user_id: int) -> tuple[FlashcardDeck, ...]:
        try:
            with self.database.transaction() as connection:
                rows = connection.execute(
                    """
                    SELECT d.id, d.name, COUNT(c.id) AS card_count
                    FROM flashcard_decks AS d
                    LEFT JOIN flashcards AS c
                      ON c.deck_id = d.id AND c.user_id = d.user_id
                    WHERE d.user_id = ?
                    GROUP BY d.id
                    ORDER BY d.name COLLATE NOCASE
                    """,
                    (user_id,),
                ).fetchall()
            return tuple(
                FlashcardDeck(int(row["id"]), str(row["name"]), int(row["card_count"]))
                for row in rows
            )
        except sqlite3.Error as error:
            raise FlashcardStorageError("Nie udało się wczytać zestawów.") from error

    def create_card(
        self,
        user_id: int,
        front: str,
        back: str,
        *,
        deck_id: int | None = None,
        division: str = "",
        topic_id: str = "",
    ) -> Flashcard:
        front = self._text(front, "Pytanie", _MAX_TEXT_LENGTH)
        back = self._text(back, "Odpowiedź", _MAX_TEXT_LENGTH)
        division = division.strip()
        topic_id = topic_id.strip()
        try:
            with self.database.transaction() as connection:
                selected_deck = self._ensure_deck(connection, user_id, deck_id)
                cursor = connection.execute(
                    """
                    INSERT INTO flashcards (
                        user_id, deck_id, front, back, division, topic_id,
                        next_review_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        selected_deck,
                        front,
                        back,
                        division,
                        topic_id,
                        self._now_string(),
                        self._now_string(),
                    ),
                )
                card_id = int(cursor.lastrowid)
            return self.get_card(user_id, card_id)
        except FlashcardError:
            raise
        except sqlite3.Error as error:
            raise FlashcardStorageError("Nie udało się utworzyć fiszki.") from error

    def update_card(
        self,
        user_id: int,
        card_id: int,
        front: str,
        back: str,
        *,
        deck_id: int | None,
        division: str,
        topic_id: str,
    ) -> Flashcard:
        front = self._text(front, "Pytanie", _MAX_TEXT_LENGTH)
        back = self._text(back, "Odpowiedź", _MAX_TEXT_LENGTH)
        try:
            with self.database.transaction() as connection:
                selected_deck = self._ensure_deck(connection, user_id, deck_id)
                cursor = connection.execute(
                    """
                    UPDATE flashcards
                    SET deck_id = ?, front = ?, back = ?, division = ?,
                        topic_id = ?, updated_at = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (
                        selected_deck,
                        front,
                        back,
                        division.strip(),
                        topic_id.strip(),
                        self._now_string(),
                        card_id,
                        user_id,
                    ),
                )
                if cursor.rowcount == 0:
                    raise FlashcardError("Nie znaleziono fiszki.")
            return self.get_card(user_id, card_id)
        except FlashcardError:
            raise
        except sqlite3.Error as error:
            raise FlashcardStorageError("Nie udało się zapisać zmian fiszki.") from error

    def delete_card(self, user_id: int, card_id: int) -> None:
        try:
            with self.database.transaction() as connection:
                cursor = connection.execute(
                    "DELETE FROM flashcards WHERE id = ? AND user_id = ?",
                    (card_id, user_id),
                )
                if cursor.rowcount == 0:
                    raise FlashcardError("Nie znaleziono fiszki.")
        except FlashcardError:
            raise
        except sqlite3.Error as error:
            raise FlashcardStorageError("Nie udało się usunąć fiszki.") from error

    def get_card(self, user_id: int, card_id: int) -> Flashcard:
        try:
            with self.database.transaction() as connection:
                row = connection.execute(
                    self._card_select() + " WHERE c.id = ? AND c.user_id = ?",
                    (card_id, user_id),
                ).fetchone()
            if row is None:
                raise FlashcardError("Nie znaleziono fiszki.")
            return self._card_from_row(row)
        except FlashcardError:
            raise
        except sqlite3.Error as error:
            raise FlashcardStorageError("Nie udało się wczytać fiszki.") from error

    def list_cards(
        self,
        user_id: int,
        *,
        search: str = "",
        deck_id: int | None = None,
        division: str | None = None,
        favorites_only: bool = False,
        sort_by: str = "front",
    ) -> tuple[Flashcard, ...]:
        sort_columns = {
            "front": "c.front COLLATE NOCASE",
            "recent": "c.updated_at DESC, c.id DESC",
            "due": "COALESCE(julianday(c.next_review_at), 0), c.id",
            "mastery": "c.mastery, c.id",
            "favorite": "c.favorite DESC, c.front COLLATE NOCASE",
        }
        if sort_by not in sort_columns:
            raise FlashcardError("Nieznany porządek sortowania.")
        clauses = ["c.user_id = ?"]
        parameters: list[object] = [user_id]
        if search.strip():
            clauses.append("(c.front LIKE ? OR c.back LIKE ? OR c.division LIKE ?)")
            needle = f"%{search.strip()}%"
            parameters.extend((needle, needle, needle))
        if deck_id is not None:
            clauses.append("c.deck_id = ?")
            parameters.append(deck_id)
        if division:
            clauses.append("c.division = ?")
            parameters.append(division)
        if favorites_only:
            clauses.append("c.favorite = 1")
        try:
            with self.database.transaction() as connection:
                rows = connection.execute(
                    self._card_select()
                    + " WHERE "
                    + " AND ".join(clauses)
                    + f" ORDER BY {sort_columns[sort_by]}",
                    parameters,
                ).fetchall()
            return tuple(self._card_from_row(row) for row in rows)
        except sqlite3.Error as error:
            raise FlashcardStorageError("Nie udało się wyszukać fiszek.") from error

    def toggle_favorite(self, user_id: int, card_id: int) -> bool:
        try:
            with self.database.transaction() as connection:
                cursor = connection.execute(
                    """
                    UPDATE flashcards
                    SET favorite = 1 - favorite, updated_at = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (self._now_string(), card_id, user_id),
                )
                if cursor.rowcount == 0:
                    raise FlashcardError("Nie znaleziono fiszki.")
                row = connection.execute(
                    "SELECT favorite FROM flashcards WHERE id = ?", (card_id,)
                ).fetchone()
            return bool(row["favorite"])
        except FlashcardError:
            raise
        except sqlite3.Error as error:
            raise FlashcardStorageError("Nie udało się zmienić ulubionej fiszki.") from error

    def create_from_topic(
        self,
        user_id: int,
        topic: LibraryTopic,
        *,
        count: int = 5,
        deck_id: int | None = None,
    ) -> tuple[Flashcard, ...]:
        if not 1 <= count <= 50:
            raise FlashcardError("Liczba automatycznych fiszek musi należeć do zakresu 1–50.")
        try:
            exercises = tuple(
                self.engine.generate(topic.exercise_topic, topic.difficulty)
                for _ in range(count)
            )
            with self.database.transaction() as connection:
                selected_deck = self._ensure_deck(connection, user_id, deck_id)
                card_ids = []
                now = self._now_string()
                for exercise in exercises:
                    cursor = connection.execute(
                        """
                        INSERT INTO flashcards (
                            user_id, deck_id, front, back, division, topic_id,
                            next_review_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            user_id,
                            selected_deck,
                            exercise.prompt,
                            f"{exercise.answer_text}\n\n{exercise.solution}",
                            topic.division,
                            topic.id,
                            now,
                            now,
                        ),
                    )
                    card_ids.append(int(cursor.lastrowid))
            return tuple(self.get_card(user_id, card_id) for card_id in card_ids)
        except (FlashcardError, ValueError):
            raise
        except sqlite3.Error as error:
            raise FlashcardStorageError("Nie udało się utworzyć fiszek z tematu.") from error

    def get_due_cards(
        self,
        user_id: int,
        *,
        deck_id: int | None = None,
        difficult_only: bool = False,
        random_order: bool = False,
        limit: int = 100,
    ) -> tuple[Flashcard, ...]:
        if not 1 <= limit <= 500:
            raise FlashcardError("Limit sesji musi należeć do zakresu 1–500.")
        clauses = [
            "c.user_id = ?",
            "(c.next_review_at IS NULL OR julianday(c.next_review_at) <= julianday(?))",
        ]
        parameters: list[object] = [user_id, self._now_string()]
        if deck_id is not None:
            clauses.append("c.deck_id = ?")
            parameters.append(deck_id)
        if difficult_only:
            clauses.append("c.mastery <= 2")
        try:
            with self.database.transaction() as connection:
                rows = connection.execute(
                    self._card_select()
                    + " WHERE " + " AND ".join(clauses)
                    + " ORDER BY c.mastery ASC, c.next_review_at ASC, c.id ASC LIMIT ?",
                    (*parameters, limit),
                ).fetchall()
            cards = [self._card_from_row(row) for row in rows]
            if random_order:
                self.rng.shuffle(cards)
            return tuple(cards)
        except sqlite3.Error as error:
            raise FlashcardStorageError("Nie udało się wczytać fiszek do powtórki.") from error

    def get_all_cards_for_study(
        self,
        user_id: int,
        *,
        deck_id: int | None = None,
        difficult_only: bool = False,
        random_order: bool = False,
        limit: int = 500,
    ) -> tuple[Flashcard, ...]:
        clauses = ["c.user_id = ?"]
        parameters: list[object] = [user_id]
        if deck_id is not None:
            clauses.append("c.deck_id = ?")
            parameters.append(deck_id)
        if difficult_only:
            clauses.append("c.mastery <= 2")
        try:
            with self.database.transaction() as connection:
                rows = connection.execute(
                    self._card_select()
                    + " WHERE " + " AND ".join(clauses)
                    + " ORDER BY c.mastery ASC, c.id ASC LIMIT ?",
                    (*parameters, limit),
                ).fetchall()
            cards = [self._card_from_row(row) for row in rows]
            if random_order:
                self.rng.shuffle(cards)
            return tuple(cards)
        except sqlite3.Error as error:
            raise FlashcardStorageError("Nie udało się wczytać fiszek do nauki.") from error

    def review(
        self,
        user_id: int,
        card_id: int,
        rating: str,
        *,
        test_correct: bool | None = None,
        test_session_id: str = "",
    ) -> FlashcardReview:
        if rating not in _RATINGS:
            raise FlashcardError("Wybierz ocenę: Nie znam, Trudne, Umiem albo Łatwe.")
        if test_correct is not None and (
            not isinstance(test_correct, bool)
            or not test_session_id.strip()
            or len(test_session_id) > 120
        ):
            raise FlashcardError("Nieprawidłowy wynik testu fiszek.")
        if test_correct is None and test_session_id:
            raise FlashcardError("Identyfikator sesji jest dostępny tylko dla testu.")
        now = self._now()
        now_string = now.strftime(_TIMESTAMP_FORMAT)
        try:
            with self.database.transaction() as connection:
                row = connection.execute(
                    """
                    SELECT c.repetitions, c.interval_days, c.ease_factor, c.mastery,
                           c.deck_id, COALESCE(d.name, 'Bez zestawu') AS deck_name
                    FROM flashcards AS c
                    LEFT JOIN flashcard_decks AS d
                        ON d.id = c.deck_id AND d.user_id = c.user_id
                    WHERE c.id = ? AND c.user_id = ?
                    """,
                    (card_id, user_id),
                ).fetchone()
                if row is None:
                    raise FlashcardError("Nie znaleziono fiszki.")
                reps = int(row["repetitions"])
                interval = float(row["interval_days"])
                ease = float(row["ease_factor"])
                mastery = int(row["mastery"])
                due_at, repetitions, interval, ease, mastery, correct = (
                    self._schedule(rating, now, reps, interval, ease, mastery)
                )
                if test_correct is not None:
                    correct = test_correct
                due_string = due_at.strftime(_TIMESTAMP_FORMAT)
                connection.execute(
                    """
                    UPDATE flashcards
                    SET repetitions = ?, interval_days = ?, ease_factor = ?,
                        mastery = ?, last_reviewed_at = ?, next_review_at = ?,
                        updated_at = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (
                        repetitions, interval, ease, mastery, now_string,
                        due_string, now_string, card_id, user_id,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO flashcard_reviews (
                        user_id, flashcard_id, rating, correct, next_review_at,
                        mastery, reviewed_at, deck_id, deck_name, tested, test_session_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id, card_id, rating, int(correct), due_string,
                        mastery, now_string, row["deck_id"], row["deck_name"],
                        int(test_correct is not None), test_session_id,
                    ),
                )
            return FlashcardReview(rating, correct, now_string, due_string, mastery)
        except FlashcardError:
            raise
        except sqlite3.Error as error:
            raise FlashcardStorageError("Nie udało się zapisać powtórki.") from error

    @staticmethod
    def _schedule(
        rating: str,
        now: datetime,
        repetitions: int,
        interval_days: float,
        ease_factor: float,
        mastery: int,
    ) -> tuple[datetime, int, float, float, int, bool]:
        if rating == "again":
            interval_days = 10 / (24 * 60)
            repetitions = 0
            ease_factor = max(1.3, ease_factor - 0.2)
            mastery = max(0, mastery - 1)
            correct = False
        elif rating == "hard":
            interval_days = max(1.0, interval_days * 1.2)
            repetitions += 1
            ease_factor = max(1.3, ease_factor - 0.15)
            correct = True
        elif rating == "know":
            interval_days = 1.0 if repetitions == 0 else (
                3.0 if repetitions == 1 else interval_days * ease_factor
            )
            repetitions += 1
            mastery = min(5, mastery + 1)
            correct = True
        else:
            interval_days = 2.0 if repetitions == 0 else (
                5.0 if repetitions == 1 else interval_days * ease_factor * 1.3
            )
            repetitions += 1
            ease_factor += 0.15
            mastery = min(5, mastery + 1)
            correct = True
        return (
            now + timedelta(days=interval_days),
            repetitions,
            interval_days,
            ease_factor,
            mastery,
            correct,
        )

    def get_review_history(
        self, user_id: int, card_id: int, *, limit: int = 50
    ) -> tuple[FlashcardReview, ...]:
        try:
            with self.database.transaction() as connection:
                rows = connection.execute(
                    """
                    SELECT r.rating, r.correct, r.reviewed_at,
                           r.next_review_at, r.mastery
                    FROM flashcard_reviews AS r
                    JOIN flashcards AS c ON c.id = r.flashcard_id
                    WHERE r.user_id = ? AND r.flashcard_id = ?
                    ORDER BY r.id DESC LIMIT ?
                    """,
                    (user_id, card_id, limit),
                ).fetchall()
            return tuple(
                FlashcardReview(
                    str(row["rating"]),
                    bool(row["correct"]),
                    str(row["reviewed_at"]),
                    str(row["next_review_at"] or ""),
                    int(row["mastery"]),
                )
                for row in rows
            )
        except sqlite3.Error as error:
            raise FlashcardStorageError("Nie udało się wczytać historii powtórek.") from error

    def get_stats(self, user_id: int) -> FlashcardStats:
        today = self._now().date().isoformat()
        now_string = self._now_string()
        try:
            with self.database.transaction() as connection:
                totals = connection.execute(
                    """
                    SELECT COUNT(*) AS total,
                           COALESCE(SUM(CASE WHEN mastery >= 4 THEN 1 ELSE 0 END), 0) AS mastered,
                           COALESCE(SUM(CASE WHEN next_review_at IS NULL OR
                               julianday(next_review_at) <= julianday(?) THEN 1 ELSE 0 END), 0) AS due
                    FROM flashcards WHERE user_id = ?
                    """,
                    (now_string, user_id),
                ).fetchone()
                daily = connection.execute(
                    """
                    SELECT COUNT(*) AS studied,
                           COALESCE(SUM(correct), 0) AS correct
                    FROM flashcard_reviews
                    WHERE user_id = ? AND date(reviewed_at) = ?
                    """,
                    (user_id, today),
                ).fetchone()
                setting = connection.execute(
                    "SELECT daily_goal FROM flashcard_settings WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
                dates = connection.execute(
                    """
                    SELECT DISTINCT date(reviewed_at) AS review_date
                    FROM flashcard_reviews WHERE user_id = ?
                    ORDER BY review_date DESC
                    """,
                    (user_id,),
                ).fetchall()
            streak = self._streak(
                [str(row["review_date"]) for row in dates],
                self._now().date(),
            )
            studied = int(daily["studied"])
            correct = int(daily["correct"])
            return FlashcardStats(
                total_cards=int(totals["total"]),
                mastered_cards=int(totals["mastered"]),
                due_cards=int(totals["due"]),
                studied_today=studied,
                daily_goal=int(setting["daily_goal"]) if setting else 10,
                correct_today=correct,
                accuracy_percent=round(correct * 100 / studied, 1) if studied else 0.0,
                streak_days=streak,
            )
        except sqlite3.Error as error:
            raise FlashcardStorageError("Nie udało się wczytać statystyk fiszek.") from error

    def set_daily_goal(self, user_id: int, daily_goal: int) -> None:
        if isinstance(daily_goal, bool) or not 1 <= daily_goal <= 500:
            raise FlashcardError("Cel dzienny musi wynosić od 1 do 500 fiszek.")
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO flashcard_settings (user_id, daily_goal)
                    VALUES (?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET daily_goal = excluded.daily_goal
                    """,
                    (user_id, daily_goal),
                )
        except sqlite3.Error as error:
            raise FlashcardStorageError("Nie udało się zapisać celu dziennego.") from error

    def export_json(
        self, user_id: int, *, deck_id: int | None = None
    ) -> str:
        cards = self.list_cards(user_id, deck_id=deck_id, sort_by="front")
        decks = self.get_decks(user_id)
        selected_decks = [deck for deck in decks if deck_id is None or deck.id == deck_id]
        payload = {
            "format": "MathMaster.flashcards",
            "version": 1,
            "decks": [
                {
                    "name": deck.name,
                    "cards": [
                        {
                            "front": card.front,
                            "back": card.back,
                            "division": card.division,
                            "topic_id": card.topic_id,
                            "favorite": card.favorite,
                        }
                        for card in cards
                        if card.deck_id == deck.id
                    ],
                }
                for deck in selected_decks
            ],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def import_json(self, user_id: int, content: str) -> int:
        if not isinstance(content, str) or len(content) > 5_000_000:
            raise FlashcardError("Plik JSON jest pusty lub przekracza limit 5 MB.")
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as error:
            raise FlashcardError("Plik nie zawiera poprawnego JSON.") from error
        if (
            not isinstance(payload, dict)
            or payload.get("format") != "MathMaster.flashcards"
            or payload.get("version") != 1
            or not isinstance(payload.get("decks"), list)
        ):
            raise FlashcardError("Nieobsługiwany format eksportu fiszek.")
        validated: list[tuple[str, list[dict[str, object]]]] = []
        total_cards = 0
        for deck in payload["decks"]:
            if not isinstance(deck, dict) or not isinstance(deck.get("cards"), list):
                raise FlashcardError("Niepoprawny zestaw w pliku JSON.")
            name = self._text(deck.get("name"), "Nazwa zestawu", 80)
            cards = []
            for item in deck["cards"]:
                if not isinstance(item, dict):
                    raise FlashcardError("Niepoprawna fiszka w pliku JSON.")
                front = self._text(item.get("front"), "Pytanie", _MAX_TEXT_LENGTH)
                back = self._text(item.get("back"), "Odpowiedź", _MAX_TEXT_LENGTH)
                division = item.get("division", "")
                topic_id = item.get("topic_id", "")
                favorite = item.get("favorite", False)
                if not isinstance(division, str) or not isinstance(topic_id, str):
                    raise FlashcardError("Niepoprawne przypisanie tematu fiszki.")
                if not isinstance(favorite, bool):
                    raise FlashcardError("Niepoprawna wartość ulubionej fiszki.")
                cards.append(
                    {
                        "front": front,
                        "back": back,
                        "division": division[:120],
                        "topic_id": topic_id[:120],
                        "favorite": favorite,
                    }
                )
                total_cards += 1
                if total_cards > _MAX_IMPORTED_CARDS:
                    raise FlashcardError("Można zaimportować najwyżej 500 fiszek.")
            validated.append((name, cards))
        try:
            with self.database.transaction() as connection:
                for name, cards in validated:
                    connection.execute(
                        """
                        INSERT INTO flashcard_decks (user_id, name)
                        VALUES (?, ?)
                        ON CONFLICT(user_id, name) DO NOTHING
                        """,
                        (user_id, name),
                    )
                    deck_row = connection.execute(
                        "SELECT id FROM flashcard_decks WHERE user_id = ? AND name = ?",
                        (user_id, name),
                    ).fetchone()
                    for card in cards:
                        connection.execute(
                            """
                            INSERT INTO flashcards (
                                user_id, deck_id, front, back, division, topic_id,
                                favorite, next_review_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                user_id, int(deck_row["id"]), card["front"],
                                card["back"], card["division"], card["topic_id"],
                                int(card["favorite"]), self._now_string(),
                                self._now_string(),
                            ),
                        )
            return total_cards
        except sqlite3.Error as error:
            raise FlashcardStorageError("Import fiszek nie powiódł się.") from error

    def _ensure_deck(
        self,
        connection: sqlite3.Connection,
        user_id: int,
        deck_id: int | None,
    ) -> int:
        if deck_id is not None:
            row = connection.execute(
                "SELECT id FROM flashcard_decks WHERE id = ? AND user_id = ?",
                (deck_id, user_id),
            ).fetchone()
            if row is None:
                raise FlashcardError("Nie znaleziono wybranego zestawu.")
            return int(row["id"])
        row = connection.execute(
            "SELECT id FROM flashcard_decks WHERE user_id = ? ORDER BY id LIMIT 1",
            (user_id,),
        ).fetchone()
        if row is not None:
            return int(row["id"])
        cursor = connection.execute(
            "INSERT INTO flashcard_decks (user_id, name) VALUES (?, ?)",
            (user_id, "Moje fiszki"),
        )
        return int(cursor.lastrowid)

    @staticmethod
    def _card_select() -> str:
        return """
            SELECT c.id, c.deck_id, COALESCE(d.name, 'Bez zestawu') AS deck_name,
                   c.front, c.back, c.division, c.topic_id, c.favorite,
                   c.repetitions, c.last_reviewed_at, c.next_review_at,
                   c.mastery, c.interval_days, c.ease_factor
            FROM flashcards AS c
            LEFT JOIN flashcard_decks AS d
              ON d.id = c.deck_id AND d.user_id = c.user_id
        """

    @staticmethod
    def _card_from_row(row: sqlite3.Row) -> Flashcard:
        return Flashcard(
            id=int(row["id"]),
            deck_id=int(row["deck_id"]) if row["deck_id"] is not None else None,
            deck_name=str(row["deck_name"]),
            front=str(row["front"]),
            back=str(row["back"]),
            division=str(row["division"]),
            topic_id=str(row["topic_id"]),
            favorite=bool(row["favorite"]),
            repetitions=int(row["repetitions"]),
            last_reviewed_at=row["last_reviewed_at"],
            next_review_at=row["next_review_at"],
            mastery=int(row["mastery"]),
            interval_days=float(row["interval_days"]),
            ease_factor=float(row["ease_factor"]),
        )

    @staticmethod
    def _text(value: object, label: str, limit: int) -> str:
        if not isinstance(value, str):
            raise FlashcardError(f"{label} musi być tekstem.")
        normalized = value.strip()
        if not normalized or len(normalized) > limit:
            raise FlashcardError(f"{label}: wymagane 1–{limit} znaków.")
        return normalized

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _now_string(self) -> str:
        return self._now().strftime(_TIMESTAMP_FORMAT)

    @staticmethod
    def _streak(review_dates: list[str], today: object) -> int:
        from datetime import date

        if not isinstance(today, date):
            return 0
        days = {date.fromisoformat(item) for item in review_dates}
        current = today if today in days else today - timedelta(days=1)
        streak = 0
        while current in days:
            streak += 1
            current -= timedelta(days=1)
        return streak

