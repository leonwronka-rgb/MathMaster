from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import random
import socket
import sqlite3
import ssl
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import sympy as sp

from database.database import Database
from gamification.service import GamificationService
from mathematics.engine import MathEngine
from mathematics.solutions import Exercise
from mathematics.topics import DIFFICULTY_LEVELS, TOPIC_CATEGORIES, Topic
from mathematics.validators import AnswerParseError, parse_answer

MAX_BUNDLE_BYTES = 5_000_000
MAX_TASKS_PER_BUNDLE = 500
MAX_TASK_NAME = 120
MAX_QUESTION = 4_000
MAX_ANSWER = 500
MAX_EXPLANATION = 4_000
MAX_HINTS = 5
MAX_CHOICES = 10
DOWNLOAD_TIMEOUT_SECONDS = 12
MAX_REDIRECTS = 3

_CATEGORY_ALIASES = {
    "arithmetic": "Arytmetyka",
    "fractions": "Ułamki",
    "fraction": "Ułamki",
    "percentages": "Procenty",
    "percent": "Procenty",
    "geometry": "Geometria",
    "powers": "Potęgi i pierwiastki",
    "functions": "Funkcje i wykresy",
    "trigonometry": "Trygonometria",
    "logarithms": "Logarytmy",
    "combinatorics": "Kombinatoryka i prawdopodobieństwo",
    "probability": "Kombinatoryka i prawdopodobieństwo",
    "statistics": "Statystyka i dane",
    "calculus": "Analiza matematyczna",
}
_DIFFICULTY_BY_NAME = {
    "easy": 1,
    "łatwy": 1,
    "łatwa": 1,
    "beginner": 1,
    "medium": 3,
    "średni": 3,
    "średnia": 3,
    "intermediate": 3,
    "hard": 4,
    "trudny": 4,
    "trudna": 4,
    "advanced": 4,
    "academic": 5,
    "akademicki": 5,
}
_DIFFICULTY_EXPORT = {1: "easy", 2: "easy", 3: "medium", 4: "hard", 5: "academic"}
_DEFAULT_XP = {1: 5, 2: 5, 3: 10, 4: 20, 5: 20}
_TOPIC_TITLES = {
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
    Topic.PERCENT_OF: "Procenty",
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
    Topic.SURFACE_AREA: "Pola powierzchni brył",
    Topic.PYTHAGOREAN: "Twierdzenie Pitagorasa",
    Topic.ANALYTIC_GEOMETRY: "Geometria analityczna",
    Topic.POWERS: "Potęgi",
    Topic.SQUARE_ROOTS: "Pierwiastki",
    Topic.FUNCTION_VALUE: "Wartości funkcji",
    Topic.GRAPH_POINT: "Wykresy funkcji",
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
_TOPIC_BY_TITLE = {
    title.casefold(): topic for topic, title in _TOPIC_TITLES.items()
}
_TOPIC_BY_VALUE = {topic.value.casefold(): topic for topic in Topic}
_CATEGORY_BY_TOPIC = {
    topic: category
    for category, topics in TOPIC_CATEGORIES.items()
    for topic in topics
}


class CustomTaskError(ValueError):
    """Invalid custom-task content or request."""


class CustomTaskStorageError(RuntimeError):
    """A custom-task database operation failed."""


class TaskDownloadError(RuntimeError):
    """A remote JSON task bundle could not be downloaded safely."""


@dataclass(frozen=True, slots=True)
class CustomTask:
    id: int
    set_id: int
    set_name: str
    external_id: str
    name: str
    question: str
    answer: str
    explanation: str
    category: str
    topic: Topic
    difficulty: int
    xp_points: int
    hints: tuple[str, ...]
    choices: tuple[str, ...]
    source_label: str


@dataclass(frozen=True, slots=True)
class CustomTaskSet:
    id: int
    name: str
    category: str
    source_kind: str
    source: str
    source_url: str
    downloaded_at: str | None
    task_count: int


@dataclass(frozen=True, slots=True)
class PreviewTask:
    index: int
    task: dict[str, Any] | None
    errors: tuple[str, ...]
    duplicate: bool

    @property
    def valid(self) -> bool:
        return self.task is not None and not self.errors and not self.duplicate


@dataclass(frozen=True, slots=True)
class TaskBundlePreview:
    name: str
    category: str
    content_hash: str
    records: tuple[PreviewTask, ...]
    source_kind: str
    source: str
    source_url: str
    downloaded_at: str | None
    duplicate_set: bool = False

    @property
    def valid_count(self) -> int:
        return sum(record.valid for record in self.records)

    @property
    def invalid_count(self) -> int:
        return sum(bool(record.errors) or record.task is None for record in self.records)

    @property
    def duplicate_count(self) -> int:
        return sum(record.duplicate for record in self.records)


@dataclass(frozen=True, slots=True)
class TaskImportResult:
    imported: int
    invalid: int
    duplicates: int
    set_name: str


@dataclass(frozen=True, slots=True)
class PracticeExercise:
    question: str
    answer: str
    explanation: str
    category: str
    topic: Topic
    difficulty: int
    xp_points: int
    hints: tuple[str, ...]
    choices: tuple[str, ...]
    source_label: str
    task_id: int | None
    set_name: str
    task_name: str
    builtin_exercise: Exercise | None = None


@dataclass(frozen=True, slots=True)
class TaskAnswerResult:
    correct: bool
    answer: str
    explanation: str
    xp_awarded: int
    total_xp: int
    leveled_up: bool
    source_label: str


@dataclass(frozen=True, slots=True)
class FetchedTaskBundle:
    content: str
    final_url: str
    source_name: str
    downloaded_at: str


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, address: str, timeout: int) -> None:
        super().__init__(host, 443, timeout=timeout, context=ssl.create_default_context())
        self._resolved_address = address

    def connect(self) -> None:
        raw_socket = socket.create_connection(
            (self._resolved_address, self.port), self.timeout, self.source_address
        )
        try:
            self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)
        except Exception:
            raw_socket.close()
            raise


