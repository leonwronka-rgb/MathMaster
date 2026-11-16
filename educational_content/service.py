from __future__ import annotations

import hashlib
import json
import random
import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sympy as sp

from database.database import Database
from mathematics.engine import MathEngine
from mathematics.solutions import Exercise
from mathematics.topic_library import LIBRARY_TOPICS
from mathematics.topics import DIFFICULTY_LEVELS, Topic
from mathematics.validators import parse_answer

CONTENT_VERSION = 1
_LEVEL_NAMES = {
    1: "Szkoła podstawowa – klasy 1–3",
    2: "Szkoła podstawowa – klasy 4–6",
    3: "Szkoła podstawowa – klasy 7–8",
    4: "Szkoła ponadpodstawowa – poziom podstawowy",
    5: "Szkoła ponadpodstawowa – poziom rozszerzony",
}
EDUCATIONAL_LEVELS = tuple(_LEVEL_NAMES.values()) + (
    "Matematyka akademicka – poziom początkowy",
    "Matematyka akademicka – poziom zaawansowany",
)
_DIFFICULTY_NAMES = {
    1: "Bardzo łatwy",
    2: "Łatwy",
    3: "Średni",
    4: "Trudny",
    5: "Ekspercki",
}
_TOPIC_BY_ID = {topic.id: topic for topic in LIBRARY_TOPICS}


class ContentError(ValueError):
    """An educational content pack is invalid or conflicts with stored content."""


class ContentStorageError(RuntimeError):
    """Could not load or store the educational content catalog."""


@dataclass(frozen=True, slots=True)
class BankTask:
    id: str
    topic_id: str
    category: str
    subtopic: str
    educational_level: str
    difficulty: int
    prompt: str
    answer: str
    solution: str
    hint: str
    points: int
    source: str
    version: int
    generator_id: str
    parameters: dict[str, Any]
    exercise: Exercise


@dataclass(frozen=True, slots=True)
class ExamPack:
    id: str
    name: str
    description: str
    category: str
    educational_level: str
    time_limit_seconds: int
    task_ids: tuple[str, ...]
    max_points: int
    pass_percent: int
    source: str
    version: int


