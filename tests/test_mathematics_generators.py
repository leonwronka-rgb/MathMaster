from __future__ import annotations

import random
import re
import unittest

from mathematics.generators import ExerciseGenerator
from mathematics.topics import (
    CURRICULUM_VERSION,
    DIFFICULTY_LEVELS,
    DIFFICULTY_NAMES,
    TOPICS,
    TOPIC_DATA,
    TOPIC_REQUIREMENTS,
    Topic,
)
from mathematics.validators import is_correct_answer


class ExerciseGeneratorTests(unittest.TestCase):
    def test_difficulty_levels_have_distinct_education_stage_names(self) -> None:
        self.assertEqual(set(DIFFICULTY_NAMES), set(DIFFICULTY_LEVELS))
        self.assertEqual(len(set(DIFFICULTY_NAMES.values())), 5)
        self.assertIn("Szkoła podstawowa", DIFFICULTY_NAMES[1])
        self.assertIn("CKU", DIFFICULTY_NAMES[3])
        self.assertIn("akademicki", DIFFICULTY_NAMES[5])

    def test_curriculum_metadata_has_requirement_arrays_for_every_topic(self) -> None:
        self.assertRegex(CURRICULUM_VERSION, r"^\d{4}/\d{4}$")
        self.assertEqual(set(TOPIC_REQUIREMENTS), set(TOPICS))
        self.assertEqual(len(TOPIC_DATA), len(TOPICS))
        for item in TOPIC_DATA:
            with self.subTest(topic=item["id"]):
                self.assertIsInstance(item["requirements"], list)
                self.assertTrue(item["requirements"])
        self.assertTrue(
            any("trapezu" in item.lower() for item in TOPIC_REQUIREMENTS[Topic.AREA])
        )

    def test_every_topic_generator_produces_a_verifiable_task_at_each_level(self) -> None:
        generator = ExerciseGenerator(random.Random(73021))
        for topic in TOPICS:
            for difficulty in DIFFICULTY_LEVELS:
                with self.subTest(topic=topic, difficulty=difficulty):
                    exercise = generator.generate(topic, difficulty)
                    self.assertEqual(exercise.topic, topic)
                    self.assertEqual(exercise.difficulty, difficulty)
                    self.assertTrue(exercise.prompt.strip())
                    self.assertTrue(exercise.solution.strip())
                    self.assertTrue(
                        is_correct_answer(exercise, exercise.answer_text),
                        exercise.answer_text,
                    )

    def test_division_generator_never_uses_zero_divisor(self) -> None:
        generator = ExerciseGenerator(random.Random(100))
        for level in DIFFICULTY_LEVELS:
            for _ in range(50):
                exercise = generator.generate(Topic.DIVISION, level)
                numbers = [int(value) for value in re.findall(r"-?\d+", exercise.prompt)]
                if exercise.prompt.startswith("Ile razy"):
                    divisor, dividend = numbers
                else:
                    dividend, divisor = numbers
                self.assertNotEqual(divisor, 0)
                self.assertEqual(dividend // divisor, int(exercise.answer))

    def test_same_seed_produces_repeatable_tasks(self) -> None:
        first = ExerciseGenerator(random.Random(42)).generate(Topic.LINEAR_SYSTEM, 3)
        second = ExerciseGenerator(random.Random(42)).generate(Topic.LINEAR_SYSTEM, 3)

        self.assertEqual(first, second)

    def test_each_topic_generates_varied_prompts(self) -> None:
        for topic in TOPICS:
            generator = ExerciseGenerator(random.Random(8102))
            prompts = {generator.generate(topic, 3).prompt for _ in range(20)}
            with self.subTest(topic=topic):
                self.assertGreater(len(prompts), 1)

    def test_area_generator_includes_required_quadrilaterals(self) -> None:
        generator = ExerciseGenerator(random.Random(20261111))
        prompts = [generator.generate(Topic.AREA, 3).prompt for _ in range(150)]
        for shape in ("równoległoboku", "rombu", "trapezu"):
            with self.subTest(shape=shape):
                self.assertTrue(any(shape in prompt for prompt in prompts))

    def test_unknown_topic_and_invalid_difficulty_are_rejected(self) -> None:
        generator = ExerciseGenerator(random.Random(1))
        with self.assertRaises(ValueError):
            generator.generate("not-a-topic", 1)
        with self.assertRaises(ValueError):
            generator.generate(Topic.ADDITION, 6)


if __name__ == "__main__":
    unittest.main()
