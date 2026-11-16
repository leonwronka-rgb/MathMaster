from __future__ import annotations

import unittest

import sympy as sp

from assistant.assistant_service import (
    AssistantInputError,
    MathAssistantService,
    UnsupportedProblemError,
)


class MathAssistantServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assistant = MathAssistantService()

    def test_linear_equation_example_is_explained_and_verified(self) -> None:
        explanation = self.assistant.explain("2x + 6 = 14")

        self.assertEqual(explanation.task_type, "Równanie liniowe")
        self.assertEqual(explanation.answer, sp.Integer(4))
        self.assertTrue(explanation.verified)
        self.assertEqual(len(explanation.steps), 4)
        self.assertIn("Odejmij 6 od obu stron", explanation.steps[1].title)
        self.assertEqual(explanation.steps[1].equation, "2*x = 8")
        self.assertEqual(explanation.steps[2].equation, "x = 4")
        self.assertIn("lewa strona = 14, prawa strona = 14", explanation.verification_text)
        self.assertEqual(len(explanation.common_mistakes), 3)

    def test_linear_equation_with_variables_on_both_sides(self) -> None:
        explanation = self.assistant.explain("3x + 4 = x + 10")

        self.assertEqual(explanation.answer, sp.Integer(3))
        self.assertTrue(explanation.verified)
        self.assertTrue(any("Odejmij x" in step.title for step in explanation.steps))
        self.assertEqual(explanation.steps[-1].equation, "13 = 13  ✓")

    def test_implicit_multiplication_and_negative_coefficients_are_supported(self) -> None:
        parenthesized = self.assistant.explain("2(x + 3) = 10")
        negative = self.assistant.explain("5 - 2x = 1")

        self.assertEqual(parenthesized.answer, sp.Integer(2))
        self.assertEqual(negative.answer, sp.Integer(2))
        self.assertTrue(parenthesized.verified)
        self.assertTrue(negative.verified)

    def test_unsupported_equations_are_reported_without_invented_steps(self) -> None:
        with self.assertRaisesRegex(UnsupportedProblemError, "stopnia 2"):
            self.assistant.explain("x^2 = 4")
        with self.assertRaises(UnsupportedProblemError):
            self.assistant.explain("sin(x) = 1")
        with self.assertRaises(UnsupportedProblemError):
            self.assistant.explain("x + 1 = x + 2")

    def test_invalid_or_unsafe_input_is_rejected(self) -> None:
        for problem in ("", "2x + 6", "__import__('os') = 1", "x = x"):
            with self.subTest(problem=problem):
                with self.assertRaises(AssistantInputError):
                    self.assistant.explain(problem)


if __name__ == "__main__":
    unittest.main()