class EducationalContentService:
    """Validates versioned JSON packs and stores them outside user-owned tables."""

    def __init__(self, database: Database, data_root: Path) -> None:
        self.database = database
        self.data_root = data_root
        self.engine = MathEngine()

    def load_packs(self) -> tuple[dict[str, Any], ...]:
        root = self.data_root / "mathematics"
        packs: list[dict[str, Any]] = []
        if not root.is_dir():
            return ()
        for path in sorted(root.glob("**/content.json")):
            try:
                pack = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise ContentError(f"Nie można odczytać paczki treści {path.name}.") from error
            self.validate_pack(pack)
            packs.append(pack)
        return tuple(packs)

    def load_exam_packs(self) -> tuple[dict[str, Any], ...]:
        root = self.data_root / "exams"
        packs: list[dict[str, Any]] = []
        if not root.is_dir():
            return ()
        for path in sorted(root.glob("**/*.json")):
            try:
                pack = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise ContentError(f"Nie można odczytać paczki egzaminów {path.name}.") from error
            self.validate_exam_pack(pack)
            packs.append(pack)
        return tuple(packs)

    def initialize(self) -> tuple[int, int]:
        packs = self.load_packs()
        exams = self.load_exam_packs()
        tasks = [task for pack in packs for task in pack["tasks"]]
        self._validate_unique_ids(packs, exams)
        task_ids = {task["id"] for task in tasks}
        for pack in exams:
            for exam in pack["exams"]:
                missing = set(exam["task_ids"]) - task_ids
                if missing:
                    raise ContentError(
                        f"Egzamin {exam['id']} odwołuje się do brakujących zadań: "
                        + ", ".join(sorted(missing))
                    )
        try:
            with self.database.transaction() as connection:
                for pack in packs:
                    self._store_content_pack(connection, pack)
                for pack in exams:
                    self._store_exam_pack(connection, pack)
            return len(tasks), sum(len(pack["exams"]) for pack in exams)
        except sqlite3.Error as error:
            raise ContentStorageError("Nie udało się zainicjalizować biblioteki treści.") from error

    def import_pack(self, pack: dict[str, Any], *, replace_existing: bool = False) -> tuple[int, int]:
        self.validate_pack(pack)
        self._validate_unique_ids((pack,), ())
        tasks = pack["tasks"]
        existing_ids = self._existing_ids("bank_tasks", [task["id"] for task in tasks])
        if existing_ids and not replace_existing:
            raise ContentError(
                "Wykryto istniejące zadania; import anulowany bez nadpisywania: "
                + ", ".join(existing_ids[:10])
            )
        try:
            with self.database.transaction() as connection:
                self._store_content_pack(connection, pack)
            return len(pack["topics"]), len(tasks)
        except sqlite3.Error as error:
            raise ContentStorageError("Nie udało się zaimportować paczki treści.") from error

    def import_exam_pack(
        self, pack: dict[str, Any], *, replace_existing: bool = False
    ) -> int:
        self.validate_exam_pack(pack)
        exam_ids = [exam["id"] for exam in pack["exams"]]
        existing = self._existing_ids("content_exams", exam_ids)
        if existing and not replace_existing:
            raise ContentError(
                "Wykryto istniejące egzaminy; import anulowany bez nadpisywania: "
                + ", ".join(existing[:10])
            )
        all_tasks = {
            task.id for task in self.list_tasks()
        }
        for exam in pack["exams"]:
            missing = set(exam["task_ids"]) - all_tasks
            if missing:
                raise ContentError(
                    f"Brak zadań wymaganych przez {exam['id']}: "
                    + ", ".join(sorted(missing))
                )
        try:
            with self.database.transaction() as connection:
                self._store_exam_pack(connection, pack)
            return len(pack["exams"])
        except sqlite3.Error as error:
            raise ContentStorageError("Nie udało się zaimportować egzaminów.") from error

    def export_pack(self, destination: Path, *, division: str | None = None) -> Path:
        selected = [pack for pack in self.load_packs() if division is None or pack["division"] == division]
        if not selected:
            raise ContentError("Nie znaleziono materiałów do eksportu.")
        if len(selected) == 1:
            payload: dict[str, Any] = selected[0]
        else:
            payload = {"format_version": CONTENT_VERSION, "packs": selected}
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return destination

    def get_topic_material(self, topic_id: str) -> dict[str, Any]:
        try:
            with self.database.transaction() as connection:
                row = connection.execute(
                    "SELECT material_json FROM content_topics WHERE topic_id = ?",
                    (topic_id,),
                ).fetchone()
            if row is not None:
                material = json.loads(str(row["material_json"]))
                if isinstance(material, dict):
                    return material
        except (sqlite3.Error, json.JSONDecodeError, TypeError) as error:
            raise ContentStorageError("Nie udało się odczytać teorii tematu.") from error
        for pack in self.load_packs():
            for topic in pack["topics"]:
                if topic["id"] == topic_id:
                    return topic
        raise ContentError(f"Brak opracowanych materiałów dla tematu {topic_id!r}.")

    def generate_exercise(self, topic: Topic, difficulty: int) -> Exercise:
        if difficulty not in DIFFICULTY_LEVELS:
            raise ContentError("Poziom trudności musi należeć do zakresu 1–5.")
        matching_ids = [
            item.id for item in LIBRARY_TOPICS if item.exercise_topic == topic
        ]
        if matching_ids:
            placeholders = ",".join("?" for _ in matching_ids)
            try:
                with self.database.transaction() as connection:
                    rows = connection.execute(
                        f"""
                        SELECT task_id FROM bank_tasks
                        WHERE topic_id IN ({placeholders}) AND difficulty = ?
                        """,
                        [*matching_ids, difficulty],
                    ).fetchall()
                if rows:
                    selected = random.choice(rows)
                    return self.get_task(str(selected["task_id"])).exercise
            except sqlite3.Error as error:
                raise ContentStorageError("Nie udało się pobrać zadania z banku.") from error
        seed = random.SystemRandom().randrange(0, 2**32)
        generated = MathEngine(random.Random(seed)).generate(topic, difficulty)
        return replace(
            generated,
            generator_id="mathmaster.mathengine.v1",
            generator_parameters_json=json.dumps(
                {"seed": seed, "topic": topic.value, "difficulty": difficulty},
                sort_keys=True,
            ),
        )

    def list_tasks(
        self, *, topic_id: str | None = None, difficulty: int | None = None
    ) -> tuple[BankTask, ...]:
        if difficulty is not None and difficulty not in DIFFICULTY_LEVELS:
            raise ContentError("Poziom trudności musi należeć do zakresu 1–5.")
        query = """
            SELECT task_id, topic_id, category, subtopic, educational_level,
                   difficulty, prompt, answer, solution, hint, points, source,
                   version, generator_id, parameters_json
            FROM bank_tasks
            WHERE (? IS NULL OR topic_id = ?)
              AND (? IS NULL OR difficulty = ?)
            ORDER BY topic_id, difficulty, task_id
        """
        try:
            with self.database.transaction() as connection:
                rows = connection.execute(
                    query, (topic_id, topic_id, difficulty, difficulty)
                ).fetchall()
            return tuple(self._row_to_task(row) for row in rows)
        except sqlite3.Error as error:
            raise ContentStorageError("Nie udało się odczytać banku zadań.") from error

    def get_task(self, task_id: str) -> BankTask:
        tasks = self._existing_task_rows([task_id])
        if not tasks:
            raise ContentError(f"Nie znaleziono zadania {task_id!r}.")
        return tasks[0]

    def list_exams(self) -> tuple[ExamPack, ...]:
        try:
            with self.database.transaction() as connection:
                rows = connection.execute(
                    """
                    SELECT exam_id, name, description, category, educational_level,
                           time_limit_seconds, task_ids_json, max_points, pass_percent,
                           source, version
                    FROM content_exams ORDER BY exam_id
                    """
                ).fetchall()
            return tuple(
                ExamPack(
                    id=str(row["exam_id"]),
                    name=str(row["name"]),
                    description=str(row["description"]),
                    category=str(row["category"]),
                    educational_level=str(row["educational_level"]),
                    time_limit_seconds=int(row["time_limit_seconds"]),
                    task_ids=tuple(json.loads(str(row["task_ids_json"]))),
                    max_points=int(row["max_points"]),
                    pass_percent=int(row["pass_percent"]),
                    source=str(row["source"]),
                    version=int(row["version"]),
                )
                for row in rows
            )
        except (sqlite3.Error, json.JSONDecodeError, TypeError) as error:
            raise ContentStorageError("Nie udało się odczytać biblioteki egzaminów.") from error

    def start_exam(self, exam_id: str, user_id: int, exam_service: Any) -> Any:
        exam = next((item for item in self.list_exams() if item.id == exam_id), None)
        if exam is None:
            raise ContentError(f"Nie znaleziono egzaminu {exam_id!r}.")
        bank = {task.id: task for task in self.list_tasks()}
        selected = tuple(bank[task_id] for task_id in exam.task_ids)
        return exam_service.start_catalog_exam(user_id, exam, selected)

    def _store_content_pack(self, connection: sqlite3.Connection, pack: dict[str, Any]) -> None:
        digest = hashlib.sha256(
            json.dumps(pack, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        now = datetime.now(timezone.utc).isoformat()
        for topic in pack["topics"]:
            connection.execute(
                """
                INSERT INTO content_topics
                  (topic_id, title, division, subdivision, description,
                   educational_level, difficulty, material_json, source, version, digest)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(topic_id) DO UPDATE SET
                  title=excluded.title, division=excluded.division,
                  subdivision=excluded.subdivision, description=excluded.description,
                  educational_level=excluded.educational_level,
                  difficulty=excluded.difficulty, material_json=excluded.material_json,
                  source=excluded.source, version=excluded.version, digest=excluded.digest
                """,
                (
                    topic["id"], topic["name"], pack["division"], topic["subdivision"],
                    topic["description"],
                    json.dumps(topic["educational_level"], ensure_ascii=False),
                    topic["difficulty"],
                    json.dumps(topic, ensure_ascii=False), pack["source"],
                    pack["version"], digest,
                ),
            )
        for item in pack["tasks"]:
            connection.execute(
                """
                INSERT INTO bank_tasks
                  (task_id, topic_id, category, subtopic, educational_level, difficulty,
                   prompt, answer, solution, hint, points, source, version, generator_id,
                   parameters_json, pack_digest)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                  topic_id=excluded.topic_id, category=excluded.category,
                  subtopic=excluded.subtopic, educational_level=excluded.educational_level,
                  difficulty=excluded.difficulty, prompt=excluded.prompt,
                  answer=excluded.answer, solution=excluded.solution, hint=excluded.hint,
                  points=excluded.points, source=excluded.source, version=excluded.version,
                  generator_id=excluded.generator_id,
                  parameters_json=excluded.parameters_json, pack_digest=excluded.pack_digest
                """,
                (
                    item["id"], item["topic_id"], pack["division"], item["subtopic"],
                    item["educational_level"], item["difficulty"], item["prompt"],
                    item["answer"], item["solution"], item["hint"], item["points"],
                    item["source"], pack["version"], item["generator_id"],
                    json.dumps(item["parameters"], sort_keys=True), digest,
                ),
            )
        connection.execute(
            """
            INSERT INTO content_versions (pack_id, version, digest, imported_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(pack_id) DO UPDATE SET version=excluded.version,
              digest=excluded.digest, imported_at=excluded.imported_at
            """,
            (pack["id"], pack["version"], digest, now),
        )

    def _store_exam_pack(self, connection: sqlite3.Connection, pack: dict[str, Any]) -> None:
        digest = hashlib.sha256(
            json.dumps(pack, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        for exam in pack["exams"]:
            connection.execute(
                """
                INSERT INTO content_exams
                  (exam_id, name, description, category, educational_level, time_limit_seconds,
                   task_ids_json, max_points, pass_percent, source, version, pack_digest)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(exam_id) DO UPDATE SET name=excluded.name,
                  description=excluded.description, category=excluded.category,
                  educational_level=excluded.educational_level,
                  time_limit_seconds=excluded.time_limit_seconds,
                  task_ids_json=excluded.task_ids_json, max_points=excluded.max_points,
                  pass_percent=excluded.pass_percent,
                  source=excluded.source, version=excluded.version, pack_digest=excluded.pack_digest
                """,
                (
                    exam["id"], exam["name"], exam["description"], exam["category"],
                    exam["educational_level"], exam["time_limit_seconds"],
                    json.dumps(exam["task_ids"]), exam["max_points"], exam["pass_percent"],
                    pack["source"], pack["version"], digest,
                ),
            )
        connection.execute(
            """
            INSERT INTO content_versions (pack_id, version, digest, imported_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(pack_id) DO UPDATE SET version=excluded.version,
              digest=excluded.digest, imported_at=excluded.imported_at
            """,
            (pack["id"], pack["version"], digest, datetime.now(timezone.utc).isoformat()),
        )

    def _existing_ids(self, table: str, ids: list[str]) -> list[str]:
        if not ids:
            return []
        if table not in {"bank_tasks", "content_exams"}:
            raise ValueError("Unsupported catalog table")
        column = "task_id" if table == "bank_tasks" else "exam_id"
        placeholders = ",".join("?" for _ in ids)
        with self.database.transaction() as connection:
            rows = connection.execute(
                f'SELECT "{column}" FROM "{table}" WHERE "{column}" IN ({placeholders})',
                ids,
            ).fetchall()
        return [str(row[0]) for row in rows]

    def _existing_task_rows(self, ids: list[str]) -> tuple[BankTask, ...]:
        if not ids:
            return ()
        placeholders = ",".join("?" for _ in ids)
        try:
            with self.database.transaction() as connection:
                rows = connection.execute(
                    f"""
                    SELECT task_id, topic_id, category, subtopic, educational_level,
                           difficulty, prompt, answer, solution, hint, points, source,
                           version, generator_id, parameters_json
                    FROM bank_tasks WHERE task_id IN ({placeholders})
                    """,
                    ids,
                ).fetchall()
            return tuple(self._row_to_task(row) for row in rows)
        except sqlite3.Error as error:
            raise ContentStorageError("Nie udało się odczytać zadania.") from error

    def _row_to_task(self, row: sqlite3.Row) -> BankTask:
        topic_id = str(row["topic_id"])
        topic = _TOPIC_BY_ID[topic_id]
        parameters = json.loads(str(row["parameters_json"]))
        seed = int(parameters["seed"])
        exercise = MathEngine(random.Random(seed)).generate(topic.exercise_topic, int(row["difficulty"]))
        if (
            exercise.prompt != str(row["prompt"])
            or exercise.answer_text != str(row["answer"])
            or exercise.solution != str(row["solution"])
        ):
            raise ContentStorageError(f"Zadanie {row['task_id']} nie jest odtwarzalne.")
        exercise = replace(
            exercise,
            bank_task_id=str(row["task_id"]),
            generator_id=str(row["generator_id"]),
            generator_parameters_json=json.dumps(parameters, sort_keys=True),
        )
        return BankTask(
            id=str(row["task_id"]),
            topic_id=topic_id,
            category=str(row["category"]),
            subtopic=str(row["subtopic"]),
            educational_level=str(row["educational_level"]),
            difficulty=int(row["difficulty"]),
            prompt=str(row["prompt"]),
            answer=str(row["answer"]),
            solution=str(row["solution"]),
            hint=str(row["hint"]),
            points=int(row["points"]),
            source=str(row["source"]),
            version=int(row["version"]),
            generator_id=str(row["generator_id"]),
            parameters=parameters,
            exercise=exercise,
        )

    @classmethod
    def validate_pack(cls, pack: dict[str, Any]) -> None:
        if not isinstance(pack, dict):
            raise ContentError("Paczka treści musi być obiektem JSON.")
        if pack.get("format_version") != CONTENT_VERSION:
            raise ContentError("Nieobsługiwana wersja formatu paczki.")
        cls._required_string(pack, "id", 100)
        cls._required_string(pack, "division", 100)
        cls._required_string(pack, "source", 300)
        if type(pack.get("version")) is not int or pack["version"] < 1:
            raise ContentError("Wersja paczki musi być dodatnią liczbą całkowitą.")
        topics = pack.get("topics")
        tasks = pack.get("tasks")
        if not isinstance(topics, list) or not topics:
            raise ContentError("Paczka musi zawierać opracowane tematy.")
        if not isinstance(tasks, list) or not tasks:
            raise ContentError("Paczka musi zawierać zadania.")
        topic_ids: set[str] = set()
        for topic in topics:
            if not isinstance(topic, dict):
                raise ContentError("Nieprawidłowy rekord tematu.")
            for key, limit in (("id", 160), ("name", 160), ("subdivision", 160),
                               ("description", 2000), ("source", 300), ("created_at", 100)):
                cls._required_string(topic, key, limit)
            if topic["id"] not in _TOPIC_BY_ID:
                raise ContentError(f"Nieznany identyfikator tematu {topic['id']!r}.")
            if _TOPIC_BY_ID[topic["id"]].division != pack["division"]:
                raise ContentError(f"Temat {topic['id']} jest przypisany do innego działu.")
            if topic["id"] in topic_ids:
                raise ContentError(f"Powielony identyfikator tematu {topic['id']}.")
            if type(topic.get("version")) is not int or topic["version"] < 1:
                raise ContentError(f"Nieprawidłowa wersja tematu {topic['id']}.")
            topic_ids.add(topic["id"])
            if not isinstance(topic.get("subtopics"), list) or not topic["subtopics"]:
                raise ContentError(f"Temat {topic['id']} musi mieć podtematy.")
            cls._validate_topic_material(topic)
        task_ids: set[str] = set()
        prompts: set[tuple[str, int, str]] = set()
        for task in tasks:
            if not isinstance(task, dict):
                raise ContentError("Nieprawidłowy rekord zadania.")
            required = {
                "id": 160, "topic_id": 160, "subtopic": 160, "educational_level": 100,
                "prompt": 2000, "answer": 500, "solution": 4000, "hint": 1000,
                "source": 300, "generator_id": 100, "category": 100, "created_at": 100,
            }
            for key, limit in required.items():
                cls._required_string(task, key, limit)
            if task["id"] in task_ids:
                raise ContentError(f"Powielony identyfikator zadania {task['id']}.")
            if task["category"] != pack["division"]:
                raise ContentError(f"Zadanie {task['id']} jest przypisane do innego działu.")
            if type(task.get("version")) is not int or task["version"] < 1:
                raise ContentError(f"Nieprawidłowa wersja zadania {task['id']}.")
            if task["topic_id"] not in topic_ids:
                raise ContentError(f"Zadanie {task['id']} nie ma tematu w tej paczce.")
            difficulty = task.get("difficulty")
            if type(difficulty) is not int or difficulty not in DIFFICULTY_LEVELS:
                raise ContentError(f"Nieprawidłowy poziom trudności w {task['id']}.")
            if task["educational_level"] not in EDUCATIONAL_LEVELS:
                raise ContentError(f"Nieznany poziom edukacyjny w {task['id']}.")
            points = task.get("points")
            if type(points) is not int or not 1 <= points <= 100:
                raise ContentError(f"Nieprawidłowa punktacja w {task['id']}.")
            parameters = task.get("parameters")
            if not isinstance(parameters, dict) or type(parameters.get("seed")) is not int:
                raise ContentError(f"Brak parametrów odtwarzania zadania {task['id']}.")
            task_ids.add(task["id"])
            prompt_key = (task["topic_id"], difficulty, task["prompt"])
            if prompt_key in prompts:
                raise ContentError(f"Powielona treść zadania {task['id']}.")
            prompts.add(prompt_key)
            cls._validate_task(task)

    @classmethod
    def validate_exam_pack(cls, pack: dict[str, Any]) -> None:
        if not isinstance(pack, dict) or pack.get("format_version") != CONTENT_VERSION:
            raise ContentError("Nieobsługiwany format egzaminów.")
        cls._required_string(pack, "id", 100)
        cls._required_string(pack, "source", 300)
        if type(pack.get("version")) is not int or pack["version"] < 1:
            raise ContentError("Wersja paczki egzaminów jest nieprawidłowa.")
        exams = pack.get("exams")
        if not isinstance(exams, list) or not exams:
            raise ContentError("Paczka musi zawierać egzaminy.")
        seen: set[str] = set()
        for exam in exams:
            if not isinstance(exam, dict):
                raise ContentError("Nieprawidłowy egzamin.")
            for key, limit in (("id", 160), ("name", 200), ("description", 2000),
                               ("category", 100),
                               ("educational_level", 100)):
                cls._required_string(exam, key, limit)
            if exam["id"] in seen:
                raise ContentError(f"Powielony identyfikator egzaminu {exam['id']}.")
            seen.add(exam["id"])
            ids = exam.get("task_ids")
            if not isinstance(ids, list) or not 1 <= len(ids) <= 50:
                raise ContentError(f"Nieprawidłowy zestaw zadań egzaminu {exam['id']}.")
            if not all(isinstance(item, str) and item for item in ids) or len(set(ids)) != len(ids):
                raise ContentError(f"Identyfikatory zadań egzaminu {exam['id']} muszą być unikalne.")
            if type(exam.get("time_limit_seconds")) is not int or not 60 <= exam["time_limit_seconds"] <= 10800:
                raise ContentError(f"Nieprawidłowy limit czasu w {exam['id']}.")
            if type(exam.get("pass_percent")) is not int or not 1 <= exam["pass_percent"] <= 100:
                raise ContentError(f"Nieprawidłowy próg zaliczenia w {exam['id']}.")
            if exam["educational_level"] not in EDUCATIONAL_LEVELS:
                raise ContentError(f"Nieznany poziom edukacyjny w egzaminie {exam['id']}.")
            if type(exam.get("max_points")) is not int or exam["max_points"] < len(ids):
                raise ContentError(f"Nieprawidłowa punktacja egzaminu {exam['id']}.")

    @staticmethod
    def _required_string(record: dict[str, Any], key: str, limit: int) -> str:
        value = record.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ContentError(f"Pole {key!r} jest wymagane (maks. {limit} znaków).")
        return value.strip()

    @classmethod
    def _validate_topic_material(cls, topic: dict[str, Any]) -> None:
        level = topic.get("educational_level")
        if not isinstance(level, list) or not level or any(item not in EDUCATIONAL_LEVELS for item in level):
            raise ContentError(f"Nieprawidłowe poziomy edukacyjne tematu {topic['id']}.")
        if type(topic.get("difficulty")) is not int or topic["difficulty"] not in DIFFICULTY_LEVELS:
            raise ContentError(f"Nieprawidłowy poziom tematu {topic['id']}.")
        required_lists = ("definitions", "formulas", "symbols", "worked_examples",
                          "common_errors", "strategies", "summary")
        for key in required_lists:
            values = topic.get(key)
            if not isinstance(values, list) or not values:
                raise ContentError(f"Temat {topic['id']} musi mieć niepuste pole {key}.")
            if any(not isinstance(item, str) or not item.strip() for item in values):
                raise ContentError(f"Temat {topic['id']} zawiera pustą treść w {key}.")

    @classmethod
    def _validate_task(cls, task: dict[str, Any]) -> None:
        topic = _TOPIC_BY_ID[task["topic_id"]]
        seed = task["parameters"]["seed"]
        generated = MathEngine(random.Random(seed)).generate(
            topic.exercise_topic, task["difficulty"]
        )
        if generated.prompt != task["prompt"] or generated.answer_text != task["answer"]:
            raise ContentError(f"Zadanie {task['id']} nie zgadza się z odtworzonym generatorem.")
        if generated.solution != task["solution"]:
            raise ContentError(f"Rozwiązanie zadania {task['id']} nie zgadza się z generatorem.")
        try:
            parsed = parse_answer(task["answer"])
            last_line = next(
                line.split(":", 1)[1].strip()
                for line in reversed(task["solution"].splitlines())
                if line.strip().startswith("Odpowiedź:")
            )
            solution_answer = parse_answer(last_line)
        except (ValueError, StopIteration, TypeError) as error:
            raise ContentError(f"Nie można zweryfikować odpowiedzi w {task['id']}.") from error
        if not _mathematically_equal(parsed, solution_answer):
            raise ContentError(f"Odpowiedź i rozwiązanie są sprzeczne w {task['id']}.")

    @classmethod
    def _validate_unique_ids(
        cls, packs: tuple[dict[str, Any], ...] | list[dict[str, Any]],
        exams: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    ) -> None:
        pack_ids: set[str] = set()
        task_ids: set[str] = set()
        for pack in packs:
            if pack["id"] in pack_ids:
                raise ContentError(f"Powielony identyfikator paczki {pack['id']}.")
            pack_ids.add(pack["id"])
            for task in pack["tasks"]:
                if task["id"] in task_ids:
                    raise ContentError(f"Powielony identyfikator zadania {task['id']}.")
                task_ids.add(task["id"])
        exam_ids: set[str] = set()
        for pack in exams:
            if pack["id"] in pack_ids:
                raise ContentError(f"Powielony identyfikator paczki {pack['id']}.")
            pack_ids.add(pack["id"])
            for exam in pack["exams"]:
                if exam["id"] in exam_ids:
                    raise ContentError(f"Powielony identyfikator egzaminu {exam['id']}.")
                exam_ids.add(exam["id"])


def _mathematically_equal(first: sp.Basic, second: sp.Basic) -> bool:
    if first == second:
        return True
    try:
        result = sp.simplify(first - second)
        return result == 0
    except (TypeError, ValueError):
        return False