class CustomTaskService:
    def __init__(
        self,
        database: Database,
        engine: MathEngine | None = None,
        *,
        rng: random.Random | None = None,
    ) -> None:
        self.database = database
        self.engine = engine or MathEngine(rng)
        self.rng = rng or random.Random()
        self.gamification = GamificationService(database)

    def list_sets(self, user_id: int) -> tuple[CustomTaskSet, ...]:
        try:
            with self.database.transaction() as connection:
                rows = connection.execute(
                    """
                    SELECT s.id, s.name, s.category, s.source_kind, s.source,
                           s.source_url, s.downloaded_at, COUNT(t.id) AS task_count
                    FROM custom_task_sets AS s
                    LEFT JOIN user_custom_tasks AS t ON t.set_id = s.id
                    WHERE s.user_id = ?
                    GROUP BY s.id
                    ORDER BY s.created_at DESC, s.id DESC
                    """,
                    (user_id,),
                ).fetchall()
            return tuple(self._set_from_row(row) for row in rows)
        except sqlite3.Error as error:
            raise CustomTaskStorageError("Nie udało się wczytać zestawów zadań.") from error

    def list_tasks(
        self,
        user_id: int,
        *,
        category: str | None = None,
        set_id: int | None = None,
        search: str = "",
    ) -> tuple[CustomTask, ...]:
        clauses = ["t.user_id = ?"]
        parameters: list[object] = [user_id]
        if category:
            category = self._category(category)
            clauses.append("t.category = ?")
            parameters.append(category)
        if set_id is not None:
            clauses.append("t.set_id = ?")
            parameters.append(set_id)
        if search.strip():
            like = f"%{search.strip()}%"
            clauses.append("(t.name LIKE ? OR t.question LIKE ? OR t.topic LIKE ?)")
            parameters.extend((like, like, like))
        try:
            with self.database.transaction() as connection:
                rows = connection.execute(
                    self._task_select() + " WHERE " + " AND ".join(clauses)
                    + " ORDER BY t.created_at DESC, t.id DESC",
                    parameters,
                ).fetchall()
            return tuple(self._task_from_row(row) for row in rows)
        except sqlite3.Error as error:
            raise CustomTaskStorageError("Nie udało się wczytać własnych zadań.") from error

    def create_set(self, user_id: int, name: str, category: str) -> CustomTaskSet:
        name = self._required_text(name, "Nazwa zestawu", 120)
        category = self._category(category)
        try:
            with self.database.transaction() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO custom_task_sets (user_id, name, category, source_kind)
                    VALUES (?, ?, ?, 'manual')
                    """,
                    (user_id, name, category),
                )
                set_id = int(cursor.lastrowid)
                row = connection.execute(
                    """
                    SELECT s.*, 0 AS task_count FROM custom_task_sets AS s
                    WHERE s.id = ?
                    """,
                    (set_id,),
                ).fetchone()
            return self._set_from_row(row)
        except sqlite3.IntegrityError as error:
            raise CustomTaskError("Zestaw o tej nazwie już istnieje.") from error
        except sqlite3.Error as error:
            raise CustomTaskStorageError("Nie udało się utworzyć zestawu.") from error

    def create_task(
        self,
        user_id: int,
        *,
        name: str,
        question: str,
        answer: str,
        explanation: str,
        category: str,
        topic: Topic | str,
        difficulty: int,
        xp_points: int,
        hints: tuple[str, ...] = (),
        choices: tuple[str, ...] = (),
        set_id: int | None = None,
    ) -> CustomTask:
        task = self._validated_task(
            {
                "id": f"manual-{hashlib.sha256((name + question).encode()).hexdigest()[:16]}",
                "name": name,
                "question": question,
                "answer": answer,
                "explanation": explanation,
                "category": category,
                "topic": str(topic),
                "difficulty": difficulty,
                "xp_points": xp_points,
                "hints": list(hints),
                "choices": list(choices),
            },
            category,
        )
        try:
            with self.database.transaction() as connection:
                selected_set = self._ensure_manual_set(
                    connection, user_id, task["category"], set_id
                )
                fingerprint = self._fingerprint(task)
                cursor = connection.execute(
                    """
                    INSERT INTO user_custom_tasks (
                        user_id, set_id, external_id, fingerprint, name, question,
                        answer, explanation, category, topic, difficulty, xp_points,
                        hints_json, choices_json, source_label
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id, selected_set, task["external_id"], fingerprint,
                        task["name"], task["question"], task["answer"],
                        task["explanation"], task["category"], task["topic"].value,
                        task["difficulty"], task["xp_points"],
                        json.dumps(task["hints"], ensure_ascii=False),
                        json.dumps(task["choices"], ensure_ascii=False),
                        "Utworzone ręcznie",
                    ),
                )
                task_id = int(cursor.lastrowid)
            return self.get_task(user_id, task_id)
        except sqlite3.IntegrityError as error:
            raise CustomTaskError("Takie zadanie już istnieje na Twoim koncie.") from error
        except sqlite3.Error as error:
            raise CustomTaskStorageError("Nie udało się zapisać zadania.") from error

    def update_task(
        self,
        user_id: int,
        task_id: int,
        **values: Any,
    ) -> CustomTask:
        task = self._validated_task(values, str(values.get("category", "")))
        set_id = values.get("set_id")
        try:
            with self.database.transaction() as connection:
                if set_id is not None:
                    self._verify_set(connection, user_id, int(set_id))
                row = connection.execute(
                    "SELECT set_id FROM user_custom_tasks WHERE id = ? AND user_id = ?",
                    (task_id, user_id),
                ).fetchone()
                if row is None:
                    raise CustomTaskError("Nie znaleziono zadania.")
                selected_set = int(set_id) if set_id is not None else int(row["set_id"])
                connection.execute(
                    """
                    UPDATE user_custom_tasks
                    SET set_id = ?, external_id = ?, fingerprint = ?, name = ?,
                        question = ?, answer = ?, explanation = ?, category = ?,
                        topic = ?, difficulty = ?, xp_points = ?, hints_json = ?,
                        choices_json = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (
                        selected_set, task["external_id"], self._fingerprint(task),
                        task["name"], task["question"], task["answer"],
                        task["explanation"], task["category"], task["topic"].value,
                        task["difficulty"], task["xp_points"],
                        json.dumps(task["hints"], ensure_ascii=False),
                        json.dumps(task["choices"], ensure_ascii=False),
                        task_id, user_id,
                    ),
                )
            return self.get_task(user_id, task_id)
        except CustomTaskError:
            raise
        except sqlite3.IntegrityError as error:
            raise CustomTaskError("Edycja utworzyłaby duplikat istniejącego zadania.") from error
        except sqlite3.Error as error:
            raise CustomTaskStorageError("Nie udało się zmienić zadania.") from error

    def delete_task(self, user_id: int, task_id: int) -> None:
        try:
            with self.database.transaction() as connection:
                cursor = connection.execute(
                    "DELETE FROM user_custom_tasks WHERE id = ? AND user_id = ?",
                    (task_id, user_id),
                )
                if not cursor.rowcount:
                    raise CustomTaskError("Nie znaleziono zadania.")
        except CustomTaskError:
            raise
        except sqlite3.Error as error:
            raise CustomTaskStorageError("Nie udało się usunąć zadania.") from error

    def get_task(self, user_id: int, task_id: int) -> CustomTask:
        try:
            with self.database.transaction() as connection:
                row = connection.execute(
                    self._task_select() + " WHERE t.id = ? AND t.user_id = ?",
                    (task_id, user_id),
                ).fetchone()
            if row is None:
                raise CustomTaskError("Nie znaleziono zadania.")
            return self._task_from_row(row)
        except CustomTaskError:
            raise
        except sqlite3.Error as error:
            raise CustomTaskStorageError("Nie udało się wczytać zadania.") from error

    def preview_import(
        self,
        content: str,
        user_id: int,
        *,
        source_kind: str = "file",
        source: str = "",
        source_url: str = "",
        downloaded_at: str | None = None,
    ) -> TaskBundlePreview:
        if source_kind not in {"file", "url"}:
            raise CustomTaskError("Nieobsługiwane źródło importu.")
        if not isinstance(content, str) or not content:
            raise CustomTaskError("Plik JSON jest pusty lub przekracza limit 5 MB.")
        try:
            if len(content.encode("utf-8")) > MAX_BUNDLE_BYTES:
                raise CustomTaskError("Plik JSON jest pusty lub przekracza limit 5 MB.")
        except UnicodeEncodeError as error:
            raise CustomTaskError("Plik zawiera niepoprawne znaki Unicode.") from error
        if content.startswith("\ufeff"):
            content = content[1:]
        try:
            payload = json.loads(content, object_pairs_hook=self._unique_object)
        except (json.JSONDecodeError, CustomTaskError, RecursionError) as error:
            raise CustomTaskError("Plik nie zawiera poprawnego JSON.") from error
        if (
            not isinstance(payload, dict)
            or type(payload.get("format_version")) is not int
            or payload.get("format_version") != 1
        ):
            raise CustomTaskError("Nieobsługiwana wersja formatu zestawu zadań.")
        name = self._required_text(payload.get("name"), "Nazwa zestawu", 120)
        category = self._category(payload.get("category"))
        raw_tasks = payload.get("tasks")
        if not isinstance(raw_tasks, list) or not raw_tasks:
            raise CustomTaskError("Zestaw musi zawierać co najmniej jedno zadanie.")
        if len(raw_tasks) > MAX_TASKS_PER_BUNDLE:
            raise CustomTaskError("Zestaw może zawierać najwyżej 500 zadań.")
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        try:
            with self.database.transaction() as connection:
                duplicate_set = connection.execute(
                    """
                    SELECT 1 FROM custom_task_sets
                    WHERE user_id = ? AND content_hash = ?
                    """,
                    (user_id, content_hash),
                ).fetchone() is not None
                records: list[PreviewTask] = []
                fingerprints: set[str] = set()
                external_ids: set[str] = set()
                for index, raw_task in enumerate(raw_tasks):
                    if not isinstance(raw_task, dict):
                        records.append(
                            PreviewTask(index, None, ("Rekord zadania musi być obiektem JSON.",), False)
                        )
                        continue
                    try:
                        task = self._validated_task(raw_task, category)
                        fingerprint = self._fingerprint(task)
                        duplicate = (
                            fingerprint in fingerprints
                            or task["external_id"] in external_ids
                            or connection.execute(
                                "SELECT 1 FROM user_custom_tasks "
                                "WHERE user_id = ? AND fingerprint = ?",
                                (user_id, fingerprint),
                            ).fetchone() is not None
                        )
                        fingerprints.add(fingerprint)
                        external_ids.add(task["external_id"])
                        records.append(PreviewTask(index, task, (), duplicate))
                    except CustomTaskError as error:
                        records.append(PreviewTask(index, None, (str(error),), False))
            return TaskBundlePreview(
                name,
                category,
                content_hash,
                tuple(records),
                source_kind,
                source.strip()[:500],
                source_url.strip()[:2_000],
                downloaded_at,
                duplicate_set,
            )
        except sqlite3.Error as error:
            raise CustomTaskStorageError("Nie udało się sprawdzić duplikatów.") from error

    def import_preview(
        self,
        user_id: int,
        preview: TaskBundlePreview,
        *,
        selected_indices: set[int] | None = None,
        allow_duplicate_set: bool = False,
    ) -> TaskImportResult:
        if preview.duplicate_set and not allow_duplicate_set:
            return TaskImportResult(0, preview.invalid_count, preview.duplicate_count, preview.name)
        if preview.source_kind not in {"file", "url"}:
            raise CustomTaskError("Nieobsługiwane źródło importu.")
        set_name = self._required_text(preview.name, "Nazwa zestawu", 120)
        category = self._category(preview.category)
        selected = selected_indices
        eligible = [
            record
            for record in preview.records
            if record.valid and (selected is None or record.index in selected)
        ]
        invalid = preview.invalid_count
        duplicates = preview.duplicate_count
        if not eligible:
            return TaskImportResult(0, invalid, duplicates, preview.name)
        source_label = (
            f"Pobrano z {urlsplit(preview.source_url).hostname or preview.source}"
            if preview.source_kind == "url"
            else f"Import JSON · {preview.source or 'plik lokalny'}"
        )
        try:
            with self.database.transaction() as connection:
                set_name = self._available_set_name(
                    connection, user_id, set_name
                )
                cursor = connection.execute(
                    """
                    INSERT INTO custom_task_sets (
                        user_id, name, category, source_kind, source, source_url,
                        downloaded_at, content_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id, set_name, category, preview.source_kind,
                        preview.source, preview.source_url, preview.downloaded_at,
                        preview.content_hash,
                    ),
                )
                set_id = int(cursor.lastrowid)
                imported = 0
                for record in eligible:
                    assert record.task is not None
                    task = self._validated_task(record.task, category)
                    try:
                        connection.execute(
                            """
                            INSERT INTO user_custom_tasks (
                                user_id, set_id, external_id, fingerprint, name,
                                question, answer, explanation, category, topic,
                                difficulty, xp_points, hints_json, choices_json,
                                source_label
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                user_id, set_id, task["external_id"],
                                self._fingerprint(task), task["name"],
                                task["question"], task["answer"], task["explanation"],
                                task["category"], task["topic"].value,
                                task["difficulty"], task["xp_points"],
                                json.dumps(task["hints"], ensure_ascii=False),
                                json.dumps(task["choices"], ensure_ascii=False),
                                source_label,
                            ),
                        )
                        imported += 1
                    except sqlite3.IntegrityError:
                        duplicates += 1
                if not imported:
                    raise CustomTaskError("Nie zaimportowano zadań; wszystkie są duplikatami.")
            return TaskImportResult(imported, invalid, duplicates, set_name)
        except CustomTaskError:
            raise
        except sqlite3.IntegrityError as error:
            raise CustomTaskError("Ten zestaw został już zaimportowany.") from error
        except sqlite3.Error as error:
            raise CustomTaskStorageError("Import zestawu nie powiódł się.") from error

    def fetch_json(self, url: str) -> FetchedTaskBundle:
        current_url = self._repository_raw_url(url.strip())
        if not current_url or len(current_url) > 2_048:
            raise TaskDownloadError("Adres HTTPS jest pusty lub przekracza 2048 znaków.")
        for redirect_count in range(MAX_REDIRECTS + 1):
            parts, addresses = self._resolve_public_https(current_url)
            path = parts.path or "/"
            if parts.query:
                path += f"?{parts.query}"
            hostname = parts.hostname or ""
            try:
                address = ipaddress.ip_address(hostname)
            except ValueError:
                address = None
            host_header = (
                f"[{hostname}]" if isinstance(address, ipaddress.IPv6Address)
                else hostname.encode("idna").decode("ascii")
            )
            connection = _PinnedHTTPSConnection(
                hostname, addresses[0], DOWNLOAD_TIMEOUT_SECONDS
            )
            try:
                connection.request(
                    "GET",
                    path,
                    headers={
                        "Accept": "application/json, text/json, text/plain, application/octet-stream",
                        "Accept-Encoding": "identity",
                        "User-Agent": "MathMaster/1.0",
                        "Host": host_header,
                    },
                )
                response = connection.getresponse()
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.getheader("Location")
                    response.read(1_024)
                    if not location or redirect_count >= MAX_REDIRECTS:
                        raise TaskDownloadError("Adres przekroczył limit przekierowań.")
                    current_url = urljoin(current_url, location)
                    continue
                if response.status != 200:
                    raise TaskDownloadError(
                        f"Serwer zwrócił odpowiedź HTTP {response.status}."
                    )
                content_type = response.getheader("Content-Type", "").split(";", 1)[0].strip().casefold()
                if content_type not in {
                    "application/json",
                    "text/json",
                    "text/plain",
                    "application/octet-stream",
                }:
                    raise TaskDownloadError(
                        f"Nieobsługiwany typ odpowiedzi: {content_type or 'brak'}."
                    )
                content_encoding = response.getheader("Content-Encoding", "identity").casefold()
                if content_encoding not in {"", "identity"}:
                    raise TaskDownloadError("Skompresowane odpowiedzi nie są obsługiwane.")
                length = response.getheader("Content-Length")
                if length:
                    try:
                        if int(length) < 0:
                            raise TaskDownloadError("Niepoprawny nagłówek Content-Length.")
                        if int(length) > MAX_BUNDLE_BYTES:
                            raise TaskDownloadError("Pobrany plik przekracza limit 5 MB.")
                    except ValueError as error:
                        raise TaskDownloadError("Niepoprawny nagłówek Content-Length.") from error
                body = response.read(MAX_BUNDLE_BYTES + 1)
                if len(body) > MAX_BUNDLE_BYTES:
                    raise TaskDownloadError("Pobrany plik przekracza limit 5 MB.")
                try:
                    text = body.decode("utf-8-sig")
                except UnicodeDecodeError as error:
                    raise TaskDownloadError("Plik nie jest poprawnym tekstem UTF-8.") from error
                final_parts = urlsplit(current_url)
                final_url = urlunsplit(
                    (final_parts.scheme, final_parts.netloc, final_parts.path, "", "")
                )
                host = urlsplit(final_url).hostname or ""
                return FetchedTaskBundle(
                    text,
                    final_url,
                    host,
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                )
            except TaskDownloadError:
                raise
            except (OSError, ssl.SSLError, http.client.HTTPException, TimeoutError) as error:
                raise TaskDownloadError(
                    "Nie udało się bezpiecznie pobrać zestawu JSON."
                ) from error
            finally:
                connection.close()
        raise TaskDownloadError("Adres przekroczył limit przekierowań.")

    def generate_exercises(
        self,
        user_id: int,
        *,
        category: str,
        topic: Topic | str,
        difficulty: int,
        count: int,
        custom_ratio: float = 0.5,
    ) -> tuple[PracticeExercise, ...]:
        category = self._category(category)
        topic_value = self._topic(topic, category)
        if difficulty not in DIFFICULTY_LEVELS:
            raise CustomTaskError("Poziom trudności musi należeć do zakresu 1–5.")
        if not 1 <= count <= 100:
            raise CustomTaskError("Liczba zadań musi należeć do zakresu 1–100.")
        if not 0 <= custom_ratio <= 1:
            raise CustomTaskError("Udział własnych zadań musi należeć do zakresu 0–1.")
        try:
            custom_tasks = self.list_tasks(
                user_id, category=category
            )
            matching = [
                task for task in custom_tasks
                if task.topic == topic_value and task.difficulty == difficulty
            ]
            self.rng.shuffle(matching)
            custom_count = min(len(matching), int(count * custom_ratio + 0.5))
            selected = matching[:custom_count]
            practice: list[PracticeExercise] = []
            for task in selected:
                practice.append(
                    PracticeExercise(
                        task.question,
                        task.answer,
                        task.explanation,
                        task.category,
                        task.topic,
                        task.difficulty,
                        task.xp_points,
                        task.hints,
                        task.choices,
                        task.source_label,
                        task.id,
                        task.set_name,
                        task.name,
                    )
                )
            for _ in range(count - len(practice)):
                exercise = self.engine.generate(topic_value, difficulty)
                practice.append(
                    PracticeExercise(
                        exercise.prompt,
                        exercise.answer_text,
                        exercise.solution,
                        category,
                        topic_value,
                        difficulty,
                        _DEFAULT_XP[difficulty],
                        (),
                        (),
                        "Generator MathMaster",
                        None,
                        "Zadania wbudowane",
                        "Zadanie generatora",
                        exercise,
                    )
                )
            self.rng.shuffle(practice)
            return tuple(practice)
        except (ValueError, CustomTaskError):
            raise

    def answer_exercise(
        self,
        user_id: int,
        exercise: PracticeExercise,
        submitted_answer: str,
        *,
        source_key: str,
    ) -> TaskAnswerResult:
        if not isinstance(submitted_answer, str) or not submitted_answer.strip():
            raise CustomTaskError("Wpisz odpowiedź przed jej sprawdzeniem.")
        if len(submitted_answer) > 500:
            raise CustomTaskError("Odpowiedź może mieć maksymalnie 500 znaków.")
        correct = self._is_correct(exercise, submitted_answer)
        try:
            with self.database.transaction() as connection:
                attempt_id: int | None = None
                if exercise.task_id is not None:
                    exists = connection.execute(
                        "SELECT 1 FROM user_custom_tasks WHERE id = ? AND user_id = ?",
                        (exercise.task_id, user_id),
                    ).fetchone()
                    if exists is None:
                        raise CustomTaskError(
                            "To zadanie zostało usunięte i nie można zapisać odpowiedzi."
                        )
                    attempt = connection.execute(
                        """
                        INSERT INTO custom_task_attempts (
                            user_id, task_id, task_name, category, topic, question,
                            submitted_answer, correct_answer, correct, source_label
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            user_id, exercise.task_id, exercise.task_name,
                            exercise.category, exercise.topic.value,
                            exercise.question, submitted_answer,
                            exercise.answer, int(correct), exercise.source_label,
                        ),
                    )
                    attempt_id = int(attempt.lastrowid)
                elapsed = 0
                connection.execute(
                    """
                    INSERT INTO exercise_history (
                        user_id, topic, correct, duration_seconds, difficulty,
                        question, submitted_answer, correct_answer, solution,
                        session_id, custom_task_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id, exercise.topic.value, int(correct), elapsed,
                        exercise.difficulty, exercise.question, submitted_answer,
                        exercise.answer, exercise.explanation,
                        f"custom-task:{source_key}", exercise.task_id,
                    ),
                )
                source_key_for_xp = (
                    "task:"
                    + hashlib.sha256(
                        (exercise.question + "\x00" + exercise.answer).encode("utf-8")
                    ).hexdigest()
                    if exercise.task_id is not None
                    else f"practice:{source_key}"
                )
                update = self.gamification.award_custom_exercise(
                    connection,
                    user_id=user_id,
                    source_key=source_key_for_xp,
                    xp_points=exercise.xp_points if correct else 0,
                )
                if attempt_id is not None:
                    connection.execute(
                        "UPDATE custom_task_attempts SET xp_awarded = ? WHERE id = ?",
                        (update.xp_awarded, attempt_id),
                    )
            return TaskAnswerResult(
                correct,
                exercise.answer,
                exercise.explanation,
                update.xp_awarded,
                update.total_xp,
                update.leveled_up,
                exercise.source_label,
            )
        except CustomTaskError:
            raise
        except sqlite3.Error as error:
            raise CustomTaskStorageError("Nie udało się zapisać odpowiedzi.") from error

    def export_json(
        self,
        user_id: int,
        *,
        category: str | None = None,
        set_id: int | None = None,
    ) -> str:
        tasks = self.list_tasks(user_id, category=category, set_id=set_id)
        if not tasks:
            raise CustomTaskError("Brak zadań do wyeksportowania.")
        if set_id is not None:
            selected_set = next(
                (item for item in self.list_sets(user_id) if item.id == set_id),
                None,
            )
            if selected_set is None:
                raise CustomTaskError("Nie znaleziono zestawu.")
            name, export_category = selected_set.name, selected_set.category
        elif category:
            export_category = self._category(category)
            name = export_category
        else:
            name, export_category = "Moje zadania", "Wszystkie kategorie"
        payload = {
            "format_version": 1,
            "name": name,
            "category": export_category,
            "tasks": [
                {
                    "id": task.external_id,
                    "name": task.name,
                    "question": task.question,
                    "answer": task.answer,
                    "difficulty": _DIFFICULTY_EXPORT[task.difficulty],
                    "explanation": task.explanation,
                    "category": task.category,
                    "topic": task.topic.value,
                    "xp_points": task.xp_points,
                    "hints": list(task.hints),
                    "choices": list(task.choices),
                    "source": task.source_label,
                }
                for task in tasks
            ],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _validated_task(
        self,
        raw: dict[str, Any],
        default_category: str,
    ) -> dict[str, Any]:
        errors: list[str] = []

        def text_field(key: str, label: str, limit: int, *, required: bool = True) -> str:
            value = raw.get(key)
            if not required and value is None:
                return ""
            try:
                return self._required_text(value, label, limit)
            except CustomTaskError as error:
                errors.append(str(error))
                return ""

        if "id" not in raw and "external_id" in raw:
            raw = {**raw, "id": raw["external_id"]}
        external_id = text_field("id", "Identyfikator", 120)
        name = text_field("name", "Nazwa zadania", MAX_TASK_NAME, required=False) or external_id
        question = text_field("question", "Treść zadania", MAX_QUESTION)
        answer = text_field("answer", "Poprawna odpowiedź", MAX_ANSWER)
        explanation = text_field("explanation", "Wyjaśnienie", MAX_EXPLANATION)
        category_value = raw.get("category", default_category)
        try:
            category = self._category(category_value)
        except CustomTaskError as error:
            category = default_category
            errors.append(str(error))
        if category == "Wszystkie kategorie":
            errors.append("Zadanie musi mieć konkretną kategorię.")
            category = next(iter(TOPIC_CATEGORIES))
        topic_value = raw.get("topic")
        if topic_value is None or topic_value == "":
            topic_value = self._infer_topic(question, category)
        try:
            topic = self._topic(topic_value, category)
        except CustomTaskError as error:
            topic = TOPIC_CATEGORIES[category][0]
            errors.append(str(error))
        difficulty_raw = raw.get("difficulty")
        try:
            difficulty = self._difficulty(difficulty_raw)
        except CustomTaskError as error:
            difficulty = 1
            errors.append(str(error))
        xp_raw = raw.get("xp_points", _DEFAULT_XP[difficulty])
        if isinstance(xp_raw, bool) or not isinstance(xp_raw, int) or not 0 <= xp_raw <= 1_000:
            xp_points = _DEFAULT_XP[difficulty]
            errors.append("Punkty XP muszą być liczbą całkowitą od 0 do 1000.")
        else:
            xp_points = xp_raw
        hints_raw = raw.get("hints", raw.get("hint", []))
        if isinstance(hints_raw, str):
            hints_raw = [hints_raw] if hints_raw.strip() else []
        if (
            not isinstance(hints_raw, (list, tuple))
            or len(hints_raw) > MAX_HINTS
            or any(not isinstance(item, str) or len(item) > 500 for item in hints_raw)
        ):
            hints: list[str] = []
            errors.append("Podpowiedzi muszą być listą maksymalnie 5 tekstów (do 500 znaków).")
        else:
            hints = [
                self._required_text(item, "Podpowiedź", 500)
                for item in hints_raw
                if item.strip()
            ]
        choices_raw = raw.get("choices", [])
        if (
            not isinstance(choices_raw, (list, tuple))
            or len(choices_raw) > MAX_CHOICES
            or any(not isinstance(item, str) or not item.strip() or len(item) > 500 for item in choices_raw)
        ):
            choices: list[str] = []
            errors.append("Odpowiedzi do wyboru muszą zawierać maksymalnie 10 tekstów.")
        else:
            choices = [
                self._required_text(item, "Odpowiedź do wyboru", 500)
                for item in choices_raw
            ]
        if choices and answer and not any(
            self._normalized_answer(choice) == self._normalized_answer(answer)
            for choice in choices
        ):
            errors.append("Poprawna odpowiedź musi występować wśród odpowiedzi do wyboru.")
        if errors:
            raise CustomTaskError(" ".join(dict.fromkeys(errors)))
        return {
            "external_id": external_id,
            "name": name,
            "question": question,
            "answer": answer,
            "explanation": explanation,
            "category": category,
            "topic": topic,
            "difficulty": difficulty,
            "xp_points": xp_points,
            "hints": tuple(hints),
            "choices": tuple(choices),
        }

    def _category(self, value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise CustomTaskError("Kategoria jest wymagana.")
        normalized = value.strip()
        aliases = {key.casefold(): category for key, category in _CATEGORY_ALIASES.items()}
        normalized = aliases.get(normalized.casefold(), normalized)
        if normalized == "Wszystkie kategorie":
            return normalized
        if normalized not in TOPIC_CATEGORIES:
            raise CustomTaskError(f"Nieznana kategoria: {value}.")
        return normalized

    @staticmethod
    def _topic(value: object, category: str) -> Topic:
        if category not in TOPIC_CATEGORIES:
            raise CustomTaskError("Dla tematu należy wskazać konkretną kategorię.")
        if value is None or value == "":
            return TOPIC_CATEGORIES[category][0]
        if isinstance(value, Topic):
            topic = value
        elif isinstance(value, str):
            topic = _TOPIC_BY_VALUE.get(value.strip().casefold())
            if topic is None:
                topic = _TOPIC_BY_TITLE.get(value.strip().casefold())
            if topic is None:
                raise CustomTaskError(f"Nieznany temat: {value}.")
        else:
            raise CustomTaskError("Temat musi być tekstem.")
        if topic not in TOPIC_CATEGORIES[category]:
            raise CustomTaskError("Wybrany temat nie należy do wskazanej kategorii.")
        return topic

    @staticmethod
    def _difficulty(value: object) -> int:
        if isinstance(value, bool):
            raise CustomTaskError("Poziom trudności jest niepoprawny.")
        if isinstance(value, int) and value in DIFFICULTY_LEVELS:
            return value
        if isinstance(value, str):
            normalized = value.strip().casefold()
            if normalized.isdigit() and int(normalized) in DIFFICULTY_LEVELS:
                return int(normalized)
            if normalized in _DIFFICULTY_BY_NAME:
                return _DIFFICULTY_BY_NAME[normalized]
        raise CustomTaskError("Poziom trudności: easy, medium, hard, academic albo 1–5.")

    def _fingerprint(self, task: dict[str, Any]) -> str:
        parts = (
            task["category"],
            task["topic"].value,
            task["question"],
            task["answer"],
        )
        normalized = "\x1f".join(
            unicodedata.normalize("NFKC", str(part)).casefold().strip()
            for part in parts
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _infer_topic(question: str, category: str) -> Topic | None:
        normalized = question.casefold()
        if category == "Ułamki":
            if "+" in question or any(word in normalized for word in ("dodaj", "suma")):
                return Topic.FRACTION_ADDITION
            if "−" in question or "odejm" in normalized:
                return Topic.FRACTION_SUBTRACTION
            if "×" in question or "mnoż" in normalized:
                return Topic.FRACTION_MULTIPLICATION
            if "÷" in question or "dziel" in normalized:
                return Topic.FRACTION_DIVISION
            if any(word in normalized for word in ("skróć", "uprość")):
                return Topic.FRACTION_SIMPLIFY
        if category == "Arytmetyka":
            if "+" in question or "dodaj" in normalized:
                return Topic.ADDITION
            if "−" in question or "odejm" in normalized:
                return Topic.SUBTRACTION
            if "×" in question or "mnoż" in normalized:
                return Topic.MULTIPLICATION
            if "÷" in question or "podziel" in normalized:
                return Topic.DIVISION
        return None

    @staticmethod
    def _normalized_answer(value: str) -> str:
        return unicodedata.normalize("NFKC", value).strip().casefold()

    def _ensure_manual_set(
        self,
        connection: sqlite3.Connection,
        user_id: int,
        category: str,
        set_id: int | None,
    ) -> int:
        if set_id is not None:
            self._verify_set(connection, user_id, set_id)
            return set_id
        row = connection.execute(
            """
            SELECT id FROM custom_task_sets
            WHERE user_id = ? AND name = 'Moje zadania' AND source_kind = 'manual'
            """,
            (user_id,),
        ).fetchone()
        if row:
            return int(row["id"])
        cursor = connection.execute(
            """
            INSERT INTO custom_task_sets (user_id, name, category, source_kind)
            VALUES (?, 'Moje zadania', ?, 'manual')
            """,
            (user_id, category),
        )
        return int(cursor.lastrowid)

    @staticmethod
    def _verify_set(
        connection: sqlite3.Connection, user_id: int, set_id: int
    ) -> None:
        if connection.execute(
            "SELECT 1 FROM custom_task_sets WHERE id = ? AND user_id = ?",
            (set_id, user_id),
        ).fetchone() is None:
            raise CustomTaskError("Nie znaleziono zestawu.")

    @staticmethod
    def _available_set_name(
        connection: sqlite3.Connection, user_id: int, name: str
    ) -> str:
        base = name[:100]
        candidate = base
        suffix = 2
        while connection.execute(
            "SELECT 1 FROM custom_task_sets WHERE user_id = ? AND name = ?",
            (user_id, candidate),
        ).fetchone():
            candidate = f"{base[:110]} ({suffix})"
            suffix += 1
        return candidate

    @staticmethod
    def _required_text(value: object, label: str, limit: int) -> str:
        if not isinstance(value, str):
            raise CustomTaskError(f"{label} musi być tekstem.")
        value = value.strip()
        if not value or len(value) > limit:
            raise CustomTaskError(f"{label} musi mieć od 1 do {limit} znaków.")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as error:
            raise CustomTaskError(f"{label} zawiera niepoprawne znaki Unicode.") from error
        if "\x00" in value:
            raise CustomTaskError(f"{label} zawiera niedozwolony znak.")
        return value

    @staticmethod
    def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise CustomTaskError(f"Powtórzone pole JSON: {key}.")
            result[key] = value
        return result

    @staticmethod
    def _repository_raw_url(url: str) -> str:
        try:
            parts = urlsplit(url)
        except ValueError as error:
            raise TaskDownloadError("Adres HTTPS jest niepoprawny.") from error
        path_parts = parts.path.strip("/").split("/")
        if (
            (parts.hostname or "").casefold() == "github.com"
            and len(path_parts) >= 5
            and path_parts[2] == "blob"
        ):
            raw_path = "/".join((path_parts[0], path_parts[1], *path_parts[3:]))
            return urlunsplit(
                (
                    "https",
                    "raw.githubusercontent.com",
                    f"/{raw_path}",
                    parts.query,
                    parts.fragment,
                )
            )
        return url

    @staticmethod
    def _set_from_row(row: sqlite3.Row) -> CustomTaskSet:
        return CustomTaskSet(
            int(row["id"]),
            str(row["name"]),
            str(row["category"]),
            str(row["source_kind"]),
            str(row["source"]),
            str(row["source_url"]),
            row["downloaded_at"],
            int(row["task_count"]),
        )

    @staticmethod
    def _task_select() -> str:
        return """
            SELECT t.*, s.name AS set_name
            FROM user_custom_tasks AS t
            JOIN custom_task_sets AS s ON s.id = t.set_id AND s.user_id = t.user_id
        """

    @staticmethod
    def _task_from_row(row: sqlite3.Row) -> CustomTask:
        return CustomTask(
            int(row["id"]),
            int(row["set_id"]),
            str(row["set_name"]),
            str(row["external_id"]),
            str(row["name"]),
            str(row["question"]),
            str(row["answer"]),
            str(row["explanation"]),
            str(row["category"]),
            Topic(str(row["topic"])),
            int(row["difficulty"]),
            int(row["xp_points"]),
            tuple(json.loads(str(row["hints_json"]))),
            tuple(json.loads(str(row["choices_json"]))),
            str(row["source_label"]),
        )

    def _is_correct(self, exercise: PracticeExercise, submitted: str) -> bool:
        if exercise.builtin_exercise is not None:
            return self.engine.check_answer(exercise.builtin_exercise, submitted)
        try:
            expected = parse_answer(exercise.answer)
            candidate = parse_answer(submitted)
            return bool(sp.simplify(candidate - expected) == 0)
        except (AnswerParseError, TypeError, ValueError):
            return self._normalized_answer(submitted) == self._normalized_answer(
                exercise.answer
            )

    @staticmethod
    def _resolve_public_https(url: str) -> tuple[Any, tuple[str, ...]]:
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError as error:
            raise TaskDownloadError("Adres HTTPS jest niepoprawny.") from error
        hostname = parts.hostname
        is_literal_ip = False
        try:
            ipaddress.ip_address(hostname or "")
            is_literal_ip = True
        except ValueError:
            pass
        if (
            parts.scheme.casefold() != "https"
            or not hostname
            or (not is_literal_ip and ("." not in hostname or hostname.casefold() == "localhost"))
            or parts.username is not None
            or parts.password is not None
            or parts.fragment
            or port not in (None, 443)
            or hostname.casefold().endswith((".localhost", ".local", ".internal"))
        ):
            raise TaskDownloadError(
                "Dozwolone są wyłącznie publiczne adresy HTTPS na porcie 443."
            )
        try:
            literal = ipaddress.ip_address(hostname)
            addresses = (str(literal),)
        except ValueError:
            try:
                info = socket.getaddrinfo(
                    hostname, 443, type=socket.SOCK_STREAM
                )
            except OSError as error:
                raise TaskDownloadError("Nie udało się rozpoznać hosta adresu HTTPS.") from error
            addresses = tuple(dict.fromkeys(str(item[4][0]) for item in info))
        if not addresses:
            raise TaskDownloadError("Adres hosta nie ma publicznych adresów IP.")
        for address in addresses:
            try:
                parsed_address = ipaddress.ip_address(address.split("%", 1)[0])
            except ValueError as error:
                raise TaskDownloadError("Host zwrócił niepoprawny adres IP.") from error
            if not parsed_address.is_global:
                raise TaskDownloadError(
                    "Pobieranie z adresów lokalnych i prywatnych jest zablokowane."
                )
        return parts, addresses
