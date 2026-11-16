from __future__ import annotations

import hashlib
import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path

from mathematics.engine import MathEngine
from mathematics.topic_library import LIBRARY_TOPICS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "data"
THEORY_PATH = DATA_ROOT / "mathematics" / "theory.json"
_DIFFICULTY_LEVEL = {
    1: "Szkoła podstawowa – klasy 1–3",
    2: "Szkoła podstawowa – klasy 4–6",
    3: "Szkoła podstawowa – klasy 7–8",
    4: "Szkoła ponadpodstawowa – poziom podstawowy",
    5: "Szkoła ponadpodstawowa – poziom rozszerzony",
}
_TOPIC_LEVEL = {
    "fraction_simplify": {
        1: _DIFFICULTY_LEVEL[2], 2: _DIFFICULTY_LEVEL[2],
        3: _DIFFICULTY_LEVEL[3], 4: _DIFFICULTY_LEVEL[4],
        5: _DIFFICULTY_LEVEL[5],
    },
    "fraction_addition": {
        1: _DIFFICULTY_LEVEL[2], 2: _DIFFICULTY_LEVEL[2],
        3: _DIFFICULTY_LEVEL[3], 4: _DIFFICULTY_LEVEL[4],
        5: _DIFFICULTY_LEVEL[5],
    },
    "percent_of": {
        1: _DIFFICULTY_LEVEL[3], 2: _DIFFICULTY_LEVEL[3],
        3: _DIFFICULTY_LEVEL[3], 4: _DIFFICULTY_LEVEL[4],
        5: _DIFFICULTY_LEVEL[5],
    },
    "linear_equation": {
        1: _DIFFICULTY_LEVEL[3], 2: _DIFFICULTY_LEVEL[3],
        3: _DIFFICULTY_LEVEL[4], 4: _DIFFICULTY_LEVEL[4],
        5: _DIFFICULTY_LEVEL[5],
    },
    "area": {
        1: _DIFFICULTY_LEVEL[2], 2: _DIFFICULTY_LEVEL[2],
        3: _DIFFICULTY_LEVEL[3], 4: _DIFFICULTY_LEVEL[4],
        5: _DIFFICULTY_LEVEL[5],
    },
    "function_value": {
        1: _DIFFICULTY_LEVEL[4], 2: _DIFFICULTY_LEVEL[4],
        3: _DIFFICULTY_LEVEL[4], 4: _DIFFICULTY_LEVEL[5],
        5: _DIFFICULTY_LEVEL[5],
    },
}
_HINTS = {
    "addition": "Zapisz działania w kolumnach i oszacuj wynik przed obliczeniem.",
    "order_of_operations": "Najpierw uprość nawiasy, a potem wykonuj działania według ich priorytetu.",
    "fraction_simplify": "Poszukaj wspólnego dzielnika licznika i mianownika.",
    "fraction_addition": "Sprowadź ułamki do wspólnego mianownika, zanim dodasz liczniki.",
    "percent_of": "Zamień procent na ułamek o mianowniku 100 i pomnóż przez całość.",
    "linear_equation": "Wykonuj to samo działanie po obu stronach równania.",
    "area": "Zaznacz na szkicu podstawę i prostopadłą do niej wysokość.",
    "function_value": "Podstaw argument do wzoru w nawiasie i oblicz wynik.",
}
_TARGETS = (
    ("Arytmetyka", "Liczby i działania", "addition", "arytmetyka"),
    ("Arytmetyka", "Systemy liczbowe", "order_of_operations", "arytmetyka"),
    ("Ułamki i liczby dziesiętne", "Ułamki zwykłe", "fraction_simplify", "ulamki"),
    ("Ułamki i liczby dziesiętne", "Działania na ułamkach", "fraction_addition", "ulamki"),
    ("Procenty i proporcje", "Procenty", "percent_of", "procenty"),
    ("Algebra", "Równania i nierówności", "linear_equation", "algebra"),
    ("Geometria płaska", "Pola i obwody", "area", "geometria_plaska"),
    ("Funkcje", "Podstawy funkcji", "function_value", "funkcje"),
)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def build() -> tuple[int, int]:
    theory_source = json.loads(THEORY_PATH.read_text(encoding="utf-8"))
    theory_by_selector = {tuple(topic["selector"]): topic for topic in theory_source["topics"]}
    library_by_selector = {
        (topic.division, topic.subdivision, topic.exercise_topic.value): topic
        for topic in LIBRARY_TOPICS
    }
    created = datetime.now(timezone.utc).isoformat()
    all_tasks: list[dict[str, object]] = []
    packs_by_folder: dict[str, dict[str, object]] = {}
    topic_ids: dict[str, str] = {}

    for division, subdivision, topic_type, folder in _TARGETS:
        selector = (division, subdivision, topic_type)
        theory = theory_by_selector[selector]
        library_topic = library_by_selector[selector]
        topic_id = library_topic.id
        topic_ids[topic_type] = topic_id
        tasks: list[dict[str, object]] = []
        for difficulty in range(1, 6):
            requested_count = 50
            seen_prompts: set[str] = set()
            accepted = 0
            seed_base = int.from_bytes(
                hashlib.sha256(f"{topic_id}:{difficulty}".encode()).digest()[:4],
                "big",
            )
            attempts = 0
            while accepted < requested_count and attempts < 5000:
                seed = seed_base + attempts
                attempts += 1
                exercise = MathEngine(random.Random(seed)).generate(
                    library_topic.exercise_topic, difficulty
                )
                if exercise.prompt in seen_prompts:
                    continue
                seen_prompts.add(exercise.prompt)
                accepted += 1
                item_id = f"task.{_slug(topic_id)}.d{difficulty}.n{accepted:02d}"
                tasks.append({
                    "id": item_id,
                    "version": 1,
                    "created_at": created,
                    "topic_id": topic_id,
                    "category": division,
                    "subtopic": subdivision,
                    "educational_level": _TOPIC_LEVEL.get(topic_type, _DIFFICULTY_LEVEL)[difficulty],
                    "difficulty": difficulty,
                    "question_type": "open",
                    "task_type": "generated",
                    "prompt": exercise.prompt,
                    "answer": exercise.answer_text,
                    "solution": exercise.solution,
                    "hint": _HINTS[topic_type],
                    "points": difficulty,
                    "source": "MathMaster: SymPy MathEngine",
                    "generator_id": "mathmaster.mathengine.v1",
                    "parameters": {
                        "seed": seed,
                        "topic": library_topic.exercise_topic.value,
                        "difficulty": difficulty,
                    },
                })
            if accepted != requested_count:
                raise RuntimeError(
                    f"Generator produced only {accepted}/{requested_count} unique "
                    f"prompts for {topic_id}, difficulty {difficulty}."
                )
        pack = packs_by_folder.setdefault(folder, {
            "format_version": 1,
            "id": f"mathmaster.starter.{folder}.v1",
            "version": 1,
            "created_at": created,
            "division": division,
            "source": "Opracowanie MathMaster; zadania utworzone i odtwarzalne przez MathEngine/SymPy.",
            "topics": [],
            "tasks": [],
        })
        pack["topics"].append({
            key: value for key, value in theory.items()
            if key != "selector"
        } | {
            "id": topic_id,
            "source": "Opracowanie MathMaster",
            "version": 1,
            "created_at": created,
        })
        pack["tasks"].extend(tasks)
        all_tasks.extend(tasks)
    for folder, pack in packs_by_folder.items():
        output = DATA_ROOT / "mathematics" / folder / "content.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")

    exams = []
    exam_specs = (
        ("starter.arithmetic.1", "Arytmetyka — sprawdzian podstawowy",
         "Sprawdza podstawowe działania i kolejność wykonywania działań.",
         "Arytmetyka", "Szkoła podstawowa – klasy 4–6", 900,
         [task for task in all_tasks if task["difficulty"] == 1 and
          task["topic_id"] in {topic_ids["addition"], topic_ids["order_of_operations"]}][:10]),
        ("starter.fractions.1", "Ułamki — sprawdzian działowy",
         "Skracanie ułamków i dodawanie ułamków o różnych mianownikach.",
         "Ułamki", "Szkoła podstawowa – klasy 4–6", 1200,
         [task for task in all_tasks if task["difficulty"] == 1 and
          task["topic_id"] in {topic_ids["fraction_simplify"], topic_ids["fraction_addition"]}][:10]),
        ("starter.algebra.1", "Równania liniowe — trening",
         "Trening przekształcania i sprawdzania równań liniowych.",
         "Algebra", "Szkoła podstawowa – klasy 7–8", 1500,
         [task for task in all_tasks if task["difficulty"] == 3 and
          task["topic_id"] == topic_ids["linear_equation"]][:10]),
    )
    for exam_id, name, description, category, level, seconds, selected in exam_specs:
        if len(selected) != 10:
            raise RuntimeError(f"Exam {exam_id} does not have ten tasks.")
        exams.append({
            "id": exam_id, "name": name, "description": description,
            "category": category, "educational_level": level,
            "time_limit_seconds": seconds,
            "task_ids": [task["id"] for task in selected],
            "max_points": sum(int(task["points"]) for task in selected),
            "pass_percent": 50,
        })
    exam_pack = {
        "format_version": 1,
        "id": "mathmaster.starter.exams.v1",
        "version": 1,
        "created_at": created,
        "source": "Opracowanie MathMaster; egzaminy składają się ze zweryfikowanych zadań z paczek startowych.",
        "exams": exams,
    }
    exam_path = DATA_ROOT / "exams" / "primary_school" / "starter.json"
    exam_path.parent.mkdir(parents=True, exist_ok=True)
    exam_path.write_text(json.dumps(exam_pack, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(theory_source["topics"]), len(all_tasks)


if __name__ == "__main__":
    topic_count, task_count = build()
    print(f"Generated {topic_count} topics and {task_count} verified reproducible tasks.")
