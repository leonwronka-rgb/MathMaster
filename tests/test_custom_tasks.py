from __future__ import annotations

import json
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from accounts.auth import AuthService
from database.database import Database
from exercises.custom_tasks import (
    CustomTaskError,
    CustomTaskService,
    TaskDownloadError,
)
from mathematics.engine import MathEngine
from mathematics.topics import Topic


def _bundle() -> str:
    return json.dumps(
        {
            "format_version": 1,
            "name": "Ułamki — poziom podstawowy",
            "category": "fractions",
            "tasks": [
                {
                    "id": "fraction_001",
                    "name": "Dodawanie ułamków",
                    "question": "Oblicz 1/2 + 1/4",
                    "answer": "3/4",
                    "difficulty": "easy",
                    "explanation": "Sprowadzamy do wspólnego mianownika.",
                    "hint": "Znajdź wspólny mianownik.",
                    "choices": ["1/4", "3/4", "1"],
                    "xp_points": 12,
                },
                {
                    "id": "fraction_invalid",
                    "question": "Które działanie?",
                    "answer": "1",
                    "difficulty": "impossible",
                    "explanation": "Błędny poziom.",
                },
                {
                    "id": "fraction_duplicate",
                    "question": "Oblicz 1/2 + 1/4",
                    "answer": "3/4",
                    "difficulty": "easy",
                    "explanation": "Inny tekst, ten sam problem.",
                },
            ],
        },
        ensure_ascii=False,
    )


class CustomTaskServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "custom-tasks.sqlite3")
        self.database.initialize()
        auth = AuthService(self.database)
        self.user = auth.register("task-author", "Task Author", "secure-pass-123")
        self.other_user = auth.register("task-reader", "Task Reader", "secure-pass-456")
        self.service = CustomTaskService(
            self.database, MathEngine(random.Random(404)), rng=random.Random(404)
        )
        self.addCleanup(self.temp_dir.cleanup)
        self.addCleanup(self.database.close)

    def test_create_edit_delete_and_account_isolation(self) -> None:
        task = self.service.create_task(
            self.user.id,
            name="Dodawanie",
            question="Oblicz 1/2 + 1/4",
            answer="3/4",
            explanation="Wspólny mianownik to 4.",
            category="Ułamki",
            topic=Topic.FRACTION_ADDITION,
            difficulty=2,
            xp_points=8,
            hints=("Znajdź wspólny mianownik.",),
            choices=("1/2", "3/4"),
        )
        self.assertEqual(self.service.list_tasks(self.user.id), (task,))
        self.assertEqual(self.service.list_tasks(self.other_user.id), ())
        with self.assertRaises(CustomTaskError):
            self.service.get_task(self.other_user.id, task.id)

        updated = self.service.update_task(
            self.user.id,
            task.id,
            id=task.external_id,
            name="Dodawanie ułamków",
            question=task.question,
            answer=task.answer,
            explanation="Zapisz oba ułamki ze wspólnym mianownikiem.",
            category="Ułamki",
            topic=Topic.FRACTION_ADDITION,
            difficulty=2,
            xp_points=8,
            hints=task.hints,
            choices=task.choices,
            set_id=task.set_id,
        )
        self.assertEqual(updated.name, "Dodawanie ułamków")
        self.service.delete_task(self.user.id, task.id)
        self.assertEqual(self.service.list_tasks(self.user.id), ())

    def test_import_preview_reports_valid_invalid_and_duplicate_records(self) -> None:
        preview = self.service.preview_import(
            _bundle(), self.user.id, source_kind="file", source="fractions.json"
        )

        self.assertEqual(preview.name, "Ułamki — poziom podstawowy")
        self.assertEqual(preview.category, "Ułamki")
        self.assertEqual(preview.valid_count, 1)
        self.assertEqual(preview.invalid_count, 1)
        self.assertEqual(preview.duplicate_count, 1)
        self.assertFalse(preview.records[0].errors)
        self.assertTrue(preview.records[1].errors)
        self.assertTrue(preview.records[2].duplicate)

        result = self.service.import_preview(self.user.id, preview)

        self.assertEqual((result.imported, result.invalid, result.duplicates), (1, 1, 1))
        imported = self.service.list_tasks(self.user.id)
        self.assertEqual(len(imported), 1)
        self.assertEqual(imported[0].source_label, "Import JSON · fractions.json")
        self.assertEqual(imported[0].hints, ("Znajdź wspólny mianownik.",))
        self.assertEqual(imported[0].choices, ("1/4", "3/4", "1"))

    def test_duplicate_set_and_task_are_never_overwritten(self) -> None:
        first = self.service.preview_import(_bundle(), self.user.id, source="set.json")
        self.service.import_preview(self.user.id, first)
        second = self.service.preview_import(_bundle(), self.user.id, source="set.json")

        self.assertTrue(second.duplicate_set)
        self.assertEqual(second.duplicate_count, 2)
        result = self.service.import_preview(self.user.id, second)
        self.assertEqual(result.imported, 0)
        self.assertEqual(len(self.service.list_tasks(self.user.id)), 1)

    def test_json_export_round_trip_preserves_polish_text_and_category_filter(self) -> None:
        first = self.service.preview_import(_bundle(), self.user.id, source="zestaw.json")
        self.service.import_preview(self.user.id, first)
        exported = self.service.export_json(self.user.id, category="Ułamki")
        payload = json.loads(exported)

        self.assertIn("Ułamki", exported)
        self.assertEqual(payload["format_version"], 1)
        self.assertEqual(payload["tasks"][0]["question"], "Oblicz 1/2 + 1/4")
        self.assertEqual(payload["tasks"][0]["category"], "Ułamki")

    def test_remote_import_keeps_source_name_and_download_time(self) -> None:
        preview = self.service.preview_import(
            _bundle(),
            self.user.id,
            source_kind="url",
            source="raw.githubusercontent.com",
            source_url="https://raw.githubusercontent.com/example/tasks.json",
            downloaded_at="2026-11-12T14:00:00+00:00",
        )
        self.service.import_preview(self.user.id, preview)

        task_set = self.service.list_sets(self.user.id)[0]
        task = self.service.list_tasks(self.user.id)[0]
        self.assertEqual(task_set.source, "raw.githubusercontent.com")
        self.assertEqual(
            task_set.source_url,
            "https://raw.githubusercontent.com/example/tasks.json",
        )
        self.assertEqual(task_set.downloaded_at, "2026-11-12T14:00:00+00:00")
        self.assertEqual(
            task.source_label, "Pobrano z raw.githubusercontent.com"
        )

    def test_generated_practice_mixes_custom_and_builtin_exercises(self) -> None:
        preview = self.service.preview_import(_bundle(), self.user.id)
        self.service.import_preview(self.user.id, preview)

        generated = self.service.generate_exercises(
            self.user.id,
            category="Ułamki",
            topic=Topic.FRACTION_ADDITION,
            difficulty=1,
            count=2,
        )

        self.assertEqual(len(generated), 2)
        self.assertEqual(sum(item.task_id is not None for item in generated), 1)
        self.assertIn(
            "Generator MathMaster",
            {item.source_label for item in generated},
        )
        self.assertTrue(all(item.question for item in generated))

    def test_answer_checking_saves_history_and_awards_custom_xp_only_once(self) -> None:
        preview = self.service.preview_import(_bundle(), self.user.id)
        self.service.import_preview(self.user.id, preview)
        task = self.service.list_tasks(self.user.id)[0]
        exercise = self.service.generate_exercises(
            self.user.id,
            category=task.category,
            topic=task.topic,
            difficulty=task.difficulty,
            count=1,
            custom_ratio=1,
        )[0]
        first = self.service.answer_exercise(
            self.user.id, exercise, "0.75", source_key="attempt-1"
        )
        second = self.service.answer_exercise(
            self.user.id, exercise, "3/4", source_key="attempt-2"
        )

        self.assertTrue(first.correct)
        self.assertGreaterEqual(first.xp_awarded, 12)
        self.assertEqual(second.xp_awarded, 0)
        with self.database.transaction() as connection:
            custom_xp = connection.execute(
                "SELECT amount FROM xp_transactions "
                "WHERE user_id = ? AND source_key LIKE 'custom-exercise:task:%'",
                (self.user.id,),
            ).fetchone()["amount"]
            attempts = connection.execute(
                "SELECT COUNT(*) FROM custom_task_attempts WHERE user_id = ?",
                (self.user.id,),
            ).fetchone()[0]
            history = connection.execute(
                "SELECT COUNT(*) FROM exercise_history WHERE user_id = ?",
                (self.user.id,),
            ).fetchone()[0]
        self.assertEqual(attempts, 2)
        self.assertEqual(history, 2)
        self.assertEqual(custom_xp, 12)

    def test_import_validation_and_selected_record_skipping(self) -> None:
        with self.assertRaises(CustomTaskError):
            self.service.preview_import('{"format_version":1,"format_version":1}', self.user.id)
        preview = self.service.preview_import(_bundle(), self.user.id)
        result = self.service.import_preview(
            self.user.id, preview, selected_indices={0}
        )
        self.assertEqual(result.imported, 1)
        self.assertEqual(len(self.service.list_tasks(self.user.id)), 1)

    def test_download_rejects_non_https_and_private_addresses(self) -> None:
        with self.assertRaises(TaskDownloadError):
            self.service.fetch_json("http://example.org/tasks.json")
        with self.assertRaises(TaskDownloadError):
            self.service.fetch_json("https://127.0.0.1/tasks.json")
        with patch(
            "exercises.custom_tasks.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("10.0.0.5", 443))],
        ):
            with self.assertRaises(TaskDownloadError):
                self.service.fetch_json("https://example.org/tasks.json")

    def test_import_requires_id_and_github_blob_link_is_normalized_to_raw_file(self) -> None:
        payload = json.loads(_bundle())
        payload["tasks"] = [dict(payload["tasks"][0])]
        del payload["tasks"][0]["id"]
        preview = self.service.preview_import(
            json.dumps(payload, ensure_ascii=False), self.user.id
        )
        self.assertEqual(preview.valid_count, 0)
        self.assertIn("Identyfikator", preview.records[0].errors[0])

        self.assertEqual(
            self.service._repository_raw_url(
                "https://github.com/owner/repo/blob/main/tasks.json"
            ),
            "https://raw.githubusercontent.com/owner/repo/main/tasks.json",
        )


if __name__ == "__main__":
    unittest.main()
