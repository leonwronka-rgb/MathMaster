from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from accounts.auth import AuthService
from database.database import Database
from mathematics.engine import MathEngine
from mathematics.library_service import TopicLibraryError, TopicLibraryService
from mathematics.topic_library import LIBRARY_DIVISIONS, LIBRARY_TOPICS
from mathematics.topics import DIFFICULTY_LEVELS, Topic


class TopicLibraryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "library.sqlite3")
        self.database.initialize()
        self.user = AuthService(self.database).register(
            "library_user", "Library User", "secure-pass-123"
        )
        self.other_user = AuthService(self.database).register(
            "library_other", "Other User", "secure-pass-456"
        )
        self.service = TopicLibraryService(
            self.database, MathEngine(random.Random(2026))
        )
        self.addCleanup(self.temp_dir.cleanup)
        self.addCleanup(self.database.close)

    def test_catalog_is_hierarchical_and_every_topic_has_unique_id_and_content(self) -> None:
        self.assertEqual(len({topic.id for topic in LIBRARY_TOPICS}), len(LIBRARY_TOPICS))
        self.assertEqual(
            len({(topic.division, topic.title) for topic in LIBRARY_TOPICS}),
            len(LIBRARY_TOPICS),
        )
        self.assertGreaterEqual(len(LIBRARY_DIVISIONS), 15)
        for division in LIBRARY_DIVISIONS:
            self.assertTrue(division.subdivisions)
            for topic in division.topics:
                with self.subTest(topic=topic.id):
                    self.assertTrue(topic.id)
                    self.assertTrue(topic.description)
                    self.assertIn(topic.difficulty, DIFFICULTY_LEVELS)
                    self.assertTrue(topic.theory)
                    self.assertTrue(topic.examples)
                    self.assertTrue(topic.subtopics)
                    self.assertTrue(topic.exercise_topic)

    def test_search_filters_by_query_division_level_and_status(self) -> None:
        area = next(
            topic for topic in LIBRARY_TOPICS
            if topic.division == "Geometria płaska" and topic.exercise_topic == Topic.AREA
            and topic.subdivision == "Pola i obwody"
        )
        self.service.set_status(self.user.id, area.id, "started")
        result = self.service.search(
            self.user.id,
            "trapez",
            division="Geometria płaska",
            difficulty=area.difficulty,
            status="started",
        )
        self.assertIn(area, result)
        self.assertEqual(
            self.service.search(
                self.other_user.id, division="Geometria płaska", status="started"
            ),
            (),
        )

    def test_topic_status_is_validated_and_persisted_per_account(self) -> None:
        topic = LIBRARY_TOPICS[0]
        self.service.set_status(self.user.id, topic.id, "mastered")
        self.assertEqual(self.service.get_statuses(self.user.id)[topic.id], "mastered")
        self.assertNotIn(topic.id, self.service.get_statuses(self.other_user.id))
        with self.assertRaises(TopicLibraryError):
            self.service.set_status(self.user.id, topic.id, "unknown")

    def test_custom_topic_can_be_added_searched_and_practiced_without_code_changes(self) -> None:
        topic_id = self.service.add_topic(
            self.user.id,
            division="Mój dział",
            subdivision="Nowe zagadnienia",
            title="Testowy temat",
            description="Treść dodana z poziomu użytkownika.",
            difficulty=3,
            theory=("Pierwsza zasada.",),
            examples=("Przykład bez narzuconego wyniku.",),
            subtopics=("Podtemat A",),
            exercise_topic=Topic.ADDITION,
        )
        topic = self.service.get_topic(self.user.id, topic_id)
        self.assertTrue(topic.custom)
        self.assertEqual(topic.theory, ("Pierwsza zasada.",))
        self.assertEqual(
            self.service.search(self.user.id, "podtemat a"),
            (topic,),
        )
        exercise = self.service.generate_exercises(self.user.id, topic_id, count=1)[0]
        self.assertEqual(exercise.topic, Topic.ADDITION)
        self.assertTrue(exercise.prompt)
        with self.assertRaises(TopicLibraryError):
            self.service.get_topic(self.other_user.id, topic_id)

    def test_custom_topic_rejects_invalid_generator_and_empty_content(self) -> None:
        arguments = {
            "division": "Dział",
            "subdivision": "Poddział",
            "title": "Temat",
            "description": "Opis",
            "difficulty": 2,
            "theory": ("Teoria",),
            "examples": ("Przykład",),
            "subtopics": ("Podtemat",),
        }
        with self.assertRaises(TopicLibraryError):
            self.service.add_topic(
                self.user.id, **arguments, exercise_topic="unknown"
            )
        with self.assertRaises(TopicLibraryError):
            self.service.add_topic(
                self.user.id,
                **{**arguments, "title": ""},
                exercise_topic=Topic.ADDITION,
            )


if __name__ == "__main__":
    unittest.main()
