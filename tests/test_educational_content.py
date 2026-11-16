from __future__ import annotations

import json
import copy
import tempfile
import unittest
from pathlib import Path

from accounts.auth import AuthService
from database.database import Database
from educational_content.service import (
    ContentError,
    EducationalContentService,
)
from exams.exam_service import ExamService


_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"


class EducationalContentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "content.sqlite3")
        self.database.initialize()
        self.user = AuthService(self.database).register(
            "content-user", "Content User", "secure-pass-123"
        )
        self.content = EducationalContentService(self.database, _DATA_ROOT)
        self.addCleanup(self.temp_dir.cleanup)
        self.addCleanup(self.database.close)

    def test_startup_seeds_versioned_content_once_and_keeps_user_data_separate(self) -> None:
        task_count, exam_count = self.content.initialize()

        self.assertEqual(task_count, 2000)
        self.assertEqual(exam_count, 3)
        self.assertEqual(len(self.content.list_exams()), 3)
        self.assertGreaterEqual(
            len(self.content.list_tasks(topic_id="curriculum.arytmetyka.liczby_i_dziaania.addition", difficulty=1)),
            50,
        )
        self.assertEqual(
            len(self.content.list_tasks(topic_id="curriculum.arytmetyka.liczby_i_dziaania.addition")),
            250,
        )
        self.assertEqual(
            self.content.initialize(),
            (2000, 3),
        )
        with self.database.transaction() as connection:
            user_count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            task_rows = connection.execute("SELECT COUNT(*) FROM bank_tasks").fetchone()[0]
            versions = connection.execute("SELECT COUNT(*) FROM content_versions").fetchone()[0]
        self.assertEqual(user_count, 1)
        self.assertEqual(task_rows, 2000)
        self.assertEqual(versions, 7)

    def test_catalog_tasks_are_reproducible_and_math_solutions_agree(self) -> None:
        self.content.initialize()
        task = self.content.list_tasks(
            topic_id="curriculum.algebra.rownania_i_nierownosci.linear_equation",
            difficulty=3,
        )[0]
        self.assertEqual(task.generator_id, "mathmaster.mathengine.v1")
        self.assertEqual(task.exercise.answer_text, task.answer)
        self.assertIn("Odpowiedź:", task.solution)
        self.assertEqual(task.exercise.bank_task_id, task.id)

        replay = self.content.get_task(task.id)
        self.assertEqual(replay.prompt, task.prompt)
        self.assertEqual(replay.solution, task.solution)

    def test_catalog_exam_uses_real_bank_tasks_and_existing_exam_flow(self) -> None:
        self.content.initialize()
        exam_service = ExamService(self.database)
        attempt = self.content.start_exam(
            "starter.algebra.1", self.user.id, exam_service
        )

        self.assertEqual(attempt.question_count, 10)
        for index, question in enumerate(attempt.questions):
            attempt.set_answer(index, question.exercise.answer_text)
        completion = exam_service.complete_exam(self.user.id, attempt)
        self.assertEqual(completion.result.correct_count, 10)
        self.assertTrue(completion.result.passed)

    def test_import_rejects_duplicate_ids_and_invalid_answer_without_overwriting(self) -> None:
        self.content.initialize()
        pack = json.loads(
            (_DATA_ROOT / "mathematics" / "arytmetyka" / "content.json").read_text(
                encoding="utf-8"
            )
        )
        self.content.validate_pack(pack)

        task = self.content.list_tasks()[0]
        with self.database.transaction() as connection:
            before = connection.execute(
                "SELECT answer FROM bank_tasks WHERE task_id = ?", (task.id,)
            ).fetchone()["answer"]
        source_pack = next(
            item for item in self.content.load_packs()
            if any(row["id"] == task.id for row in item["tasks"])
        )
        with self.assertRaises(ContentError):
            self.content.import_pack(source_pack)
        with self.database.transaction() as connection:
            after = connection.execute(
                "SELECT answer FROM bank_tasks WHERE task_id = ?", (task.id,)
            ).fetchone()["answer"]
        self.assertEqual(before, after)

    def test_validator_rejects_wrong_answers_and_duplicate_task_ids(self) -> None:
        pack = next(
            item for item in self.content.load_packs()
            if item["division"] == "Algebra"
        )
        wrong_answer = copy.deepcopy(pack)
        wrong_answer["tasks"][0]["answer"] = "999999"
        with self.assertRaises(ContentError):
            self.content.validate_pack(wrong_answer)
        duplicate = copy.deepcopy(pack)
        duplicate["tasks"][1]["id"] = duplicate["tasks"][0]["id"]
        with self.assertRaises(ContentError):
            self.content.validate_pack(duplicate)

    def test_topics_return_substantive_theory_and_existing_topic_ids(self) -> None:
        self.content.initialize()
        topic = next(
            item for pack in self.content.load_packs()
            for item in pack["topics"]
            if item["name"] == "Pola podstawowych figur płaskich"
        )
        material = self.content.get_topic_material(topic["id"])
        self.assertGreater(len(material["theory"]), 100)
        self.assertTrue(material["formulas"])
        self.assertTrue(material["worked_examples"])
        self.assertEqual(material["id"], topic["id"])

